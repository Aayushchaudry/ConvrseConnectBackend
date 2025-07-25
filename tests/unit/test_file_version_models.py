# tests/unit/test_file_version_models.py

import uuid
import pytest
from datetime import datetime
from sqlalchemy import select

from src.models.review_item_file import ReviewItemFile
from src.models.file_version import FileVersion, VersionType
from src.models.review_item import ReviewItem


@pytest.mark.asyncio
async def test_review_item_file_model(db_session):
    """Test the ReviewItemFile model creation and relationships."""
    # Create a mock review item
    review_item_id = uuid.uuid4()
    mock_review_item = ReviewItem(
        id=review_item_id,
        project_id=uuid.uuid4(),
        deliverable_id=uuid.uuid4(),
        item_type="DOCUMENT",
        description="Test Review Item",
        sequence_number=1,
        review_round=1
    )
    db_session.add(mock_review_item)
    await db_session.commit()
    
    # Create a review item file
    platform_file_id = uuid.uuid4()
    review_item_file = ReviewItemFile(
        review_item_id=review_item_id,
        platform_file_id=platform_file_id,
        file_name="test_document.pdf",
        file_type="pdf",
        file_size=1024,
        sequence_order=1
    )
    db_session.add(review_item_file)
    await db_session.commit()
    
    # Query the file to verify it was created
    result = await db_session.execute(
        select(ReviewItemFile).filter(ReviewItemFile.platform_file_id == platform_file_id)
    )
    retrieved_file = result.scalar_one()
    
    # Verify the file properties
    assert retrieved_file.review_item_id == review_item_id
    assert retrieved_file.platform_file_id == platform_file_id
    assert retrieved_file.file_name == "test_document.pdf"
    assert retrieved_file.file_type == "pdf"
    assert retrieved_file.file_size == 1024
    assert retrieved_file.sequence_order == 1
    
    # Verify relationship to review item
    assert retrieved_file.review_item_ref.id == review_item_id
    assert retrieved_file.review_item_ref.description == "Test Review Item"


@pytest.mark.asyncio
async def test_file_version_model(db_session):
    """Test the FileVersion model creation and versioning."""
    # Create original file version
    original_file_id = uuid.uuid4()
    current_file_id = uuid.uuid4()
    
    file_version = FileVersion(
        original_file_id=original_file_id,
        current_file_id=current_file_id,
        version_number=1,
        version_type=VersionType.INITIAL.value,
        version_notes="Initial version",
        created_by=uuid.uuid4(),
        is_final=False,
        is_active=True
    )
    db_session.add(file_version)
    await db_session.commit()
    
    # Query the version to verify it was created
    result = await db_session.execute(
        select(FileVersion).filter(FileVersion.original_file_id == original_file_id)
    )
    retrieved_version = result.scalar_one()
    
    # Verify the version properties
    assert retrieved_version.original_file_id == original_file_id
    assert retrieved_version.current_file_id == current_file_id
    assert retrieved_version.version_number == 1
    assert retrieved_version.version_type == VersionType.INITIAL.value
    assert retrieved_version.version_notes == "Initial version"
    assert retrieved_version.is_final is False
    assert retrieved_version.is_active is True
    
    # Create a revision version
    revision_file_id = uuid.uuid4()
    revision_version = FileVersion(
        original_file_id=original_file_id,
        current_file_id=revision_file_id,
        version_number=2,
        version_type=VersionType.REVISION.value,
        version_notes="Revision after feedback",
        created_by=uuid.uuid4(),
        is_final=False,
        is_active=True
    )
    db_session.add(revision_version)
    await db_session.commit()
    
    # Query all versions to verify both were created
    result = await db_session.execute(
        select(FileVersion)
        .filter(FileVersion.original_file_id == original_file_id)
        .order_by(FileVersion.version_number)
    )
    versions = result.scalars().all()
    
    # Verify we have two versions
    assert len(versions) == 2
    assert versions[0].version_number == 1
    assert versions[1].version_number == 2
    assert versions[1].version_type == VersionType.REVISION.value


@pytest.mark.asyncio
async def test_review_item_file_with_versions(db_session):
    """Test the integration between ReviewItemFile and FileVersion models."""
    # Create a mock review item
    review_item_id = uuid.uuid4()
    mock_review_item = ReviewItem(
        id=review_item_id,
        project_id=uuid.uuid4(),
        deliverable_id=uuid.uuid4(),
        item_type="DOCUMENT",
        description="Test Review Item with Versions",
        sequence_number=1,
        review_round=1
    )
    db_session.add(mock_review_item)
    await db_session.commit()
    
    # Create a review item file
    platform_file_id = uuid.uuid4()
    review_item_file = ReviewItemFile(
        review_item_id=review_item_id,
        platform_file_id=platform_file_id,
        file_name="versioned_document.pdf",
        file_type="pdf",
        file_size=2048,
        sequence_order=1
    )
    db_session.add(review_item_file)
    await db_session.commit()
    
    # Create initial version
    file_version = FileVersion(
        original_file_id=platform_file_id,
        current_file_id=platform_file_id,  # Same ID for initial version
        version_number=1,
        version_type=VersionType.INITIAL.value,
        version_notes="Initial version",
        is_final=False,
        is_active=True
    )
    db_session.add(file_version)
    await db_session.commit()
    
    # Create a revision version
    revision_file_id = uuid.uuid4()
    revision_version = FileVersion(
        original_file_id=platform_file_id,
        current_file_id=revision_file_id,
        version_number=2,
        version_type=VersionType.REVISION.value,
        version_notes="Revision after feedback",
        is_final=False,
        is_active=True
    )
    db_session.add(revision_version)
    await db_session.commit()
    
    # Create a final version
    final_file_id = uuid.uuid4()
    final_version = FileVersion(
        original_file_id=platform_file_id,
        current_file_id=final_file_id,
        version_number=3,
        version_type=VersionType.FINAL.value,
        version_notes="Final approved version",
        is_final=True,
        is_active=True
    )
    db_session.add(final_version)
    await db_session.commit()
    
    # Query all versions for the file
    result = await db_session.execute(
        select(FileVersion)
        .filter(FileVersion.original_file_id == platform_file_id)
        .order_by(FileVersion.version_number)
    )
    versions = result.scalars().all()
    
    # Verify we have three versions
    assert len(versions) == 3
    assert versions[0].version_number == 1
    assert versions[1].version_number == 2
    assert versions[2].version_number == 3
    assert versions[2].is_final is True
    assert versions[2].version_type == VersionType.FINAL.value