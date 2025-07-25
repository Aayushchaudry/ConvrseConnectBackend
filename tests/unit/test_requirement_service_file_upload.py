# tests/unit/test_requirement_service_file_upload.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID
from io import BytesIO

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.requirement_service import RequirementService
from src.models.requirement import Requirement, RequirementType, RequirementStatus
from src.models.requirement_file import RequirementFile


@pytest.fixture
def mock_db_session():
    """Mock database session"""
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def requirement_service(mock_db_session):
    """Create RequirementService instance with mocked dependencies"""
    return RequirementService(mock_db_session)


@pytest.fixture
def sample_requirement():
    """Sample requirement for testing"""
    return Requirement(
        id=uuid4(),
        project_id=uuid4(),
        deliverable_id=uuid4(),
        requirement_name="Test Requirement",
        requirement_type=RequirementType.FILE_UPLOAD,
        status=RequirementStatus.PENDING,
        is_mandatory=True
    )


@pytest.fixture
def sample_upload_files():
    """Sample upload files for testing"""
    files = []
    
    # Create mock PDF file
    pdf_content = b"Mock PDF content"
    pdf_file = UploadFile(
        filename="test_document.pdf",
        file=BytesIO(pdf_content),
        size=len(pdf_content)
    )
    pdf_file.content_type = "application/pdf"
    files.append(pdf_file)
    
    # Create mock image file
    img_content = b"Mock image content"
    img_file = UploadFile(
        filename="test_image.png",
        file=BytesIO(img_content),
        size=len(img_content)
    )
    img_file.content_type = "image/png"
    files.append(img_file)
    
    return files


class TestRequirementServiceFileUpload:
    """Test cases for requirement file upload functionality"""

    @pytest.mark.asyncio
    async def test_upload_requirement_files_success(
        self, 
        requirement_service, 
        mock_db_session,
        sample_requirement,
        sample_upload_files
    ):
        """Test successful requirement file upload"""
        
        # Mock requirement lookup
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = sample_requirement
        mock_db_session.execute.return_value = mock_result
        
        # Mock file upload service
        with patch('src.services.requirement_service.FileUploadIntegrationService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            
            # Mock upload result
            mock_upload_result = MagicMock()
            mock_upload_result.platform_file_ids = [uuid4(), uuid4()]
            mock_service.upload_requirement_files.return_value = mock_upload_result
            
            # Mock get_requirement_files
            requirement_service.get_requirement_files = AsyncMock(return_value=[])
            requirement_service.update_requirement_status = AsyncMock(return_value=sample_requirement)
            
            # Execute upload
            user_context = {"user_id": str(uuid4())}
            result = await requirement_service.upload_requirement_files(
                sample_requirement.id,
                sample_upload_files,
                user_context
            )
            
            # Verify calls
            mock_service.upload_requirement_files.assert_called_once()
            requirement_service.update_requirement_status.assert_called_once_with(
                sample_requirement.id,
                RequirementStatus.RECEIVED,
                mock_upload_result.platform_file_ids
            )
            
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_upload_requirement_files_requirement_not_found(
        self,
        requirement_service,
        mock_db_session,
        sample_upload_files
    ):
        """Test upload when requirement doesn't exist"""
        
        # Mock requirement not found
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result
        
        # Execute and expect error
        with pytest.raises(ValueError, match="Requirement with ID .* not found"):
            await requirement_service.upload_requirement_files(
                uuid4(),
                sample_upload_files
            )

    @pytest.mark.asyncio
    async def test_upload_requirement_files_wrong_type(
        self,
        requirement_service,
        mock_db_session,
        sample_upload_files
    ):
        """Test upload when requirement is not FILE_UPLOAD type"""
        
        # Create requirement with wrong type
        wrong_type_requirement = Requirement(
            id=uuid4(),
            project_id=uuid4(),
            requirement_name="Text Requirement",
            requirement_type=RequirementType.TEXT_INPUT,
            status=RequirementStatus.PENDING
        )
        
        # Mock requirement lookup
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = wrong_type_requirement
        mock_db_session.execute.return_value = mock_result
        
        # Execute and expect error
        with pytest.raises(ValueError, match="is not of type FILE_UPLOAD"):
            await requirement_service.upload_requirement_files(
                wrong_type_requirement.id,
                sample_upload_files
            )

    @pytest.mark.asyncio
    async def test_validate_requirement_files_success(
        self,
        requirement_service,
        sample_upload_files
    ):
        """Test successful file validation"""
        
        # Should not raise any exception
        await requirement_service._validate_requirement_files(sample_upload_files)

    @pytest.mark.asyncio
    async def test_validate_requirement_files_no_files(
        self,
        requirement_service
    ):
        """Test validation with no files"""
        
        with pytest.raises(ValueError, match="No files provided for upload"):
            await requirement_service._validate_requirement_files([])

    @pytest.mark.asyncio
    async def test_validate_requirement_files_invalid_extension(
        self,
        requirement_service
    ):
        """Test validation with invalid file extension"""
        
        # Create file with invalid extension
        invalid_file = UploadFile(
            filename="malicious.exe",
            file=BytesIO(b"content"),
            size=7
        )
        
        with pytest.raises(ValueError, match="File type 'exe' not allowed"):
            await requirement_service._validate_requirement_files([invalid_file])

    @pytest.mark.asyncio
    async def test_validate_requirement_files_no_extension(
        self,
        requirement_service
    ):
        """Test validation with file without extension"""
        
        # Create file without extension
        no_ext_file = UploadFile(
            filename="noextension",
            file=BytesIO(b"content"),
            size=7
        )
        
        with pytest.raises(ValueError, match="File must have an extension"):
            await requirement_service._validate_requirement_files([no_ext_file])

    @pytest.mark.asyncio
    async def test_validate_requirement_files_duplicate_names(
        self,
        requirement_service
    ):
        """Test validation with duplicate filenames"""
        
        # Create files with same name
        file1 = UploadFile(
            filename="duplicate.pdf",
            file=BytesIO(b"content1"),
            size=8
        )
        file2 = UploadFile(
            filename="duplicate.pdf",
            file=BytesIO(b"content2"),
            size=8
        )
        
        with pytest.raises(ValueError, match="Duplicate filename"):
            await requirement_service._validate_requirement_files([file1, file2])

    @pytest.mark.asyncio
    async def test_validate_requirement_files_too_large(
        self,
        requirement_service
    ):
        """Test validation with file too large"""
        
        # Create oversized file
        large_file = UploadFile(
            filename="large.pdf",
            file=BytesIO(b"content"),
            size=200 * 1024 * 1024  # 200MB
        )
        
        with pytest.raises(ValueError, match="exceeds maximum size limit"):
            await requirement_service._validate_requirement_files([large_file])

    @pytest.mark.asyncio
    async def test_update_requirement_status(
        self,
        requirement_service,
        mock_db_session,
        sample_requirement
    ):
        """Test updating requirement status"""
        
        # Mock requirement lookup
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = sample_requirement
        mock_db_session.execute.return_value = mock_result
        
        # Execute status update
        file_ids = [uuid4(), uuid4()]
        result = await requirement_service.update_requirement_status(
            sample_requirement.id,
            RequirementStatus.RECEIVED,
            file_ids
        )
        
        # Verify status updated
        assert sample_requirement.status == RequirementStatus.RECEIVED
        assert "2 file(s) uploaded" in sample_requirement.notes
        
        # Verify database operations
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once_with(sample_requirement)

    @pytest.mark.asyncio
    async def test_get_requirement_files(
        self,
        requirement_service,
        mock_db_session
    ):
        """Test getting requirement files"""
        
        requirement_id = uuid4()
        
        # Mock file results
        mock_files = [
            RequirementFile(
                id=uuid4(),
                requirement_id=requirement_id,
                platform_file_id=uuid4(),
                file_name="test1.pdf",
                is_active=True
            ),
            RequirementFile(
                id=uuid4(),
                requirement_id=requirement_id,
                platform_file_id=uuid4(),
                file_name="test2.png",
                is_active=True
            )
        ]
        
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = mock_files
        mock_db_session.execute.return_value = mock_result
        
        # Execute
        result = await requirement_service.get_requirement_files(requirement_id)
        
        # Verify
        assert len(result) == 2
        assert all(isinstance(f, RequirementFile) for f in result)

    @pytest.mark.asyncio
    async def test_delete_requirement_file(
        self,
        requirement_service,
        mock_db_session
    ):
        """Test soft deleting a requirement file"""
        
        requirement_id = uuid4()
        file_id = uuid4()
        
        # Mock file lookup
        mock_file = RequirementFile(
            id=file_id,
            requirement_id=requirement_id,
            platform_file_id=uuid4(),
            file_name="test.pdf",
            is_active=True
        )
        
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = mock_file
        mock_db_session.execute.return_value = mock_result
        
        # Execute deletion
        result = await requirement_service.delete_requirement_file(
            requirement_id,
            file_id
        )
        
        # Verify
        assert result is True
        assert mock_file.is_active is False
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_requirement_file_not_found(
        self,
        requirement_service,
        mock_db_session
    ):
        """Test deleting non-existent file"""
        
        # Mock file not found
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result
        
        # Execute deletion
        result = await requirement_service.delete_requirement_file(
            uuid4(),
            uuid4()
        )
        
        # Verify
        assert result is False
        mock_db_session.commit.assert_not_called()