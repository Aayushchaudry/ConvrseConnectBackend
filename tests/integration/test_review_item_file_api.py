# tests/integration/test_review_item_file_api.py

import io
import json
import uuid
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi import UploadFile, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

# Mock the app instead of importing from main
app = FastAPI()
from src.models.review_item import ReviewItem, ReviewItemType, ReviewStatus
from src.models.review_item_file import ReviewItemFile
from src.models.file_version import FileVersion, VersionType
from src.models.internal_task import InternalTask, TaskStatus, TaskType
from src.services.file_upload_integration_service import FileUploadResult


@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app."""
    # Import the router directly
    from src.api.review_items.controllers import router
    
    # Create a new FastAPI app and include the router
    test_app = FastAPI()
    test_app.include_router(router)
    
    return TestClient(test_app)


@pytest.fixture
def mock_auth_middleware():
    """Mock the authentication middleware to bypass auth."""
    with patch("src.middleware.auth_middleware.get_required_auth_dependency") as mock:
        auth_context = MagicMock()
        auth_context.user_id = uuid.uuid4()
        auth_context.is_authenticated = True
        mock.return_value = lambda: auth_context
        yield mock


@pytest.fixture
def mock_file_upload_service():
    """Mock the file upload integration service."""
    with patch("src.services.file_upload_integration_service.FileUploadIntegrationService") as mock:
        instance = mock.return_value
        
        # Mock upload_review_item_files method
        instance.upload_review_item_files = AsyncMock()
        instance.upload_review_item_files.return_value = FileUploadResult(
            success=True,
            platform_file_ids=[uuid.uuid4(), uuid.uuid4()],
            file_metadata=[
                {"file_name": "test1.pdf", "file_type": "pdf", "file_size": 1024},
                {"file_name": "test2.png", "file_type": "png", "file_size": 512}
            ]
        )
        
        # Mock upload_file_version method
        instance.upload_file_version = AsyncMock()
        instance.upload_file_version.return_value = FileUploadResult(
            success=True,
            platform_file_ids=[uuid.uuid4()],
            file_metadata=[{"file_name": "test_v2.pdf", "file_type": "pdf", "file_size": 1536}]
        )
        
        yield instance


@pytest.mark.asyncio
async def test_complete_task_with_files(
    db_session, test_client, mock_auth_middleware, mock_file_upload_service
):
    """Test completing a task with files API endpoint."""
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
    
    # Create test files
    test_file1 = io.BytesIO(b"test file content 1")
    test_file2 = io.BytesIO(b"test file content 2")
    
    # Make the API request
    with patch("src.api.review_items.controllers.get_db_session", return_value=db_session):
        response = test_client.post(
            f"/api/v1/internal-tasks/{task_id}/complete-with-files",
            data={
                "review_item_type": "DOCUMENT",
                "notes": "Test completion notes"
            },
            files=[
                ("files", ("test1.pdf", test_file1, "application/pdf")),
                ("files", ("test2.png", test_file2, "image/png"))
            ]
        )
    
    # Verify response
    assert response.status_code == 201
    response_data = response.json()
    assert len(response_data) > 0
    
    # Verify file upload service was called correctly
    mock_file_upload_service.upload_review_item_files.assert_called_once()
    call_args = mock_file_upload_service.upload_review_item_files.call_args[1]
    assert call_args["task_id"] == task_id
    assert len(call_args["files"]) == 2
    
    # Verify review items were created in the database
    result = await db_session.execute(
        select(ReviewItem).filter(ReviewItem.source_internal_task_id == task_id)
    )
    review_items = result.scalars().all()
    assert len(review_items) > 0
    
    # Verify review item files were created
    for review_item in review_items:
        file_result = await db_session.execute(
            select(ReviewItemFile).filter(ReviewItemFile.review_item_id == review_item.id)
        )
        files = file_result.scalars().all()
        assert len(files) > 0


@pytest.mark.asyncio
async def test_get_review_item_files(
    db_session, test_client, mock_auth_middleware
):
    """Test getting review item files API endpoint."""
    # Create test data
    review_item_id = uuid.uuid4()
    platform_file_id = uuid.uuid4()
    
    # Create a review item
    review_item = ReviewItem(
        id=review_item_id,
        project_id=uuid.uuid4(),
        deliverable_id=uuid.uuid4(),
        item_type=ReviewItemType.DOCUMENT.value,
        description="Test Review Item",
        sequence_number=1,
        review_round=1,
        review_status=ReviewStatus.PENDING_REVIEW.value
    )
    db_session.add(review_item)
    
    # Create a review item file
    review_item_file = ReviewItemFile(
        review_item_id=review_item_id,
        platform_file_id=platform_file_id,
        file_name="test_document.pdf",
        file_type="pdf",
        file_size=1024,
        sequence_order=1
    )
    db_session.add(review_item_file)
    
    # Create a file version
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
    
    # Make the API request
    with patch("src.api.review_items.controllers.get_db_session", return_value=db_session):
        response = test_client.get(f"/api/v1/review-items/{review_item_id}/files")
    
    # Verify response
    assert response.status_code == 200
    response_data = response.json()
    assert len(response_data) == 1
    
    file_data = response_data[0]
    assert file_data["review_item_id"] == str(review_item_id)
    assert file_data["platform_file_id"] == str(platform_file_id)
    assert file_data["file_name"] == "test_document.pdf"
    assert file_data["file_type"] == "pdf"
    assert file_data["file_size"] == 1024
    assert file_data["version_info"]["current_version"] == 1


@pytest.mark.asyncio
async def test_create_file_version(
    db_session, test_client, mock_auth_middleware, mock_file_upload_service
):
    """Test creating a new file version API endpoint."""
    # Create test data
    review_item_id = uuid.uuid4()
    platform_file_id = uuid.uuid4()
    
    # Create a review item
    review_item = ReviewItem(
        id=review_item_id,
        project_id=uuid.uuid4(),
        deliverable_id=uuid.uuid4(),
        item_type=ReviewItemType.DOCUMENT.value,
        description="Test Review Item",
        sequence_number=1,
        review_round=1,
        review_status=ReviewStatus.PENDING_REVIEW.value
    )
    db_session.add(review_item)
    
    # Create a review item file
    review_item_file = ReviewItemFile(
        review_item_id=review_item_id,
        platform_file_id=platform_file_id,
        file_name="test_document.pdf",
        file_type="pdf",
        file_size=1024,
        sequence_order=1
    )
    db_session.add(review_item_file)
    
    # Create a file version
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
    
    # Create test file for new version
    test_file = io.BytesIO(b"updated file content")
    
    # Make the API request
    with patch("src.api.review_items.controllers.get_db_session", return_value=db_session):
        response = test_client.put(
            f"/api/v1/review-items/{review_item_id}/files/{platform_file_id}/version",
            data={"version_notes": "Updated with client feedback"},
            files=[("new_file", ("test_v2.pdf", test_file, "application/pdf"))]
        )
    
    # Verify response
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["original_file_id"] == str(platform_file_id)
    assert "version_number" in response_data
    assert response_data["version_type"] == "revision"
    
    # Verify file upload service was called correctly
    mock_file_upload_service.upload_file_version.assert_called_once()
    call_args = mock_file_upload_service.upload_file_version.call_args[1]
    assert call_args["original_file_id"] == platform_file_id
    
    # Verify new version was created in the database
    result = await db_session.execute(
        select(FileVersion)
        .filter(FileVersion.original_file_id == platform_file_id)
        .order_by(FileVersion.version_number.desc())
    )
    versions = result.scalars().all()
    assert len(versions) == 2  # Original + new version
    assert versions[0].version_number == 2
    assert versions[0].version_type == "revision"