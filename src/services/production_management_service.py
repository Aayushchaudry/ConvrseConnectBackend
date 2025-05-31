# src/services/production_management_service.py

import logging
from typing import List, Dict, Any, Callable, Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from src.config.database import AsyncSessionLocal
from src.events.event_bus_interface import EventBus

# --- Import Models ---
from src.models.project import Project
from src.models.deliverable import Deliverable
from src.models.internal_task import InternalTask, TaskType, TaskStatus, Priority # Import Task enums
# from src.models.user import User # Uncomment if you implement User model

# --- Import Commands Consumed by this Service ---
from src.orchestrators.deliverable_saga_orchestrator.commands import (
    InitiateModelingCommand,
    InitiateTexturingCommand,
    InitiateRenderingCommand
)
from src.commands.production_commands import ( # From central commands folder
    CreateInternalTaskCommand,
    UpdateInternalTaskStatusCommand,
    CreateReworkTaskCommand
)

# --- Import Events Published by this Service ---
from src.events.task_events import (
    InternalTaskCreatedEvent,
    InternalTaskCompletedEvent,
    InternalTaskFailedEvent,
    InternalTaskStatusUpdatedEvent
)

logger = logging.getLogger(__name__)

class ProductionManagementService:
    """
    Service responsible for managing internal production tasks (e.g., modeling, texturing, rendering).
    Consumes commands from Deliverable SAGA Orchestrator and publishes task-related events.
    """
    def __init__(self, db_session_factory: Callable[[], AsyncSession], event_bus: EventBus):
        self.db_session_factory = db_session_factory
        self.event_bus = event_bus

    async def _get_deliverable_and_project(self, session: AsyncSession, deliverable_id: UUID, project_id: UUID):
        """Helper to fetch deliverable and project for context/validation."""
        from sqlalchemy import select
        deliverable_result = await session.execute(
            select(Deliverable).filter(Deliverable.id == deliverable_id, Deliverable.project_id == project_id)
        )
        deliverable = deliverable_result.scalar_one_or_none()
        
        project_result = await session.execute(
            select(Project).filter(Project.id == project_id)
        )
        project = project_result.scalar_one_or_none()

        if not deliverable or not project:
            raise ValueError(f"Project {project_id} or Deliverable {deliverable_id} not found.")
        return project, deliverable

    async def handle_initiate_modeling_command(self, command: InitiateModelingCommand):
        """
        Handles InitiateModelingCommand to create a modeling task.
        """
        logger.info(f"ProductionManagementService: Received InitiateModelingCommand for Deliverable {command.deliverable_id}")

        async with self.db_session_factory() as session:
            try:
                project, deliverable = await self._get_deliverable_and_project(session, command.deliverable_id, command.project_id)

                # Check if modeling task already exists for idempotency
                from sqlalchemy import select
                existing_task_query = await session.execute(
                    select(InternalTask).filter(
                        InternalTask.deliverable_id == command.deliverable_id,
                        InternalTask.task_type == TaskType.MODELING
                    )
                )
                if existing_task_query.scalar_one_or_none():
                    logger.warning(f"Modeling task already exists for Deliverable {command.deliverable_id}. Skipping creation. Idempotent.")
                    return # Task already created, just return

                new_task = InternalTask(
                    project_id=command.project_id,
                    deliverable_id=command.deliverable_id,
                    task_name=f"Modeling for {deliverable.deliverable_type.value} {deliverable.deliverable_sub_type or ''}",
                    task_type=TaskType.MODELING,
                    status=TaskStatus.TODO,
                    priority=Priority.HIGH,
                    start_date=datetime.utcnow()
                )
                session.add(new_task)
                await session.commit()
                await session.refresh(new_task)

                logger.info(f"ProductionManagementService: Created new Modeling task: {new_task.id} for Deliverable {command.deliverable_id}")

                # Publish event that a new task was created
                await self.event_bus.publish(
                    topic="internal_task.created", # Define this topic in your config/event_bus.py (or global events file)
                    message=InternalTaskCreatedEvent(
                        project_id=new_task.project_id,
                        deliverable_id=new_task.deliverable_id,
                        task_id=new_task.id,
                        task_name=new_task.task_name,
                        task_type=new_task.task_type.value
                    ).__dict__
                )
            except ValueError as ve:
                logger.error(f"ProductionManagementService Error: {ve}")
                # Publish a failure event if project/deliverable not found
                # Or handle this upstream in orchestrator if it's a critical SAGA error
            except Exception as e:
                logger.error(f"Error creating modeling task for Deliverable {command.deliverable_id}: {e}", exc_info=True)
                await session.rollback()
                # Publish InternalTaskFailedEvent
                await self.event_bus.publish(
                    topic="internal_task.failed", # Define this topic
                    message=InternalTaskFailedEvent(
                        project_id=command.project_id,
                        deliverable_id=command.deliverable_id,
                        task_id=None, # Task might not have been created
                        task_name="Modeling Task Creation Failed",
                        task_type=TaskType.MODELING.value,
                        reason=f"Failed to create: {str(e)}"
                    ).__dict__
                )

    async def handle_create_rework_task_command(self, command: CreateReworkTaskCommand):
        """
        Handles CreateReworkTaskCommand to create a rework task, usually due to client comments.
        """
        logger.info(f"ProductionManagementService: Received CreateReworkTaskCommand for Deliverable {command.deliverable_id}, Original Task {command.original_task_id}")

        async with self.db_session_factory() as session:
            try:
                project, deliverable = await self._get_deliverable_and_project(session, command.deliverable_id, command.project_id)
                
                # Fetch the original task if original_task_id is provided
                original_task = None
                if command.original_task_id:
                    from sqlalchemy import select
                    original_task_result = await session.execute(
                        select(InternalTask).filter(InternalTask.id == command.original_task_id)
                    )
                    original_task = original_task_result.scalar_one_or_none()
                    if not original_task:
                        logger.warning(f"Original task {command.original_task_id} not found for rework command. Creating standalone rework task.")

                new_rework_task = InternalTask(
                    project_id=command.project_id,
                    deliverable_id=command.deliverable_id,
                    task_name=f"Rework: {original_task.task_name if original_task else 'General Rework'} - Client Comment",
                    task_type=TaskType.REWORK,
                    parent_task_id=original_task.id if original_task else None,
                    source_review_item_id=command.comment_id, # Linking rework to the client comment event ID (or actual ClientFeedback ID later)
                    status=TaskStatus.TODO,
                    priority=Priority.HIGH,
                    start_date=datetime.utcnow(),
                    description=command.rework_description
                )
                session.add(new_rework_task)
                await session.commit()
                await session.refresh(new_rework_task)

                logger.info(f"ProductionManagementService: Created new Rework task: {new_rework_task.id} for Deliverable {command.deliverable_id}")
                
                # Publish event that a rework task was created
                await self.event_bus.publish(
                    topic="internal_task.created",
                    message=InternalTaskCreatedEvent(
                        project_id=new_rework_task.project_id,
                        deliverable_id=new_rework_task.deliverable_id,
                        task_id=new_rework_task.id,
                        task_name=new_rework_task.task_name,
                        task_type=new_rework_task.task_type.value
                    ).__dict__
                )
            except ValueError as ve:
                logger.error(f"ProductionManagementService Error: {ve}")
            except Exception as e:
                logger.error(f"Error creating rework task for Deliverable {command.deliverable_id}: {e}", exc_info=True)
                await session.rollback()
                await self.event_bus.publish(
                    topic="internal_task.failed",
                    message=InternalTaskFailedEvent(
                        project_id=command.project_id,
                        deliverable_id=command.deliverable_id,
                        task_id=None,
                        task_name="Rework Task Creation Failed",
                        task_type=TaskType.REWORK.value,
                        reason=f"Failed to create: {str(e)}"
                    ).__dict__
                )

    async def handle_update_internal_task_status_command(self, command: UpdateInternalTaskStatusCommand):
        """
        Handles UpdateInternalTaskStatusCommand to update an internal task's status.
        """
        logger.info(f"ProductionManagementService: Received UpdateInternalTaskStatusCommand for Task {command.task_id} to status {command.new_status}")

        async with self.db_session_factory() as session:
            try:
                from sqlalchemy import select
                task = await session.execute(
                    select(InternalTask).filter(InternalTask.id == command.task_id)
                )
                task = task.scalar_one_or_none()

                if not task:
                    logger.error(f"Internal Task {command.task_id} not found for status update command. Skipping.")
                    return

                old_status = task.status.value
                try:
                    new_status_enum = TaskStatus(command.new_status)
                except ValueError:
                    logger.error(f"Invalid new_status '{command.new_status}' for Task {command.task_id}. Skipping update.")
                    return

                task.status = new_status_enum
                if new_status_enum == TaskStatus.DONE or new_status_enum == TaskStatus.REJECTED_TERMINATED:
                    task.actual_end_date = datetime.utcnow()
                
                session.add(task)
                await session.commit()
                await session.refresh(task)

                logger.info(f"ProductionManagementService: Updated Task {task.id} status from {old_status} to {new_status_enum.value}.")

                # Publish event about task status update
                await self.event_bus.publish(
                    topic="internal_task.status_updated", # Define this topic
                    message=InternalTaskStatusUpdatedEvent(
                        project_id=task.project_id,
                        deliverable_id=task.deliverable_id,
                        task_id=task.id,
                        old_status=old_status,
                        new_status=new_status_enum.value
                    ).__dict__
                )

                # If task is DONE, publish InternalTaskCompletedEvent
                if new_status_enum == TaskStatus.DONE:
                    await self.event_bus.publish(
                        topic="internal_task.completed", # Define this topic
                        message=InternalTaskCompletedEvent(
                            project_id=task.project_id,
                            deliverable_id=task.deliverable_id,
                            task_id=task.id,
                            task_name=task.task_name,
                            task_type=task.task_type.value
                        ).__dict__
                    )
                # If task is rejected/terminated, publish InternalTaskFailedEvent (or a specific rejected event)
                elif new_status_enum == TaskStatus.REJECTED_TERMINATED:
                    await self.event_bus.publish(
                        topic="internal_task.failed", # Or specific 'internal_task.rejected'
                        message=InternalTaskFailedEvent(
                            project_id=task.project_id,
                            deliverable_id=task.deliverable_id,
                            task_id=task.id,
                            task_name=task.task_name,
                            task_type=task.task_type.value,
                            reason="Task rejected/terminated by SAGA Orchestrator."
                        ).__dict__
                    )

            except Exception as e:
                logger.error(f"Error updating task status for Task {command.task_id}: {e}", exc_info=True)
                await session.rollback()
                # Consider publishing a specific event for task status update failure here.