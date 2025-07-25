# tests/integration/test_file_upload_integration.py

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4
from io import BytesIO

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.file_upload_integration_service import (
    FileUploadIntegrationService,
    FileUploadContext,
    RequirementFileMetadata,
    ReviewItemFileMetadata
)


class TestFileUploadIntegrationFlow:
    """Integration tests for file upload workflows"""

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

    def create_mock_upload_file(self, filename: str, content: bytes, content_type: str = None):
        """Helper to create mock UploadFile"""
        file = Mock(spec=UploadFile)
        file.filename = filename
        file.content_type = content_type
        file.size = len(content)
        file.read = AsyncMock(return_value=content)
        file.seek = AsyncMock()
        return file

    async def test_file_validation_workflow(self, service):
        """Test complete file validation workflow"""
        # Test valid files
        valid_files = [
            self.create_mock_upload_file("document.pdf", b"PDF content", "application/pdf"),
            self.create_mock_upload_file("image.jpg", b"JPEG content", "image/jpeg"),
            self.create_mock_upload_file("model.dwg", b"CAD content", "application/dwg")
        ]
        
        result = await service.validate_file_types(valid_files, FileUploadContext.REQUIREMENT)
        assert result.is_valid is True
        assert len(result.errors) == 0
        
        # Test invalid files
        invalid_files = [
            self.create_mock_upload_file("malware.exe", b"Executable content"),
            self.create_mock_upload_file("script.bat", b"Batch script"),
        ]
        
        result = await service.validate_file_types(invalid_files, FileUploadContext.REQUIREMENT)
        assert result.is_valid is False
        assert len(result.errors) > 0

    async def test_file_type_context_validation(self, service):
        """Test that file types are validated correctly for different contexts"""
        # Video file should be valid for review items but not requirements
        video_file = self.create_mock_upload_file("demo.mp4", b"Video content", "video/mp4")
        
        # Should be valid for review items
        result = await service.validate_file_types([video_file], FileUploadContext.REVIEW_ITEM)
        assert result.is_valid is True
        
        # Should be invalid for requirements
        result = await service.validate_file_types([video_file], FileUploadContext.REQUIREMENT)
        assert result.is_valid is False

    async def test_file_size_validation(self, service):
        """Test file size validation"""
        # Create oversized file
        large_content = b"x" * (service.max_file_size + 1)
        large_file = self.create_mock_upload_file("large.pdf", large_content)
        
        result = await service.validate_file_types([large_file], FileUploadContext.REQUIREMENT)
        assert result.is_valid is False
        assert any("exceeds maximum size" in error for error in result.errors)

    async def test_suspicious_filename_detection(self, service):
        """Test detection of suspicious filename patterns"""
        suspicious_files = [
            self.create_mock_upload_file("../../../etc/passwd", b"content"),
            self.create_mock_upload_file("file<script>alert()</script>.pdf", b"content"),
            self.create_mock_upload_file("file|pipe.pdf", b"content")
        ]
        
        for file in suspicious_files:
            result = await service.validate_file_types([file], FileUploadContext.REQUIREMENT)
            assert len(result.warnings) > 0
            assert any("Suspicious filename pattern" in warning for warning in result.warnings)

    async def test_duplicate_filename_detection(self, service):
        """Test detection of duplicate filenames in upload batch"""
        file1 = self.create_mock_upload_file("document.pdf", b"content1")
        file2 = self.create_mock_upload_file("document.pdf", b"content2")  # Same name
        
        result = await service.validate_file_types([file1, file2], FileUploadContext.REQUIREMENT)
        assert result.is_valid is False
        assert any("Duplicate filename" in error for error in result.errors)

    async def test_empty_file_warning(self, service):
        """Test warning for empty files"""
        empty_file = self.create_mock_upload_file("empty.pdf", b"")
        
        result = await service.validate_file_types([empty_file], FileUploadContext.REQUIREMENT)
        assert len(result.warnings) > 0
        assert any("Empty file detected" in warning for warning in result.warnings)

    async def test_mime_type_mismatch_warning(self, service):
        """Test warning for MIME type mismatches"""
        # PDF file with wrong MIME type
        file = self.create_mock_upload_file("document.pdf", b"PDF content", "text/plain")
        
        result = await service.validate_file_types([file], FileUploadContext.REQUIREMENT)
        assert len(result.warnings) > 0
        assert any("MIME type mismatch" in warning for warning in result.warnings)

    async def test_total_upload_size_validation(self, service):
        """Test validation of total upload size"""
        # Create files that exceed total size limit
        large_content = b"x" * (service.max_total_size // 2 + 1)
        file1 = self.create_mock_upload_file("large1.pdf", large_content)
        file2 = self.create_mock_upload_file("large2.pdf", large_content)
        
        result = await service.validate_file_types([file1, file2], FileUploadContext.REQUIREMENT)
        assert result.is_valid is False
        assert any("Total upload size exceeds limit" in error for error in result.errors)

    async def test_file_extension_extraction(self, service):
        """Test file extension extraction logic"""
        test_cases = [
            ("document.pdf", "pdf"),
            ("image.JPEG", "jpeg"),  # Should be lowercase
            ("archive.tar.gz", "gz"),  # Should get last extension
            ("noextension", ""),  # No extension
            ("", ""),  # Empty filename
            ("file.", ""),  # Ends with dot
        ]
        
        for filename, expected_ext in test_cases:
            actual_ext = service._get_file_extension(filename)
            assert actual_ext == expected_ext, f"Failed for {filename}: expected {expected_ext}, got {actual_ext}"

    async def test_suspicious_pattern_detection(self, service):
        """Test suspicious pattern detection logic"""
        suspicious_filenames = [
            "../../../etc/passwd",  # Directory traversal
            "file<script>",  # HTML tags
            "file|pipe",  # Pipe character
            "file:drive",  # Colon
            "file*wildcard",  # Wildcard
            "file?query",  # Question mark
            'file"quote',  # Quote
            "file\x00null",  # Null byte
            "scriptexec.txt",  # Suspicious keyword
            "cmdcommand.pdf",  # Suspicious keyword
        ]
        
        for filename in suspicious_filenames:
            is_suspicious = service._contains_suspicious_patterns(filename)
            assert is_suspicious is True, f"Should detect {filename} as suspicious"
        
        # Test safe filenames
        safe_filenames = [
            "document.pdf",
            "image.jpg",
            "model.dwg",
            "presentation.pptx",
            "data.xlsx"
        ]
        
        for filename in safe_filenames:
            is_suspicious = service._contains_suspicious_patterns(filename)
            assert is_suspicious is False, f"Should not detect {filename} as suspicious"


class TestFileUploadServiceConfiguration:
    """Test service configuration and initialization"""

    def test_service_initialization_defaults(self):
        """Test service initialization with default values"""
        mock_session = AsyncMock(spec=AsyncSession)
        service = FileUploadIntegrationService(db_session=mock_session)
        
        assert service.platform_service_url == "http://platform-service:8000"
        assert service.max_retries == 3
        assert service.retry_delay_base == 1.0
        assert service.retry_backoff_factor == 2.0
        assert service.max_file_size == 100 * 1024 * 1024  # 100MB
        assert service.max_total_size == 500 * 1024 * 1024  # 500MB

    def test_service_initialization_custom_values(self):
        """Test service initialization with custom values"""
        mock_session = AsyncMock(spec=AsyncSession)
        service = FileUploadIntegrationService(
            db_session=mock_session,
            platform_service_url="http://custom-platform:9000"
        )
        
        assert service.platform_service_url == "http://custom-platform:9000"

    def test_allowed_file_types_configuration(self):
        """Test that allowed file types are configured correctly"""
        mock_session = AsyncMock(spec=AsyncSession)
        service = FileUploadIntegrationService(db_session=mock_session)
        
        # Check requirement allowed types
        requirement_types = service.requirement_allowed_types
        assert 'pdf' in requirement_types
        assert 'jpg' in requirement_types
        assert 'dwg' in requirement_types
        assert 'mp4' not in requirement_types  # Video not allowed for requirements
        
        # Check review item allowed types
        review_types = service.review_item_allowed_types
        assert 'pdf' in review_types
        assert 'jpg' in review_types
        assert 'mp4' in review_types  # Video allowed for review items
        assert 'dwg' not in review_types  # CAD not typically needed for review items

    def test_dangerous_extensions_configuration(self):
        """Test that dangerous extensions are properly configured"""
        mock_session = AsyncMock(spec=AsyncSession)
        service = FileUploadIntegrationService(db_session=mock_session)
        
        dangerous_extensions = service.dangerous_extensions
        assert 'exe' in dangerous_extensions
        assert 'bat' in dangerous_extensions
        assert 'sh' in dangerous_extensions
        assert 'cmd' in dangerous_extensions
        assert 'scr' in dangerous_extensions
        assert 'vbs' in dangerous_extensions
        assert 'js' in dangerous_extensions
        assert 'jar' in dangerous_extensions

    def test_mime_type_mappings(self):
        """Test MIME type mappings configuration"""
        mock_session = AsyncMock(spec=AsyncSession)
        service = FileUploadIntegrationService(db_session=mock_session)
        
        mappings = service.mime_type_mappings
        assert mappings['pdf'] == 'application/pdf'
        assert mappings['jpg'] == 'image/jpeg'
        assert mappings['jpeg'] == 'image/jpeg'
        assert mappings['png'] == 'image/png'
        assert mappings['mp4'] == 'video/mp4'


if __name__ == "__main__":
    pytest.main([__file__])