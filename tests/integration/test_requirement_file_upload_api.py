# tests/integration/test_requirement_file_upload_api.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from io import BytesIO

from fastapi.testclient import TestClient
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.main import app
from src.models.requirement import Requirement, RequirementType, RequirementStatus
from src.models.requirement_file import RequirementFile
from src.models.project import Project
from src.models.deliverable import Deliverable


@pytest.fixture
def client():
    """Test client for API testing"""
    return TestClient(app)


@pytest.fixture
def mock_auth_context():
    """Mock authentication context"""
    context = MagicMock()
    context.user_id = uuid4()
    context.business_id = "test-business"
    context.has_permission.return_value = True
    context.has_business_access.return_value = True
    return context


@pytest.fixture
def sample_requirement():
    """Sample requirement for testing"""
    return Requirement(
        id=uuid4(),
        project_id=uuid4(),
        deliverable_id=uuid4(),
        requirement_name="Test File Upload Requirement",
        requirement_type=RequirementType.FILE_UPLOAD,
        status=RequirementStatus.PENDING,
        is_mandatory=True
    )


@pytest.fixture
def sample_requirement_files():
    """Sample requirement files for testing"""
    requirement_id = uuid4()
    return [
        RequirementFile(
            id=uuid4(),
            requirement_id=requirement_id,
            platform_file_id=uuid4(),
            file_name="test_document.pdf",
            file_type="pdf",
            file_size=1024,
            is_active=True
        ),
        RequirementFile(
            id=uuid4(),
            requirement_id=requirement_id,
            platform_file_id=uuid4(),
            file_name="test_image.png",
            file_type="png",
            file_size=2048,
            is_active=True
        )
    ]


class TestRequirementFileUploadAPI:
    """Integration tests for requirement file upload API endpoints"""

    @patch('src.api.requirements.controllers.require_resource_permission')
    @patch('src.api.requirements.controllers.get_db_session')
    @patch('src.services.requirement_service.RequirementService')
    def test_upload_requirement_files_success(
        self,
        mock_service_class,
        mock_get_db,
        mock_auth,
        client,
        mock_auth_context,
        sample_requirement_files
    ):
        """Test successful file upload to requirement"""
        
        # Setup mocks
        mock_auth.return_value = mock_auth_context
        mock_db = AsyncMock()
        mock_get_db.return_value = mock_db
        
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        mock_service.upload_requirement_files.return_value = sample_requirement_files
        
        # Prepare test files
        requirement_id = str(uuid4())
        files = [
            ("files", ("test.pdf", BytesIO(b"PDF content"), "application/pdf")),
            ("files", ("test.png", BytesIO(b"PNG content"), "image/png"))
        ]
        
        # Make request
        response = client.post(
            f"/api/v1/requirements/{requirement_id}/files",
            files=files
        )
        
        # Verify response
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert "Successfully uploaded" in data["message"]
        assert len(data["uploaded_files"]) == 2
        assert len(data["platform_file_ids"]) == 2

    @patch('src.api.requirements.controllers.require_resource_permission')
    @patch('src.api.requirements.controllers.get_db_session')
    @patch('src.services.requirement_service.RequirementService')
    def test_upload_requirement_files_validation_error(
        self,
        mock_service_class,
        mock_get_db,
        mock_auth,
        client,
        mock_auth_context
    ):
        """Test file upload with validation error"""
        
        # Setup mocks
        mock_auth.return_value = mock_auth_context
        mock_db = AsyncMock()
        mock_get_db.return_value = mock_db
        
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        mock_service.upload_requirement_files.side_effect = ValueError("Invalid file type")
        
        # Prepare test files
        requirement_id = str(uuid4())
        files = [
            ("files", ("malicious.exe", BytesIO(b"EXE content"), "application/octet-stream"))
        ]
        
        # Make request
        response = client.post(
            f"/api/v1/requirements/{requirement_id}/files",
            files=files
        )
        
        # Verify response
        assert response.status_code == 422
        data = response.json()
        assert "Invalid file type" in data["detail"]

    @patch('src.api.requirements.controllers.require_resource_permission')
    @patch('src.api.requirements.controllers.get_db_session')
    @patch('src.services.requirement_service.RequirementService')
    def test_upload_requirement_files_no_files(
        self,
        mock_service_class,
        mock_get_db,
        mock_auth,
        client,
        mock_auth_context
    ):
        """Test file upload with no files provided"""
        
        # Setup mocks
        mock_auth.return_value = mock_auth_context
        mock_db = AsyncMock()
        mock_get_db.return_value = mock_db
        
        # Make request without files
        requirement_id = str(uuid4())
        response = client.post(f"/api/v1/requirements/{requirement_id}/files")
        
        # Verify response
        assert response.status_code == 422

    @patch('src.api.requirements.controllers.require_resource_permission')
    @patch('src.api.requirements.controllers.get_db_session')
    @patch('src.services.requirement_service.RequirementService')
    def test_get_requirement_files_success(
        self,
        mock_service_class,
        mock_get_db,
        mock_auth,
        client,
        mock_auth_context,
        sample_requirement_files
    ):
        """Test successful retrieval of requirement files"""
        
        # Setup mocks
        mock_auth.return_value = mock_auth_context
        mock_db = AsyncMock()
        mock_get_db.return_value = mock_db
        
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        mock_service.get_requirement_files.return_value = sample_requirement_files
        
        # Make request
        requirement_id = str(uuid4())
        response = client.get(f"/api/v1/requirements/{requirement_id}/files")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all("file_name" in file for file in data)
        assert all("platform_file_id" in file for file in data)

    @patch('src.api.requirements.controllers.require_resource_permission')
    @patch('src.api.requirements.controllers.get_db_session')
    @patch('src.services.requirement_service.RequirementService')
    def test_get_requirement_files_with_inactive(
        self,
        mock_service_class,
        mock_get_db,
        mock_auth,
        client,
        mock_auth_context,
        sample_requirement_files
    ):
        """Test retrieval of requirement files including inactive ones"""
        
        # Setup mocks
        mock_auth.return_value = mock_auth_context
        mock_db = AsyncMock()
        mock_get_db.return_value = mock_db
        
        # Add inactive file
        inactive_file = RequirementFile(
            id=uuid4(),
            requirement_id=sample_requirement_files[0].requirement_id,
            platform_file_id=uuid4(),
            file_name="deleted_file.pdf",
            file_type="pdf",
            file_size=512,
            is_active=False
        )
        all_files = sample_requirement_files + [inactive_file]
        
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        mock_service.get_requirement_files.return_value = all_files
        
        # Make request with include_inactive=true
        requirement_id = str(uuid4())
        response = client.get(
            f"/api/v1/requirements/{requirement_id}/files?include_inactive=true"
        )
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        
        # Verify service was called with correct parameter
        mock_service.get_requirement_files.assert_called_once_with(
            requirement_id=uuid4(requirement_id),
            include_inactive=True
        )

    @patch('src.api.requirements.controllers.require_resource_permission')
    @patch('src.api.requirements.controllers.get_db_session')
    @patch('src.services.requirement_service.RequirementService')
    def test_delete_requirement_file_success(
        self,
        mock_service_class,
        mock_get_db,
        mock_auth,
        client,
        mock_auth_context
    ):
        """Test successful deletion of requirement file"""
        
        # Setup mocks
        mock_auth.return_value = mock_auth_context
        mock_db = AsyncMock()
        mock_get_db.return_value = mock_db
        
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        mock_service.delete_requirement_file.return_value = True
        
        # Make request
        requirement_id = str(uuid4())
        file_id = str(uuid4())
        response = client.delete(
            f"/api/v1/requirements/{requirement_id}/files/{file_id}"
        )
        
        # Verify response
        assert response.status_code == 204
        
        # Verify service was called
        mock_service.delete_requirement_file.assert_called_once()

    @patch('src.api.requirements.controllers.require_resource_permission')
    @patch('src.api.requirements.controllers.get_db_session')
    @patch('src.services.requirement_service.RequirementService')
    def test_delete_requirement_file_not_found(
        self,
        mock_service_class,
        mock_get_db,
        mock_auth,
        client,
        mock_auth_context
    ):
        """Test deletion of non-existent requirement file"""
        
        # Setup mocks
        mock_auth.return_value = mock_auth_context
        mock_db = AsyncMock()
        mock_get_db.return_value = mock_db
        
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        mock_service.delete_requirement_file.return_value = False
        
        # Make request
        requirement_id = str(uuid4())
        file_id = str(uuid4())
        response = client.delete(
            f"/api/v1/requirements/{requirement_id}/files/{file_id}"
        )
        
        # Verify response
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    @patch('src.api.requirements.controllers.require_resource_permission')
    def test_upload_files_unauthorized(self, mock_auth, client):
        """Test file upload without proper authorization"""
        
        # Setup mock to deny permission
        mock_auth.side_effect = Exception("Unauthorized")
        
        # Make request
        requirement_id = str(uuid4())
        files = [
            ("files", ("test.pdf", BytesIO(b"PDF content"), "application/pdf"))
        ]
        
        response = client.post(
            f"/api/v1/requirements/{requirement_id}/files",
            files=files
        )
        
        # Verify response
        assert response.status_code in [401, 403, 500]  # Depending on auth implementation

    @patch('src.api.requirements.controllers.require_resource_permission')
    @patch('src.api.requirements.controllers.get_db_session')
    @patch('src.services.requirement_service.RequirementService')
    def test_upload_files_large_file(
        self,
        mock_service_class,
        mock_get_db,
        mock_auth,
        client,
        mock_auth_context
    ):
        """Test file upload with oversized file"""
        
        # Setup mocks
        mock_auth.return_value = mock_auth_context
        mock_db = AsyncMock()
        mock_get_db.return_value = mock_db
        
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        mock_service.upload_requirement_files.side_effect = ValueError(
            "File exceeds maximum size limit"
        )
        
        # Prepare large file
        requirement_id = str(uuid4())
        large_content = b"x" * (200 * 1024 * 1024)  # 200MB
        files = [
            ("files", ("large_file.pdf", BytesIO(large_content), "application/pdf"))
        ]
        
        # Make request
        response = client.post(
            f"/api/v1/requirements/{requirement_id}/files",
            files=files
        )
        
        # Verify response
        assert response.status_code == 422
        data = response.json()
        assert "size limit" in data["detail"].lower()

    @patch('src.api.requirements.controllers.require_resource_permission')
    @patch('src.api.requirements.controllers.get_db_session')
    @patch('src.services.requirement_service.RequirementService')
    def test_get_files_empty_result(
        self,
        mock_service_class,
        mock_get_db,
        mock_auth,
        client,
        mock_auth_context
    ):
        """Test getting files when no files exist"""
        
        # Setup mocks
        mock_auth.return_value = mock_auth_context
        mock_db = AsyncMock()
        mock_get_db.return_value = mock_db
        
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        mock_service.get_requirement_files.return_value = []
        
        # Make request
        requirement_id = str(uuid4())
        response = client.get(f"/api/v1/requirements/{requirement_id}/files")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data == []