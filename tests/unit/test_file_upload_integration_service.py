# tests/unit/test_file_upload_integration_service.py

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID
from datetime import datetime
from io import BytesIO

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
import aiohttp

from src.services.file_upload_integration_service import (
    FileUploadIntegrationService,
    FileUploadContext,
    FileUploadError,
    FileUploadErrorHandler,
    RequirementFileMetadata,
    ReviewItemFileMetadata,
    ValidationResult,
    FileUploadResult
)
from src.models.requirement import Requirement
from src.models.requirement_file import RequirementFile
from src.models.internal_task import InternalTask
from src.models.review_item import ReviewItem, ReviewItemType


class TestFileUploadIntegrationService:
    """Test suite for FileUploadIntegrationService"""

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session"""
        session = AsyncMock(spec=AsyncSession)
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.add = Mock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create FileUploadIntegrationService instance"""
        return FileUploadIntegrationService(
            db_session=mock_db_session,
            platform_service_url="http://test-platform:8000"
        )

    @pytest.fixture
    def mock_upload_file(self):
        """Create mock UploadFile"""
        file_content = b"test file content"
        file = Mock(spec=UploadFile)
        file.filename = "test.pdf"
        file.content_type = "application/pdf"
        file.size = len(file_content)
        file.read = AsyncMock(return_value=file_content)
        file.seek = AsyncMock()
        return file

    @pytest.fixture
    def requirement_metadata(self):
        """Create requirement file metadata"""
        return RequirementFileMetadata(
            requirement_id=uuid4(),
            uploaded_by=uuid4(),
            file_description="Test requirement file"
        )

    @pytest.fixture
    def review_item_metadata(self):
        """Create review item file metadata"""
        return ReviewItemFileMetadata(
            task_id=uuid4(),
            review_item_type="STATIC_RENDER",
            sequence_number=1,
            description="Test review item"
        )

    async def test_validate_file_types_requirement_success(self, service, mock_upload_file):
        """Test successful file validation for requirement context"""
        mock_upload_file.filename = "document.pdf"
        files = [mock_upload_file]
        
        result = await service.validate_file_types(files, FileUploadContext.REQUIREMENT)
        
        assert result.is_valid is True
        assert len(result.errors) == 0

    async def test_validate_file_types_invalid_extension(self, service, mock_upload_file):
        """Test file validation with invalid extension"""
        mock_upload_file.filename = "malicious.exe"
        files = [mock_upload_file]
        
        result = await service.validate_file_types(files, FileUploadContext.REQUIREMENT)
        
        assert result.is_valid is False
        assert any("not allowed" in error for error in result.errors)

    async def test_validate_file_types_dangerous_extension(self, service, mock_upload_file):
        """Test file validation with dangerous extension"""
        mock_upload_file.filename = "script.bat"
        files = [mock_upload_file]
        
        result = await service.validate_file_types(files, FileUploadContext.REQUIREMENT)
        
        assert result.is_valid is False
        assert any("Dangerous file type" in error for error in result.errors)

    async def test_validate_file_types_oversized_file(self, service, mock_upload_file):
        """Test file validation with oversized file"""
        mock_upload_file.filename = "large.pdf"
        mock_upload_file.size = service.max_file_size + 1
        files = [mock_upload_file]
        
        result = await service.validate_file_types(files, FileUploadContext.REQUIREMENT)
        
        assert result.is_valid is False
        assert any("exceeds maximum size" in error for error in result.errors)

    async def test_validate_file_types_duplicate_filenames(self, service):
        """Test file validation with duplicate filenames"""
        file1 = Mock(spec=UploadFile)
        file1.filename = "test.pdf"
        file1.size = 1000
        
        file2 = Mock(spec=UploadFile)
        file2.filename = "test.pdf"  # Same filename
        file2.size = 1000
        
        files = [file1, file2]
        
        result = await service.validate_file_types(files, FileUploadContext.REQUIREMENT)
        
        assert result.is_valid is False
        assert any("Duplicate filename" in error for error in result.errors)

    async def test_validate_file_types_suspicious_patterns(self, service, mock_upload_file):
        """Test file validation with suspicious filename patterns"""
        mock_upload_file.filename = "../../../etc/passwd"
        files = [mock_upload_file]
        
        result = await service.validate_file_types(files, FileUploadContext.REQUIREMENT)
        
        assert len(result.warnings) > 0
        assert any("Suspicious filename pattern" in warning for warning in result.warnings)

    @patch('aiohttp.ClientSession.post')
    async def test_upload_requirement_files_success(
        self, mock_post, service, mock_upload_file, requirement_metadata, mock_db_session
    ):
        """Test successful requirement file upload"""
        # Mock requirement exists
        mock_requirement = Mock(spec=Requirement)
        mock_requirement.id = requirement_metadata.requirement_id
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_requirement
        
        # Mock platform service response
        platform_file_id = uuid4()
        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json.return_value = {"file_id": str(platform_file_id)}
        mock_post.return_value.__aenter__.return_value = mock_response
        
        files = [mock_upload_file]
        
        result = await service.upload_requirement_files(
            requirement_metadata.requirement_id,
            files,
            requirement_metadata
        )
        
        assert isinstance(result, FileUploadResult)
        assert len(result.platform_file_ids) == 1
        assert result.platform_file_ids[0] == platform_file_id
        assert len(result.uploaded_files) == 1
        assert result.uploaded_files[0]["file_name"] == "test.pdf"
        
        # Verify database operations
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

    async def test_upload_requirement_files_requirement_not_found(
        self, service, mock_upload_file, requirement_metadata, mock_db_session
    ):
        """Test requirement file upload when requirement doesn't exist"""
        # Mock requirement not found
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = None
        
        files = [mock_upload_file]
        
        with pytest.raises(FileUploadError) as exc_info:
            await service.upload_requirement_files(
                requirement_metadata.requirement_id,
                files,
                requirement_metadata
            )
        
        assert exc_info.value.service == "RequirementService"
        assert exc_info.value.error_type == "NOT_FOUND"

    async def test_upload_requirement_files_validation_error(
        self, service, requirement_metadata, mock_db_session
    ):
        """Test requirement file upload with validation error"""
        # Mock requirement exists
        mock_requirement = Mock(spec=Requirement)
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_requirement
        
        # Create invalid file
        invalid_file = Mock(spec=UploadFile)
        invalid_file.filename = "malicious.exe"
        invalid_file.size = 1000
        files = [invalid_file]
        
        with pytest.raises(FileUploadError) as exc_info:
            await service.upload_requirement_files(
                requirement_metadata.requirement_id,
                files,
                requirement_metadata
            )
        
        assert exc_info.value.service == "RequirementService"
        assert exc_info.value.error_type == "VALIDATION_ERROR"

    @patch('aiohttp.ClientSession.post')
    async def test_upload_review_item_files_success(
        self, mock_post, service, mock_upload_file, review_item_metadata, mock_db_session
    ):
        """Test successful review item file upload"""
        # Mock task exists
        mock_task = Mock(spec=InternalTask)
        mock_task.id = review_item_metadata.task_id
        mock_task.project_id = uuid4()
        mock_task.deliverable_id = uuid4()
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_task
        
        # Mock platform service response
        platform_file_id = uuid4()
        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json.return_value = {"file_id": str(platform_file_id)}
        mock_post.return_value.__aenter__.return_value = mock_response
        
        files = [mock_upload_file]
        
        result = await service.upload_review_item_files(
            review_item_metadata.task_id,
            files,
            review_item_metadata
        )
        
        assert isinstance(result, FileUploadResult)
        assert len(result.platform_file_ids) == 1
        assert result.platform_file_ids[0] == platform_file_id
        assert len(result.uploaded_files) == 1
        
        # Verify database operations
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

    async def test_upload_review_item_files_task_not_found(
        self, service, mock_upload_file, review_item_metadata, mock_db_session
    ):
        """Test review item file upload when task doesn't exist"""
        # Mock task not found
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = None
        
        files = [mock_upload_file]
        
        with pytest.raises(FileUploadError) as exc_info:
            await service.upload_review_item_files(
                review_item_metadata.task_id,
                files,
                review_item_metadata
            )
        
        assert exc_info.value.service == "ReviewItemService"
        assert exc_info.value.error_type == "NOT_FOUND"

    @patch('aiohttp.ClientSession.post')
    async def test_platform_service_connection_error(
        self, mock_post, service, mock_upload_file, requirement_metadata, mock_db_session
    ):
        """Test handling of platform service connection errors"""
        # Mock requirement exists
        mock_requirement = Mock(spec=Requirement)
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_requirement
        
        # Mock connection error
        mock_post.side_effect = aiohttp.ClientError("Connection failed")
        
        files = [mock_upload_file]
        
        with pytest.raises(FileUploadError) as exc_info:
            await service.upload_requirement_files(
                requirement_metadata.requirement_id,
                files,
                requirement_metadata
            )
        
        assert exc_info.value.service == "RequirementService"
        assert exc_info.value.error_type == "UPLOAD_ERROR"

    async def test_get_file_upload_statistics(self, service, mock_db_session):
        """Test getting file upload statistics"""
        # Mock database results
        mock_req_files = [
            Mock(file_type="pdf", file_size=1000),
            Mock(file_type="jpg", file_size=2000)
        ]
        mock_review_items = [Mock(), Mock(), Mock()]
        
        mock_db_session.execute.return_value.scalars.return_value.all.side_effect = [
            mock_req_files,
            mock_review_items
        ]
        
        stats = await service.get_file_upload_statistics()
        
        assert "total_uploads" in stats
        assert "context_distribution" in stats
        assert "file_type_distribution" in stats
        assert stats["context_distribution"]["requirement"]["count"] == 2
        assert stats["context_distribution"]["review_item"]["count"] == 3

    async def test_cleanup_orphaned_files(self, service, mock_db_session):
        """Test cleanup of orphaned files"""
        # Mock orphaned files
        mock_orphaned_file = Mock(spec=RequirementFile)
        mock_orphaned_file.id = uuid4()
        mock_orphaned_file.is_active = True
        
        mock_db_session.execute.return_value.scalars.return_value = [mock_orphaned_file]
        
        result = await service.cleanup_orphaned_files()
        
        assert "orphaned_requirement_files" in result
        assert "total_cleaned" in result
        assert mock_orphaned_file.is_active is False
        mock_db_session.commit.assert_called_once()


class TestFileUploadErrorHandler:
    """Test suite for FileUploadErrorHandler"""

    @pytest.fixture
    def error_handler(self):
        """Create FileUploadErrorHandler instance"""
        return FileUploadErrorHandler(max_retries=3, retry_delay=1.0)

    async def test_handle_requirement_upload_error_validation(self, error_handler):
        """Test handling requirement upload validation error"""
        error = FileUploadError(
            "RequirementService",
            "VALIDATION_ERROR",
            {"errors": ["Invalid file type"]}
        )
        
        result = await error_handler.handle_requirement_upload_error(error, uuid4())
        
        assert result["error_type"] == "VALIDATION_ERROR"
        assert result["service"] == "RequirementService"
        assert len(result["recovery_suggestions"]) > 0
        assert any("Check file types" in suggestion for suggestion in result["recovery_suggestions"])

    async def test_handle_review_item_upload_error_connection(self, error_handler):
        """Test handling review item upload connection error"""
        error = FileUploadError(
            "ReviewItemService",
            "CONNECTION_ERROR",
            {"error": "Network timeout"}
        )
        
        result = await error_handler.handle_review_item_upload_error(error, uuid4())
        
        assert result["error_type"] == "CONNECTION_ERROR"
        assert result["service"] == "ReviewItemService"
        assert any("network" in suggestion.lower() for suggestion in result["recovery_suggestions"])

    async def test_retry_failed_upload_success_on_retry(self, error_handler):
        """Test successful retry after initial failure"""
        call_count = 0
        
        async def mock_upload_function():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise FileUploadError("TestService", "TEMPORARY_ERROR", {})
            return "success"
        
        result = await error_handler.retry_failed_upload(mock_upload_function)
        
        assert result == "success"
        assert call_count == 2

    async def test_retry_failed_upload_all_attempts_fail(self, error_handler):
        """Test retry mechanism when all attempts fail"""
        async def mock_upload_function():
            raise FileUploadError("TestService", "PERSISTENT_ERROR", {})
        
        with pytest.raises(FileUploadError) as exc_info:
            await error_handler.retry_failed_upload(mock_upload_function)
        
        assert exc_info.value.error_type == "PERSISTENT_ERROR"

    async def test_handle_platform_service_error_413(self, error_handler):
        """Test handling platform service 413 (Payload Too Large) error"""
        error = FileUploadError(
            "PlatformService",
            "UPLOAD_FAILED",
            {"status": 413, "error": "Payload too large"}
        )
        
        result = await error_handler.handle_platform_service_error(error, "requirement")
        
        assert result["error_type"] == "UPLOAD_FAILED"
        assert any("size exceeds" in suggestion for suggestion in result["recovery_suggestions"])

    async def test_handle_platform_service_error_415(self, error_handler):
        """Test handling platform service 415 (Unsupported Media Type) error"""
        error = FileUploadError(
            "PlatformService",
            "UPLOAD_FAILED",
            {"status": 415, "error": "Unsupported media type"}
        )
        
        result = await error_handler.handle_platform_service_error(error, "review_item")
        
        assert result["error_type"] == "UPLOAD_FAILED"
        assert any("not supported" in suggestion for suggestion in result["recovery_suggestions"])

    async def test_handle_platform_service_error_500(self, error_handler):
        """Test handling platform service 500 (Internal Server Error) error"""
        error = FileUploadError(
            "PlatformService",
            "UPLOAD_FAILED",
            {"status": 500, "error": "Internal server error"}
        )
        
        result = await error_handler.handle_platform_service_error(error, "requirement")
        
        assert result["error_type"] == "UPLOAD_FAILED"
        assert any("internal errors" in suggestion for suggestion in result["recovery_suggestions"])


class TestFileUploadIntegrationServiceHealthChecks:
    """Test suite for health check and monitoring features"""

    @pytest.fixture
    def service(self):
        """Create FileUploadIntegrationService instance"""
        mock_session = AsyncMock(spec=AsyncSession)
        return FileUploadIntegrationService(
            db_session=mock_session,
            platform_service_url="http://test-platform:8000"
        )

    @patch('aiohttp.ClientSession.get')
    async def test_check_platform_service_health_success(self, mock_get, service):
        """Test successful platform service health check"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"status": "ok", "version": "1.0.0"}
        mock_response.headers = {"X-Response-Time": "50ms"}
        mock_get.return_value.__aenter__.return_value = mock_response
        
        result = await service.check_platform_service_health()
        
        assert result["status"] == "healthy"
        assert result["response_time_ms"] == "50ms"
        assert result["details"]["status"] == "ok"

    @patch('aiohttp.ClientSession.get')
    async def test_check_platform_service_health_unhealthy(self, mock_get, service):
        """Test platform service health check when service is unhealthy"""
        mock_response = AsyncMock()
        mock_response.status = 503
        mock_response.text.return_value = "Service unavailable"
        mock_get.return_value.__aenter__.return_value = mock_response
        
        result = await service.check_platform_service_health()
        
        assert result["status"] == "unhealthy"
        assert result["status_code"] == 503

    @patch('aiohttp.ClientSession.get')
    async def test_check_platform_service_health_unreachable(self, mock_get, service):
        """Test platform service health check when service is unreachable"""
        mock_get.side_effect = aiohttp.ClientError("Connection refused")
        
        result = await service.check_platform_service_health()
        
        assert result["status"] == "unreachable"
        assert "Connection refused" in result["error"]

    async def test_get_upload_queue_status(self, service):
        """Test getting upload queue status"""
        result = await service.get_upload_queue_status()
        
        assert "queued_uploads" in result
        assert "failed_uploads" in result
        assert "retry_queue_size" in result
        assert isinstance(result["queued_uploads"], int)


if __name__ == "__main__":
    pytest.main([__file__])