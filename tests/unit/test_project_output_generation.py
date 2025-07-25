"""
Unit tests for project output generation functionality.
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
from src.models.file_version import FileVersion, VersionType
from src.services.project_output_service import ProjectOutputService


@pytest.mark.asyncio
async def test_generate_project_output_for_deliverable():
    """Test generating a project output for a deliverable with approved reviews."""
    # Setup
    deliverable_id = uuid.uuid4()
    project_id = uuid.uuid4()
    
    # Mock session
    session = AsyncMock()
    
    # Mock deliverable
    deliverable = Deliverable(
        id=deliverable_id,
        project_id=project_id,
        deliverable_name="Test Deliverable",
        status=DeliverableStatus.IN_REVIEW.value
    )
    
    # Mock review items
    review_item = ReviewItem(
        id=uuid.uuid4(),
        deliverable_id=deliverable_id,
        review_status=ReviewStatus.APPROVED.value,
        review_item_type="FINAL_RENDER",
        sequence_number=1
    )
    
    # Mock review item files
    file = ReviewItemFile(
        id=uuid.uuid4(),
        review_item_id=review_item.id,
        platform_file_id=uuid.uuid4(),
        file_name="test_file.jpg",
        file_type="image/jpeg"
    )
    
    # Mock query results
    deliverable_result = AsyncMock()
    deliverable_result.scalar_one_or_none.return_value = deliverable
    
    all_approved_result = AsyncMock()
    all_approved_result.scalar.return_value = 1  # All reviews approved
    
    approved_items_result = AsyncMock()
    approved_items_result.scalars.return_value.all.return_value = [review_item]
    
    files_result = AsyncMock()
    files_result.scalars.return_value.all.return_value = [file]
    
    version_result = AsyncMock()
    version_result.scalar_one_or_none.return_value = None  # No final version yet
    
    # Setup session execute to return our mocked results
    session.execute.side_effect = [
        deliverable_result,  # For getting deliverable
        all_approved_result,  # For checking all reviews approved (total count)
        all_approved_result,  # For checking all reviews approved (approved count)
        approved_items_result,  # For getting approved review items
        files_result,  # For getting files
        version_result  # For checking file versions
    ]
    
    # Create service with mocked session
    service = ProjectOutputService(lambda: session)
    
    # Execute
    result = await service.generate_project_output_for_deliverable(deliverable_id)
    
    # Assert
    assert result is not None
    assert result.deliverable_id == deliverable_id
    assert result.project_id == project_id
    assert "Test Deliverable" in result.output_name
    assert session.add.call_count == 1
    assert session.flush.call_count == 1
    
    # Verify deliverable status was updated to DELIVERED
    assert deliverable.status == DeliverableStatus.DELIVERED.value


@pytest.mark.asyncio
async def test_generate_outputs_for_approved_deliverables():
    """Test automatically generating outputs for all deliverables with approved reviews."""
    # Setup
    deliverable_id = uuid.uuid4()
    project_id = uuid.uuid4()
    
    # Mock session
    session = AsyncMock()
    
    # Mock deliverable
    deliverable = Deliverable(
        id=deliverable_id,
        project_id=project_id,
        deliverable_name="Test Deliverable",
        status=DeliverableStatus.IN_REVIEW.value
    )
    
    # Mock query results
    deliverables_result = AsyncMock()
    deliverables_result.scalars.return_value.all.return_value = [deliverable]
    
    all_approved_result = AsyncMock()
    all_approved_result.scalar.return_value = 1  # All reviews approved
    
    output_result = AsyncMock()
    output_result.scalar_one_or_none.return_value = None  # No existing output
    
    # Create a mock for generate_project_output_for_deliverable
    with patch.object(
        ProjectOutputService, 
        'generate_project_output_for_deliverable',
        return_value=ProjectOutput(
            id=uuid.uuid4(),
            deliverable_id=deliverable_id,
            project_id=project_id,
            output_name="Test Output"
        )
    ) as mock_generate:
        # Create a mock for mark_files_as_final_versions
        with patch.object(
            ProjectOutputService,
            'mark_files_as_final_versions',
            return_value=True
        ) as mock_mark_final:
            # Create a mock for compile_final_deliverable
            with patch.object(
                ProjectOutputService,
                'compile_final_deliverable',
                return_value=True
            ) as mock_compile:
                # Setup session execute to return our mocked results
                session.execute.side_effect = [
                    deliverables_result,  # For getting deliverables
                    all_approved_result,  # For checking all reviews approved (total count)
                    all_approved_result,  # For checking all reviews approved (approved count)
                    output_result  # For checking existing output
                ]
                
                # Create service with mocked session
                service = ProjectOutputService(lambda: session)
                
                # Execute
                result = await service.generate_outputs_for_approved_deliverables()
                
                # Assert
                assert len(result) == 1
                assert deliverable_id in result
                mock_generate.assert_called_once_with(deliverable_id)
                mock_mark_final.assert_called_once_with(deliverable_id)
                mock_compile.assert_called_once()


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
    
    # Mock query results
    project_result = AsyncMock()
    project_result.scalar_one_or_none.return_value = project
    
    total_count_result = AsyncMock()
    total_count_result.scalar.return_value = 2  # Total deliverables
    
    delivered_count_result = AsyncMock()
    delivered_count_result.scalar.return_value = 2  # All deliverables delivered
    
    # Create a mock for create_project_compilation
    with patch.object(
        ProjectOutputService,
        'create_project_compilation',
        return_value="https://example.com/api/project-compilations/test"
    ) as mock_compile:
        # Setup session execute to return our mocked results
        session.execute.side_effect = [
            project_result,  # For getting project
            total_count_result,  # For checking project completion (total count)
            delivered_count_result  # For checking project completion (delivered count)
        ]
        
        # Create service with mocked session and event bus
        event_bus = AsyncMock()
        service = ProjectOutputService(lambda: session, event_bus)
        
        # Execute
        result = await service.process_project_completion(project_id)
        
        # Assert
        assert result is True
        assert project.status == ProjectStatus.COMPLETED.value
        assert session.add.call_count == 1
        assert session.commit.call_count == 1
        mock_compile.assert_called_once_with(project_id)
        event_bus.publish.assert_called_once()