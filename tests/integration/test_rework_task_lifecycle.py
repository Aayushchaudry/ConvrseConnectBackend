"""
Integration tests for the rework task lifecycle.
"""

import asyncio
import pytest
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.deliverable import Deliverable, DeliverableStatus
from src.models.internal_task import InternalTask, TaskStatus, TaskType, Priority
from src.models.review_item import ReviewItem, ReviewStatus, ReviewItemType
from src.models.review_feedback import ReviewFeedback, FeedbackType
from src.commands.production_commands import CreateReworkTaskCommand
from src.events.task_events import InternalTaskCompletedWithMediaEvent
from src.services.production_management_service import ProductionManagementService
from src.services.review_management_service import ReviewManagementService


@pytest.mark.asyncio
async def test_create_rework_task_command():
    """Test creating a rework task from a command."""
    # Setup
    project_id = uuid.uuid4()
    deliverable_id = uuid.uuid4()
    original_task_id = uuid.uuid4()
    review_item_id = uuid.uuid4()
    comment_id = uuid.uuid4()
    
    # Mock session and event bus
    session = AsyncMock()
    event_bus = AsyncMock()
    db_session_factory = AsyncMock()
    db_session_factory.return_value.__aenter__.return_value = session
    
    # Mock project and deliverable
    project = MagicMock()
    deliverable = MagicMock()
    
    # Mock original task
    original_task = InternalTask(
        id=original_task_id,
        project_id=project_id,
        deliverable_id=deliverable_id,
        task_name="Original Task",
        task_type=TaskType.MODELING.value,
        status=TaskStatus.DONE.value,
        estimated_hours=8
    )
    
    # Mock review item
    review_item = ReviewItem(
        id=review_item_id,
        project_id=project_id,
        deliverable_id=deliverable_id,
        source_internal_task_id=original_task_id,
        item_type=ReviewItemType.STATIC_RENDER.value,
        review_status=ReviewStatus.REJECTED.value
    )
    
    # Mock feedback
    feedback = ReviewFeedback(
        id=comment_id,
        review_item_id=review_item_id,
        feedback_type=FeedbackType.REJECT.value,
        comment_text="Needs improvement"
    )
    
    # Setup session execute to return our mocked results
    project_deliverable_result = AsyncMock()
    project_deliverable_result.scalar_one_or_none.side_effect = [project, deliverable]
    
    original_task_result = AsyncMock()
    original_task_result.scalar_one_or_none.return_value = original_task
    
    review_item_result = AsyncMock()
    review_item_result.scalar_one_or_none.return_value = review_item
    
    feedback_result = AsyncMock()
    feedback_result.scalar_one_or_none.return_value = feedback
    
    session.execute.side_effect = [
        project_deliverable_result,  # For _get_deliverable_and_project
        original_task_result,        # For original task query
        review_item_result,          # For review item query
        feedback_result              # For feedback query
    ]
    
    # Create command
    command = CreateReworkTaskCommand(
        project_id=project_id,
        deliverable_id=deliverable_id,
        original_task_id=original_task_id,
        review_item_id=review_item_id,
        comment_id=comment_id,
        rework_description="Fix the model based on feedback"
    )
    
    # Create service and execute command
    service = ProductionManagementService(db_session_factory, event_bus)
    rework_task = await service.handle_create_rework_task_command(command)
    
    # Assert
    assert rework_task is not None
    assert rework_task.project_id == project_id
    assert rework_task.deliverable_id == deliverable_id
    assert rework_task.parent_task_id == original_task_id
    assert rework_task.source_review_item_id == review_item_id
    assert rework_task.is_rework is True
    assert rework_task.task_type == original_task.task_type
    assert "Rework" in rework_task.task_name
    assert rework_task.status == TaskStatus.TODO.value
    assert rework_task.priority == Priority.HIGH.value
    assert rework_task.estimated_hours == 4  # Half of original task's 8 hours
    
    # Verify event bus was called
    assert event_bus.publish.call_count == 1
    

@pytest.mark.asyncio
async def test_create_review_items_for_completed_rework_task():
    """Test creating review items for a completed rework task."""
    # Setup
    project_id = uuid.uuid4()
    deliverable_id = uuid.uuid4()
    task_id = uuid.uuid4()
    original_review_item_id = uuid.uuid4()
    platform_file_ids = [uuid.uuid4(), uuid.uuid4()]
    
    # Mock session and event bus
    session = AsyncMock()
    event_bus = AsyncMock()
    db_session_factory = AsyncMock()
    db_session_factory.return_value.__aenter__.return_value = session
    
    # Mock rework task
    rework_task = InternalTask(
        id=task_id,
        project_id=project_id,
        deliverable_id=deliverable_id,
        task_name="Rework Task",
        task_type=TaskType.MODELING.value,
        status=TaskStatus.DONE.value,
        is_rework=True,
        source_review_item_id=original_review_item_id
    )
    
    # Mock original review item
    original_review_item = ReviewItem(
        id=original_review_item_id,
        project_id=project_id,
        deliverable_id=deliverable_id,
        item_type=ReviewItemType.STATIC_RENDER.value,
        review_round=1,
        review_status=ReviewStatus.REJECTED.value
    )
    
    # Mock created review items
    created_review_items = [
        ReviewItem(
            id=uuid.uuid4(),
            project_id=project_id,
            deliverable_id=deliverable_id,
            source_internal_task_id=task_id,
            item_type=ReviewItemType.STATIC_RENDER.value,
            review_round=1,  # Will be updated to 2
            sequence_number=1,
            review_status=ReviewStatus.PENDING_REVIEW.value
        ),
        ReviewItem(
            id=uuid.uuid4(),
            project_id=project_id,
            deliverable_id=deliverable_id,
            source_internal_task_id=task_id,
            item_type=ReviewItemType.STATIC_RENDER.value,
            review_round=1,  # Will be updated to 2
            sequence_number=2,
            review_status=ReviewStatus.PENDING_REVIEW.value
        )
    ]
    
    # Setup session execute to return our mocked results
    task_result = AsyncMock()
    task_result.scalar_one_or_none.return_value = rework_task
    
    original_review_item_result = AsyncMock()
    original_review_item_result.scalar_one_or_none.return_value = original_review_item
    
    session.execute.side_effect = [task_result, original_review_item_result]
    
    # Mock the review management service
    with patch('src.services.review_management_service.ReviewManagementService') as mock_review_service_class:
        mock_review_service = AsyncMock()
        mock_review_service.create_review_items_from_task_completion.return_value = created_review_items
        mock_review_service_class.return_value = mock_review_service
        
        # Create service and execute method
        service = ProductionManagementService(db_session_factory, event_bus)
        result = await service.create_review_items_for_completed_rework_task(
            task_id=task_id,
            platform_file_ids=platform_file_ids
        )
        
        # Assert
        assert result is True
        mock_review_service.create_review_items_from_task_completion.assert_called_once()
        
        # Verify review round was updated
        for item in created_review_items:
            assert item.review_round == 2  # Incremented from original review item's round
        
        # Verify session commit was called
        assert session.commit.call_count == 1


@pytest.mark.asyncio
async def test_rework_task_lifecycle_integration():
    """Test the complete lifecycle of a rework task."""
    # This would be a more complex integration test with the actual services
    # For now, we'll just test the individual components
    pass