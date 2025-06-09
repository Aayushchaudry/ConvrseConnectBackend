# src/orchestrators/saga_processor.py

import enum
import logging
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.events.event_bus_interface import EventBus
from src.models.saga_state import SagaState, SagaStatus, SagaType

logger = logging.getLogger(__name__)


class SagaProcessor:
    """
    Provides generic utilities for SAGA orchestrators to manage state and send messages.
    """

    def __init__(self, event_bus: EventBus):
        """
        Initializes the SagaProcessor.
        Args:
            event_bus: The EventBus instance for publishing commands/events.
        """
        self.event_bus = event_bus

    async def get_or_create_saga_state(
        self,
        session: AsyncSession,
        project_id: UUID,
        saga_type: SagaType,
        initial_state: str,
        deliverable_id: Optional[UUID] = None,
        saga_id: Optional[UUID] = None,  # For resuming an existing saga with a known ID
    ) -> SagaState:
        """
        Retrieves an existing SagaState or creates a new one if not found.
        Ensures idempotency for SAGA initiation.
        """
        if saga_id:
            result = await session.execute(
                select(SagaState).filter(SagaState.saga_id == saga_id)
            )
            saga_state = result.scalar_one_or_none()
            if saga_state:
                logger.info(
                    f"Retrieved existing SAGA state (ID: {saga_id}) for {saga_type.value} project {project_id}."
                )
                return saga_state

        # If no specific saga_id provided or not found, try to find by project/deliverable
        # For PROJECT_LIFECYCLE, deliverable_id is null
        # For DELIVERABLE_PRODUCTION, deliverable_id is required

        query = select(SagaState).filter(
            SagaState.project_id == project_id, SagaState.saga_type == saga_type
        )
        if deliverable_id:
            query = query.filter(SagaState.deliverable_id == deliverable_id)
        else:
            query = query.filter(
                SagaState.deliverable_id.is_(None)
            )  # Ensure no deliverable_id for project saga

        result = await session.execute(query)
        saga_state = result.scalar_one_or_none()

        if saga_state is None:
            # Create a new SAGA state if it doesn't exist
            new_saga_state = SagaState(
                saga_id=saga_id if saga_id else uuid.uuid4(),
                saga_type=saga_type,
                project_id=project_id,
                deliverable_id=deliverable_id,
                current_state=initial_state,
                status=SagaStatus.IN_PROGRESS,
            )
            session.add(new_saga_state)
            await session.commit()
            await session.refresh(new_saga_state)
            logger.info(
                f"New SAGA state created for {saga_type.value} project {project_id}. SAGA ID: {new_saga_state.saga_id}"
            )
            return new_saga_state
        else:
            logger.info(
                f"Existing SAGA state found for {saga_type.value} project {project_id}. Current state: {saga_state.current_state}"
            )
            return saga_state

    async def update_saga_state(
        self,
        session: AsyncSession,
        saga_state: SagaState,
        new_state_enum: enum.Enum,  # Use an enum for clarity (ProjectSagaState or DeliverableSagaState)
        event_id: UUID,
        command_id: Optional[UUID] = None,
        new_saga_status: Optional[
            SagaStatus
        ] = None,  # Optional, for final statuses like COMPLETED, FAILED
    ):
        """
        Updates the SAGA's current state and persists changes to the database.
        Includes idempotency check for the last processed event.
        """
        if saga_state.last_event_processed_id == str(event_id):
            logger.warning(
                f"SAGA {saga_state.saga_id} already processed event {event_id}. Skipping update."
            )
            return

        saga_state.current_state = new_state_enum.value
        saga_state.last_event_processed_id = str(event_id)
        saga_state.last_event_processed_timestamp = datetime.utcnow()

        if command_id:
            saga_state.last_command_sent_id = str(command_id)
            saga_state.last_command_sent_timestamp = datetime.utcnow()

        if new_saga_status:
            saga_state.status = new_saga_status

        saga_state.updated_at = datetime.utcnow()
        session.add(saga_state)  # Re-add for update tracking if not already attached
        await session.commit()
        await session.refresh(saga_state)
        logger.info(
            f"SAGA {saga_state.saga_id} (Type: {saga_state.saga_type.value}) state updated to '{new_state_enum.value}'. Status: {saga_state.status.value}"
        )

    async def publish_message(self, topic: str, message_payload: Any):
        """
        Publishes a command or event message to the Event Bus.
        Ensures the message is converted to a dictionary.
        """
        if hasattr(message_payload, "__dict__"):
            message_dict = message_payload.__dict__
        else:
            message_dict = message_payload

        await self.event_bus.publish(topic=topic, message=message_dict)
        logger.info(
            f"Published message to topic '{topic}': {message_payload.command_type if hasattr(message_payload, 'command_type') else message_payload.event_type}"
        )
