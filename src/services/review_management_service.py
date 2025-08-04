# src/services/review_management_service.py

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, and_, func
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
from src.models.file_version import FileVersion, VersionType
from src.models.internal_task import InternalTask, TaskStatus, TaskType

# --- Import Models ---
from src.models.project import Project
from src.models.review_item import ReviewItem, ReviewItemType, ReviewStatus
from src.models.review_item_file import ReviewItemFile
from src.models.review_feedback import ReviewFeedback
from src.models.review_feedback_result import ReviewFeedbackResult

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

        deliverable = None
        if deliverable_id is not None:
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

        if not project:
            raise ValueError(f"Project {project_id} not found.")
        
        if deliverable_id is not None and not deliverable:
            raise ValueError(f"Deliverable {deliverable_id} not found.")

        return project, deliverable, internal_task

    async def _get_review_item_by_id(
        self, session: AsyncSession, review_item_id: UUID
    ) -> Optional[ReviewItem]:
        """Helper to fetch a review item by ID."""
        return await session.get(ReviewItem, review_item_id)

    async def create_review_items_from_task_completion(
        self,
        session: AsyncSession,
        task_id: UUID,
        platform_file_ids: List[UUID],
        file_metadata: List[Dict[str, Any]],
        review_item_type: ReviewItemType,
    ) -> List[ReviewItem]:
        """
        Create review items from completed task with file associations.
        
        Args:
            session: Database session
            task_id: ID of the completed task
            platform_file_ids: List of platform file IDs to associate
            file_metadata: List of metadata for each file (name, type, size)
            review_item_type: Type of review item to create
            
        Returns:
            List[ReviewItem]: Created review items
        """
        logger.info(f"Creating review items from task {task_id} with {len(platform_file_ids)} files")
        
        # Get the task and validate
        task_result = await session.execute(
            select(InternalTask).filter(InternalTask.id == task_id)
        )
        task = task_result.scalar_one_or_none()
        
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        if task.status != TaskStatus.DONE.value:
            raise ValueError(f"Task {task_id} is not completed (status: {task.status})")
        
        # Get project and deliverable context
        project_id = task.project_id
        deliverable_id = task.deliverable_id
        
        # Determine review round - check if there are existing review items for this task
        review_round_result = await session.execute(
            select(func.coalesce(func.max(ReviewItem.review_round), 0))
            .filter(
                ReviewItem.source_internal_task_id == task_id
            )
        )
        current_max_round = review_round_result.scalar()
        review_round = current_max_round + 1
        
        # Create a review item for each file
        created_review_items = []
        
        for idx, (platform_file_id, metadata) in enumerate(zip(platform_file_ids, file_metadata)):
            # Generate sequence number
            sequence_result = await session.execute(
                select(func.coalesce(func.max(ReviewItem.sequence_number), 0))
                .filter(
                    ReviewItem.deliverable_id == deliverable_id
                )
            )
            sequence_number = sequence_result.scalar() + 1
            
            # Create the review item
            review_item = ReviewItem(
                project_id=project_id,
                deliverable_id=deliverable_id,
                source_internal_task_id=task_id,
                item_type=review_item_type.value,
                platform_file_id=platform_file_id,  # Still store main file ID on review item for backward compatibility
                description=f"Review for {metadata.get('file_name', f'File {idx+1}')} - Round {review_round}",
                sequence_number=sequence_number,
                review_round=review_round,
                review_status=ReviewStatus.PENDING_REVIEW.value,
                presented_at=datetime.utcnow(),
            )
            session.add(review_item)
            await session.flush()  # Flush to get the ID
            
            # Create the review item file association
            review_item_file = ReviewItemFile(
                review_item_id=review_item.id,
                platform_file_id=platform_file_id,
                file_name=metadata.get('file_name', f'file_{idx+1}'),
                file_type=metadata.get('file_type'),
                file_size=metadata.get('file_size'),
                sequence_order=idx + 1
            )
            session.add(review_item_file)
            
            # Create initial file version
            file_version = FileVersion(
                original_file_id=platform_file_id,
                current_file_id=platform_file_id,
                version_number=1,
                version_type=VersionType.INITIAL.value,
                version_notes=f"Initial version from task {task_id}",
                created_by=task.assigned_to,
                is_final=False,
                is_active=True
            )
            session.add(file_version)
            
            created_review_items.append(review_item)
        
        await session.commit()
        logger.info(f"Created {len(created_review_items)} review items with file associations")
        
        return created_review_items

    async def handle_generate_review_item_command(
        self, command: GenerateReviewItemCommand
    ):
        """
        Handles GenerateReviewItemCommand. Creates a new ReviewItem for a deliverable.
        Enhanced to support rework tasks with proper review round incrementing.
        """
        logger.info(
            f"ReviewManagementService: Received GenerateReviewItemCommand for Deliverable {command.deliverable_id}, Type: {command.review_item_type}"
        )

        async with self.db_session_factory() as session:
            try:
                project, deliverable, internal_task = await self._get_context_entities(
                    session, command.project_id, command.deliverable_id
                )

                # Skip review item creation for project-level tasks without deliverable_id
                if command.deliverable_id is None:
                    logger.info(
                        f"ReviewManagementService: Skipping review item creation for project-level task without deliverable_id. Project: {command.project_id}"
                    )
                    return

                # Find the most recent completed task for this deliverable
                recent_task_query = await session.execute(
                    select(InternalTask)
                    .filter(
                        InternalTask.deliverable_id == command.deliverable_id,
                        InternalTask.status == "DONE",
                    )
                    .order_by(InternalTask.updated_at.desc())
                    .limit(1)
                )
                recent_task = recent_task_query.scalar_one_or_none()
                source_internal_task_id = recent_task.id if recent_task else None

                # Check if this is a rework task by looking at the parent_task_id
                is_rework_task = False
                if recent_task and recent_task.parent_task_id:
                    is_rework_task = True
                    logger.info(f"Detected rework task {recent_task.id} with parent {recent_task.parent_task_id}")

                # Determine review round based on task type
                if is_rework_task:
                    # For rework tasks, find the original task and increment review round
                    original_task_id = recent_task.parent_task_id
                    
                    # Get the maximum review round for the original task
                    review_round_result = await session.execute(
                        select(func.coalesce(func.max(ReviewItem.review_round), 0))
                        .filter(
                            ReviewItem.source_internal_task_id == original_task_id
                        )
                    )
                    current_max_round = review_round_result.scalar()
                    review_round = current_max_round + 1
                    
                    logger.info(f"Rework task: Original task {original_task_id}, current max round: {current_max_round}, new round: {review_round}")
                else:
                    # For regular tasks, start with round 1
                    review_round = 1
                    logger.info(f"Regular task: Starting with review round {review_round}")

                # Use sequence_number from command or auto-generate
                if command.sequence_number is not None:
                    sequence_number = command.sequence_number
                else:
                    # Auto-generate sequence number if not provided
                    result = await session.execute(
                        select(func.coalesce(func.max(ReviewItem.sequence_number), 0)).filter(
                            ReviewItem.deliverable_id == command.deliverable_id
                        )
                    )
                    max_sequence = result.scalar()
                    sequence_number = max_sequence + 1

                # Check for idempotency: Different logic for rework vs regular tasks
                existing_review_item = None
                if is_rework_task:
                    # For rework tasks, check if a review item already exists for this specific task and review round
                    existing_review_item_query = await session.execute(
                        select(ReviewItem).filter(
                            ReviewItem.deliverable_id == command.deliverable_id,
                            ReviewItem.source_internal_task_id == recent_task.id,
                            ReviewItem.review_round == review_round,
                        )
                    )
                    existing_review_item = existing_review_item_query.scalar_one_or_none()
                else:
                    # For regular tasks, check by platform_file_id and sequence if available
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
                    existing_review_item = existing_review_item_query.scalar_one_or_none()
                
                if existing_review_item:
                    logger.warning(
                        f"Review item for deliverable {command.deliverable_id}, type {command.review_item_type}, "
                        f"file_id {command.platform_file_id}, sequence {sequence_number}, round {review_round} already exists. Skipping creation. Idempotent."
                    )
                    return

                # Handle both string and enum deliverable_type, with None check
                if deliverable and deliverable.deliverable_type:
                    deliverable_type_str = (
                        deliverable.deliverable_type.value 
                        if hasattr(deliverable.deliverable_type, 'value') 
                        else str(deliverable.deliverable_type)
                    )
                else:
                    # For project-level tasks without a specific deliverable
                    deliverable_type_str = "PROJECT_TASK"
                
                # Set the source task ID to the actual task that generated this review item
                actual_source_task_id = recent_task.id if recent_task else source_internal_task_id
                
                new_review_item = ReviewItem(
                    project_id=command.project_id,
                    deliverable_id=command.deliverable_id,
                    source_internal_task_id=actual_source_task_id,
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
                    f"ReviewManagementService: Created new ReviewItem {new_review_item.id} for Deliverable {command.deliverable_id}, "
                    f"Round {review_round}, Task {actual_source_task_id}, {'Rework' if is_rework_task else 'Regular'} task."
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
                    
                    # Create rework task if rejected
                    await self._create_rework_task_from_feedback(
                        session=session,
                        review_item=review_item,
                        feedback=new_feedback
                    )
                elif event.feedback_type == FeedbackType.COMMENT.value:
                    review_item.review_status = ReviewStatus.NEEDS_REVISION.value
                    
                    # Create rework task for revision needed
                    await self._create_rework_task_from_feedback(
                        session=session,
                        review_item=review_item,
                        feedback=new_feedback
                    )
                elif event.feedback_type == FeedbackType.LIKE.value:
                    review_item.review_status = ReviewStatus.LIKED.value
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

    async def _create_rework_task_from_feedback(
        self,
        session: AsyncSession,
        review_item: ReviewItem,
        feedback: ClientFeedback
    ) -> Optional[InternalTask]:
        """
        Create a rework task based on feedback for a rejected or revision-needed review item.
        
        Args:
            session: Database session
            review_item: The review item that received feedback
            feedback: The client feedback
            
        Returns:
            Optional[InternalTask]: The created rework task, if any
        """
        logger.info(f"Creating rework task for review item {review_item.id} based on feedback")
        
        try:
            # Get the original task that produced this review item
            if not review_item.source_internal_task_id:
                logger.warning(f"Review item {review_item.id} has no source task, cannot create rework task")
                return None
                
            source_task_result = await session.execute(
                select(InternalTask).filter(InternalTask.id == review_item.source_internal_task_id)
            )
            source_task = source_task_result.scalar_one_or_none()
            
            if not source_task:
                logger.warning(f"Source task {review_item.source_internal_task_id} not found for review item {review_item.id}")
                return None
            
            # Create a rework task with the original task as parent
            rework_task = InternalTask(
                project_id=review_item.project_id,
                deliverable_id=review_item.deliverable_id,
                parent_task_id=source_task.id,
                task_name=f"Rework: {source_task.task_name}",
                task_type=source_task.task_type,  # Same type as original
                description=f"Rework required based on feedback: {feedback.comment_text or 'No specific comments provided'}",
                status=TaskStatus.TODO.value,
                priority=source_task.priority,  # Same priority
                estimated_hours=source_task.estimated_hours / 2 if source_task.estimated_hours else None,  # Half the original estimate
                tentative_end_date=datetime.utcnow(),  # Due immediately
                start_date=datetime.utcnow()  # Start immediately
            )
            
            session.add(rework_task)
            await session.flush()
            
            # Link the feedback to the generated task
            feedback.generated_task_id = rework_task.id
            session.add(feedback)
            
            logger.info(f"Created rework task {rework_task.id} for review item {review_item.id}")
            return rework_task
            
        except Exception as e:
            logger.error(f"Error creating rework task for review item {review_item.id}: {e}", exc_info=True)
            return None

    async def submit_review_feedback(
        self,
        review_item_id: UUID,
        feedback_type: str,
        comment_text: Optional[str] = None,
        timestamp_seconds: Optional[int] = None,
        coordinates: Optional[Dict[str, Any]] = None,
        submitted_by: Optional[UUID] = None,
        new_platform_file_id: Optional[UUID] = None
    ) -> ReviewFeedbackResult:
        """
        Submit feedback for a review item with enhanced support for coordinates and timestamps.
        
        Args:
            review_item_id: ID of the review item
            feedback_type: Type of feedback (ACCEPT, REJECT, COMMENT)
            comment_text: Optional comment text
            timestamp_seconds: Optional timestamp for video/audio feedback
            coordinates: Optional coordinates for image annotations
            submitted_by: ID of the user submitting feedback
            new_platform_file_id: Optional new file ID for versioning
            
        Returns:
            ReviewFeedbackResult: Result of the feedback submission
        """
        logger.info(f"Submitting review feedback for item {review_item_id} with type {feedback_type}")
        
        async with self.db_session_factory() as session:
            try:
                # Get the review item
                review_item = await self._get_review_item_by_id(session, review_item_id)
                if not review_item:
                    raise ValueError(f"Review item {review_item_id} not found")
                
                # Create enhanced feedback record
                feedback = ReviewFeedback(
                    review_item_id=review_item_id,
                    feedback_type=feedback_type,
                    comment_text=comment_text,
                    timestamp_seconds=timestamp_seconds,
                    coordinates=coordinates,
                    submitted_by=submitted_by,
                    submitted_at=datetime.utcnow()
                )
                session.add(feedback)
                await session.flush()  # Get the ID without committing
                
                # Update review item status
                old_status = review_item.review_status
                task_generated = False
                generated_task_id = None
                
                if feedback_type == FeedbackType.ACCEPT.value:
                    review_item.review_status = ReviewStatus.APPROVED.value
                    
                    # Mark files as final versions
                    await self._mark_files_as_final(session, review_item)
                    
                    # Progress deliverable if all review items are approved
                    await self._check_and_progress_deliverable(session, review_item.deliverable_id)
                    
                elif feedback_type in (FeedbackType.REJECT.value, FeedbackType.COMMENT.value):
                    review_item.review_status = (
                        ReviewStatus.REJECTED.value if feedback_type == FeedbackType.REJECT.value
                        else ReviewStatus.NEEDS_REVISION.value
                    )
                    
                    # Create rework task
                    rework_task = await self._create_rework_task_from_feedback(
                        session=session,
                        review_item=review_item,
                        feedback=feedback
                    )
                    
                    if rework_task:
                        task_generated = True
                        generated_task_id = rework_task.id
                        feedback.generated_task_id = rework_task.id
                        session.add(feedback)
                    
                    # Handle file versioning if a new file is provided
                    if new_platform_file_id:
                        await self._create_file_version_from_feedback(
                            session=session,
                            review_item=review_item,
                            new_platform_file_id=new_platform_file_id,
                            feedback=feedback
                        )
                
                elif feedback_type == FeedbackType.LIKE.value:
                    review_item.review_status = ReviewStatus.LIKED.value
                
                session.add(review_item)
                await session.commit()
                
                # Create and return result
                result = ReviewFeedbackResult(
                    feedback_id=feedback.id,
                    review_item_id=review_item_id,
                    feedback_type=feedback_type,
                    review_status=review_item.review_status,
                    submitted_at=feedback.submitted_at,
                    comment_text=comment_text,
                    timestamp_seconds=timestamp_seconds,
                    coordinates=coordinates,
                    task_generated=task_generated,
                    generated_task_id=generated_task_id
                )
                
                # Publish event if event bus is available
                if self.event_bus:
                    if feedback_type == FeedbackType.ACCEPT.value:
                        await self.event_bus.publish(
                            topic="review.item.approved",
                            message={
                                "review_item_id": str(review_item_id),
                                "deliverable_id": str(review_item.deliverable_id),
                                "project_id": str(review_item.project_id),
                                "feedback_id": str(feedback.id)
                            }
                        )
                    elif feedback_type == FeedbackType.REJECT.value:
                        await self.event_bus.publish(
                            topic="review.item.rejected",
                            message={
                                "review_item_id": str(review_item_id),
                                "deliverable_id": str(review_item.deliverable_id),
                                "project_id": str(review_item.project_id),
                                "feedback_id": str(feedback.id),
                                "generated_task_id": str(generated_task_id) if generated_task_id else None
                            }
                        )
                
                return result
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Error submitting review feedback: {e}", exc_info=True)
                raise
    
    async def _mark_files_as_final(self, session: AsyncSession, review_item: ReviewItem) -> None:
        """
        Mark all files associated with a review item as final versions.
        
        Args:
            session: Database session
            review_item: The review item with approved files
        """
        try:
            # Get all files associated with the review item
            files_result = await session.execute(
                select(ReviewItemFile)
                .filter(ReviewItemFile.review_item_id == review_item.id)
            )
            files = files_result.scalars().all()
            
            for file in files:
                # Get the latest version of each file
                latest_version_result = await session.execute(
                    select(FileVersion)
                    .filter(
                        FileVersion.original_file_id == file.platform_file_id,
                        FileVersion.is_active == True
                    )
                    .order_by(FileVersion.version_number.desc())
                    .limit(1)
                )
                latest_version = latest_version_result.scalar_one_or_none()
                
                if latest_version:
                    latest_version.is_final = True
                    latest_version.version_type = VersionType.FINAL.value
                    session.add(latest_version)
        
        except Exception as e:
            logger.error(f"Error marking files as final: {e}", exc_info=True)
            raise
    
    async def _check_and_progress_deliverable(self, session: AsyncSession, deliverable_id: UUID) -> bool:
        """
        Check if all review items for a deliverable are approved and progress the deliverable if so.
        
        Args:
            session: Database session
            deliverable_id: ID of the deliverable to check
            
        Returns:
            bool: True if deliverable was progressed, False otherwise
        """
        try:
            # Count total review items for this deliverable
            total_count_result = await session.execute(
                select(func.count())
                .filter(ReviewItem.deliverable_id == deliverable_id)
            )
            total_count = total_count_result.scalar()
            
            # Count approved review items
            approved_count_result = await session.execute(
                select(func.count())
                .filter(
                    ReviewItem.deliverable_id == deliverable_id,
                    ReviewItem.review_status == ReviewStatus.APPROVED.value
                )
            )
            approved_count = approved_count_result.scalar()
            
            # If all review items are approved, progress the deliverable
            if total_count > 0 and total_count == approved_count:
                # Get the deliverable
                deliverable_result = await session.execute(
                    select(Deliverable)
                    .filter(Deliverable.id == deliverable_id)
                )
                deliverable = deliverable_result.scalar_one_or_none()
                
                if deliverable:
                    # Update deliverable status - this is simplified and would be handled by the orchestrator
                    # in a real implementation with proper state transitions
                    if deliverable.status == "IN_REVIEW":
                        deliverable.status = "APPROVED"
                        session.add(deliverable)
                        
                        # Publish event if event bus is available
                        if self.event_bus:
                            await self.event_bus.publish(
                                topic="deliverable.approved",
                                message={
                                    "deliverable_id": str(deliverable_id),
                                    "project_id": str(deliverable.project_id)
                                }
                            )
                        
                        return True
            
            return False
                
        except Exception as e:
            logger.error(f"Error checking and progressing deliverable: {e}", exc_info=True)
            return False
    
    async def _create_file_version_from_feedback(
        self,
        session: AsyncSession,
        review_item: ReviewItem,
        new_platform_file_id: UUID,
        feedback: ReviewFeedback
    ) -> Optional[FileVersion]:
        """
        Create a new file version based on feedback.
        
        Args:
            session: Database session
            review_item: The review item
            new_platform_file_id: ID of the new file version
            feedback: The feedback that prompted the new version
            
        Returns:
            Optional[FileVersion]: The created file version, if any
        """
        try:
            # Get the review item files
            files_result = await session.execute(
                select(ReviewItemFile)
                .filter(ReviewItemFile.review_item_id == review_item.id)
                .order_by(ReviewItemFile.sequence_order)
                .limit(1)  # Just get the first file for now
            )
            file = files_result.scalar_one_or_none()
            
            if not file:
                logger.warning(f"No files found for review item {review_item.id}")
                return None
            
            # Get the current highest version number
            version_result = await session.execute(
                select(func.coalesce(func.max(FileVersion.version_number), 0))
                .filter(FileVersion.original_file_id == file.platform_file_id)
            )
            current_version = version_result.scalar()
            
            # Create new version
            new_version = FileVersion(
                original_file_id=file.platform_file_id,
                current_file_id=new_platform_file_id,
                version_number=current_version + 1,
                version_type=VersionType.REVISION.value,
                version_notes=f"Revision based on feedback: {feedback.comment_text or 'No comments'}",
                created_by=feedback.submitted_by,
                is_final=False,
                is_active=True
            )
            
            session.add(new_version)
            return new_version
            
        except Exception as e:
            logger.error(f"Error creating file version from feedback: {e}", exc_info=True)
            return None
    
    async def process_review_feedback_with_file_versioning(
        self,
        review_item_id: UUID,
        feedback_type: str,
        comment_text: Optional[str] = None,
        new_platform_file_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None
    ) -> Tuple[ReviewItem, Optional[FileVersion]]:
        """
        Process review feedback with file versioning support.
        
        Args:
            review_item_id: ID of the review item
            feedback_type: Type of feedback (ACCEPT, REJECT, COMMENT)
            comment_text: Optional comment text
            new_platform_file_id: Optional new file ID for versioning
            user_id: ID of the user submitting feedback
            
        Returns:
            Tuple[ReviewItem, Optional[FileVersion]]: Updated review item and new file version if created
        """
        logger.info(f"Processing review feedback for item {review_item_id} with type {feedback_type}")
        
        async with self.db_session_factory() as session:
            try:
                # Get the review item
                review_item = await self._get_review_item_by_id(session, review_item_id)
                if not review_item:
                    raise ValueError(f"Review item {review_item_id} not found")
                
                # Create feedback record
                feedback = ClientFeedback(
                    project_id=review_item.project_id,
                    deliverable_id=review_item.deliverable_id,
                    review_item_id=review_item_id,
                    feedback_type=feedback_type,
                    comment_text=comment_text,
                    submitted_at=datetime.utcnow()
                )
                session.add(feedback)
                
                # Update review item status
                if feedback_type == FeedbackType.ACCEPT.value:
                    review_item.review_status = ReviewStatus.APPROVED.value
                    
                    # If there's a file, mark it as final version
                    if review_item.platform_file_id:
                        # Get the latest version
                        latest_version_result = await session.execute(
                            select(FileVersion)
                            .filter(
                                FileVersion.original_file_id == review_item.platform_file_id,
                                FileVersion.is_active == True
                            )
                            .order_by(FileVersion.version_number.desc())
                            .limit(1)
                        )
                        latest_version = latest_version_result.scalar_one_or_none()
                        
                        if latest_version:
                            latest_version.is_final = True
                            latest_version.version_type = VersionType.FINAL.value
                            session.add(latest_version)
                
                elif feedback_type in (FeedbackType.REJECT.value, FeedbackType.COMMENT.value):
                    review_item.review_status = (
                        ReviewStatus.REJECTED.value if feedback_type == FeedbackType.REJECT.value
                        else ReviewStatus.NEEDS_REVISION.value
                    )
                    
                    # Create rework task
                    rework_task = await self._create_rework_task_from_feedback(
                        session=session,
                        review_item=review_item,
                        feedback=feedback
                    )
                    
                    # If a new file version is provided, create version record
                    new_version = None
                    if new_platform_file_id and review_item.platform_file_id:
                        new_version = FileVersion(
                            original_file_id=review_item.platform_file_id,
                            current_file_id=new_platform_file_id,
                            version_type=VersionType.REVISION.value,
                            version_notes=f"Revision based on feedback: {comment_text or 'No comments'}",
                            created_by=user_id
                        )
                        
                        # Get the current highest version number
                        version_result = await session.execute(
                            select(FileVersion.version_number)
                            .filter(FileVersion.original_file_id == review_item.platform_file_id)
                            .order_by(FileVersion.version_number.desc())
                            .limit(1)
                        )
                        current_version = version_result.scalar_one_or_none() or 0
                        new_version.version_number = current_version + 1
                        
                        session.add(new_version)
                
                session.add(review_item)
                await session.commit()
                
                # Return the updated review item and new version if created
                return review_item, new_version if 'new_version' in locals() else None
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Error processing review feedback: {e}", exc_info=True)
                raise

    # Add methods for API endpoints to call to actually *receive* client feedback from frontend
    async def update_review_item_status(
        self,
        review_item_id: UUID,
        status: str,
        user_id: Optional[UUID] = None,
        comment: Optional[str] = None
    ) -> ReviewItem:
        """
        Update the status of a review item directly.
        
        Args:
            review_item_id: ID of the review item
            status: New status for the review item
            user_id: ID of the user making the update
            comment: Optional comment about the status change
            
        Returns:
            ReviewItem: The updated review item
        """
        logger.info(f"Updating status of review item {review_item_id} to {status}")
        
        async with self.db_session_factory() as session:
            try:
                # Get the review item
                review_item = await self._get_review_item_by_id(session, review_item_id)
                if not review_item:
                    raise ValueError(f"Review item {review_item_id} not found")
                
                # Validate the status
                try:
                    new_status = ReviewStatus(status)
                except ValueError:
                    raise ValueError(f"Invalid review status: {status}")
                
                # Update the status
                old_status = review_item.review_status
                review_item.review_status = new_status.value
                
                # Create a feedback entry to record the status change
                feedback = ReviewFeedback(
                    review_item_id=review_item_id,
                    feedback_type=FeedbackType.COMMENT.value,  # Use COMMENT type for status updates
                    comment_text=f"Status changed from {old_status} to {new_status.value}" + 
                                (f": {comment}" if comment else ""),
                    submitted_by=user_id,
                    submitted_at=datetime.utcnow()
                )
                session.add(feedback)
                
                # If status is APPROVED, check if we need to progress the deliverable
                if new_status == ReviewStatus.APPROVED:
                    await self._mark_files_as_final(session, review_item)
                    await self._check_and_progress_deliverable(session, review_item.deliverable_id)
                
                # If status is REJECTED or NEEDS_REVISION, create a rework task
                elif new_status in (ReviewStatus.REJECTED, ReviewStatus.NEEDS_REVISION):
                    rework_task = await self._create_rework_task_from_feedback(
                        session=session,
                        review_item=review_item,
                        feedback=feedback
                    )
                    
                    if rework_task:
                        feedback.generated_task_id = rework_task.id
                        session.add(feedback)
                
                session.add(review_item)
                await session.commit()
                
                # Publish event if event bus is available
                if self.event_bus:
                    await self.event_bus.publish(
                        topic="review.item.status.updated",
                        message={
                            "review_item_id": str(review_item_id),
                            "old_status": old_status,
                            "new_status": new_status.value,
                            "updated_by": str(user_id) if user_id else None
                        }
                    )
                
                return review_item
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Error updating review item status: {e}", exc_info=True)
                raise
    
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

    async def get_review_feedback_history(
        self,
        review_item_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        Get feedback history for a review item.
        
        Args:
            review_item_id: ID of the review item
            
        Returns:
            List[Dict[str, Any]]: List of feedback entries with details
        """
        logger.info(f"Getting feedback history for review item {review_item_id}")
        
        async with self.db_session_factory() as session:
            try:
                # Get the review feedback entries
                feedback_result = await session.execute(
                    select(ReviewFeedback)
                    .filter(ReviewFeedback.review_item_id == review_item_id)
                    .order_by(ReviewFeedback.submitted_at.desc())
                )
                feedback_entries = feedback_result.scalars().all()
                
                result = []
                for feedback in feedback_entries:
                    # Get task details if a task was generated
                    task_details = None
                    if feedback.generated_task_id:
                        task_result = await session.execute(
                            select(InternalTask)
                            .filter(InternalTask.id == feedback.generated_task_id)
                        )
                        task = task_result.scalar_one_or_none()
                        if task:
                            task_details = {
                                "task_id": str(task.id),
                                "task_name": task.task_name,
                                "status": task.status,
                                "tentative_end_date": task.tentative_end_date.isoformat() if task.tentative_end_date else None
                            }
                    
                    # Format the feedback entry
                    feedback_entry = {
                        "id": str(feedback.id),
                        "feedback_type": feedback.feedback_type.value,
                        "comment_text": feedback.comment_text,
                        "timestamp_seconds": feedback.timestamp_seconds,
                        "coordinates": feedback.coordinates,
                        "submitted_by": str(feedback.submitted_by) if feedback.submitted_by else None,
                        "submitted_at": feedback.submitted_at.isoformat(),
                        "generated_task": task_details
                    }
                    result.append(feedback_entry)
                
                return result
                
            except Exception as e:
                logger.error(f"Error getting feedback history: {e}", exc_info=True)
                raise
    
    async def get_review_item_files(
        self,
        review_item_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        Get all files associated with a review item, including version information.
        
        Args:
            review_item_id: ID of the review item
            
        Returns:
            List[Dict[str, Any]]: List of files with their metadata and version info
        """
        logger.info(f"Getting files for review item {review_item_id}")
        
        async with self.db_session_factory() as session:
            try:
                # Get the review item files
                files_result = await session.execute(
                    select(ReviewItemFile)
                    .filter(ReviewItemFile.review_item_id == review_item_id)
                    .order_by(ReviewItemFile.sequence_order)
                )
                files = files_result.scalars().all()
                
                if not files:
                    logger.info(f"No files found for review item {review_item_id}")
                    return []
                
                # Get version information for each file
                result_files = []
                for file in files:
                    # Get version history for this file
                    versions_result = await session.execute(
                        select(FileVersion)
                        .filter(FileVersion.original_file_id == file.platform_file_id)
                        .order_by(FileVersion.version_number)
                    )
                    versions = versions_result.scalars().all()
                    
                    # Get latest version
                    latest_version = None
                    if versions:
                        latest_version = max(versions, key=lambda v: v.version_number)
                    
                    # Build version info
                    version_info = {
                        "has_versions": len(versions) > 0,
                        "current_version": latest_version.version_number if latest_version else 1,
                        "is_final": latest_version.is_final if latest_version else False,
                        "version_count": len(versions),
                        "latest_version_id": str(latest_version.id) if latest_version else None,
                        "latest_file_id": str(latest_version.current_file_id) if latest_version else str(file.platform_file_id)
                    }
                    
                    # Build file info with version data
                    file_info = {
                        "id": str(file.id),
                        "review_item_id": str(file.review_item_id),
                        "platform_file_id": str(file.platform_file_id),
                        "file_name": file.file_name,
                        "file_type": file.file_type,
                        "file_size": file.file_size,
                        "sequence_order": file.sequence_order,
                        "created_at": file.created_at.isoformat() if file.created_at else None,
                        "version_info": version_info
                    }
                    
                    result_files.append(file_info)
                
                logger.info(f"Returning {len(result_files)} files for review item {review_item_id}")
                return result_files
                
            except Exception as e:
                logger.error(f"Error getting review item files: {e}", exc_info=True)
                raise
                
                # Get version information for each file
                result_files = []
                for file in files:
                    # Get latest version
                    version_result = await session.execute(
                        select(FileVersion)
                        .filter(
                            FileVersion.original_file_id == file.platform_file_id,
                            FileVersion.is_active == True
                        )
                        .order_by(FileVersion.version_number.desc())
                        .limit(1)
                    )
                    latest_version = version_result.scalar_one_or_none()
                    
                    # Get version count
                    version_count_result = await session.execute(
                        select(func.count(FileVersion.id))
                        .filter(
                            FileVersion.original_file_id == file.platform_file_id,
                            FileVersion.is_active == True
                        )
                    )
                    version_count = version_count_result.scalar() or 1
                    
                    file_data = {
                        "id": str(file.id),
                        "review_item_id": str(file.review_item_id),
                        "platform_file_id": str(file.platform_file_id),
                        "file_name": file.file_name,
                        "file_type": file.file_type,
                        "file_size": file.file_size,
                        "sequence_order": file.sequence_order,
                        "created_at": file.created_at.isoformat() if file.created_at else None,
                        "version_info": {
                            "current_version": latest_version.version_number if latest_version else 1,
                            "is_final": latest_version.is_final if latest_version else False,
                            "version_count": version_count,
                            "latest_version_id": str(latest_version.id) if latest_version else None,
                            "latest_file_id": str(latest_version.current_file_id) if latest_version else str(file.platform_file_id)
                        }
                    }
                    result_files.append(file_data)
                
                logger.info(f"Found {len(result_files)} files for review item {review_item_id}")
                return result_files
                
            except Exception as e:
                logger.error(f"Error getting review item files: {e}", exc_info=True)
                raise