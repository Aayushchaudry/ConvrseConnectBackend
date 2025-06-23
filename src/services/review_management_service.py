# src/services/review_management_service.py

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import AsyncSessionLocal

# --- Import Events Published by this Service ---
from src.events.client_feedback_events import (
    ClientFeedbackSubmittedEvent,
)  # This event is published *by the client* or API, then handled by orchestrator, and later by this service if it generates a client-facing event
from src.events.client_feedback_events import (
    ReviewItemApprovedEvent,
    ReviewItemRejectedEvent,
)
from src.events.event_bus_interface import EventBus
from src.models.client_feedback import (  # Import FeedbackType enum
    ClientFeedback,
    FeedbackType,
)
from src.models.deliverable import Deliverable
from src.models.internal_task import InternalTask

# --- Import Models ---
from src.models.project import Project
from src.models.review_item import ReviewItem, ReviewItemType, ReviewStatus

# --- Import Commands Consumed by this Service ---
from src.commands.deliverable_commands import (
    GenerateReviewItemCommand,
)  # Main command to consume

logger = logging.getLogger(__name__)


class ReviewManagementService:
    """
    Service responsible for managing review items and processing client feedback.
    Consumes commands from Deliverable SAGA Orchestrator and publishes events.
    """

    def __init__(
        self, db_session_factory: Callable[[], AsyncSession], event_bus: EventBus
    ):
        self.db_session_factory = db_session_factory
        self.event_bus = event_bus

    async def _get_context_entities(
        self,
        session: AsyncSession,
        project_id: UUID,
        deliverable_id: UUID,
        source_internal_task_id: UUID = None,
    ):
        """Helper to fetch related entities for context/validation."""
        project_result = await session.execute(
            select(Project).filter(Project.id == project_id)
        )
        project = project_result.scalar_one_or_none()

        deliverable_result = await session.execute(
            select(Deliverable).filter(Deliverable.id == deliverable_id)
        )
        deliverable = deliverable_result.scalar_one_or_none()

        internal_task = None
        if source_internal_task_id:
            internal_task_result = await session.execute(
                select(InternalTask).filter(InternalTask.id == source_internal_task_id)
            )
            internal_task = internal_task_result.scalar_one_or_none()

        if not project or not deliverable:
            raise ValueError(
                f"Project {project_id} or Deliverable {deliverable_id} not found."
            )

        return project, deliverable, internal_task

    async def _get_review_item_by_id(
        self, session: AsyncSession, review_item_id: UUID
    ) -> Optional[ReviewItem]:
        """Helper to fetch a review item by ID."""
        return await session.get(ReviewItem, review_item_id)

    async def handle_generate_review_item_command(
        self, command: GenerateReviewItemCommand
    ):
        """
        Handles GenerateReviewItemCommand to create a new ReviewItem for client feedback.
        """
        logger.info(
            f"ReviewManagementService: Received GenerateReviewItemCommand for Deliverable {command.deliverable_id} (Type: {command.review_item_type})"
        )

        async with self.db_session_factory() as session:
            try:
                project, deliverable, internal_task = await self._get_context_entities(
                    session, command.project_id, command.deliverable_id
                )

                # Since GenerateReviewItemCommand doesn't have source_internal_task_id or review_round,
                # we'll set defaults and use the most recent modeling task for this deliverable
                review_round = 1  # Default to first review round
                source_internal_task_id = None

                # Find the most recent completed modeling task for this deliverable
                recent_task_query = await session.execute(
                    select(InternalTask)
                    .filter(
                        InternalTask.deliverable_id == command.deliverable_id,
                        InternalTask.task_type == "MODELING",
                        InternalTask.status == "DONE",
                    )
                    .order_by(InternalTask.updated_at.desc())
                    .limit(1)
                )
                recent_task = recent_task_query.scalar_one_or_none()
                if recent_task:
                    source_internal_task_id = recent_task.id

                # Use sequence_number from command or auto-generate
                if command.sequence_number is not None:
                    sequence_number = command.sequence_number
                else:
                    # Auto-generate sequence number if not provided
                    from sqlalchemy import func
                    result = await session.execute(
                        select(func.coalesce(func.max(ReviewItem.sequence_number), 0)).filter(
                            ReviewItem.deliverable_id == command.deliverable_id
                        )
                    )
                    max_sequence = result.scalar()
                    sequence_number = max_sequence + 1

                # Check for idempotency: Check by platform_file_id and sequence if available
                if command.platform_file_id:
                    existing_review_item_query = await session.execute(
                        select(ReviewItem).filter(
                            ReviewItem.deliverable_id == command.deliverable_id,
                            ReviewItem.platform_file_id == command.platform_file_id,
                            ReviewItem.sequence_number == sequence_number,
                        )
                    )
                else:
                    # Fallback to old idempotency check for backwards compatibility
                    existing_review_item_query = await session.execute(
                        select(ReviewItem).filter(
                            ReviewItem.deliverable_id == command.deliverable_id,
                            ReviewItem.item_type == ReviewItemType(command.review_item_type),
                            ReviewItem.review_round == review_round,
                        )
                    )
                
                if existing_review_item_query.scalar_one_or_none():
                    logger.warning(
                        f"Review item for deliverable {command.deliverable_id}, type {command.review_item_type}, "
                        f"file_id {command.platform_file_id}, sequence {sequence_number} already exists. Skipping creation. Idempotent."
                    )
                    return

                # Handle both string and enum deliverable_type
                deliverable_type_str = (
                    deliverable.deliverable_type.value 
                    if hasattr(deliverable.deliverable_type, 'value') 
                    else str(deliverable.deliverable_type)
                )
                
                new_review_item = ReviewItem(
                    project_id=command.project_id,
                    deliverable_id=command.deliverable_id,
                    source_internal_task_id=source_internal_task_id,
                    item_type=ReviewItemType(
                        command.review_item_type
                    ),  # Convert string to enum
                    platform_file_id=command.platform_file_id if command.platform_file_id else None,
                    item_url=command.item_url,  # Use item_url from command (deprecated in favor of file references)
                    description=f"Review for {deliverable_type_str} ({command.review_item_type}) - Round {review_round}",
                    sequence_number=sequence_number,
                    review_round=review_round,
                    review_status=ReviewStatus.PENDING_REVIEW.value,
                    presented_at=datetime.utcnow(),
                )
                session.add(new_review_item)
                await session.commit()
                await session.refresh(new_review_item)

                logger.info(
                    f"ReviewManagementService: Created new ReviewItem {new_review_item.id} for Deliverable {command.deliverable_id}, Round {review_round}."
                )

                # (Optional) Publish event that a review item was created
                # This could be consumed by a UI service to notify clients or update a dashboard
                # For now, orchestrator is already waiting for ClientFeedbackSubmittedEvent.

            except ValueError as ve:
                logger.error(
                    f"ReviewManagementService Error: Context entity not found or invalid type for command: {ve}"
                )
                # Publish a DeliverableFailedEvent or specific ReviewItemCreationFailedEvent
            except Exception as e:
                logger.error(
                    f"Error generating review item for Deliverable {command.deliverable_id}: {e}",
                    exc_info=True,
                )
                await session.rollback()
                # Publish a failure event, e.g., ReviewItemGenerationFailedEvent

    async def handle_client_feedback_submitted(
        self, event: ClientFeedbackSubmittedEvent
    ):
        """
        Handles ClientFeedbackSubmittedEvent. Processes the client's feedback
        and updates the ReviewItem status.
        """
        logger.info(
            f"ReviewManagementService: Received ClientFeedbackSubmittedEvent for ReviewItem {event.review_item_id}, Type: {event.feedback_type}"
        )

        async with self.db_session_factory() as session:
            try:
                review_item = await self._get_review_item_by_id(
                    session, event.review_item_id
                )
                if not review_item:
                    logger.error(
                        f"ReviewManagementService Error: ReviewItem {event.review_item_id} not found for feedback event. Skipping."
                    )
                    return

                # Check for idempotency: if this exact event was already processed
                # Skip this check since ClientFeedback doesn't have event_id field
                # existing_feedback_result = await session.execute(
                #     select(ClientFeedback).filter(
                #         ClientFeedback.event_id == event.event_id # Assuming event_id is stored if event is converted to feedback
                #     )
                # )
                # if existing_feedback_result.scalar_one_or_none():
                #     logger.warning(f"ClientFeedbackSubmittedEvent {event.event_id} already processed. Idempotent.")
                #     return

                # 1. Create a ClientFeedback record
                new_feedback = ClientFeedback(
                    project_id=event.project_id,
                    deliverable_id=event.deliverable_id,
                    review_item_id=event.review_item_id,
                    # client_user_id=event.client_user_id, # Field is commented out in model
                    feedback_type=FeedbackType(
                        event.feedback_type
                    ),  # Convert string to Enum
                    comment_text=event.comment_text,
                    timestamp_seconds=event.timestamp_seconds,
                    context_coordinates=event.context_coordinates,
                )
                session.add(new_feedback)
                await session.flush()  # Flush to get new_feedback.id if needed, but don't commit yet

                # 2. Update the ReviewItem's status based on feedback type
                old_review_status = review_item.review_status.value
                if event.feedback_type == FeedbackType.ACCEPT.value:
                    review_item.review_status = ReviewStatus.APPROVED.value
                elif event.feedback_type == FeedbackType.REJECT.value:
                    review_item.review_status = ReviewStatus.REJECTED.value
                elif event.feedback_type == FeedbackType.COMMENT.value:
                    review_item.review_status = ReviewStatus.NEEDS_REVISION.value
                elif event.feedback_type == FeedbackType.LIKE.value:
                    # 'Like' might not change review_status, or change to 'CLIENT_LIKED' if that's a status
                    pass
                session.add(review_item)  # Mark for update

                await session.commit()
                logger.info(
                    f"ReviewManagementService: Stored feedback {new_feedback.id} for ReviewItem {review_item.id}. ReviewItem status updated from {old_review_status} to {review_item.review_status.value}."
                )

                # 3. Publish specific outcome events for Orchestrator (Orchestrator might do this itself)
                # The DeliverableSagaOrchestrator directly listens to ClientFeedbackSubmittedEvent.
                # So, publishing ReviewItemApprovedEvent/RejectedEvent might be redundant if orchestrator processes ClientFeedbackSubmittedEvent fully.
                # It's better to let orchestrator decide if an "Approved" or "Rejected" event is needed,
                # as it has the full SAGA context. This service's primary job is to store feedback and update item status.

            except Exception as e:
                logger.error(
                    f"Error processing client feedback for ReviewItem {event.review_item_id}: {e}",
                    exc_info=True,
                )
                await session.rollback()
                # Consider publishing a failure event here if processing fails

    # Add methods for API endpoints to call to actually *receive* client feedback from frontend
    async def receive_client_feedback_via_api(
        self,
        project_id: UUID,
        deliverable_id: UUID,
        review_item_id: UUID,
        client_user_id: Optional[UUID],
        feedback_type: str,
        comment_text: Optional[str] = None,
        timestamp_seconds: Optional[int] = None,
        context_coordinates: Optional[Dict[str, Any]] = None,
    ):
        """
        Receives feedback from an API call, stores it, and publishes a ClientFeedbackSubmittedEvent.
        """
        # Create ClientFeedbackSubmittedEvent from raw API data
        event = ClientFeedbackSubmittedEvent(
            project_id=project_id,
            deliverable_id=deliverable_id,
            review_item_id=review_item_id,
            client_user_id=client_user_id,
            feedback_type=feedback_type,
            comment_text=comment_text,
            timestamp_seconds=timestamp_seconds,
            context_coordinates=context_coordinates,
        )

        # Publish the event to the Event Bus
        await self.event_bus.publish(
            topic="client.feedback.submitted", message=event.__dict__
        )  # Define this topic
        logger.info(
            f"ReviewManagementService: Published ClientFeedbackSubmittedEvent for ReviewItem {review_item_id} (Type: {feedback_type})."
        )
