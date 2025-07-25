"""
Enhanced file workflow functionality for the DeliverableSagaOrchestrator.
This module contains methods to handle file-based review completions and automatic project output creation.
"""

import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.deliverable import Deliverable, DeliverableStatus
from src.models.review_item import ReviewItem, ReviewStatus
from src.models.review_item_file import ReviewItemFile
from src.models.project_output import ProjectOutput
from src.orchestrators.deliverable_saga_orchestrator.commands import GenerateFinalOutputCommand
from src.events.project_events import DeliverableDeliveredEvent

logger = logging.getLogger(__name__)

async def check_all_reviews_approved(session: AsyncSession, deliverable_id: UUID) -> bool:
    """
    Check if all review items for a deliverable are approved.
    
    Args:
        session: Database session
        deliverable_id: ID of the deliverable to check
        
    Returns:
        bool: True if all review items are approved, False otherwise
    """
    # Get count of all review items for this deliverable
    total_count_result = await session.execute(
        select(func.count(ReviewItem.id))
        .filter(ReviewItem.deliverable_id == deliverable_id)
    )
    total_count = total_count_result.scalar()
    
    if total_count == 0:
        logger.warning(f"No review items found for deliverable {deliverable_id}")
        return False
    
    # Get count of approved review items
    approved_count_result = await session.execute(
        select(func.count(ReviewItem.id))
        .filter(
            ReviewItem.deliverable_id == deliverable_id,
            ReviewItem.review_status == ReviewStatus.APPROVED.value
        )
    )
    approved_count = approved_count_result.scalar()
    
    logger.info(f"Deliverable {deliverable_id}: {approved_count}/{total_count} review items approved")
    
    # All review items must be approved
    return approved_count > 0 and approved_count == total_count

async def get_latest_approved_review_items(session: AsyncSession, deliverable_id: UUID) -> List[ReviewItem]:
    """
    Get the latest approved review items for a deliverable.
    
    Args:
        session: Database session
        deliverable_id: ID of the deliverable
        
    Returns:
        List[ReviewItem]: List of latest approved review items
    """
    # Get the maximum sequence number for each review round
    subquery = select(
        ReviewItem.review_round,
        func.max(ReviewItem.sequence_number).label("max_sequence")
    ).filter(
        ReviewItem.deliverable_id == deliverable_id,
        ReviewItem.review_status == ReviewStatus.APPROVED.value
    ).group_by(ReviewItem.review_round).subquery()
    
    # Get the review items with the maximum sequence number for each round
    result = await session.execute(
        select(ReviewItem)
        .join(
            subquery,
            and_(
                ReviewItem.review_round == subquery.c.review_round,
                ReviewItem.sequence_number == subquery.c.max_sequence
            )
        )
        .filter(
            ReviewItem.deliverable_id == deliverable_id,
            ReviewItem.review_status == ReviewStatus.APPROVED.value
        )
        .order_by(ReviewItem.review_round.desc())
    )
    
    return result.scalars().all()

async def create_project_output(
    session: AsyncSession, 
    deliverable_id: UUID,
    project_id: UUID,
    approved_review_items: List[ReviewItem]
) -> Optional[ProjectOutput]:
    """
    Create a project output for an approved deliverable.
    
    Args:
        session: Database session
        deliverable_id: ID of the deliverable
        project_id: ID of the project
        approved_review_items: List of approved review items
        
    Returns:
        Optional[ProjectOutput]: Created project output, if successful
    """
    try:
        # Get the deliverable
        deliverable_result = await session.execute(
            select(Deliverable).filter(Deliverable.id == deliverable_id)
        )
        deliverable = deliverable_result.scalar_one_or_none()
        
        if not deliverable:
            logger.error(f"Deliverable {deliverable_id} not found")
            return None
        
        # Get all files from the approved review items with their metadata
        file_data = []
        for review_item in approved_review_items:
            files_result = await session.execute(
                select(ReviewItemFile)
                .filter(ReviewItemFile.review_item_id == review_item.id)
            )
            files = files_result.scalars().all()
            
            for file in files:
                # Get the final version of the file if available
                version_result = await session.execute(
                    select(FileVersion)
                    .filter(
                        FileVersion.original_file_id == file.platform_file_id,
                        FileVersion.is_final == True
                    )
                    .order_by(FileVersion.version_number.desc())
                    .limit(1)
                )
                final_version = version_result.scalar_one_or_none()
                
                file_id = final_version.current_file_id if final_version else file.platform_file_id
                
                # Add file with metadata to our collection
                file_data.append({
                    "file_id": file_id,
                    "file_name": file.file_name,
                    "file_type": file.file_type,
                    "review_item_type": review_item.review_item_type,
                    "review_round": review_item.review_round,
                    "sequence_number": review_item.sequence_number
                })
        
        if not file_data:
            logger.warning(f"No files found for approved review items of deliverable {deliverable_id}")
            return None
        
        # Create a structured output URL with metadata
        file_ids = [str(file["file_id"]) for file in file_data]
        file_ids_str = ",".join(file_ids)
        
        # Create a more detailed metadata structure for the output
        output_metadata = {
            "deliverable_id": str(deliverable_id),
            "project_id": str(project_id),
            "file_count": len(file_data),
            "files": file_data,
            "creation_date": datetime.now().isoformat()
        }
        
        # Create the project output
        output = ProjectOutput(
            deliverable_id=deliverable_id,
            project_id=project_id,
            output_name=f"Final Output - {deliverable.deliverable_name}",
            output_url=f"https://example.com/api/outputs/{deliverable_id}?files={file_ids_str}",
            comments_allowed_on_output=True
        )
        
        session.add(output)
        await session.flush()
        
        # Update deliverable status to DELIVERED
        deliverable.status = DeliverableStatus.DELIVERED.value
        session.add(deliverable)
        
        logger.info(f"Created project output {output.id} for deliverable {deliverable_id}")
        return output
        
    except Exception as e:
        logger.error(f"Error creating project output for deliverable {deliverable_id}: {e}", exc_info=True)
        return None

async def check_project_completion(session: AsyncSession, project_id: UUID) -> bool:
    """
    Check if all deliverables in a project are delivered.
    
    Args:
        session: Database session
        project_id: ID of the project
        
    Returns:
        bool: True if all deliverables are delivered, False otherwise
    """
    # Get count of all deliverables for this project
    total_count_result = await session.execute(
        select(func.count(Deliverable.id))
        .filter(Deliverable.project_id == project_id)
    )
    total_count = total_count_result.scalar()
    
    if total_count == 0:
        logger.warning(f"No deliverables found for project {project_id}")
        return False
    
    # Get count of delivered deliverables
    delivered_count_result = await session.execute(
        select(func.count(Deliverable.id))
        .filter(
            Deliverable.project_id == project_id,
            Deliverable.status == DeliverableStatus.DELIVERED.value
        )
    )
    delivered_count = delivered_count_result.scalar()
    
    logger.info(f"Project {project_id}: {delivered_count}/{total_count} deliverables delivered")
    
    # All deliverables must be delivered
    return delivered_count > 0 and delivered_count == total_count