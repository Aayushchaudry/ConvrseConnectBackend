"""
Unit tests for enhanced project output generation functionality.
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
from src.models.review_item import ReviewItem, ReviewStatus, ReviewItemType
from src.models.review_item_file import ReviewItemFile
from src.models.project_output import ProjectOutput
from src.models.file_version import FileVersion, VersionType
from src.services.project_output_service import ProjectOutputService
from src.services.platform_file_service import PlatformFileService


@pytest.mark.asyncio
async def test_generate_outputs_for_approved_deliverables():
    """Test automatically generating outputs for all deliverables with approved reviews."""
    # Setup
    project_id = uuid.uuid4()
    deliverable_id1 = uuid.uuid4()
    deliverable_id2 = uuid.uuid4()
    
    # Mock session
    session = AsyncMock()
    
    # Mock deliverables
    deliverable1 = Deliverable(
        id=deliverable_id1,
        project_id=project_id,
        deliverable_name="Test Deliverable 1",
        status=DeliverableStatus.IN_REVIEW.value
    )
    
    deliverable2 = Deliverable(
        id=deliverable_id2,
        project_id=project_id,
        deliverable_name="Test Deliverable 2",
        status=DeliverableStatus.IN_REVIEW.value
    )
    
    # Mock query results
    deliverables_result = AsyncMock()
    deliverables_result.scalars.return_value.all.return_value = [deliverable1, deliverable2]
    
    # For first deliverable - all reviews approved, no existing output
    all_approved_result1 = AsyncMock()
    all_approved_result1.scalar.return_value = 1  # All reviews approved
    
    output_result1 = AsyncMock()
    output_result1.scalar_one_or_none.return_value = None  # No existing output
    
    # For second deliverable - not all reviews approved
    all_approved_result2 = AsyncMock()
    all_approved_result2.scalar.return_value = 0  # Not all reviews approved
    
    # Setup session execute to return our mocked results
    session.execute.side_effect = [
        deliverables_result,  # For getting deliverables
        all_approved_result1,  # For checking all reviews approved for deliverable 1 (total count)
        all_approved_result1,  # For checking all reviews approved for deliverable 1 (approved count)
        output_result1,  # For checking existing output for deliverable 1
        all_approved_result2,  # For checking all reviews approved for deliverable 2 (total count)
    ]
    
    # Create mocks for the methods we'll call
    with patch.object(
        ProjectOutputService, 
        'generate_project_output_for_deliverable',
        return_value=ProjectOutput(
            id=uuid.uuid4(),
            deliverable_id=deliverable_id1,
            project_id=project_id,
            output_name="Test Output"
        )
    ) as mock_generate:
        with patch.object(
            ProjectOutputService,
            'mark_files_as_final_versions',
            return_value=True
        ) as mock_mark_final:
            with patch.object(
                ProjectOutputService,
                'compile_final_deliverable',
                return_value=True
            ) as mock_compile:
                with patch.object(
                    ProjectOutputService,
                    'process_project_completion',
                    return_value=False
                ) as mock_process_completion:
                    # Create service with mocked session
                    service = ProjectOutputService(lambda: session)
                    
                    # Execute
                    result = await service.generate_outputs_for_approved_deliverables()
                    
                    # Assert
                    assert len(result) == 1
                    assert deliverable_id1 in result
                    mock_generate.assert_called_once_with(deliverable_id1)
                    mock_mark_final.assert_called_once_with(deliverable_id1)
                    mock_compile.assert_called_once()
                    mock_process_completion.assert_called_once_with(project_id)


@pytest.mark.asyncio
async def test_process_project_completion():
    """Test processing project completion when all deliverables are delivered."""
    # Setup
    project_id = uuid.uuid4()
    
    # Mock session
    session = AsyncMock()
    
    # Mock project
    project = Project(
        id=project_id,
        project_name="Test Project",
        status=ProjectStatus.IN_PROGRESS.value
    )
    
    # Mock project outputs
    output1 = ProjectOutput(
        id=uuid.uuid4(),
        project_id=project_id,
        deliverable_id=uuid.uuid4(),
        output_name="Output 1",
        output_url="https://example.com/output1"
    )
    
    output2 = ProjectOutput(
        id=uuid.uuid4(),
        project_id=project_id,
        deliverable_id=uuid.uuid4(),
        output_name="Output 2",
        output_url="https://example.com/output2"
    )
    
    # Mock deliverables
    deliverable1 = Deliverable(
        id=output1.deliverable_id,
        project_id=project_id,
        deliverable_name="Deliverable 1",
        status=DeliverableStatus.DELIVERED.value
    )
    
    deliverable2 = Deliverable(
        id=output2.deliverable_id,
        project_id=project_id,
        deliverable_name="Deliverable 2",
        status=DeliverableStatus.DELIVERED.value
    )
    
    # Mock query results
    project_result = AsyncMock()
    project_result.scalar_one_or_none.return_value = project
    
    total_count_result = AsyncMock()
    total_count_result.scalar.return_value = 2  # Total deliverables
    
    delivered_count_result = AsyncMock()
    delivered_count_result.scalar.return_value = 2  # All deliverables delivered
    
    outputs_result = AsyncMock()
    outputs_result.scalars.return_value.all.return_value = [output1, output2]
    
    deliverables_result = AsyncMock()
    deliverables_result.scalars.return_value.all.return_value = [deliverable1, deliverable2]
    
    # Setup session execute to return our mocked results
    session.execute.side_effect = [
        project_result,  # For getting project
        total_count_result,  # For checking project completion (total count)
        delivered_count_result,  # For checking project completion (delivered count)
        outputs_result,  # For getting project outputs
        deliverables_result  # For getting deliverables
    ]
    
    # Create mock for platform file service
    platform_file_service = AsyncMock()
    platform_file_service.upload_file.return_value = uuid.uuid4()
    
    # Create mock for event bus
    event_bus = AsyncMock()
    
    # Create service with mocked dependencies
    service = ProjectOutputService(lambda: session, event_bus, platform_file_service)
    
    # Execute
    with patch('tempfile.TemporaryDirectory'):
        with patch('zipfile.ZipFile'):
            with patch('os.makedirs'):
                with patch('os.path.join', return_value='/mock/path'):
                    with patch('open', create=True):
                        result = await service.process_project_completion(project_id)
    
    # Assert
    assert result is True
    assert project.status == ProjectStatus.COMPLETED.value
    assert session.add.call_count == 1
    assert session.commit.call_count == 1
    event_bus.publish.assert_called_once()


@pytest.mark.asyncio
async def test_compile_final_deliverable():
    """Test compiling final deliverable with file organization."""
    # Setup
    deliverable_id = uuid.uuid4()
    project_id = uuid.uuid4()
    output_id = uuid.uuid4()
    
    # Mock session
    session = AsyncMock()
    
    # Mock project output
    output = ProjectOutput(
        id=output_id,
        deliverable_id=deliverable_id,
        project_id=project_id,
        output_name="Test Output"
    )
    
    # Mock deliverable
    deliverable = Deliverable(
        id=deliverable_id,
        project_id=project_id,
        deliverable_name="Test Deliverable",
        status=DeliverableStatus.IN_REVIEW.value
    )
    
    # Mock review items
    review_item1 = ReviewItem(
        id=uuid.uuid4(),
        deliverable_id=deliverable_id,
        review_status=ReviewStatus.APPROVED.value,
        review_item_type=ReviewItemType.FINAL_RENDER.value,
        sequence_number=1
    )
    
    review_item2 = ReviewItem(
        id=uuid.uuid4(),
        deliverable_id=deliverable_id,
        review_status=ReviewStatus.APPROVED.value,
        review_item_type=ReviewItemType.TECHNICAL_DIAGRAM.value,
        sequence_number=1
    )
    
    # Mock review item files
    file1 = ReviewItemFile(
        id=uuid.uuid4(),
        review_item_id=review_item1.id,
        platform_file_id=uuid.uuid4(),
        file_name="render.jpg",
        file_type="image/jpeg"
    )
    
    file2 = ReviewItemFile(
        id=uuid.uuid4(),
        review_item_id=review_item2.id,
        platform_file_id=uuid.uuid4(),
        file_name="diagram.png",
        file_type="image/png"
    )
    
    # Mock file version
    file_version = FileVersion(
        id=uuid.uuid4(),
        original_file_id=file1.platform_file_id,
        current_file_id=uuid.uuid4(),
        version_number=2,
        version_type=VersionType.FINAL.value,
        is_final=True
    )
    
    # Mock query results
    output_result = AsyncMock()
    output_result.scalar_one_or_none.return_value = output
    
    deliverable_result = AsyncMock()
    deliverable_result.scalar_one_or_none.return_value = deliverable
    
    approved_items_result = AsyncMock()
    approved_items_result.scalars.return_value.all.return_value = [review_item1, review_item2]
    
    files_result1 = AsyncMock()
    files_result1.scalars.return_value.all.return_value = [file1]
    
    files_result2 = AsyncMock()
    files_result2.scalars.return_value.all.return_value = [file2]
    
    version_result1 = AsyncMock()
    version_result1.scalar_one_or_none.return_value = file_version
    
    version_result2 = AsyncMock()
    version_result2.scalar_one_or_none.return_value = None
    
    # Setup session execute to return our mocked results
    session.execute.side_effect = [
        output_result,  # For getting project output
        deliverable_result,  # For getting deliverable
        approved_items_result,  # For getting approved review items
        files_result1,  # For getting files for review item 1
        version_result1,  # For checking file version for file 1
        files_result2,  # For getting files for review item 2
        version_result2  # For checking file version for file 2
    ]
    
    # Create mock for platform file service
    platform_file_service = AsyncMock()
    platform_file_service.download_file.return_value = True
    platform_file_service.upload_file.return_value = uuid.uuid4()
    
    # Create service with mocked dependencies
    service = ProjectOutputService(lambda: session, platform_file_service=platform_file_service)
    
    # Execute
    with patch('tempfile.TemporaryDirectory'):
        with patch('os.makedirs'):
            with patch('zipfile.ZipFile'):
                with patch('os.path.join', return_value='/mock/path'):
                    with patch('os.path.basename', return_value='mock_file'):
                        with patch('os.path.splitext', return_value=('base', '.ext')):
                            with patch('os.path.relpath', return_value='mock_rel_path'):
                                with patch('os.walk', return_value=[('/mock/path', [], ['file1', 'file2'])]):
                                    with patch('open', create=True):
                                        result = await service.compile_final_deliverable(deliverable_id, output_id)
    
    # Assert
    assert result is True
    assert platform_file_service.download_file.call_count == 2
    assert platform_file_service.upload_file.call_count == 1
    assert session.add.call_count == 1
    assert session.commit.call_count == 1


@pytest.mark.asyncio
async def test_create_project_compilation():
    """Test creating comprehensive project compilation."""
    # Setup
    project_id = uuid.uuid4()
    
    # Mock session
    session = AsyncMock()
    
    # Mock project
    project = Project(
        id=project_id,
        project_name="Test Project",
        status=ProjectStatus.COMPLETED.value
    )
    
    # Mock deliverables and outputs
    deliverable_id1 = uuid.uuid4()
    deliverable_id2 = uuid.uuid4()
    
    deliverable1 = Deliverable(
        id=deliverable_id1,
        project_id=project_id,
        deliverable_name="Deliverable 1",
        status=DeliverableStatus.DELIVERED.value
    )
    
    deliverable2 = Deliverable(
        id=deliverable_id2,
        project_id=project_id,
        deliverable_name="Deliverable 2",
        status=DeliverableStatus.DELIVERED.value
    )
    
    output1 = ProjectOutput(
        id=uuid.uuid4(),
        deliverable_id=deliverable_id1,
        project_id=project_id,
        output_name="Output 1",
        output_url=f"https://example.com/api/compiled-outputs/{uuid.uuid4()}/output1.zip"
    )
    
    output2 = ProjectOutput(
        id=uuid.uuid4(),
        deliverable_id=deliverable_id2,
        project_id=project_id,
        output_name="Output 2",
        output_url=f"https://example.com/api/compiled-outputs/{uuid.uuid4()}/output2.zip"
    )
    
    # Mock query results
    project_result = AsyncMock()
    project_result.scalar_one_or_none.return_value = project
    
    outputs_result = AsyncMock()
    outputs_result.scalars().all.return_value = [output1, output2]
    
    deliverables_result = AsyncMock()
    deliverables_result.scalars().all.return_value = [deliverable1, deliverable2]
    
    # Setup session execute to return our mocked results
    session.execute.side_effect = [
        project_result,  # For getting project
        outputs_result,  # For getting project outputs
        deliverables_result  # For getting deliverables
    ]
    
    # Create mock for platform file service
    platform_file_service = AsyncMock()
    platform_file_service.download_file.return_value = True
    platform_file_service.upload_file.return_value = uuid.uuid4()
    
    # Create service with mocked dependencies
    service = ProjectOutputService(lambda: session, platform_file_service=platform_file_service)
    
    # Execute
    with patch('tempfile.TemporaryDirectory'):
        with patch('os.makedirs'):
            with patch('zipfile.ZipFile'):
                with patch('os.path.join', return_value='/mock/path'):
                    with patch('os.path.basename', return_value='mock_file'):
                        with patch('os.walk', return_value=[('/mock/path', [], ['file1', 'file2'])]):
                            with patch('os.path.relpath', return_value='mock_rel_path'):
                                with patch('open', create=True):
                                    result = await service.create_project_compilation(project_id)
    
    # Assert
    assert result is not None
    assert "https://" in result
    assert platform_file_service.upload_file.call_count == 1