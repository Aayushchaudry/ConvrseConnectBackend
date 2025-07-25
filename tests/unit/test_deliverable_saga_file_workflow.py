"""
Unit tests for the DeliverableSagaOrchestrator file-driven workflows.
"""

import asyncio
import pytest
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.deliverable import Deliverable, DeliverableStatus
from src.models.project import Project, ProjectStatus
from src.models.review_item import ReviewItem, ReviewStatus
from src.models.review_item_file import ReviewItemFile
from src.models.project_output import ProjectOutput
from src.events.client_feedback_events import ClientFeedbackSubmittedEvent
from src.events.project_events import DeliverableDeliveredEvent
from src.orchestrators.deliverable_saga_orchestrator.commands import GenerateFinalOutputCommand
from src.orchestrators.deliverable_saga_orchestrator.enhanced_file_workflow import (
    check_all_reviews_approved,
    get_latest_approved_review_items,
    create_project_output,
    check_project_completion,
)


@pytest.mark.asyncio
async def test_check_all_reviews_approved_true():
    """Test check_all_reviews_approved when all reviews are approved."""
    # Setup
    deliverable_id = uuid.uuid4()
    
    # Mock session
    session = AsyncMock()
    
    # Mock query results
    total_count_result = AsyncMock()
    total_count_result.scalar.return_value = 3
    
    approved_count_result = AsyncMock()
    approved_count_result.scalar.return_value = 3
    
    # Setup session execute to return our mocked results
    session.execute.side_effect = [total_count_result, approved_count_result]
    
    # Execute
    result = await check_all_reviews_approved(session, deliverable_id)
    
    # Assert
    assert result is True
    assert session.execute.call_count == 2


@pytest.mark.asyncio
async def test_check_all_reviews_approved_false():
    """Test check_all_reviews_approved when not all reviews are approved."""
    # Setup
    deliverable_id = uuid.uuid4()
    
    # Mock session
    session = AsyncMock()
    
    # Mock query results
    total_count_result = AsyncMock()
    total_count_result.scalar.return_value = 3
    
    approved_count_result = AsyncMock()
    approved_count_result.scalar.return_value = 2  # Only 2 of 3 approved
    
    # Setup session execute to return our mocked results
    session.execute.side_effect = [total_count_result, approved_count_result]
    
    # Execute
    result = await check_all_reviews_approved(session, deliverable_id)
    
    # Assert
    assert result is False
    assert session.execute.call_count == 2


@pytest.mark.asyncio
async def test_get_latest_approved_review_items():
    """Test get_latest_approved_review_items returns the latest approved items."""
    # Setup
    deliverable_id = uuid.uuid4()
    
    # Mock session
    session = AsyncMock()
    
    # Mock review items
    review_item1 = ReviewItem(id=uuid.uuid4(), review_round=1, sequence_number=1)
    review_item2 = ReviewItem(id=uuid.uuid4(), review_round=2, sequence_number=2)
    
    # Mock query results
    result_mock = AsyncMock()
    result_mock.scalars.return_value.all.return_value = [review_item1, review_item2]
    
    # Setup session execute to return our mocked results
    session.execute.return_value = result_mock
    
    # Execute
    result = await get_latest_approved_review_items(session, deliverable_id)
    
    # Assert
    assert len(result) == 2
    assert result[0].id == review_item1.id
    assert result[1].id == review_item2.id
    assert session.execute.call_count == 1


@pytest.mark.asyncio
async def test_create_project_output():
    """Test create_project_output creates a project output for approved deliverable."""
    # Setup
    deliverable_id = uuid.uuid4()
    project_id = uuid.uuid4()
    
    # Mock session
    session = AsyncMock()
    
    # Mock deliverable
    deliverable = Deliverable(
        id=deliverable_id,
        project_id=project_id,
        deliverable_name="Test Deliverable"
    )
    
    # Mock review items
    review_item1 = ReviewItem(id=uuid.uuid4())
    review_item2 = ReviewItem(id=uuid.uuid4())
    approved_review_items = [review_item1, review_item2]
    
    # Mock review item files
    file1 = ReviewItemFile(review_item_id=review_item1.id, platform_file_id=uuid.uuid4())
    file2 = ReviewItemFile(review_item_id=review_item2.id, platform_file_id=uuid.uuid4())
    
    # Mock query results
    deliverable_result = AsyncMock()
    deliverable_result.scalar_one_or_none.return_value = deliverable
    
    files_result1 = AsyncMock()
    files_result1.scalars.return_value.all.return_value = [file1]
    
    files_result2 = AsyncMock()
    files_result2.scalars.return_value.all.return_value = [file2]
    
    # Setup session execute to return our mocked results
    session.execute.side_effect = [deliverable_result, files_result1, files_result2]
    
    # Execute
    result = await create_project_output(session, deliverable_id, project_id, approved_review_items)
    
    # Assert
    assert result is not None
    assert result.deliverable_id == deliverable_id
    assert result.project_id == project_id
    assert "Test Deliverable" in result.output_name
    assert session.add.call_count == 1
    assert session.flush.call_count == 1


@pytest.mark.asyncio
async def test_check_project_completion_true():
    """Test check_project_completion when all deliverables are delivered."""
    # Setup
    project_id = uuid.uuid4()
    
    # Mock session
    session = AsyncMock()
    
    # Mock query results
    total_count_result = AsyncMock()
    total_count_result.scalar.return_value = 3
    
    delivered_count_result = AsyncMock()
    delivered_count_result.scalar.return_value = 3
    
    # Setup session execute to return our mocked results
    session.execute.side_effect = [total_count_result, delivered_count_result]
    
    # Execute
    result = await check_project_completion(session, project_id)
    
    # Assert
    assert result is True
    assert session.execute.call_count == 2


@pytest.mark.asyncio
async def test_check_project_completion_false():
    """Test check_project_completion when not all deliverables are delivered."""
    # Setup
    project_id = uuid.uuid4()
    
    # Mock session
    session = AsyncMock()
    
    # Mock query results
    total_count_result = AsyncMock()
    total_count_result.scalar.return_value = 3
    
    delivered_count_result = AsyncMock()
    delivered_count_result.scalar.return_value = 2  # Only 2 of 3 delivered
    
    # Setup session execute to return our mocked results
    session.execute.side_effect = [total_count_result, delivered_count_result]
    
    # Execute
    result = await check_project_completion(session, project_id)
    
    # Assert
    assert result is False
    assert session.execute.call_count == 2


@pytest.mark.asyncio
async def test_client_feedback_submitted_all_approved():
    """Test on_client_feedback_submitted when all reviews are approved."""
    # This would be a more complex integration test with the actual orchestrator
    # For now, we'll just test the individual components
    pass


@pytest.mark.asyncio
async def test_handle_generate_final_output_command():
    """Test handle_generate_final_output_command creates project output."""
    # This would be a more complex integration test with the actual orchestrator
    # For now, we'll just test the individual components
    pass