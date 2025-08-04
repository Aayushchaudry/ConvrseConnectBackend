# src/orchestrators/project_lifecycle_orchestrator/project_lifecycle_orchestrator.py (UPDATED)

import logging
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Type
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from src.commands.project_commands import (
    StartDeliverableSagaCommand,
    StartInformationGatheringCommand,
)
from src.config.database import AsyncSessionLocal  # Can be used as db_session_factory
from src.events.event_bus_interface import EventBus
from src.events.project_events import (
    DeliverableDeliveredEvent,
    DeliverableFailedEvent,
    ProjectCompletedEvent,
    ProjectCreatedEvent,
    ProjectFailedEvent,
)
from src.events.task_events import (
    InternalTaskCompletedEvent,
    InternalTaskCompletedWithMediaEvent,
    InternalTaskStatusUpdatedEvent,
)
from src.events.deliverable_events import RequirementUpdatedEvent
from src.models.project import Project, ProjectStatus  # Already imported
from src.models.saga_state import SagaState, SagaStatus, SagaType
from src.orchestrators.project_lifecycle_orchestrator.states import ProjectSagaState
from src.orchestrators.saga_processor import (
    SagaProcessor,
)  # <--- NEW IMPORT: Import the SagaProcessor

logger = logging.getLogger(__name__)


class ProjectLifecycleOrchestrator:
    """
    Orchestrates the high-level lifecycle of a Project SAGA.
    Reacts to project-level events and sends commands to services/nested Sagas.
    """

    def __init__(
        self, db_session_factory: Callable[[], AsyncSession], event_bus: EventBus
    ):
        logger.info("🚨 [ORCHESTRATOR] ProjectLifecycleOrchestrator __init__ called - orchestrator is being instantiated.")
        """
        Initializes the ProjectLifecycleOrchestrator.
        Args:
            db_session_factory: A factory function to get a new AsyncSession.
            event_bus: The EventBus instance for publishing commands/events.
        """
        self.db_session_factory = db_session_factory
        self.event_bus = event_bus
        self.saga_processor = SagaProcessor(
            event_bus=event_bus
        )  # Initialize SagaProcessor

        self.event_handlers: Dict[str, Callable[[Any], Any]] = (
            {  # Type hint for handler arg changed to Any
                "ProjectCreatedEvent": self.on_project_created,
                "DeliverableDeliveredEvent": self.on_deliverable_delivered,
                "DeliverableFailedEvent": self.on_deliverable_failed,
                # Project Status Progression Events
                "InternalTaskCompletedEvent": self.on_work_progress_made,
                "InternalTaskCompletedWithMediaEvent": self.on_work_progress_made,
                "InternalTaskStatusUpdatedEvent": self.on_task_status_updated,
                "RequirementUpdatedEvent": self.on_requirement_updated,
                # Add handlers for other events as you define them
            }
        )

    def _get_project_id(self, event):
        """
        Safely extract project_id from either an event object or dict.
        """
        if hasattr(event, 'project_id'):
            return event.project_id
        elif isinstance(event, dict) and 'project_id' in event:
            return event['project_id']
        else:
            logger.warning(f"Could not extract project_id from event: {event}")
            return None

    async def on_project_created(self, event: ProjectCreatedEvent):
        """
        Handles the ProjectCreatedEvent to initiate the Project Lifecycle SAGA.
        This is the entry point for the Project SAGA orchestration.
        Backend orchestration: Auto-creates deliverables from deliverable_types and creates timeline milestones.
        """
        logger.info(f"🚦 Orchestrator: Received ProjectCreatedEvent: {event}")
        logger.info(
            f"🔄 ProjectLifecycleOrchestrator: Received ProjectCreatedEvent for Project ID: {event.project_id}"
        )
        logger.info(
            f"🔄 ProjectLifecycleOrchestrator: Auto-creating {len(event.deliverable_types)} deliverable types: {event.deliverable_types}"
        )

        async with self.db_session_factory() as session:
            # Use SagaProcessor to get or create the SAGA state
            saga_state = await self.saga_processor.get_or_create_saga_state(
                session=session,
                project_id=event.project_id,
                saga_type=SagaType.PROJECT_LIFECYCLE,
                initial_state=ProjectSagaState.PROJECT_CREATED.value,
                saga_id=event.project_id,  # Using project_id as saga_id for main project SAGA
            )

            # Idempotency check handled by saga_processor.update_saga_state,
            # but a quick check here if already processed, to avoid unnecessary work.
            if (
                saga_state.last_event_processed_id == str(event.event_id)
                and saga_state.current_state
                == ProjectSagaState.INFO_GATHERING_INITIATED.value
            ):  # Check target state too
                logger.warning(
                    f"ProjectLifecycleOrchestrator: ProjectCreatedEvent {event.event_id} already processed to {ProjectSagaState.INFO_GATHERING_INITIATED.value} for Project {event.project_id}. Idempotent."
                )
                return

            # 1. AUTO-CREATE DELIVERABLES from deliverable_types (Backend Orchestration)
            created_deliverable_ids = []
            deliverable_type_to_days = {}
            deliverable_type_to_subtype = {}
            if event.deliverable_types:
                logger.info(f"🔄 ProjectLifecycleOrchestrator: Creating deliverables for project {event.project_id}")
                from src.services.deliverable_service import DeliverableService
                from src.models.deliverable import DeliverableType
                from src.models.project import Project
                from src.config.event_bus import get_event_bus
                from sqlalchemy import select
                project_result = await session.execute(
                    select(Project).filter(Project.id == event.project_id)
                )
                project = project_result.scalar_one_or_none()
                if not project:
                    logger.error(f"❌ ProjectLifecycleOrchestrator: Project {event.project_id} not found")
                    return
                project_created_by = project.created_by
                event_bus_instance = await get_event_bus()
                deliverable_service = DeliverableService(db_session=session, event_bus=event_bus_instance)
                for deliverable_type_str in event.deliverable_types:
                    try:
                        deliverable_type_enum = DeliverableType(deliverable_type_str)
                        custom_timeline_days = event.deliverable_timeline_days.get(deliverable_type_str)
                        if custom_timeline_days:
                            timeline_days = custom_timeline_days
                        else:
                            # Set reasonable defaults for timeline based on deliverable type
                            if deliverable_type_enum == DeliverableType.RENDERED_IMAGES:
                                timeline_days = 14
                            elif deliverable_type_enum == DeliverableType.TECHNICAL_RENDERS:
                                timeline_days = 10
                            elif deliverable_type_enum == DeliverableType.EXTERIOR_VR_TOUR:
                                timeline_days = 21
                            elif deliverable_type_enum == DeliverableType.ANIMATED_VR_TOUR:
                                timeline_days = 28
                            elif deliverable_type_enum == DeliverableType.VIDEO_WALKTHROUGH:
                                timeline_days = 21
                            elif deliverable_type_enum == DeliverableType.INVENTORY_MODULE:
                                timeline_days = 14
                            elif deliverable_type_enum == DeliverableType.LOCATION_MAP:
                                timeline_days = 7
                            elif deliverable_type_enum == DeliverableType.INTERACTIVE_SALES_APP:
                                timeline_days = 35
                            elif deliverable_type_enum == DeliverableType.INTERACTIVE_DRONE_SHOOT:
                                timeline_days = 21
                            elif deliverable_type_enum == DeliverableType.INTERPLAYER_SOFTWARE:
                                timeline_days = 28
                            else:
                                timeline_days = 30  # Default fallback
                        custom_sub_type = event.deliverable_sub_types.get(deliverable_type_str)
                        if custom_sub_type:
                            deliverable_sub_type = custom_sub_type.title()
                        else:
                            if deliverable_type_enum == DeliverableType.RENDERED_IMAGES:
                                deliverable_sub_type = "Interior & Exterior Views"
                            elif deliverable_type_enum == DeliverableType.TECHNICAL_RENDERS:
                                deliverable_sub_type = "Technical Visualization"
                            elif deliverable_type_enum == DeliverableType.EXTERIOR_VR_TOUR:
                                deliverable_sub_type = "Exterior Virtual Tour"
                            elif deliverable_type_enum == DeliverableType.ANIMATED_VR_TOUR:
                                deliverable_sub_type = "Animated Virtual Tour"
                            elif deliverable_type_enum == DeliverableType.VIDEO_WALKTHROUGH:
                                deliverable_sub_type = "Video Walkthrough"
                            elif deliverable_type_enum == DeliverableType.INVENTORY_MODULE:
                                deliverable_sub_type = "Inventory Management"
                            elif deliverable_type_enum == DeliverableType.LOCATION_MAP:
                                deliverable_sub_type = "Location Mapping"
                            elif deliverable_type_enum == DeliverableType.INTERACTIVE_SALES_APP:
                                deliverable_sub_type = "Interactive Sales Application"
                            elif deliverable_type_enum == DeliverableType.INTERACTIVE_DRONE_SHOOT:
                                deliverable_sub_type = "Drone Photography & Integration"
                            elif deliverable_type_enum == DeliverableType.INTERPLAYER_SOFTWARE:
                                deliverable_sub_type = "Interplayer AV Room Setup"
                            else:
                                deliverable_sub_type = "Standard"
                        created_deliverable = await deliverable_service.create_deliverable(
                            project_id=event.project_id,
                            deliverable_type=deliverable_type_enum,
                            deliverable_sub_type=deliverable_sub_type,
                            tentative_timeline_days=timeline_days,
                            created_by=project_created_by,
                            assigned_to=None,
                        )
                        created_deliverable_ids.append(created_deliverable.id)
                        deliverable_type_to_days[deliverable_type_str] = timeline_days
                        deliverable_type_to_subtype[deliverable_type_str] = deliverable_sub_type
                        logger.info(f"✅ ProjectLifecycleOrchestrator: Created deliverable {created_deliverable.id} of type {deliverable_type_str}")
                    except ValueError as e:
                        logger.error(f"❌ ProjectLifecycleOrchestrator: Invalid deliverable type '{deliverable_type_str}': {e}")
                        continue
                    except Exception as e:
                        logger.error(f"❌ ProjectLifecycleOrchestrator: Failed to create deliverable '{deliverable_type_str}': {e}")
                        continue
                logger.info(f"✅ ProjectLifecycleOrchestrator: Created {len(created_deliverable_ids)} deliverables for project {event.project_id}")
            else:
                logger.info(f"⚠️ ProjectLifecycleOrchestrator: No deliverable types specified for project {event.project_id}")

            # 2. CREATE TIMELINE MILESTONES DIRECTLY HERE (PER GROUP, NOT PER DELIVERABLE)
            from src.models.project_timeline import ProjectTimeline
            from datetime import timedelta
            from collections import defaultdict

            # Group deliverables by subtype
            subtype_to_days = defaultdict(list)
            for deliverable_type, timeline_days in deliverable_type_to_days.items():
                sub_type = deliverable_type_to_subtype.get(deliverable_type, "Other")
                subtype_to_days[sub_type].append(timeline_days)

            timeline_entries = []
            logger.info(f"🟢 Timeline creation: {len(subtype_to_days)} groups found: {list(subtype_to_days.keys())}")
            for subtype, days_list in subtype_to_days.items():
                max_days = max(days_list)
                current_date = datetime.now().date()
                if "exterior" in subtype.lower():
                    logger.info(f"🟢 Using EXTERIOR timeline template for group '{subtype}'")
                    milestones = [
                        {"phase_name": "Kick-off Meeting", "fixed_days": 1, "phase_order": 1},
                        {"phase_name": "Modeling", "fixed_days": 7, "phase_order": 2},
                        {"phase_name": "Texturing and landscaping", "fixed_days": 8, "phase_order": 3},
                        {"phase_name": "Lighting", "fixed_days": 3, "phase_order": 4},
                        {"phase_name": "Final Deliverable", "fixed_days": max_days, "phase_order": 5},
                    ]
                    timeline_type = "exterior"
                elif "interior" in subtype.lower():
                    logger.info(f"🟢 Using INTERIOR timeline template for group '{subtype}'")
                    milestones = [
                        {"phase_name": "Kick-off Meeting", "fixed_days": 1, "phase_order": 1},
                        {"phase_name": "Theme Approval", "fixed_days": 3, "phase_order": 2},
                        {"phase_name": "Modeling and Texturing and landscaping", "fixed_days": 8, "phase_order": 3},
                        {"phase_name": "Final Deliverable", "fixed_days": max_days, "phase_order": 4},
                    ]
                    timeline_type = "interior"
                else:
                    logger.warning(f"⚠️ Skipping group '{subtype}' (no custom timeline template defined)")
                    continue

                for milestone in milestones:
                    end_date = current_date + timedelta(days=milestone["fixed_days"])
                    timeline_entry = ProjectTimeline(
                        project_id=event.project_id,
                        phase_name=milestone["phase_name"],
                        phase_order=milestone["phase_order"],
                        planned_start_date=current_date,
                        planned_end_date=end_date,
                        is_milestone=False,
                        percentage_complete=0,
                        dependencies={},
                        timeline_type=timeline_type,
                    )
                    session.add(timeline_entry)
                    timeline_entries.append(timeline_entry)
                    current_date = end_date
            await session.commit()
            logger.info(f"🟢 Timeline creation: Created {len(timeline_entries)} timeline milestones for project {event.project_id}")

            # 3. Transition SAGA State and Send Next Command
            next_state = ProjectSagaState.INFO_GATHERING_INITIATED
            command = StartInformationGatheringCommand(
                project_id=event.project_id,
                deliverable_ids=created_deliverable_ids,
            )
            await self.saga_processor.publish_message(
                topic="project.command.start_info_gathering",
                message_payload=command,
            )
            await self.saga_processor.update_saga_state(
                session=session,
                saga_state=saga_state,
                new_state_enum=next_state,
                event_id=event.event_id,
                command_id=command.command_id,
            )
            logger.info(
                f"✅ ProjectLifecycleOrchestrator: Project SAGA for {event.project_id} transitioned to {next_state.value} and sent StartInformationGatheringCommand with {len(created_deliverable_ids)} deliverables."
            )

    async def on_deliverable_delivered(self, event: DeliverableDeliveredEvent):
        """
        Handles DeliverableDeliveredEvent, indicating a deliverable SAGA has completed.
        """
        logger.info(
            f"ProjectLifecycleOrchestrator: Received DeliverableDeliveredEvent for Project {event.project_id}, Deliverable {event.deliverable_id}"
        )

        async with self.db_session_factory() as session:
            saga_state = await self.saga_processor.get_or_create_saga_state(  # Use get_or_create for robustness
                session=session,
                project_id=event.project_id,
                saga_type=SagaType.PROJECT_LIFECYCLE,
                initial_state=ProjectSagaState.COORDINATING_DELIVERABLES.value,  # Initial state if this event creates the saga
                saga_id=event.project_id,  # Using project_id as saga_id for main project SAGA
            )

            if saga_state.last_event_processed_id == str(event.event_id):
                logger.warning(
                    f"ProjectLifecycleOrchestrator: DeliverableDeliveredEvent {event.event_id} already processed for Project {event.project_id}. Idempotent."
                )
                return

            # In a real scenario, you'd check how many deliverables are complete for this project
            # and transition the Project SAGA state based on that.
            # This example assumes a simple transition for now.
            next_state = ProjectSagaState.COORDINATING_DELIVERABLES

            # Here, you'd typically query the DB to see if ALL deliverables are done
            # from src.models.deliverable import Deliverable
            # total_deliverables_count = await session.execute(select(func.count(Deliverable.id)).filter_by(project_id=event.project_id))
            # completed_deliverables_count = await session.execute(
            #     select(func.count(Deliverable.id)).filter(
            #         Deliverable.project_id == event.project_id,
            #         Deliverable.status == DELIVERABLE_STATUS.DELIVERED # Needs DeliverableStatus Enum
            #     )
            # )
            # if completed_deliverables_count.scalar_one() == total_deliverables_count.scalar_one():
            #    next_state = ProjectSagaState.ALL_DELIVERABLES_DELIVERED
            #    # Send ProjectCompletedEvent here:
            #    # command = ProjectCompletedEvent(...)
            #    # await self.saga_processor.publish_message(topic="project.completed", message_payload=command)

            await self.saga_processor.update_saga_state(
                session=session,
                saga_state=saga_state,
                new_state_enum=next_state,
                event_id=event.event_id,
            )
            logger.info(
                f"Project SAGA for {event.project_id} transitioned to {next_state.value} upon Deliverable Delivered."
            )

    async def on_deliverable_failed(self, event: DeliverableFailedEvent):
        """
        Handles DeliverableFailedEvent, indicating a deliverable SAGA has failed.
        """
        logger.warning(
            f"ProjectLifecycleOrchestrator: Received DeliverableFailedEvent for Project {event.project_id}, Deliverable {event.deliverable_id}. Reason: {event.reason}"
        )

        async with self.db_session_factory() as session:
            saga_state = await self.saga_processor.get_or_create_saga_state(  # Use get_or_create
                session=session,
                project_id=event.project_id,
                saga_type=SagaType.PROJECT_LIFECYCLE,
                initial_state=ProjectSagaState.PROJECT_FAILED.value,  # Initial state if this event creates the saga
                saga_id=event.project_id,  # Using project_id as saga_id for main project SAGA
            )

            if saga_state.last_event_processed_id == str(event.event_id):
                logger.warning(
                    f"ProjectLifecycleOrchestrator: DeliverableFailedEvent {event.event_id} already processed for Project {event.project_id}. Idempotent."
                )
                return

            # Example compensation: Mark overall SAGA as failed
            await self.saga_processor.update_saga_state(
                session=session,
                saga_state=saga_state,
                new_state_enum=ProjectSagaState.PROJECT_FAILED,
                event_id=event.event_id,
                new_saga_status=SagaStatus.FAILED,  # Pass the enum directly, not .value
            )
            logger.info(
                f"Project SAGA for {event.project_id} transitioned to {ProjectSagaState.PROJECT_FAILED.value} due to Deliverable Failure."
            )

            # Here, you would typically send a command to notify a PM:
            # from src.commands.project_commands import NotifyProjectManagerCommand
            # command = NotifyProjectManagerCommand(project_id=event.project_id, message=f"Deliverable {event.deliverable_name} failed. Reason: {event.reason}")
            # await self.saga_processor.publish_message(topic="notification.command.pm", message_payload=command)

    async def on_work_progress_made(self, event):
        """
        Handles task completion events (InternalTaskCompletedEvent or InternalTaskCompletedWithMediaEvent).
        When any task is completed, it indicates work has begun and project should move from 'initiated' to 'in_progress'.
        """
        project_id = self._get_project_id(event)
        if not project_id:
            logger.error(f"Could not extract project_id from task completion event: {event}")
            return
            
        logger.info(
            f"ProjectLifecycleOrchestrator: Received task completion event for Project {project_id}. Checking if project status should progress."
        )

        # Safely get task_id
        task_id = getattr(event, 'task_id', None) or (event.get('task_id') if isinstance(event, dict) else None)
        await self._progress_project_from_initiated_to_in_progress(project_id, f"Task {task_id} completed")

    async def on_task_status_updated(self, event):
        """
        Handles task status updates. When a task moves to 'in-progress', it indicates work has begun.
        """
        project_id = self._get_project_id(event)
        if not project_id:
            logger.error(f"Could not extract project_id from task status update event: {event}")
            return
        
        # Safely get new_status and task_id
        new_status = getattr(event, 'new_status', None) or (event.get('new_status') if isinstance(event, dict) else None)
        task_id = getattr(event, 'task_id', None) or (event.get('task_id') if isinstance(event, dict) else None)
        
        # Only trigger progression if task is now in-progress (work actually started)
        if new_status and new_status.lower() in ['in-progress', 'in_progress']:
            logger.info(
                f"ProjectLifecycleOrchestrator: Task {task_id} moved to in-progress for Project {project_id}. Checking if project status should progress."
            )
            await self._progress_project_from_initiated_to_in_progress(project_id, f"Task {task_id} started (in-progress)")

    async def on_requirement_updated(self, event):
        """
        Handles requirement status updates. When a requirement is completed/approved, it indicates progress.
        """
        project_id = self._get_project_id(event)
        if not project_id:
            logger.error(f"Could not extract project_id from requirement update event: {event}")
            return
        
        # Safely get new_status and requirement_id
        new_status = getattr(event, 'new_status', None) or (event.get('new_status') if isinstance(event, dict) else None)
        requirement_id = getattr(event, 'requirement_id', None) or (event.get('requirement_id') if isinstance(event, dict) else None)
        
        # Only trigger progression if requirement is now done/completed
        if new_status and new_status.lower() in ['received', 'approved']:
            logger.info(
                f"ProjectLifecycleOrchestrator: Requirement {requirement_id} marked as {new_status} for Project {project_id}. Checking if project status should progress."
            )
            await self._progress_project_from_initiated_to_in_progress(project_id, f"Requirement {requirement_id} completed ({new_status})")

    async def _progress_project_from_initiated_to_in_progress(self, project_id: UUID, reason: str):
        """
        Helper method to progress a project from 'initiated' to 'in_progress' if it's currently in 'initiated' status.
        Only updates if the project is currently in 'initiated' status to avoid unnecessary updates.
        """
        async with self.db_session_factory() as session:
            try:
                # Get current project status
                result = await session.execute(
                    select(Project).filter(Project.id == project_id)
                )
                project = result.scalar_one_or_none()
                
                if not project:
                    logger.warning(f"Project {project_id} not found for status progression")
                    return
                
                # Only progress if currently in 'initiated' status
                # Handle both enum and string comparisons
                current_status = project.status
                if isinstance(current_status, ProjectStatus):
                    current_status_value = current_status.value
                    is_initiated = current_status == ProjectStatus.INITIATED
                else:
                    current_status_value = current_status
                    is_initiated = current_status == ProjectStatus.INITIATED.value
                
                if is_initiated:
                    logger.info(
                        f"ProjectLifecycleOrchestrator: Progressing Project {project_id} from 'initiated' to 'in_progress'. Reason: {reason}"
                    )
                    
                    # Update project status to in_progress
                    await session.execute(
                        update(Project)
                        .where(Project.id == project_id)
                        .values(
                            status=ProjectStatus.IN_PROGRESS.value,
                            updated_at=datetime.utcnow()
                        )
                    )
                    
                    await session.commit()
                    
                    logger.info(
                        f"ProjectLifecycleOrchestrator: Successfully updated Project {project_id} status to 'in_progress'"
                    )
                    
                    # TODO: Consider publishing a ProjectStatusUpdatedEvent here for other systems to react
                    # project_status_event = ProjectStatusUpdatedEvent(
                    #     project_id=project_id,
                    #     old_status=ProjectStatus.INITIATED.value,
                    #     new_status=ProjectStatus.IN_PROGRESS.value,
                    #     reason=reason
                    # )
                    # await self.event_bus.publish(topic="project.status.updated", message=project_status_event)
                    
                else:
                    logger.debug(
                        f"ProjectLifecycleOrchestrator: Project {project_id} is already in '{current_status_value}' status. No progression needed."
                    )
                    
            except Exception as e:
                logger.error(
                    f"ProjectLifecycleOrchestrator: Error progressing project {project_id} status: {e}",
                    exc_info=True
                )
                await session.rollback()

    # You can add a generic handler for all events if you want a centralized dispatch
    async def handle_event(self, event_data: Dict[str, Any]):
        """
        Generic event handler to dispatch to specific methods.
        This will be called by your listener.
        """
        event_type = event_data.get("event_type")
        if not event_type:
            logger.error(f"Received event with no 'event_type': {event_data}")
            return

        # This part assumes event dataclasses have been correctly defined in events/
        # and their names match their event_type string.
        # It's more robust to have a central event deserializer.
        from src.events import (
            project_events,
        )  # Import the module containing your event dataclasses

        event_cls = getattr(
            project_events, event_type, None
        )  # Get class from module by name

        if not event_cls:
            logger.warning(
                f"No specific event class found for event_type: {event_type}. Processing as generic dict."
            )
            event_obj = event_data  # Process as a generic dict
        else:
            try:
                event_obj = event_cls(**event_data)  # Attempt to instantiate dataclass
            except Exception as e:
                logger.error(
                    f"Failed to deserialize event {event_type}: {e}. Data: {event_data}"
                )
                return

        handler = self.event_handlers.get(event_type)
        if handler:
            try:
                await handler(event_obj)
            except Exception as e:
                # Safely get project_id for error logging
                project_id = self._get_project_id(event_obj) or "unknown"
                
                logger.error(
                    f"Error handling event {event_type} for Project {project_id}: {e}",
                    exc_info=True,
                )
                # Here, you might publish a SagaFailedEvent or handle retry logic
        else:
            logger.warning(f"No handler registered for event type: {event_type}")
