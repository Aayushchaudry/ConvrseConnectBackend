# tests/unit/test_review_management_service.py

import uuid
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.review_item import ReviewItem, ReviewItemType, ReviewStatus
from src.models.review_item_file import ReviewItemFile
from src.models.file_version import FileVersion, VersionType
from src.models.internal_task import InternalTask, TaskStatus, TaskType
from src.models.client_feedback import ClientFeedback, FeedbackType
from src.services.review_management_service import ReviewManagementService


@pytest.fixture
def mock_event_bus():
    """Mock event bus for testing."""
    event_bus = AsyncMock()
    event_bus.publish = AsyncMock()
    return event_bus


@pytest.fixture
def review_service(mock_event_bus):
    """Create a review management service with mocked dependencies."""
    db_session_factory = AsyncMock()
    return ReviewManagementService(db_session_factory, mock_event_bus)


@pytest.mark.asyncio
async def test_create_review_items_from_task_completion(db_session):
    """Test creating review items from task completion with file associations."""
    # Create test data
    project_id = uuid.uuid4()
    deliverable_id = uuid.uuid4()
    task_id = uuid.uuid4()
    
    # Create a test task
    task = InternalTask(
        id=task_id,
        project_id=project_id,
        deliverable_id=deliverable_id,
        task_type=TaskType.MODELING.value,
        title="Test Modeling Task",
        description="Test task description",
        status=TaskStatus.DONE.value,
        assigned_to=uuid.uuid4()
    )
    db_session.add(task)
    await db_session.commit()
    
    # Create service
    event_bus = AsyncMock()
    
    async def session_factory():
        return db_session
    
    service = ReviewManagementService(session_factory, event_bus)
    
    # Test data for file uploads
    platform_file_ids = [uuid.uuid4(), uuid.uuid4()]
    file_metadata = [
        {
            "file_name": "test_document.pdf",
            "file_type": "pdf",
            "file_size": 1024
        },
        {
            "file_name": "test_image.png",
            "file_type": "png",
            "file_size": 512
        }
    ]
    
    # Call the method
    review_items = await service.create_review_items_from_task_completion(
        db_session,
        task_id,
        platform_file_ids,
        file_metadata,
        ReviewItemType.DOCUMENT
    )
    
    # Verify review items were created
    assert len(review_items) == 2
    
    # Verify review item properties
    for review_item in review_items:
        assert review_item.project_id == project_id
        assert review_item.deliverable_id == deliverable_id
        assert review_item.source_internal_task_id == task_id
        assert review_item.item_type == ReviewItemType.DOCUMENT.value
        assert review_item.review_status == ReviewStatus.PENDING_REVIEW.value
        assert review_item.review_round == 1
    
    # Verify review item files were created
    for i, file_id in enumerate(platform_file_ids):
        result = await db_session.execute(
            select(ReviewItemFile).filter(ReviewItemFile.platform_file_id == file_id)
        )
        file = result.scalar_one()
        
        assert file.platform_file_id == file_id
        assert file.file_name == file_metadata[i]["file_name"]
        assert file.file_type == file_metadata[i]["file_type"]
        assert file.file_size == file_metadata[i]["file_size"]
        assert file.sequence_order == i + 1
        
        # Verify file version was created
        version_result = await db_session.execute(
            select(FileVersion).filter(FileVersion.original_file_id == file_id)
        )
        version = version_result.scalar_one()
        
        assert version.original_file_id == file_id
        assert version.current_file_id == file_id
        assert version.version_number == 1
        assert version.version_type == VersionType.INITIAL.value
        assert version.is_final is False


@pytest.mark.asyncio
async def test_create_rework_task_from_feedback(db_session):
    """Test creating a rework task from feedback."""
    # Create test data
    project_id = uuid.uuid4()
    deliverable_id = uuid.uuid4()
    source_task_id = uuid.uuid4()
    review_item_id = uuid.uuid4()
    
    # Create a source task
    source_task = InternalTask(
        id=source_task_id,
        project_id=project_id,
        deliverable_id=deliverable_id,
        task_type=TaskType.MODELING.value,
        title="Original Task",
        description="Original task description",
        status=TaskStatus.DONE.value,
        assigned_to=uuid.uuid4(),
        estimated_hours=8,
        priority=2
    )
    db_session.add(source_task)
    
    # Create a review item
    review_item = ReviewItem(
        id=review_item_id,
        project_id=project_id,
        deliverable_id=deliverable_id,
        source_internal_task_id=source_task_id,
        item_type=ReviewItemType.DOCUMENT.value,
        description="Test Review Item",
        sequence_number=1,
        review_round=1,
        review_status=ReviewStatus.PENDING_REVIEW.value
    )
    db_session.add(review_item)
    await db_session.commit()
    
    # Create feedback
    feedback = ClientFeedback(
        project_id=project_id,
        deliverable_id=deliverable_id,
        review_item_id=review_item_id,
        feedback_type=FeedbackType.REJECT.value,
        comment_text="Needs more details"
    )
    db_session.add(feedback)
    
    # Create service
    event_bus = AsyncMock()
    
    async def session_factory():
        return db_session
    
    service = ReviewManagementService(session_factory, event_bus)
    
    # Call the method
    rework_task = await service._create_rework_task_from_feedback(
        db_session,
        review_item,
        feedback
    )
    
    # Verify rework task was created
    assert rework_task is not None
    assert rework_task.project_id == project_id
    assert rework_task.deliverable_id == deliverable_id
    assert rework_task.parent_task_id == source_task_id
    assert rework_task.task_type == source_task.task_type
    assert "Rework" in rework_task.title
    assert "Needs more details" in rework_task.description
    assert rework_task.status == TaskStatus.TODO.value
    assert rework_task.assigned_to == source_task.assigned_to
    assert rework_task.priority == source_task.priority
    assert rework_task.estimated_hours == source_task.estimated_hours / 2
    assert rework_task.is_rework is True
    
    # Verify feedback is linked to the task
    await db_session.refresh(feedback)
    assert feedback.generated_task_id == rework_task.id


@pytest.mark.asyncio
async def test_process_review_feedback_with_file_versioning_approve(db_session):
    """Test processing review feedback with file versioning for approval."""
    # Create test data
    project_id = uuid.uuid4()
    deliverable_id = uuid.uuid4()
    review_item_id = uuid.uuid4()
    platform_file_id = uuid.uuid4()
    
    # Create a review item with file
    review_item = ReviewItem(
        id=review_item_id,
        project_id=project_id,
        deliverable_id=deliverable_id,
        item_type=ReviewItemType.DOCUMENT.value,
        platform_file_id=platform_file_id,
        description="Test Review Item",
        sequence_number=1,
        review_round=1,
        review_status=ReviewStatus.PENDING_REVIEW.value
    )
    db_session.add(review_item)
    
    # Create file version
    file_version = FileVersion(
        original_file_id=platform_file_id,
        current_file_id=platform_file_id,
        version_number=1,
        version_type=VersionType.INITIAL.value,
        is_final=False,
        is_active=True
    )
    db_session.add(file_version)
    await db_session.commit()
    
    # Create service
    event_bus = AsyncMock()
    
    async def session_factory():
        return db_session
    
    service = ReviewManagementService(session_factory, event_bus)
    
    # Call the method with approval
    updated_item, new_version = await service.process_review_feedback_with_file_versioning(
        review_item_id,
        FeedbackType.ACCEPT.value,
        "Looks good"
    )
    
    # Verify review item was updated
    assert updated_item.review_status == ReviewStatus.APPROVED.value
    
    # Verify no new version was created
    assert new_version is None
    
    # Verify existing version was marked as final
    await db_session.refresh(file_version)
    assert file_version.is_final is True
    assert file_version.version_type == VersionType.FINAL.value
    
    # Verify feedback was created
    feedback_result = await db_session.execute(
        select(ClientFeedback).filter(ClientFeedback.review_item_id == review_item_id)
    )
    feedback = feedback_result.scalar_one()
    assert feedback.feedback_type == FeedbackType.ACCEPT.value
    assert feedback.comment_text == "Looks good"


@pytest.mark.asyncio
async def test_process_review_feedback_with_file_versioning_reject(db_session):
    """Test processing review feedback with file versioning for rejection."""
    # Create test data
    project_id = uuid.uuid4()
    deliverable_id = uuid.uuid4()
    task_id = uuid.uuid4()
    review_item_id = uuid.uuid4()
    platform_file_id = uuid.uuid4()
    new_file_id = uuid.uuid4()
    user_id = uuid.uuid4()
    
    # Create a task
    task = InternalTask(
        id=task_id,
        project_id=project_id,
        deliverable_id=deliverable_id,
        task_type=TaskType.MODELING.value,
        title="Original Task",
        description="Original task description",
        status=TaskStatus.DONE.value,
        assigned_to=user_id,
        estimated_hours=8
    )
    db_session.add(task)
    
    # Create a review item with file
    review_item = ReviewItem(
        id=review_item_id,
        project_id=project_id,
        deliverable_id=deliverable_id,
        source_internal_task_id=task_id,
        item_type=ReviewItemType.DOCUMENT.value,
        platform_file_id=platform_file_id,
        description="Test Review Item",
        sequence_number=1,
        review_round=1,
        review_status=ReviewStatus.PENDING_REVIEW.value
    )
    db_session.add(review_item)
    
    # Create file version
    file_version = FileVersion(
        original_file_id=platform_file_id,
        current_file_id=platform_file_id,
        version_number=1,
        version_type=VersionType.INITIAL.value,
        is_final=False,
        is_active=True
    )
    db_session.add(file_version)
    await db_session.commit()
    
    # Create service
    event_bus = AsyncMock()
    
    async def session_factory():
        return db_session
    
    service = ReviewManagementService(session_factory, event_bus)
    
    # Call the method with rejection and new file
    updated_item, new_version = await service.process_review_feedback_with_file_versioning(
        review_item_id,
        FeedbackType.REJECT.value,
        "Needs more details",
        new_platform_file_id=new_file_id,
        user_id=user_id
    )
    
    # Verify review item was updated
    assert updated_item.review_status == ReviewStatus.REJECTED.value
    
    # Verify new version was created
    assert new_version is not None
    assert new_version.original_file_id == platform_file_id
    assert new_version.current_file_id == new_file_id
    assert new_version.version_number == 2
    assert new_version.version_type == VersionType.REVISION.value
    assert new_version.created_by == user_id
    assert "Needs more details" in new_version.version_notes
    
    # Verify feedback was created
    feedback_result = await db_session.execute(
        select(ClientFeedback).filter(ClientFeedback.review_item_id == review_item_id)
    )
    feedback = feedback_result.scalar_one()
    assert feedback.feedback_type == FeedbackType.REJECT.value
    assert feedback.comment_text == "Needs more details"
    
    # Verify rework task was created
    task_result = await db_session.execute(
        select(InternalTask).filter(
            InternalTask.parent_task_id == task_id,
            InternalTask.is_rework == True
        )
    )
    rework_task = task_result.scalar_one()
    assert rework_task is not None
    assert "Rework" in rework_task.title
    assert "Needs more details" in rework_task.description


@pytest.mark.asyncio
async def test_get_review_item_files(db_session):
    """Test getting files for a review item with version information."""
    # Create test data
    review_item_id = uuid.uuid4()
    platform_file_id1 = uuid.uuid4()
    platform_file_id2 = uuid.uuid4()
    
    # Create a review item
    review_item = ReviewItem(
        id=review_item_id,
        project_id=uuid.uuid4(),
        deliverable_id=uuid.uuid4(),
        item_type=ReviewItemType.DOCUMENT.value,
        description="Test Review Item",
        sequence_number=1,
        review_round=1
    )
    db_session.add(review_item)
    
    # Create review item files
    file1 = ReviewItemFile(
        review_item_id=review_item_id,
        platform_file_id=platform_file_id1,
        file_name="document.pdf",
        file_type="pdf",
        file_size=1024,
        sequence_order=1
    )
    file2 = ReviewItemFile(
        review_item_id=review_item_id,
        platform_file_id=platform_file_id2,
        file_name="image.png",
        file_type="png",
        file_size=512,
        sequence_order=2
    )
    db_session.add_all([file1, file2])
    
    # Create file versions
    version1 = FileVersion(
        original_file_id=platform_file_id1,
        current_file_id=platform_file_id1,
        version_number=1,
        version_type=VersionType.INITIAL.value,
        is_final=False,
        is_active=True
    )
    version2 = FileVersion(
        original_file_id=platform_file_id2,
        current_file_id=platform_file_id2,
        version_number=1,
        version_type=VersionType.INITIAL.value,
        is_final=True,
        is_active=True
    )
    db_session.add_all([version1, version2])
    await db_session.commit()
    
    # Create service
    event_bus = AsyncMock()
    
    async def session_factory():
        return db_session
    
    service = ReviewManagementService(session_factory, event_bus)
    
    # Call the method
    files = await service.get_review_item_files(review_item_id)
    
    # Verify files were returned
    assert len(files) == 2
    
    # Verify file properties
    file1_data = next(f for f in files if f["file_name"] == "document.pdf")
    file2_data = next(f for f in files if f["file_name"] == "image.png")
    
    assert file1_data["platform_file_id"] == str(platform_file_id1)
    assert file1_data["file_type"] == "pdf"
    assert file1_data["file_size"] == 1024
    assert file1_data["sequence_order"] == 1
    assert file1_data["version_info"]["current_version"] == 1
    assert file1_data["version_info"]["is_final"] is False
    
    assert file2_data["platform_file_id"] == str(platform_file_id2)
    assert file2_data["file_type"] == "png"
    assert file2_data["file_size"] == 512
    assert file2_data["sequence_order"] == 2
    assert file2_data["version_info"]["current_version"] == 1
    assert file2_data["version_info"]["is_final"] is True