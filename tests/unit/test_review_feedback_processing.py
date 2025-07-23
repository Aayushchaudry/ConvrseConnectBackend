import asyncio
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from src.models.client_feedback import FeedbackType
from src.models.internal_task import InternalTask, TaskStatus
from src.models.review_feedback import ReviewFeedback
from src.models.review_item import ReviewItem, ReviewStatus
from src.services.review_management_service import ReviewManagementService


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_db_session_factory(mock_db_session):
    """Create a mock database session factory."""
    async def _factory():
        return mock_db_session
    return _factory


@pytest.fixture
def mock_event_bus():
    """Create a mock event bus."""
    event_bus = AsyncMock()
    event_bus.publish = AsyncMock()
    return event_bus


@pytest.fixture
def review_management_service(mock_db_session_factory, mock_event_bus):
    """Create a ReviewManagementService with mock dependencies."""
    return ReviewManagementService(mock_db_session_factory, mock_event_bus)


@pytest.fixture
def sample_review_item():
    """Create a sample review item."""
    return ReviewItem(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        deliverable_id=uuid.uuid4(),
        source_internal_task_id=uuid.uuid4(),
        item_type="IMAGE",
        review_status=ReviewStatus.PENDING_REVIEW.value,
        sequence_number=1,
        review_round=1,
        presented_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )


@pytest.fixture
def sample_source_task():
    """Create a sample source task."""
    return InternalTask(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        deliverable_id=uuid.uuid4(),
        task_type="MODELING",
        title="Create 3D Model",
        description="Create a 3D model of the product",
        status=TaskStatus.DONE.value,
        assigned_to=uuid.uuid4(),
        priority=1,
        estimated_hours=4,
        due_date=datetime.utcnow(),
        is_rework=False
    )


class TestReviewFeedbackProcessing:
    """Test cases for review feedback processing logic."""

    @pytest.mark.asyncio
    async def test_submit_review_feedback_approval(self, review_management_service, mock_db_session, sample_review_item):
        """Test submitting approval feedback for a review item."""
        # Arrange
        review_item_id = sample_review_item.id
        feedback_type = FeedbackType.ACCEPT.value
        comment_text = "Looks great!"
        submitted_by = uuid.uuid4()
        
        # Mock database queries
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = sample_review_item
        
        # Act
        result = await review_management_service.submit_review_feedback(
            review_item_id=review_item_id,
            feedback_type=feedback_type,
            comment_text=comment_text,
            submitted_by=submitted_by
        )
        
        # Assert
        assert result.feedback_type == feedback_type
        assert result.review_status == ReviewStatus.APPROVED.value
        assert result.comment_text == comment_text
        assert not result.task_generated
        assert result.generated_task_id is None
        
        # Verify database operations
        mock_db_session.add.assert_called()
        mock_db_session.commit.assert_called_once()
        
        # Verify event bus publication
        review_management_service.event_bus.publish.assert_called_once()
        call_args = review_management_service.event_bus.publish.call_args[1]
        assert call_args["topic"] == "review.item.approved"
        assert call_args["message"]["review_item_id"] == str(review_item_id)

    @pytest.mark.asyncio
    async def test_submit_review_feedback_rejection(
        self, review_management_service, mock_db_session, sample_review_item, sample_source_task
    ):
        """Test submitting rejection feedback for a review item."""
        # Arrange
        review_item_id = sample_review_item.id
        feedback_type = FeedbackType.REJECT.value
        comment_text = "Needs improvements"
        submitted_by = uuid.uuid4()
        
        # Mock database queries
        mock_db_session.execute.return_value.scalar_one_or_none.side_effect = [
            sample_review_item,  # First call for review item
            sample_source_task,  # Second call for source task
        ]
        
        # Mock rework task creation
        rework_task = InternalTask(
            id=uuid.uuid4(),
            project_id=sample_review_item.project_id,
            deliverable_id=sample_review_item.deliverable_id,
            parent_task_id=sample_source_task.id,
            task_type=sample_source_task.task_type,
            title=f"Rework: {sample_source_task.title}",
            status=TaskStatus.TODO.value,
            is_rework=True
        )
        
        # Act
        with patch.object(
            review_management_service, 
            '_create_rework_task_from_feedback', 
            return_value=asyncio.Future()
        ) as mock_create_task:
            mock_create_task.return_value.set_result(rework_task)
            result = await review_management_service.submit_review_feedback(
                review_item_id=review_item_id,
                feedback_type=feedback_type,
                comment_text=comment_text,
                submitted_by=submitted_by
            )
        
        # Assert
        assert result.feedback_type == feedback_type
        assert result.review_status == ReviewStatus.REJECTED.value
        assert result.comment_text == comment_text
        assert result.task_generated
        assert result.generated_task_id == rework_task.id
        
        # Verify database operations
        mock_db_session.add.assert_called()
        mock_db_session.commit.assert_called_once()
        
        # Verify event bus publication
        review_management_service.event_bus.publish.assert_called_once()
        call_args = review_management_service.event_bus.publish.call_args[1]
        assert call_args["topic"] == "review.item.rejected"
        assert call_args["message"]["review_item_id"] == str(review_item_id)
        assert call_args["message"]["generated_task_id"] == str(rework_task.id)

    @pytest.mark.asyncio
    async def test_get_review_feedback_history(self, review_management_service, mock_db_session):
        """Test getting feedback history for a review item."""
        # Arrange
        review_item_id = uuid.uuid4()
        
        # Create sample feedback entries
        feedback1 = ReviewFeedback(
            id=uuid.uuid4(),
            review_item_id=review_item_id,
            feedback_type=FeedbackType.COMMENT.value,
            comment_text="Initial comment",
            submitted_by=uuid.uuid4(),
            submitted_at=datetime.utcnow()
        )
        
        feedback2 = ReviewFeedback(
            id=uuid.uuid4(),
            review_item_id=review_item_id,
            feedback_type=FeedbackType.REJECT.value,
            comment_text="Needs work",
            submitted_by=uuid.uuid4(),
            submitted_at=datetime.utcnow(),
            generated_task_id=uuid.uuid4()
        )
        
        # Mock database queries
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = [feedback2, feedback1]
        
        # Act
        result = await review_management_service.get_review_feedback_history(review_item_id)
        
        # Assert
        assert len(result) == 2
        assert result[0]["id"] == str(feedback2.id)
        assert result[0]["feedback_type"] == feedback2.feedback_type.value
        assert result[1]["id"] == str(feedback1.id)
        assert result[1]["feedback_type"] == feedback1.feedback_type.value

    @pytest.mark.asyncio
    async def test_update_review_item_status(self, review_management_service, mock_db_session, sample_review_item):
        """Test updating the status of a review item."""
        # Arrange
        review_item_id = sample_review_item.id
        new_status = ReviewStatus.APPROVED.value
        user_id = uuid.uuid4()
        comment = "Approved after review"
        
        # Mock database queries
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = sample_review_item
        
        # Act
        result = await review_management_service.update_review_item_status(
            review_item_id=review_item_id,
            status=new_status,
            user_id=user_id,
            comment=comment
        )
        
        # Assert
        assert result.review_status == new_status
        
        # Verify database operations
        mock_db_session.add.assert_called()
        mock_db_session.commit.assert_called_once()
        
        # Verify event bus publication
        review_management_service.event_bus.publish.assert_called_once()
        call_args = review_management_service.event_bus.publish.call_args[1]
        assert call_args["topic"] == "review.item.status.updated"
        assert call_args["message"]["review_item_id"] == str(review_item_id)
        assert call_args["message"]["new_status"] == new_status