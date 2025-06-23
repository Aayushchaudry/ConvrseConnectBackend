# src/api/review_items/controllers.py

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db_session  # Dependency for database session
from src.config.event_bus import get_event_bus  # Dependency for Event Bus
from src.events.event_bus_interface import EventBus  # Import the interface type
from src.models.client_feedback import FeedbackType  # Import FeedbackType enum
from src.models.review_item import (  # Import ReviewItem models and enums
    ReviewItem,
    ReviewItemType,
    ReviewStatus,
)
from src.services.review_management_service import (
    ReviewManagementService,
)  # Import your ReviewManagementService
from src.middleware.auth_middleware import require_auth, AuthContext  # Import auth middleware
from src.middleware.permissions_middleware import require_permission

logger = logging.getLogger(__name__)

# Create a FastAPI APIRouter instance
router = APIRouter(tags=["Review Items"])  # Tags for API documentation (Swagger UI)


# --- Pydantic Schema for Request Body (Client Feedback Submission) ---
class SubmitFeedbackRequest(BaseModel):
    """
    Schema for the request body when a client submits feedback on a ReviewItem.
    """

    client_user_id: Optional[UUID] = Field(
        None,
        description="ID of the client user submitting feedback (optional if anonymous)",
    )
    feedback_type: FeedbackType = Field(
        ..., description="Type of feedback (e.g., ACCEPT, REJECT, COMMENT, LIKE)"
    )
    comment_text: Optional[str] = Field(None, description="Detailed comment text")
    timestamp_seconds: Optional[int] = Field(
        None, ge=0, description="Timestamp in seconds for video/audio comments"
    )
    context_coordinates: Optional[Dict[str, Any]] = Field(
        None,
        description='JSONB for image/3D coordinates (e.g., {"x":100, "y":200, "w":50, "h":50})',
    )


# --- Pydantic Schema for Response Body (ReviewItem Details) ---
class ReviewItemResponse(BaseModel):
    """
    Schema for the response body when returning ReviewItem details.
    """

    id: UUID
    project_id: UUID
    deliverable_id: UUID
    source_internal_task_id: UUID
    item_type: ReviewItemType
    platform_file_id: Optional[UUID] = None  # Add platform_file_id field
    item_url: Optional[str] = None  # Make optional since it can be None when platform_file_id is used
    description: Optional[str]
    review_status: ReviewStatus
    sequence_number: Optional[int]
    review_round: Optional[int]
    presented_at: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True  # Pydantic V2 equivalent of orm_mode = True


# --- Pydantic Schema for Request Body (Creating ReviewItem) ---
class CreateReviewItemRequest(BaseModel):
    """
    Schema for the request body when creating a new review item.
    """

    project_id: UUID
    deliverable_id: UUID
    source_internal_task_id: UUID
    item_type: ReviewItemType
    platform_file_id: Optional[UUID] = None  # Optional file reference from platform-service
    item_url: Optional[str] = None  # Optional URL reference
    description: Optional[str] = None
    sequence_number: Optional[int] = None
    review_round: Optional[int] = 1


# --- Pydantic Schema for Request Body (Assigning Reviewer) ---
class AssignReviewerRequest(BaseModel):
    """
    Schema for the request body when assigning a reviewer.
    """

    reviewer_id: int


# --- Pydantic Schema for Request Body (Review Feedback) ---
class ReviewFeedbackRequest(BaseModel):
    """
    Schema for the request body when submitting review feedback.
    """

    status: str
    comments: Optional[str] = None
    rating: Optional[int] = Field(None, ge=1, le=5)


# --- API Endpoints ---


@router.post("/review_items/{review_item_id}/feedback", include_in_schema=True)
@router.post("/review_items/{review_item_id}/feedback/", include_in_schema=False)
async def submit_feedback_on_review_item(
    review_item_id: UUID,
    feedback_data: SubmitFeedbackRequest,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
):
    """
    Allows a client to submit feedback (accept, reject, comment, like) on a specific ReviewItem.
    Publishes a ClientFeedbackSubmittedEvent.
    """
    try:
        # First, fetch the ReviewItem to get project_id and deliverable_id
        from sqlalchemy import select

        result = await db_session.execute(
            select(ReviewItem).filter(ReviewItem.id == review_item_id)
        )
        review_item = result.scalar_one_or_none()

        if not review_item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Review item not found"
            )

        review_service = ReviewManagementService(
            db_session_factory=lambda: db_session, event_bus=event_bus
        )

        await review_service.receive_client_feedback_via_api(
            project_id=review_item.project_id,  # Get from ReviewItem
            deliverable_id=review_item.deliverable_id,  # Get from ReviewItem
            review_item_id=review_item_id,
            client_user_id=feedback_data.client_user_id,
            feedback_type=feedback_data.feedback_type.value,  # Pass enum value as string
            comment_text=feedback_data.comment_text,
            timestamp_seconds=feedback_data.timestamp_seconds,
            context_coordinates=feedback_data.context_coordinates,
        )
        return {"message": "Feedback submitted successfully. Processing initiated."}
    except HTTPException:
        raise  # Re-raise FastAPI HTTP exceptions
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid input: {str(ve)}"
        )
    except Exception as e:
        logger.error(
            f"Error submitting feedback for review item {review_item_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit feedback: {str(e)}",
        )


@router.get(
    "/projects/{project_id}/deliverables/{deliverable_id}/review_items/",
    response_model=List[ReviewItemResponse],
)
async def list_review_items_for_deliverable(
    project_id: UUID,
    deliverable_id: UUID,
    request: Request,
    auth_context: AuthContext = Depends(require_auth),
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(
        get_event_bus
    ),  # Event bus not directly used, but consistent pattern
):
    """
    Retrieves all review items for a specific deliverable.
    """
    review_service = ReviewManagementService(
        db_session_factory=lambda: db_session, event_bus=event_bus
    )
    from sqlalchemy import select

    from src.models.review_item import ReviewItem

    result = await db_session.execute(
        select(ReviewItem).filter(
            ReviewItem.project_id == project_id,
            ReviewItem.deliverable_id == deliverable_id,
        )
    )
    review_items = result.scalars().all()
    if not review_items:
        # Optionally raise 404 if no review items exist, or return empty list
        logger.info(
            f"No review items found for deliverable {deliverable_id} in project {project_id}"
        )
    return review_items


@router.get("/review_items/{review_item_id}", response_model=ReviewItemResponse)
async def get_review_item_details(
    review_item_id: UUID,
    request: Request,
    auth_context: AuthContext = Depends(require_auth),
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
):
    """
    Retrieves details of a specific review item by its ID.
    """
    review_service = ReviewManagementService(
        db_session_factory=lambda: db_session, event_bus=event_bus
    )
    from sqlalchemy import select

    from src.models.review_item import ReviewItem

    review_item = await db_session.execute(
        select(ReviewItem).filter(ReviewItem.id == review_item_id)
    ).scalar_one_or_none()

    if not review_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Review item not found"
        )
    return review_item


@router.post(
    "/review-items/",
    response_model=ReviewItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_review_item(
    review_data: CreateReviewItemRequest,
    request: Request,
    auth_context: AuthContext = Depends(require_auth),
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
):
    """
    Creates a new review item.
    """
    try:
        import uuid

        review_item = ReviewItem(
            id=uuid.uuid4(),
            project_id=review_data.project_id,
            deliverable_id=review_data.deliverable_id,
            source_internal_task_id=review_data.source_internal_task_id,
            item_type=review_data.item_type,
            item_url=review_data.item_url,
            description=review_data.description,
            review_status=ReviewStatus.PENDING_REVIEW,
            sequence_number=review_data.sequence_number,
            review_round=review_data.review_round,
            presented_at=datetime.utcnow(),
        )

        db_session.add(review_item)
        await db_session.commit()
        await db_session.refresh(review_item)

        return review_item

    except Exception as e:
        logger.error(f"Error creating review item: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create review item: {str(e)}",
        )


@router.patch("/review-items/{review_item_id}/assign", response_model=Dict)
async def assign_reviewer(
    review_item_id: UUID,
    assign_data: AssignReviewerRequest,
    request: Request,
    auth_context: AuthContext = Depends(require_auth),
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
):
    """
    Assigns a reviewer to a review item.
    """
    try:
        from sqlalchemy import select

        result = await db_session.execute(
            select(ReviewItem).filter(ReviewItem.id == review_item_id)
        )
        review_item = result.scalar_one_or_none()

        if not review_item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Review item not found"
            )

        # For now, just return the review item with a mock reviewer_id field
        response_data = ReviewItemResponse.model_validate(review_item)
        response_dict = response_data.model_dump()
        response_dict["reviewer_id"] = assign_data.reviewer_id

        return response_dict

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning reviewer: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assign reviewer: {str(e)}",
        )


@router.patch("/review-items/{review_item_id}/feedback", response_model=Dict)
async def submit_review_feedback(
    review_item_id: UUID,
    feedback_data: ReviewFeedbackRequest,
    request: Request,
    auth_context: AuthContext = Depends(require_auth),
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
):
    """
    Submits review feedback for a review item.
    """
    try:
        from sqlalchemy import select

        result = await db_session.execute(
            select(ReviewItem).filter(ReviewItem.id == review_item_id)
        )
        review_item = result.scalar_one_or_none()

        if not review_item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Review item not found"
            )

        # Update review status based on feedback
        if feedback_data.status == "approved":
            review_item.review_status = ReviewStatus.ACCEPTED
        elif feedback_data.status == "rejected":
            review_item.review_status = ReviewStatus.REJECTED

        await db_session.commit()

        return {
            "id": str(review_item.id),
            "status": feedback_data.status,
            "comments": feedback_data.comments,
            "rating": feedback_data.rating,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting feedback: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit feedback: {str(e)}",
        )
