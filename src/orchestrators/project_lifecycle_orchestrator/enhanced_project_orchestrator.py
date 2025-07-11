# Enhanced Project Lifecycle Orchestrator for Phase 4 Integration

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.events.event_bus_interface import EventBus
from src.events.project_events import ProjectCreatedEvent, DeliverableDeliveredEvent
from src.events.task_events import InternalTaskCreatedEvent
from src.events.deliverable_events import RequirementUpdatedEvent
from src.models.deliverable import Deliverable, DeliverableType, DeliverableStatus
from src.models.project_timeline import ProjectTimeline
from src.services.pricing_service import PricingService
from src.services.requirement_service import RequirementService
from src.services.timeline_tracking_service import TimelineTrackingService
from src.services.task_management_service import TaskManagementService
from src.services.deliverable_service import DeliverableService

logger = logging.getLogger(__name__)


class EnhancedProjectLifecycleOrchestrator:
    """Enhanced Project Lifecycle Orchestrator for Phase 4 Integration."""

    def __init__(self, db_session_factory: Callable[[], AsyncSession], event_bus: EventBus):
        self.db_session_factory = db_session_factory
        self.event_bus = event_bus
        
        # Don't initialize services here since they require db_session
        # Services will be created in individual methods when needed

    async def on_project_created_enhanced(self, event: ProjectCreatedEvent):
        """Auto-generate requirements, timeline, and tasks on project creation."""
        logger.info(f"Enhanced auto-generation for project {event.project_id}")
        
        async with self.db_session_factory() as session:
            try:
                # Initialize services with session
                requirement_service = RequirementService(session)
                pricing_service = PricingService(session)
                timeline_service = TimelineTrackingService(session)
                task_service = TaskManagementService(session)
                deliverable_service = DeliverableService(session, self.event_bus)
                
                # Auto-create deliverables from event data
                created_deliverables = []
                if hasattr(event, 'deliverable_types') and event.deliverable_types:
                    logger.info(f"Auto-creating {len(event.deliverable_types)} deliverables for project {event.project_id}")
                    
                    for deliverable_type in event.deliverable_types:
                        # Get sub-type and timeline days if provided
                        sub_type = getattr(event, 'deliverable_sub_types', {}).get(deliverable_type)
                        timeline_days = getattr(event, 'deliverable_timeline_days', {}).get(deliverable_type)
                        
                        try:
                            deliverable = await deliverable_service.create_deliverable(
                                project_id=event.project_id,
                                deliverable_type=DeliverableType(deliverable_type),
                                deliverable_sub_type=sub_type,
                                tentative_timeline_days=timeline_days,
                                created_by=UUID("00000000-0000-0000-0000-000000000001"),
                                assigned_to=UUID("00000000-0000-0000-0000-000000000001")
                            )
                            created_deliverables.append(deliverable)
                            logger.info(f"Created deliverable: {deliverable.id} ({deliverable_type})")
                        except Exception as e:
                            logger.error(f"Failed to create deliverable {deliverable_type}: {e}")
                
                # Get all project deliverables (including newly created ones)
                deliverables_result = await session.execute(
                    select(Deliverable).filter(Deliverable.project_id == event.project_id)
                )
                deliverables = deliverables_result.scalars().all()
                
                if not deliverables:
                    logger.warning(f"No deliverables found for project {event.project_id}")
                    return
                
                # Group deliverables by type
                interior_deliverables = [d for d in deliverables if "interior" in (d.deliverable_sub_type or "").lower()]
                exterior_deliverables = [d for d in deliverables if "exterior" in (d.deliverable_sub_type or "").lower()]
                
                # Auto-generate requirements for each deliverable
                for deliverable in deliverables:
                    await requirement_service.auto_generate_requirements(
                        project_id=event.project_id,
                        deliverable_id=deliverable.id,
                        deliverable_type=deliverable.deliverable_type or "standard"
                    )
                
                # Auto-generate project-level requirements
                await requirement_service.auto_generate_requirements(
                    project_id=event.project_id,
                    deliverable_id=None,
                    deliverable_type="project"
                )
                
                # Initialize project budget
                budget_result = await pricing_service.calculate_project_budget(
                    project_id=event.project_id
                )
                
                # Create timelines and tasks for each delivery type
                timeline_tasks = {}
                
                # Handle interior deliverables if any
                if interior_deliverables:
                    max_interior_days = max(
                        (d.tentative_timeline_days for d in interior_deliverables if d.tentative_timeline_days is not None),
                        default=None
                    )
                    
                    interior_milestones = await timeline_service.create_project_milestones(
                        project_id=event.project_id,
                        delivery_type="interior",
                        deliverable_tentative_days=max_interior_days,
                        deliverable_types=[d.deliverable_type for d in interior_deliverables]
                    )
                    
                    # Create tasks for interior timeline phases
                    interior_tasks = await self._create_phase_tasks(
                        session=session,
                        project_id=event.project_id,
                        milestones=interior_milestones,
                        deliverables=interior_deliverables,
                        task_service=task_service
                    )
                    timeline_tasks["interior"] = interior_tasks
                
                # Handle exterior deliverables if any
                if exterior_deliverables:
                    max_exterior_days = max(
                        (d.tentative_timeline_days for d in exterior_deliverables if d.tentative_timeline_days is not None),
                        default=None
                    )
                    
                    exterior_milestones = await timeline_service.create_project_milestones(
                        project_id=event.project_id,
                        delivery_type="exterior",
                        deliverable_tentative_days=max_exterior_days,
                        deliverable_types=[d.deliverable_type for d in exterior_deliverables]
                    )
                    
                    # Create tasks for exterior timeline phases
                    exterior_tasks = await self._create_phase_tasks(
                        session=session,
                        project_id=event.project_id,
                        milestones=exterior_milestones,
                        deliverables=exterior_deliverables,
                        task_service=task_service
                    )
                    timeline_tasks["exterior"] = exterior_tasks
                
                logger.info(f"Auto-generation completed for project {event.project_id}")
                logger.info(f"Created {len(interior_deliverables)} interior and {len(exterior_deliverables)} exterior deliverables")
                
            except Exception as e:
                logger.error(f"Error in enhanced project creation: {e}", exc_info=True)
                raise

    async def on_task_completed_enhanced(self, event):
        """Enhanced task completion with timeline tracking."""
        async with self.db_session_factory() as session:
            try:
                timeline_service = TimelineTrackingService(session)
                await timeline_service.log_daily_progress(
                    task_id=event.task_id,
                    progress_date=datetime.now().date(),
                    percentage_complete=100,
                    hours_spent=getattr(event, 'hours_spent', 0),
                    notes=f"Task completed via {type(event).__name__}",
                    created_by=getattr(event, 'user_id', None)
                )
                
                logger.info(f"Logged completion for task {event.task_id}")
                
            except Exception as e:
                logger.error(f"Error in task completion tracking: {e}")

    async def on_task_status_updated_enhanced(self, event: InternalTaskCreatedEvent):
        """Enhanced handler for task status updates with timeline integration."""
        if event.new_status.lower() in ['in-progress', 'in_progress']:
            async with self.db_session_factory() as session:
                try:
                    timeline_service = TimelineTrackingService(session)
                    # Log task start progress
                    await timeline_service.log_daily_progress(
                        task_id=event.task_id,
                        progress_date=datetime.now().date(),
                        percentage_complete=10,  # Initial progress when started
                        hours_spent=0,
                        notes=f"Task started - status updated to {event.new_status}",
                        created_by=getattr(event, 'user_id', None)
                    )
                    
                    logger.info(f"Logged start progress for task {event.task_id}")
                    
                except Exception as e:
                    logger.error(f"Error logging task start progress: {e}")

    async def on_requirement_updated_enhanced(self, event: RequirementUpdatedEvent):
        """Enhanced handler for requirement updates with budget recalculation."""
        if event.new_status.lower() in ['received', 'approved']:
            async with self.db_session_factory() as session:
                try:
                    # Create pricing service with session
                    pricing_service = PricingService(session)
                    # Recalculate project budget as requirements may affect scope
                    await pricing_service.recalculate_project_budget(
                        project_id=event.project_id
                    )
                    
                    logger.info(f"Recalculated budget after requirement {event.requirement_id} update")
                    
                except Exception as e:
                    logger.error(f"Error recalculating budget after requirement update: {e}")

    async def on_deliverable_delivered_enhanced(self, event: DeliverableDeliveredEvent):
        """Enhanced handler for deliverable completion with budget and timeline updates."""
        async with self.db_session_factory() as session:
            try:
                # Create services with session
                pricing_service = PricingService(session)
                timeline_service = TimelineTrackingService(session)
                
                # Update budget tracking
                await pricing_service.recalculate_project_budget(
                    project_id=event.project_id
                )
                
                # Update timeline completion
                await timeline_service.calculate_project_completion(event.project_id)
                
                logger.info(f"Updated budget and timeline for completed deliverable {event.deliverable_id}")
                
            except Exception as e:
                logger.error(f"Error in enhanced deliverable completion: {e}")

    async def _create_phase_tasks(
        self,
        session: AsyncSession,
        project_id: UUID,
        milestones: List[ProjectTimeline],
        deliverables: List[Deliverable],
        task_service: TaskManagementService
    ) -> Dict[str, List[UUID]]:
        """Create tasks for each timeline phase and establish dependencies."""
        phase_tasks = {}
        previous_phase_tasks = []

        for milestone in sorted(milestones, key=lambda m: m.phase_order):
            phase_tasks[milestone.phase_name] = []
            
            # Create phase-specific tasks
            if milestone.phase_name == "Kick-off Meeting":
                task_id = await task_service.create_task(
                    project_id=project_id,
                    task_type="meeting",
                    title=f"Project Kick-off Meeting",
                    description="Initial project kick-off meeting with team",
                    duration_days=1,
                    dependencies=[]
                )
                phase_tasks[milestone.phase_name].append(task_id)
                
            elif milestone.phase_name in ["Modeling", "Modeling & Texturing"]:
                for deliverable in deliverables:
                    task_id = await task_service.create_task(
                        project_id=project_id,
                        task_type="modeling",
                        title=f"Create 3D Model - {deliverable.name}",
                        description=f"Create 3D model for {deliverable.name}",
                        duration_days=milestone.fixed_days,
                        dependencies=previous_phase_tasks
                    )
                    phase_tasks[milestone.phase_name].append(task_id)
                    
            elif milestone.phase_name in ["Texturing", "Texturing & Landscaping"]:
                for deliverable in deliverables:
                    task_id = await task_service.create_task(
                        project_id=project_id,
                        task_type="texturing",
                        title=f"Apply Textures - {deliverable.name}",
                        description=f"Apply textures and materials for {deliverable.name}",
                        duration_days=milestone.fixed_days,
                        dependencies=previous_phase_tasks
                    )
                    phase_tasks[milestone.phase_name].append(task_id)
                    
            elif milestone.phase_name == "Lighting":
                for deliverable in deliverables:
                    task_id = await task_service.create_task(
                        project_id=project_id,
                        task_type="lighting",
                        title=f"Setup Lighting - {deliverable.name}",
                        description=f"Setup and configure lighting for {deliverable.name}",
                        duration_days=milestone.fixed_days,
                        dependencies=previous_phase_tasks
                    )
                    phase_tasks[milestone.phase_name].append(task_id)
            
            # Update previous phase tasks for next iteration
            previous_phase_tasks = phase_tasks[milestone.phase_name]
            
            # Emit events for task creation
            for task_id in phase_tasks[milestone.phase_name]:
                await self.event_bus.publish(
                    InternalTaskCreatedEvent(
                        project_id=project_id,
                        task_id=task_id,
                        task_type=milestone.phase_name.lower(),
                        deliverable_id=None  # Set to specific deliverable if needed
                    )
                )
        
        return phase_tasks
 