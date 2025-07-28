# src/api/review_items/controllers.py

import logging
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db_session
from src.middleware.auth_middleware import get_required_auth_dependency
from src.models.client_feedback import FeedbackType
from src.models.review_feedback_result import ReviewFeedbackResult
from src.models.review_item import ReviewItemType, ReviewStatus, ReviewItem
from src.models.review_feedback import ReviewFeedback
from src.services.file_upload_integration_service import FileUploadIntegrationService
from src.services.file_version_service import FileVersionService
from src.services.review_management_service import ReviewManagementService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["review-items"])


class ReviewItemFileResponse(BaseModel):
    """Response model for review item file."""
    id: str
    review_item_id: str
    platform_file_id: str
    file_name: str
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    sequence_order: int
    created_at: Optional[str] = None
    version_info: Dict


class ReviewFeedbackRequest(BaseModel):
    """Request model for submitting review feedback."""
    feedback_type: str = Field(..., description="Type of feedback (ACCEPT, REJECT, COMMENT)")
    comment_text: Optional[str] = Field(None, description="Optional comment text")
    timestamp_seconds: Optional[int] = Field(None, description="Timestamp for video/audio feedback")
    coordinates: Optional[Dict] = Field(None, description="Coordinates for image annotations")
    new_platform_file_id: Optional[str] = Field(None, description="Optional ID of a new file version")


class ReviewStatusUpdateRequest(BaseModel):
    """Request model for updating review item status."""
    status: str = Field(..., description="New status for the review item")
    comment: Optional[str] = Field(None, description="Optional comment about the status change")


class TaskCompletionWithFilesRequest(BaseModel):
    """Request model for completing a task with files."""
    task_id: UUID = Field(..., description="ID of the task being completed")
    review_item_type: str = Field(..., description="Type of review item to create")
    notes: Optional[str] = Field(None, description="Optional notes about the completion")


@router.post(
    "/internal-tasks/{task_id}/complete-with-files",
    status_code=status.HTTP_201_CREATED,
    response_model=List[Dict],
)
async def complete_task_with_files(
    task_id: UUID,
    review_item_type: str = Form(...),
    notes: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    current_user=Depends(get_required_auth_dependency()),
    db_session=Depends(get_db_session),
):
    """
    Complete an internal task and create review items with uploaded files.
    
    This endpoint:
    1. Uploads the files to the platform file service
    2. Creates review items for the completed task
    3. Associates the files with the review items
    4. Returns the created review items with file information
    """
    logger.info(f"Completing task {task_id} with {len(files)} files")
    
    try:
        # Validate review item type
        try:
            review_item_type_enum = ReviewItemType(review_item_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid review item type: {review_item_type}. Valid types: {[t.value for t in ReviewItemType]}"
            )
        
        # Initialize services
        file_upload_service = FileUploadIntegrationService(db_session)
        review_service = ReviewManagementService(lambda: db_session, None)  # Event bus not needed for direct API calls
        
        # Upload files to platform service
        review_item_metadata = {
            "task_id": str(task_id),
            "review_item_type": review_item_type,
            "notes": notes,
            "user_id": str(current_user.user_id) if current_user and current_user.user_id else None
        }
        
        upload_result = await file_upload_service.upload_review_item_files(
            task_id=task_id,
            files=files,
            metadata=review_item_metadata
        )
        
        if not upload_result.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File upload failed: {upload_result.error_message}"
            )
        
        # Create review items with file associations
        review_items = await review_service.create_review_items_from_task_completion(
            session=db_session,
            task_id=task_id,
            platform_file_ids=upload_result.platform_file_ids,
            file_metadata=upload_result.file_metadata,
            review_item_type=review_item_type_enum
        )
        
        # Return review items with file information
        result = []
        for review_item in review_items:
            files = await review_service.get_review_item_files(review_item.id)
            result.append({
                "review_item_id": str(review_item.id),
                "review_status": review_item.review_status,
                "review_round": review_item.review_round,
                "files": files
            })
        
        return result
        
    except ValueError as ve:
        logger.error(f"Validation error: {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        logger.error(f"Error completing task with files: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your request"
        )


@router.get(
    "/review-items/{review_item_id}/files",
    response_model=List[ReviewItemFileResponse],
)
async def get_review_item_files(
    review_item_id: UUID,
    current_user=Depends(get_required_auth_dependency()),
    db_session=Depends(get_db_session),
):
    """
    Get all files associated with a review item, including version information.
    """
    logger.info(f"Getting files for review item {review_item_id}")
    
    try:
        review_service = ReviewManagementService(lambda: db_session, None)
        files = await review_service.get_review_item_files(review_item_id)
        
        return files
        
    except Exception as e:
        logger.error(f"Error getting review item files: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving review item files"
        )


@router.post(
    "/review-items/{review_item_id}/feedback",
    response_model=ReviewFeedbackResult,
    status_code=status.HTTP_201_CREATED,
)
async def submit_review_feedback(
    review_item_id: UUID,
    feedback: ReviewFeedbackRequest,
    current_user=Depends(get_required_auth_dependency()),
    db_session=Depends(get_db_session),
):
    """
    Submit feedback for a review item.
    
    This endpoint:
    1. Creates a feedback record with the provided details
    2. Updates the review item status based on the feedback type
    3. Creates rework tasks automatically for rejected items
    4. Returns the result of the feedback submission
    """
    logger.info(f"Submitting feedback for review item {review_item_id}")
    
    try:
        # Validate feedback type
        try:
            feedback_type = FeedbackType(feedback.feedback_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid feedback type: {feedback.feedback_type}. Valid types: {[t.value for t in FeedbackType]}"
            )
        
        # Initialize service
        review_service = ReviewManagementService(lambda: db_session, None)  # Event bus not needed for direct API calls
        
        # Convert new_platform_file_id to UUID if provided
        new_platform_file_id = None
        if feedback.new_platform_file_id:
            try:
                new_platform_file_id = UUID(feedback.new_platform_file_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid new_platform_file_id: {feedback.new_platform_file_id}"
                )
        
        # Submit feedback
        result = await review_service.submit_review_feedback(
            review_item_id=review_item_id,
            feedback_type=feedback.feedback_type,
            comment_text=feedback.comment_text,
            timestamp_seconds=feedback.timestamp_seconds,
            coordinates=feedback.coordinates,
            submitted_by=current_user.user_id if current_user and current_user.user_id else None,
            new_platform_file_id=new_platform_file_id
        )
        
        return result
        
    except ValueError as ve:
        logger.error(f"Validation error: {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        logger.error(f"Error submitting review feedback: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while submitting review feedback"
        )


@router.get(
    "/review-items/{review_item_id}/feedback",
    response_model=List[Dict],
)
async def get_review_feedback_history(
    review_item_id: UUID,
    current_user=Depends(get_required_auth_dependency()),
    db_session=Depends(get_db_session),
):
    """
    Get feedback history for a review item.
    
    This endpoint returns all feedback entries for a review item, ordered by submission time (newest first).
    """
    logger.info(f"Getting feedback history for review item {review_item_id}")
    
    try:
        # Initialize service
        review_service = ReviewManagementService(lambda: db_session, None)
        
        # Get feedback history
        feedback_history = await review_service.get_review_feedback_history(review_item_id)
        
        return feedback_history
        
    except Exception as e:
        logger.error(f"Error getting feedback history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving feedback history"
        )


@router.put(
    "/review-items/{review_item_id}/status",
    response_model=Dict,
)
async def update_review_item_status(
    review_item_id: UUID,
    status_update: ReviewStatusUpdateRequest,
    current_user=Depends(get_required_auth_dependency()),
    db_session=Depends(get_db_session),
):
    """
    Update the status of a review item.
    
    This endpoint:
    1. Updates the review item status
    2. Creates a feedback entry to record the status change
    3. Triggers appropriate actions based on the new status (e.g., creating rework tasks)
    """
    logger.info(f"Updating status of review item {review_item_id} to {status_update.status}")
    
    try:
        # Validate status
        try:
            new_status = ReviewStatus(status_update.status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_update.status}. Valid statuses: {[s.value for s in ReviewStatus]}"
            )
        
        # Initialize service
        review_service = ReviewManagementService(lambda: db_session, None)
        
        # Update status
        updated_item = await review_service.update_review_item_status(
            review_item_id=review_item_id,
            status=status_update.status,
            user_id=current_user.user_id if current_user and current_user.user_id else None,
            comment=status_update.comment
        )
        
        # Return updated item
        return {
            "review_item_id": str(updated_item.id),
            "status": updated_item.review_status,
            "updated_at": updated_item.updated_at.isoformat() if updated_item.updated_at else None
        }
        
    except ValueError as ve:
        logger.error(f"Validation error: {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        logger.error(f"Error updating review item status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating review item status"
        )


@router.put(
    "/review-items/{review_item_id}/files/{file_id}/version",
    response_model=Dict,
)
async def create_file_version(
    review_item_id: UUID,
    file_id: UUID,
    new_file: UploadFile = File(...),
    version_notes: Optional[str] = Form(None),
    current_user=Depends(get_required_auth_dependency()),
    db_session=Depends(get_db_session),
):
    """
    Create a new version of a review item file.
    
    This endpoint:
    1. Uploads the new file version to the platform file service
    2. Creates a version record linking the original file to the new version
    3. Returns the version information
    """
    logger.info(f"Creating new version for file {file_id} in review item {review_item_id}")
    
    try:
        # Initialize services
        file_upload_service = FileUploadIntegrationService(db_session)
        file_version_service = FileVersionService(db_session)
        
        # Upload the new file version
        metadata = {
            "review_item_id": str(review_item_id),
            "original_file_id": str(file_id),
            "version_notes": version_notes,
            "user_id": str(current_user.user_id) if current_user and current_user.user_id else None
        }
        
        upload_result = await file_upload_service.upload_file_version(
            original_file_id=file_id,
            new_file=new_file,
            metadata=metadata
        )
        
        if not upload_result.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File upload failed: {upload_result.error_message}"
            )
        
        # Create file version record
        new_version = await file_version_service.create_file_version(
            original_file_id=file_id,
            new_file_id=upload_result.platform_file_ids[0],
            version_type="revision",
            created_by=current_user.user_id if current_user and current_user.user_id else None,
            version_notes=version_notes
        )
        
        # Return version information
        return {
            "version_id": str(new_version.id),
            "original_file_id": str(new_version.original_file_id),
            "current_file_id": str(new_version.current_file_id),
            "version_number": new_version.version_number,
            "version_type": new_version.version_type,
            "created_at": new_version.created_at.isoformat() if new_version.created_at else None
        }
        
    except ValueError as ve:
        logger.error(f"Validation error: {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        logger.error(f"Error creating file version: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the file version"
        )


@router.get(
    "/deliverables/{deliverable_id}/review-items",
    response_model=List[Dict],
)
async def get_deliverable_review_items(
    deliverable_id: UUID,
    current_user=Depends(get_required_auth_dependency()),
    db_session=Depends(get_db_session),
):
    """
    Get all review items for a specific deliverable.
    
    Returns:
        List[Dict]: List of review items with their details
    """
    logger.info(f"Getting review items for deliverable {deliverable_id}")
    
    try:
        # Query review items for the deliverable
        result = await db_session.execute(
            select(ReviewItem)
            .filter(ReviewItem.deliverable_id == deliverable_id)
            .order_by(ReviewItem.sequence_number, ReviewItem.review_round, ReviewItem.created_at)
        )
        review_items = result.scalars().all()
        
        # Convert to response format
        response_items = []
        for item in review_items:
            # Get feedback count for each review item
            feedback_count_result = await db_session.execute(
                select(func.count())
                .select_from(ReviewFeedback)
                .filter(ReviewFeedback.review_item_id == item.id)
            )
            feedback_count = feedback_count_result.scalar() or 0
            
            response_items.append({
                "id": str(item.id),
                "project_id": str(item.project_id),
                "deliverable_id": str(item.deliverable_id),
                "source_internal_task_id": str(item.source_internal_task_id),
                "item_type": item.item_type.value,
                "platform_file_id": str(item.platform_file_id) if item.platform_file_id else None,
                "item_url": item.item_url,
                "description": item.description,
                "review_status": item.review_status.value,
                "sequence_number": item.sequence_number,
                "review_round": item.review_round,
                "presented_at": item.presented_at.isoformat() if item.presented_at else None,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                "feedback_count": feedback_count
            })
        
        return response_items
        
    except Exception as e:
        logger.error(f"Error getting review items for deliverable {deliverable_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving review items"
        )


@router.get(
    "/projects/{project_id}/deliverables/{deliverable_id}/review_items",
    response_model=List[Dict],
)
async def get_project_deliverable_review_items(
    project_id: UUID,
    deliverable_id: UUID,
    current_user=Depends(get_required_auth_dependency()),
    db_session=Depends(get_db_session),
):
    """
    Get all review items for a specific deliverable within a project.
    
    Returns:
        List[Dict]: List of review items with their details
    """
    logger.info(f"Getting review items for project {project_id}, deliverable {deliverable_id}")
    
    try:
        # Query review items for the deliverable within the project
        result = await db_session.execute(
            select(ReviewItem)
            .filter(
                ReviewItem.project_id == project_id,
                ReviewItem.deliverable_id == deliverable_id
            )
            .order_by(ReviewItem.sequence_number, ReviewItem.review_round, ReviewItem.created_at)
        )
        review_items = result.scalars().all()
        
        # Convert to response format
        response_items = []
        for item in review_items:
            # Get feedback count for each review item
            feedback_count_result = await db_session.execute(
                select(func.count())
                .select_from(ReviewFeedback)
                .filter(ReviewFeedback.review_item_id == item.id)
            )
            feedback_count = feedback_count_result.scalar() or 0
            
            response_items.append({
                "id": str(item.id),
                "project_id": str(item.project_id),
                "deliverable_id": str(item.deliverable_id),
                "source_internal_task_id": str(item.source_internal_task_id),
                "item_type": item.item_type.value,
                "platform_file_id": str(item.platform_file_id) if item.platform_file_id else None,
                "item_url": item.item_url,
                "description": item.description,
                "review_status": item.review_status.value,
                "sequence_number": item.sequence_number,
                "review_round": item.review_round,
                "presented_at": item.presented_at.isoformat() if item.presented_at else None,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                "feedback_count": feedback_count
            })
        
        return response_items
        
    except Exception as e:
        logger.error(f"Error getting review items for project {project_id}, deliverable {deliverable_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving review items"
        )