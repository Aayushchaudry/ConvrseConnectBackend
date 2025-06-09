# src/services/delivery_service.py

import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import AsyncSessionLocal
from src.events.event_bus_interface import EventBus

# --- Import Events Published by this Service ---
from src.events.project_events import (
    DeliverableDeliveredEvent as ProjectDeliverableDeliveredEvent,
)  # Alias for clarity if similar name exists
from src.models.deliverable import Deliverable

# --- Import Models ---
from src.models.project import Project
from src.models.project_output import ProjectOutput  # Import the ProjectOutput model

# --- Import Commands Consumed by this Service ---
from src.orchestrators.deliverable_saga_orchestrator.commands import (
    GenerateFinalOutputCommand,
)  # Main command to consume

logger = logging.getLogger(__name__)


class DeliveryService:
    """
    Service responsible for generating and managing final project deliverables (ProjectOutputs).
    Consumes commands from Deliverable SAGA Orchestrator and publishes final delivery events.
    """

    def __init__(
        self, db_session_factory: Callable[[], AsyncSession], event_bus: EventBus
    ):
        self.db_session_factory = db_session_factory
        self.event_bus = event_bus

    async def _get_context_entities(
        self, session: AsyncSession, project_id: UUID, deliverable_id: UUID
    ):
        """Helper to fetch related project and deliverable for context/validation."""
        project_result = await session.execute(
            select(Project).filter(Project.id == project_id)
        )
        project = project_result.scalar_one_or_none()

        deliverable_result = await session.execute(
            select(Deliverable).filter(Deliverable.id == deliverable_id)
        )
        deliverable = deliverable_result.scalar_one_or_none()

        if not project or not deliverable:
            raise ValueError(
                f"Project {project_id} or Deliverable {deliverable_id} not found."
            )
        return project, deliverable

    async def handle_generate_final_output_command(
        self, command: GenerateFinalOutputCommand
    ):
        """
        Handles GenerateFinalOutputCommand to create a final ProjectOutput record.
        """
        logger.info(
            f"DeliveryService: Received GenerateFinalOutputCommand for Deliverable {command.deliverable_id} (Output: {command.output_name})"
        )

        async with self.db_session_factory() as session:
            try:
                project, deliverable = await self._get_context_entities(
                    session, command.project_id, command.deliverable_id
                )

                # Check for idempotency: Avoid creating duplicate ProjectOutput for the same deliverable/name
                existing_output_result = await session.execute(
                    select(ProjectOutput).filter(
                        ProjectOutput.deliverable_id == command.deliverable_id,
                        ProjectOutput.output_name
                        == command.output_name,  # Assuming unique name per deliverable
                    )
                )
                existing_output = existing_output_result.scalar_one_or_none()
                if existing_output:
                    logger.warning(
                        f"Project output '{command.output_name}' already exists for Deliverable {command.deliverable_id}. Skipping creation. Idempotent."
                    )
                    # Still publish delivered event if it's already there
                    await self.event_bus.publish(
                        topic="deliverable.delivered.final",  # This is the topic the Orchestrator expects
                        message=ProjectDeliverableDeliveredEvent(
                            project_id=command.project_id,
                            deliverable_id=command.deliverable_id,
                            deliverable_name=deliverable.deliverable_type.value,  # Get deliverable type name
                            final_output_url=existing_output.output_url,  # Use existing URL
                        ).__dict__,
                    )
                    return

                # In a real scenario, this is where you'd integrate with:
                # 1. An asset management system to retrieve the final files.
                # 2. A cloud storage service (e.g., S3) to upload or get a shareable URL.
                # For this example, we'll use a dummy URL.
                dummy_output_url = f"https://your-cloud-storage.com/{command.project_id}/{command.deliverable_id}/{command.output_name.replace(' ', '_').lower()}.zip"

                new_project_output = ProjectOutput(
                    project_id=command.project_id,
                    deliverable_id=command.deliverable_id,
                    output_name=command.output_name,
                    output_url=dummy_output_url,
                    delivery_date=datetime.utcnow(),
                    comments_allowed_on_output=True,  # Default to true for final outputs
                )
                session.add(new_project_output)
                await session.commit()
                await session.refresh(new_project_output)

                logger.info(
                    f"DeliveryService: Created new ProjectOutput {new_project_output.id} for Deliverable {command.deliverable_id}."
                )

                # Publish event that the deliverable has been fully delivered
                await self.event_bus.publish(
                    topic="deliverable.delivered.final",  # This is the topic the Orchestrator expects
                    message=ProjectDeliverableDeliveredEvent(
                        project_id=new_project_output.project_id,
                        deliverable_id=new_project_output.deliverable_id,
                        deliverable_name=deliverable.deliverable_type.value,  # Get deliverable type name
                        final_output_url=new_project_output.output_url,
                    ).__dict__,
                )
            except ValueError as ve:
                logger.error(
                    f"DeliveryService Error: Context entity not found for command: {ve}"
                )
                # Publish DeliverableFailedEvent from Project_events to orchestrator
                await self._publish_delivery_failed_event(
                    command.project_id,
                    command.deliverable_id,
                    deliverable.deliverable_type.value if deliverable else "Unknown",
                    f"Context missing: {str(ve)}",
                )
            except Exception as e:
                logger.error(
                    f"Error generating final output for Deliverable {command.deliverable_id}: {e}",
                    exc_info=True,
                )
                await session.rollback()
                # Publish DeliverableFailedEvent (from project_events)
                await self._publish_delivery_failed_event(
                    command.project_id,
                    command.deliverable_id,
                    deliverable.deliverable_type.value if deliverable else "Unknown",
                    f"Failed to generate output: {str(e)}",
                )

    async def _publish_delivery_failed_event(
        self, project_id: UUID, deliverable_id: UUID, deliverable_name: str, reason: str
    ):
        """Helper to publish DeliverableFailedEvent if delivery fails."""
        from src.events.project_events import (
            DeliverableFailedEvent as ProjectDeliverableFailedEvent,
        )  # Alias

        await self.event_bus.publish(
            topic="project.deliverable.failed",  # Topic Project Orchestrator listens to
            message=ProjectDeliverableFailedEvent(
                project_id=project_id,
                deliverable_id=deliverable_id,
                deliverable_name=deliverable_name,
                reason=reason,
            ).__dict__,
        )
