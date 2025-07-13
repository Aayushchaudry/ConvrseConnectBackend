# src/services/production_management_service.py

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.commands.production_commands import (  # From central commands folder
    CreateInternalTaskCommand,
    CreateReworkTaskCommand,
    UpdateInternalTaskStatusCommand,
)
from src.config.database import AsyncSessionLocal
from src.events.event_bus_interface import EventBus

# --- Import Events Published by this Service ---
from src.events.task_events import (
    InternalTaskCompletedEvent,
    InternalTaskCreatedEvent,
    InternalTaskFailedEvent,
    InternalTaskStatusUpdatedEvent,
)
from src.models.deliverable import Deliverable
from src.models.internal_task import (
    InternalTask,  # Import Task enums
    Priority,
    TaskStatus,
    TaskType,
)

# --- Import Models ---
from src.models.project import Project

# --- Import Commands Consumed by this Service ---
from src.orchestrators.deliverable_saga_orchestrator.commands import (
    InitiateModelingCommand,
    InitiateRenderingCommand,
    InitiateTexturingCommand,
)

# from src.models.user import User # Uncomment if you implement User model


logger = logging.getLogger(__name__)


class ProductionManagementService:
    """
    Service responsible for managing internal production tasks (e.g., modeling, texturing, rendering).
    Consumes commands from Deliverable SAGA Orchestrator and publishes task-related events.
    """

    def __init__(
        self, db_session_factory: Callable[[], AsyncSession], event_bus: EventBus
    ):
        self.db_session_factory = db_session_factory
        self.event_bus = event_bus

    async def _get_deliverable_and_project(
        self, session: AsyncSession, deliverable_id: UUID, project_id: UUID
    ):
        """Helper to fetch deliverable and project for context/validation."""
        from sqlalchemy import select

        deliverable_result = await session.execute(
            select(Deliverable).filter(
                Deliverable.id == deliverable_id, Deliverable.project_id == project_id
            )
        )
        deliverable = deliverable_result.scalar_one_or_none()

        project_result = await session.execute(
            select(Project).filter(Project.id == project_id)
        )
        project = project_result.scalar_one_or_none()

        if not deliverable or not project:
            raise ValueError(
                f"Project {project_id} or Deliverable {deliverable_id} not found."
            )
        return project, deliverable

    async def _get_task_by_id(
        self, session: AsyncSession, task_id: UUID
    ) -> Optional[InternalTask]:
        """Helper to fetch a task by ID."""
        from sqlalchemy import select

        result = await session.execute(
            select(InternalTask).filter(InternalTask.id == task_id)
        )
        return result.scalar_one_or_none()

    async def handle_initiate_modeling_command(self, command: InitiateModelingCommand):
        """
        Handles the InitiateModelingCommand to create a modeling task.
        Creates project-level modeling task (once per project) instead of per deliverable.
        """
        logger.info(
            f"ProductionManagementService: Received InitiateModelingCommand for Project {command.project_id}, Deliverable {command.deliverable_id}"
        )

        async with self.db_session_factory() as session:
            try:
                # Validate project and deliverable exist
                project, deliverable = await self._get_deliverable_and_project(
                    session, command.deliverable_id, command.project_id
                )

                # Check if a project-level modeling task already exists
                from sqlalchemy import select

                existing_task = await session.execute(
                    select(InternalTask).filter(
                        InternalTask.project_id == command.project_id,
                        InternalTask.task_type == TaskType.MODELING.value,
                        InternalTask.is_project_level == True,
                        InternalTask.deliverable_id.is_(None),  # Project-level tasks have no deliverable_id
                    )
                )
                existing_modeling_task = existing_task.scalar_one_or_none()

                if existing_modeling_task:
                    logger.info(
                        f"✅ Project-level modeling task already exists: {existing_modeling_task.id} for project {command.project_id}. Skipping creation."
                    )
                    
                    # Publish event for existing task (to maintain workflow consistency)
                    await self.event_bus.publish(
                        topic="internal_task.completed",  # Use existing topic that orchestrator listens to
                        message=InternalTaskCreatedEvent(
                            project_id=existing_modeling_task.project_id,
                            deliverable_id=command.deliverable_id,  # Keep original deliverable_id for context
                            task_id=existing_modeling_task.id,
                            task_name=existing_modeling_task.task_name,
                            task_type=existing_modeling_task.task_type,
                        ).__dict__,
                    )
                    return

                # Create four project-level tasks for each phase instead of a single modeling task
                phase_definitions = [
                    {
                        "task_name": f"Phase 1 - Modeling - {project.name}",
                        "task_type": TaskType.MODELING.value,
                        "description": f"3D modeling work for all deliverables in project {project.name}",
                    },
                    {
                        "task_name": f"Phase 2 - Texturing and Landscaping - {project.name}",
                        "task_type": TaskType.TEXTURING.value,
                        "description": f"Texturing and landscaping for all deliverables in project {project.name}",
                    },
                    {
                        "task_name": f"Phase 3 - Lighting - {project.name}",
                        "task_type": TaskType.LIGHTING.value,
                        "description": f"Lighting work for all deliverables in project {project.name}",
                    },
                    {
                        "task_name": f"Phase 4 - Final Deliverable - {project.name}",
                        "task_type": TaskType.FINAL_DELIVERABLE.value if hasattr(TaskType, 'FINAL_DELIVERABLE') else TaskType.RENDERING.value,
                        "description": f"Final deliverable phase for all deliverables in project {project.name}",
                    },
                ]
                created_tasks = []
                for phase in phase_definitions:
                    task = InternalTask(
                        project_id=command.project_id,
                        deliverable_id=None,  # Project-level task
                        task_name=phase["task_name"],
                        task_type=phase["task_type"],
                        status=TaskStatus.TODO.value,
                        priority=Priority.HIGH.value,
                        start_date=datetime.utcnow(),
                        is_project_level=True,  # Mark as project-level
                        description=phase["description"],
                    )
                    session.add(task)
                    created_tasks.append(task)
                await session.commit()
                for task in created_tasks:
                    await session.refresh(task)
                    logger.info(
                        f"✅ ProductionManagementService: Created new project-level task: {task.id} for project {command.project_id} ({task.task_name})"
                    )
                    # Publish event that a new task was created
                    await self.event_bus.publish(
                        topic="internal_task.completed",  # Use existing topic that orchestrator listens to
                        message=InternalTaskCreatedEvent(
                            project_id=task.project_id,
                            deliverable_id=command.deliverable_id,  # Keep original deliverable_id for context
                            task_id=task.id,
                            task_name=task.task_name,
                            task_type=task.task_type,
                        ).__dict__,
                    )
            except ValueError as ve:
                logger.error(f"ProductionManagementService Error: {ve}")
                # Publish a failure event if project/deliverable not found
                # Or handle this upstream in orchestrator if it's a critical SAGA error
            except Exception as e:
                logger.error(
                    f"Error creating modeling task for Deliverable {command.deliverable_id}: {e}",
                    exc_info=True,
                )
                await session.rollback()
                # Publish InternalTaskFailedEvent
                await self.event_bus.publish(
                    topic="internal_task.completed",  # Use existing topic that orchestrator listens to
                    message=InternalTaskFailedEvent(
                        project_id=command.project_id,
                        deliverable_id=command.deliverable_id,
                        task_id=None,  # Task might not have been created
                        task_name="Modeling Task Creation Failed",
                        task_type=TaskType.MODELING.value,
                        reason=f"Failed to create: {str(e)}",
                    ).__dict__,
                )

    async def handle_create_rework_task_command(self, command: CreateReworkTaskCommand):
        """
        Handles CreateReworkTaskCommand to create a rework task, usually due to client comments.
        """
        logger.info(
            f"ProductionManagementService: Received CreateReworkTaskCommand for Deliverable {command.deliverable_id}, Original Task {command.original_task_id}"
        )

        async with self.db_session_factory() as session:
            try:
                project, deliverable = await self._get_deliverable_and_project(
                    session, command.deliverable_id, command.project_id
                )

                # Fetch the original task if original_task_id is provided
                original_task = None
                if command.original_task_id:
                    from sqlalchemy import select

                    original_task_result = await session.execute(
                        select(InternalTask).filter(
                            InternalTask.id == command.original_task_id
                        )
                    )
                    original_task = original_task_result.scalar_one_or_none()
                    if not original_task:
                        logger.warning(
                            f"Original task {command.original_task_id} not found for rework command. Creating standalone rework task."
                        )

                # Create new task with same type as original task
                task_type = (
                    original_task.task_type if original_task else TaskType.REWORK
                )
                task_name = f"Rework: {original_task.task_name if original_task else 'General Rework'} - Client Comment"

                new_rework_task = InternalTask(
                    project_id=command.project_id,
                    deliverable_id=command.deliverable_id,
                    task_name=task_name,
                    task_type=task_type,  # Use original task type
                    parent_task_id=original_task.id if original_task else None,
                    source_review_item_id=command.review_item_id,  # Use review_item_id instead of comment_id
                    status=TaskStatus.TODO.value,  # Explicitly use .value for database
                    priority=Priority.HIGH.value,  # Explicitly use .value for database
                    start_date=datetime.utcnow(),
                    description=command.rework_description,
                )
                session.add(new_rework_task)
                await session.commit()
                await session.refresh(new_rework_task)

                logger.info(
                    f"ProductionManagementService: Created new Rework task: {new_rework_task.id} for Deliverable {command.deliverable_id}"
                )

                # Publish event that a rework task was created
                await self.event_bus.publish(
                    topic="internal_task.completed",  # Use existing topic that orchestrator listens to
                    message=InternalTaskCreatedEvent(
                        project_id=new_rework_task.project_id,
                        deliverable_id=new_rework_task.deliverable_id,
                        task_id=new_rework_task.id,
                        task_name=new_rework_task.task_name,
                        task_type=new_rework_task.task_type,
                    ).__dict__,
                )
            except ValueError as ve:
                logger.error(f"ProductionManagementService Error: {ve}")
            except Exception as e:
                logger.error(
                    f"Error creating rework task for Deliverable {command.deliverable_id}: {e}",
                    exc_info=True,
                )
                await session.rollback()
                await self.event_bus.publish(
                    topic="internal_task.completed",  # Use existing topic that orchestrator listens to
                    message=InternalTaskFailedEvent(
                        project_id=command.project_id,
                        deliverable_id=command.deliverable_id,
                        task_id=None,
                        task_name="Rework Task Creation Failed",
                        task_type=TaskType.REWORK.value,
                        reason=f"Failed to create: {str(e)}",
                    ).__dict__,
                )

    async def handle_update_internal_task_status_command(
        self, command: UpdateInternalTaskStatusCommand
    ) -> Optional[InternalTask]:
        """
        Handles UpdateInternalTaskStatusCommand to update an internal task's status.
        """
        logger.info(
            f"ProductionManagementService: Received UpdateInternalTaskStatusCommand for Task {command.task_id} to status {command.new_status}"
        )

        async with self.db_session_factory() as session:
            try:
                task = await self._get_task_by_id(session, command.task_id)

                if not task:
                    logger.error(
                        f"Internal Task {command.task_id} not found for status update command. Skipping."
                    )
                    return None

                old_status = task.status.value
                try:
                    new_status_enum = TaskStatus(command.new_status)
                except ValueError:
                    logger.error(
                        f"Invalid new_status '{command.new_status}' for Task {command.task_id}. Skipping update."
                    )
                    return None

                task.status = new_status_enum
                if (
                    new_status_enum == TaskStatus.DONE
                    or new_status_enum == TaskStatus.REJECTED_TERMINATED
                ):
                    task.actual_end_date = datetime.utcnow()

                session.add(task)
                await session.commit()
                await session.refresh(task)

                logger.info(
                    f"ProductionManagementService: Updated Task {task.id} status from {old_status} to {new_status_enum.value}."
                )

                # Publish event about task status update
                await self.event_bus.publish(
                    topic="internal_task.completed",  # Use existing topic that orchestrator listens to
                    message=InternalTaskStatusUpdatedEvent(
                        project_id=task.project_id,
                        deliverable_id=task.deliverable_id,
                        task_id=task.id,
                        old_status=old_status,
                        new_status=new_status_enum.value,
                    ).__dict__,
                )

                # If task is DONE, publish InternalTaskCompletedEvent
                if new_status_enum == TaskStatus.DONE:
                    await self.event_bus.publish(
                        topic="internal_task.completed",  # Define this topic
                        message=InternalTaskCompletedEvent(
                            project_id=task.project_id,
                            deliverable_id=task.deliverable_id,
                            task_id=task.id,
                            task_name=task.task_name,
                            task_type=task.task_type.value,
                        ).__dict__,
                    )
                # If task is rejected/terminated, publish InternalTaskFailedEvent (or a specific rejected event)
                elif new_status_enum == TaskStatus.REJECTED_TERMINATED:
                    await self.event_bus.publish(
                        topic="internal_task.completed",  # Use existing topic that orchestrator listens to
                        message=InternalTaskFailedEvent(
                            project_id=task.project_id,
                            deliverable_id=task.deliverable_id,
                            task_id=task.id,
                            task_name=task.task_name,
                            task_type=task.task_type.value,
                            reason="Task rejected/terminated by SAGA Orchestrator.",
                        ).__dict__,
                    )

                return task

            except Exception as e:
                logger.error(
                    f"Error updating task status for Task {command.task_id}: {e}",
                    exc_info=True,
                )
                await session.rollback()
                # Consider publishing a specific event for task status update failure here.
                return None

    async def complete_internal_task(
        self, task_id: UUID, actual_end_date: datetime = None
    ) -> InternalTask:
        """
        Simulates the completion of an internal task by updating its status to DONE
        and publishing InternalTaskCompletedEvent.
        """
        logger.info(
            f"ProductionManagementService: Attempting to complete Task {task_id}."
        )

        async with self.db_session_factory() as session:
            task = await self._get_task_by_id(session, task_id)

            if not task:
                raise ValueError(f"Task with ID {task_id} not found.")

            if task.status == TaskStatus.DONE:
                logger.warning(f"Task {task_id} is already DONE. Skipping update.")
                return task

            old_status = task.status.value
            task.status = TaskStatus.DONE
            task.actual_end_date = (
                actual_end_date or datetime.utcnow()
            )  # Use provided date or current time

            session.add(task)
            await session.commit()
            await session.refresh(task)

            logger.info(
                f"ProductionManagementService: Task {task.id} status updated from {old_status} to DONE."
            )

            # Publish event that the task was completed
            await self.event_bus.publish(
                topic="internal_task.completed",
                message=InternalTaskCompletedEvent(
                    project_id=task.project_id,
                    deliverable_id=task.deliverable_id,
                    task_id=task.id,
                    task_name=task.task_name,
                    task_type=task.task_type.value,
                ).__dict__,
            )
            logger.info(
                f"ProductionManagementService: Published InternalTaskCompletedEvent for Task {task.id}."
            )
            return task
