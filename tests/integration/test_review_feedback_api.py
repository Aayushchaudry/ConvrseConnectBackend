import json
import uuid
from typing import Dict, Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.config.database import get_db_session
from src.main import app
from src.models.client_feedback import FeedbackType
from src.models.review_feedback import ReviewFeedback
from src.models.review_item import ReviewItem, ReviewStatus
from tests.integration.test_api_endpoints import create_test_auth_header


@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Create authentication headers for API requests."""
    return create_test_auth_header()


@pytest.fixture
async def test_review_item(test_db_session):
    """Create a test review item in the database."""
    # Create a project, deliverable, and task first
    project_id = uuid.uuid4()
    deliverable_id = uuid.uuid4()
    task_id = uuid.uuid4()
    
    # Create the review item
    review_item = ReviewItem(
        id=uuid.uuid4(),
        project_id=project_id,
        deliverable_id=deliverable_id,
        source_internal_task_id=task_id,
        item_type="IMAGE",
        review_status=ReviewStatus.PENDING_REVIEW.value,
        sequence_number=1,
        review_round=1
    )
    
    test_db_session.add(review_item)
    await test_db_session.commit()
    
    return review_item


class TestReviewFeedbackAPI:
    """Integration tests for review feedback API endpoints."""
    
    @pytest.mark.asyncio
    async def test_submit_review_feedback(self, test_client, auth_headers, test_review_item, test_db_session):
        """Test submitting feedback for a review item."""
        # Arrange
        review_item_id = test_review_item.id
        feedback_data = {
            "feedback_type": FeedbackType.ACCEPT.value,
            "comment_text": "Looks great!",
            "timestamp_seconds": None,
            "coordinates": None
        }
        
        # Act
        response = test_client.post(
            f"/api/v1/review-items/{review_item_id}/feedback",
            json=feedback_data,
            headers=auth_headers
        )
        
        # Assert
        assert response.status_code == 201
        result = response.json()
        assert result["feedback_type"] == FeedbackType.ACCEPT.value
        assert result["review_status"] == ReviewStatus.APPROVED.value
        assert result["comment_text"] == "Looks great!"
        
        # Verify database update
        query = select(ReviewItem).filter(ReviewItem.id == review_item_id)
        result = await test_db_session.execute(query)
        updated_item = result.scalar_one()
        assert updated_item.review_status == ReviewStatus.APPROVED.value
        
        # Verify feedback record creation
        query = select(ReviewFeedback).filter(ReviewFeedback.review_item_id == review_item_id)
        result = await test_db_session.execute(query)
        feedback = result.scalar_one()
        assert feedback.feedback_type == FeedbackType.ACCEPT.value
        assert feedback.comment_text == "Looks great!"
    
    @pytest.mark.asyncio
    async def test_get_review_feedback_history(self, test_client, auth_headers, test_review_item, test_db_session):
        """Test getting feedback history for a review item."""
        # Arrange
        review_item_id = test_review_item.id
        
        # Create some feedback entries
        feedback1 = ReviewFeedback(
            id=uuid.uuid4(),
            review_item_id=review_item_id,
            feedback_type=FeedbackType.COMMENT.value,
            comment_text="Initial comment"
        )
        
        feedback2 = ReviewFeedback(
            id=uuid.uuid4(),
            review_item_id=review_item_id,
            feedback_type=FeedbackType.ACCEPT.value,
            comment_text="Final approval"
        )
        
        test_db_session.add(feedback1)
        test_db_session.add(feedback2)
        await test_db_session.commit()
        
        # Act
        response = test_client.get(
            f"/api/v1/review-items/{review_item_id}/feedback",
            headers=auth_headers
        )
        
        # Assert
        assert response.status_code == 200
        result = response.json()
        assert len(result) == 2
        assert any(item["feedback_type"] == FeedbackType.COMMENT.value for item in result)
        assert any(item["feedback_type"] == FeedbackType.ACCEPT.value for item in result)
    
    @pytest.mark.asyncio
    async def test_update_review_item_status(self, test_client, auth_headers, test_review_item, test_db_session):
        """Test updating the status of a review item."""
        # Arrange
        review_item_id = test_review_item.id
        status_data = {
            "status": ReviewStatus.APPROVED.value,
            "comment": "Approved after review meeting"
        }
        
        # Act
        response = test_client.put(
            f"/api/v1/review-items/{review_item_id}/status",
            json=status_data,
            headers=auth_headers
        )
        
        # Assert
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == ReviewStatus.APPROVED.value
        
        # Verify database update
        query = select(ReviewItem).filter(ReviewItem.id == review_item_id)
        result = await test_db_session.execute(query)
        updated_item = result.scalar_one()
        assert updated_item.review_status == ReviewStatus.APPROVED.value
        
        # Verify feedback record creation
        query = select(ReviewFeedback).filter(ReviewFeedback.review_item_id == review_item_id)
        result = await test_db_session.execute(query)
        feedback = result.scalar_one()
        assert feedback.comment_text.endswith(": Approved after review meeting")
    
    @pytest.mark.asyncio
    async def test_submit_review_feedback_with_invalid_type(self, test_client, auth_headers, test_review_item):
        """Test submitting feedback with an invalid feedback type."""
        # Arrange
        review_item_id = test_review_item.id
        feedback_data = {
            "feedback_type": "INVALID_TYPE",
            "comment_text": "This should fail"
        }
        
        # Act
        response = test_client.post(
            f"/api/v1/review-items/{review_item_id}/feedback",
            json=feedback_data,
            headers=auth_headers
        )
        
        # Assert
        assert response.status_code == 400
        assert "Invalid feedback type" in response.json()["detail"]