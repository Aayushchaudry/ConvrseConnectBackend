"""
Service for project output generation and management.
"""

import logging
import os
import json
import zipfile
import tempfile
import shutil
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import AsyncSessionLocal
from src.events.event_bus_interface import EventBus
from src.events.project_events import DeliverableDeliveredEvent, ProjectCompletedEvent
from src.models.deliverable import Deliverable, DeliverableStatus
from src.models.project import Project, ProjectStatus
from src.models.project_output import ProjectOutput
from src.models.review_item import ReviewItem, ReviewStatus
from src.models.review_item_file import ReviewItemFile
from src.models.file_version import FileVersion, VersionType
from src.services.platform_file_service import PlatformFileService

logger = logging.getLogger(__name__)


class ProjectOutputService:
    """
    Service responsible for generating and managing project outputs.
    Handles the creation of final deliverables from approved review items,
    compilation of files, and project completion detection.
    """

    def __init__(
        self, db_session_factory: Callable[[], AsyncSession], event_bus: EventBus = None,
        platform_file_service: PlatformFileService = None
    ):
        self.db_session_factory = db_session_factory
        self.event_bus = event_bus
        self.platform_file_service = platform_file_service or PlatformFileService()

    async def generate_project_output_for_deliverable(
        self,
        deliverable_id: UUID,
        output_name: Optional[str] = None,
        approved_review_item_ids: Optional[List[UUID]] = None
    ) -> Optional[ProjectOutput]:
        """
        Generate a project output for an approved deliverable.
        
        Args:
            deliverable_id: ID of the deliverable
            output_name: Optional name for the output
            approved_review_item_ids: Optional list of specific approved review item IDs to include
            
        Returns:
            Optional[ProjectOutput]: Created project output, if successful
        """
        logger.info(f"Generating project output for deliverable {deliverable_id}")
        
        async with self.db_session_factory() as session:
            try:
                # Get the deliverable
                deliverable_result = await session.execute(
                    select(Deliverable).filter(Deliverable.id == deliverable_id)
                )
                deliverable = deliverable_result.scalar_one_or_none()
                
                if not deliverable:
                    logger.error(f"Deliverable {deliverable_id} not found")
                    return None
                
                # Check if all review items are approved (if not explicitly provided)
                if not approved_review_item_ids:
                    all_approved = await self._check_all_reviews_approved(session, deliverable_id)
                    if not all_approved:
                        logger.warning(f"Not all review items for deliverable {deliverable_id} are approved")
                        return None
                    
                    # Get the latest approved review items
                    approved_items = await self._get_latest_approved_review_items(session, deliverable_id)
                    approved_review_item_ids = [item.id for item in approved_items]
                
                # Get all files from the approved review items with their metadata
                file_data = []
                for review_item_id in approved_review_item_ids:
                    # Get the review item to access its metadata
                    review_item_result = await session.execute(
                        select(ReviewItem).filter(ReviewItem.id == review_item_id)
                    )
                    review_item = review_item_result.scalar_one_or_none()
                    
                    if not review_item:
                        continue
                        
                    # Get all files for this review item
                    files_result = await session.execute(
                        select(ReviewItemFile)
                        .filter(ReviewItemFile.review_item_id == review_item_id)
                    )
                    files = files_result.scalars().all()
                    
                    # Process each file, getting the final version if available
                    for file in files:
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
                # In a real implementation, this would point to an actual compiled output
                file_ids = [str(file["file_id"]) for file in file_data]
                file_ids_str = ",".join(file_ids)
                
                # Create a more detailed metadata structure for the output
                output_metadata = {
                    "deliverable_id": str(deliverable_id),
                    "project_id": str(deliverable.project_id),
                    "file_count": len(file_data),
                    "files": file_data,
                    "creation_date": datetime.now().isoformat()
                }
                
                # In a real implementation, this metadata would be stored with the compiled output
                # For now, we'll include it in the URL as a placeholder
                output_url = f"https://example.com/api/outputs/{deliverable_id}?files={file_ids_str}"
                
                # Use provided output name or generate one
                if not output_name:
                    output_name = f"Final Output - {deliverable.deliverable_name}"
                
                # Create the project output
                output = ProjectOutput(
                    deliverable_id=deliverable_id,
                    project_id=deliverable.project_id,
                    output_name=output_name,
                    output_url=output_url,
                    comments_allowed_on_output=True
                )
                
                session.add(output)
                await session.flush()
                
                # Update deliverable status to DELIVERED
                deliverable.status = DeliverableStatus.DELIVERED.value
                session.add(deliverable)
                
                # Check if project is now complete
                project_complete = await self._check_project_completion(session, deliverable.project_id)
                if project_complete:
                    logger.info(f"All deliverables for project {deliverable.project_id} are delivered. Project is complete.")
                    # Update project status to COMPLETED
                    project = await session.get(Project, deliverable.project_id)
                    if project:
                        project.status = ProjectStatus.COMPLETED.value
                        session.add(project)
                        
                        # Publish project completed event
                        if self.event_bus:
                            await self.event_bus.publish(
                                "project.completed",
                                ProjectCompletedEvent(
                                    project_id=project.id,
                                    project_name=project.project_name,
                                    completion_date=datetime.now()
                                )
                            )
                
                # Publish deliverable delivered event
                if self.event_bus:
                    await self.event_bus.publish(
                        "deliverable.delivered",
                        DeliverableDeliveredEvent(
                            project_id=deliverable.project_id,
                            deliverable_id=deliverable.id,
                            deliverable_name=deliverable.deliverable_name,
                            output_id=output.id
                        )
                    )
                
                await session.commit()
                
                logger.info(f"Created project output {output.id} for deliverable {deliverable_id}")
                return output
                
            except Exception as e:
                logger.error(f"Error generating project output for deliverable {deliverable_id}: {e}", exc_info=True)
                await session.rollback()
                return None

    async def compile_final_deliverable(
        self,
        deliverable_id: UUID,
        output_id: UUID,
        include_metadata: bool = True
    ) -> bool:
        """
        Compile and prepare the final deliverable files.
        
        Args:
            deliverable_id: ID of the deliverable
            output_id: ID of the project output
            include_metadata: Whether to include metadata in the compiled output
            
        Returns:
            bool: True if compilation was successful, False otherwise
        """
        logger.info(f"Compiling final deliverable for output {output_id}")
        
        async with self.db_session_factory() as session:
            try:
                # Get the project output
                output_result = await session.execute(
                    select(ProjectOutput).filter(ProjectOutput.id == output_id)
                )
                output = output_result.scalar_one_or_none()
                
                if not output:
                    logger.error(f"Project output {output_id} not found")
                    return False
                
                # Get the deliverable
                deliverable_result = await session.execute(
                    select(Deliverable).filter(Deliverable.id == deliverable_id)
                )
                deliverable = deliverable_result.scalar_one_or_none()
                
                if not deliverable:
                    logger.error(f"Deliverable {deliverable_id} not found")
                    return False
                
                # Get all approved review items for this deliverable
                approved_items_result = await session.execute(
                    select(ReviewItem)
                    .filter(
                        ReviewItem.deliverable_id == deliverable_id,
                        ReviewItem.review_status == ReviewStatus.APPROVED.value
                    )
                )
                approved_items = approved_items_result.scalars().all()
                
                # Get all files from approved review items
                file_data = []
                file_ids_to_download = []
                file_names_map = {}  # Map file IDs to names for download
                
                for review_item in approved_items:
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
                        
                        # Add to list of files to download
                        file_ids_to_download.append(file_id)
                        file_names_map[str(file_id)] = file.file_name
                        
                        file_data.append({
                            "file_id": str(file_id),
                            "file_name": file.file_name,
                            "file_type": file.file_type,
                            "review_item_id": str(review_item.id),
                            "review_item_type": review_item.review_item_type,
                            "review_round": review_item.review_round,
                            "sequence_number": review_item.sequence_number,
                            "is_final_version": bool(final_version)
                        })
                
                if not file_data:
                    logger.warning(f"No files found for approved review items of deliverable {deliverable_id}")
                    return False
                
                # Create a unique output identifier
                output_identifier = f"{deliverable.deliverable_name.replace(' ', '_')}_{output_id}"
                
                # Create metadata for the compiled output
                metadata = {
                    "output_id": str(output_id),
                    "deliverable_id": str(deliverable_id),
                    "project_id": str(deliverable.project_id),
                    "deliverable_name": deliverable.deliverable_name,
                    "output_name": output.output_name,
                    "compilation_date": datetime.now().isoformat(),
                    "file_count": len(file_data),
                    "files": file_data
                }
                
                # Create a temporary directory for compilation
                with tempfile.TemporaryDirectory() as temp_dir:
                    # Download all files to the temporary directory
                    for file_id in file_ids_to_download:
                        file_name = file_names_map.get(str(file_id), f"file_{file_id}.bin")
                        file_path = os.path.join(temp_dir, file_name)
                        
                        # In a real implementation, this would download from the platform file service
                        # await self.platform_file_service.download_file(file_id, file_path)
                        
                        # For demonstration, create placeholder files
                        with open(file_path, 'w') as f:
                            f.write(f"Placeholder content for file {file_id}")
                        
                        logger.info(f"Downloaded file {file_id} to {file_path}")
                    
                    # Create metadata.json if requested
                    if include_metadata:
                        metadata_path = os.path.join(temp_dir, "metadata.json")
                        with open(metadata_path, 'w') as f:
                            json.dump(metadata, f, indent=2)
                        logger.info(f"Created metadata.json with {len(metadata)} fields")
                    
                    # Create zip file
                    zip_filename = f"{output_identifier}.zip"
                    zip_path = os.path.join(temp_dir, zip_filename)
                    
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for root, _, files in os.walk(temp_dir):
                            for file in files:
                                if file == zip_filename:  # Skip the zip file itself
                                    continue
                                file_path = os.path.join(root, file)
                                arcname = os.path.relpath(file_path, temp_dir)
                                zipf.write(file_path, arcname)
                    
                    logger.info(f"Created zip file: {zip_path}")
                    
                    # In a real implementation, upload the zip file to a storage service
                    # zip_url = await self.platform_file_service.upload_file(zip_path)
                    
                    # For demonstration, use a placeholder URL
                    output_url = f"https://example.com/api/compiled-outputs/{output_identifier}.zip"
                    
                    # Update the output URL to point to the compiled output
                    output.output_url = output_url
                    output.delivery_date = datetime.now()
                    session.add(output)
                    await session.commit()
                
                logger.info(f"Compiled final deliverable for output {output_id}, URL: {output_url}")
                return True
                
            except Exception as e:
                logger.error(f"Error compiling final deliverable for output {output_id}: {e}", exc_info=True)
                await session.rollback()
                return False

    async def _check_all_reviews_approved(self, session: AsyncSession, deliverable_id: UUID) -> bool:
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

    async def mark_files_as_final_versions(self, deliverable_id: UUID) -> bool:
        """
        Mark all files from approved review items as final versions.
        
        Args:
            deliverable_id: ID of the deliverable
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Marking files as final versions for deliverable {deliverable_id}")
        
        async with self.db_session_factory() as session:
            try:
                # Get the latest approved review items
                approved_items = await self._get_latest_approved_review_items(session, deliverable_id)
                
                if not approved_items:
                    logger.warning(f"No approved review items found for deliverable {deliverable_id}")
                    return False
                
                # Get all files from approved review items
                for review_item in approved_items:
                    files_result = await session.execute(
                        select(ReviewItemFile)
                        .filter(ReviewItemFile.review_item_id == review_item.id)
                    )
                    files = files_result.scalars().all()
                    
                    for file in files:
                        # Check if there's already a final version for this file
                        version_result = await session.execute(
                            select(FileVersion)
                            .filter(
                                FileVersion.original_file_id == file.platform_file_id,
                                FileVersion.is_final == True
                            )
                        )
                        existing_final = version_result.scalar_one_or_none()
                        
                        if existing_final:
                            logger.info(f"File {file.platform_file_id} already has a final version")
                            continue
                        
                        # Get the latest version of this file
                        latest_version_result = await session.execute(
                            select(FileVersion)
                            .filter(FileVersion.original_file_id == file.platform_file_id)
                            .order_by(FileVersion.version_number.desc())
                            .limit(1)
                        )
                        latest_version = latest_version_result.scalar_one_or_none()
                        
                        if latest_version:
                            # Mark the latest version as final
                            latest_version.is_final = True
                            latest_version.version_type = VersionType.FINAL.value
                            session.add(latest_version)
                            logger.info(f"Marked file version {latest_version.id} as final for file {file.platform_file_id}")
                        else:
                            # Create a new final version entry if no versions exist
                            new_version = FileVersion(
                                original_file_id=file.platform_file_id,
                                current_file_id=file.platform_file_id,
                                version_number=1,
                                version_type=VersionType.FINAL.value,
                                is_final=True,
                                created_at=datetime.now()
                            )
                            session.add(new_version)
                            logger.info(f"Created new final version for file {file.platform_file_id}")
                
                await session.commit()
                logger.info(f"Successfully marked files as final versions for deliverable {deliverable_id}")
                return True
                
            except Exception as e:
                logger.error(f"Error marking files as final versions for deliverable {deliverable_id}: {e}", exc_info=True)
                await session.rollback()
                return False
    
    async def _get_latest_approved_review_items(self, session: AsyncSession, deliverable_id: UUID) -> List[ReviewItem]:
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

    async def create_project_compilation(self, project_id: UUID) -> Optional[str]:
        """
        Create a comprehensive compilation of all project outputs when a project is completed.
        
        Args:
            project_id: ID of the project
            
        Returns:
            Optional[str]: URL to the compiled project package, if successful
        """
        logger.info(f"Creating comprehensive project compilation for project {project_id}")
        
        async with self.db_session_factory() as session:
            try:
                # Get the project
                project_result = await session.execute(
                    select(Project).filter(Project.id == project_id)
                )
                project = project_result.scalar_one_or_none()
                
                if not project:
                    logger.error(f"Project {project_id} not found")
                    return None
                
                # Verify project is completed
                if project.status != ProjectStatus.COMPLETED.value:
                    logger.warning(f"Project {project_id} is not completed (status: {project.status})")
                    return None
                
                # Get all project outputs for this project
                outputs_result = await session.execute(
                    select(ProjectOutput).filter(ProjectOutput.project_id == project_id)
                )
                outputs = outputs_result.scalars().all()
                
                if not outputs:
                    logger.warning(f"No project outputs found for project {project_id}")
                    return None
                
                # Create metadata for the project compilation
                compilation_metadata = {
                    "project_id": str(project_id),
                    "project_name": project.project_name,
                    "compilation_date": datetime.now().isoformat(),
                    "output_count": len(outputs),
                    "outputs": [
                        {
                            "output_id": str(output.id),
                            "output_name": output.output_name,
                            "deliverable_id": str(output.deliverable_id),
                            "output_url": output.output_url,
                            "delivery_date": output.delivery_date.isoformat() if output.delivery_date else None
                        }
                        for output in outputs
                    ]
                }
                
                # In a real implementation, this would:
                # 1. Download all project outputs
                # 2. Compile them into a single package
                # 3. Upload to a storage service
                # 4. Return the URL to the compiled package
                
                # For now, we'll simulate this process
                compilation_url = f"https://example.com/api/project-compilations/{project_id}"
                
                logger.info(f"Created project compilation for project {project_id}: {compilation_url}")
                return compilation_url
                
            except Exception as e:
                logger.error(f"Error creating project compilation for project {project_id}: {e}", exc_info=True)
                return None
    
    async def _check_project_completion(self, session: AsyncSession, project_id: UUID) -> bool:
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
   async def generate_outputs_for_approved_deliverables(self) -> Dict[UUID, UUID]:
        """
        Automatically generate project outputs for all deliverables that have all reviews approved
        but don't have project outputs yet.
        
        Returns:
            Dict[UUID, UUID]: Mapping of deliverable IDs to created project output IDs
        """
        logger.info("Checking for deliverables with all reviews approved for automatic output generation")
        
        created_outputs = {}
        
        async with self.db_session_factory() as session:
            try:
                # Get all deliverables that are not yet delivered
                deliverables_result = await session.execute(
                    select(Deliverable)
                    .filter(Deliverable.status != DeliverableStatus.DELIVERED.value)
                )
                deliverables = deliverables_result.scalars().all()
                
                for deliverable in deliverables:
                    # Check if all reviews for this deliverable are approved
                    all_approved = await self._check_all_reviews_approved(session, deliverable.id)
                    
                    if all_approved:
                        # Check if this deliverable already has a project output
                        output_result = await session.execute(
                            select(ProjectOutput)
                            .filter(ProjectOutput.deliverable_id == deliverable.id)
                        )
                        existing_output = output_result.scalar_one_or_none()
                        
                        if not existing_output:
                            # Generate project output for this deliverable
                            logger.info(f"Generating project output for deliverable {deliverable.id} with all reviews approved")
                            output = await self.generate_project_output_for_deliverable(deliverable.id)
                            
                            if output:
                                created_outputs[deliverable.id] = output.id
                                
                                # Mark files as final versions
                                await self.mark_files_as_final_versions(deliverable.id)
                                
                                # Compile the final deliverable
                                await self.compile_final_deliverable(deliverable.id, output.id)
                
                return created_outputs
                
            except Exception as e:
                logger.error(f"Error generating outputs for approved deliverables: {e}", exc_info=True)
                return {}

    async def process_project_completion(self, project_id: UUID) -> bool:
        """
        Process project completion when all deliverables are delivered.
        Creates a comprehensive project compilation.
        
        Args:
            project_id: ID of the project to check
            
        Returns:
            bool: True if project was completed, False otherwise
        """
        logger.info(f"Processing potential project completion for project {project_id}")
        
        async with self.db_session_factory() as session:
            try:
                # Check if project is already completed
                project_result = await session.execute(
                    select(Project).filter(Project.id == project_id)
                )
                project = project_result.scalar_one_or_none()
                
                if not project:
                    logger.error(f"Project {project_id} not found")
                    return False
                
                if project.status == ProjectStatus.COMPLETED.value:
                    logger.info(f"Project {project_id} is already completed")
                    return True
                
                # Check if all deliverables are delivered
                project_complete = await self._check_project_completion(session, project_id)
                
                if project_complete:
                    logger.info(f"All deliverables for project {project_id} are delivered. Marking project as complete.")
                    
                    # Update project status to COMPLETED
                    project.status = ProjectStatus.COMPLETED.value
                    session.add(project)
                    
                    # Create project compilation
                    compilation_url = await self.create_project_compilation(project_id)
                    
                    # Publish project completed event
                    if self.event_bus:
                        await self.event_bus.publish(
                            "project.completed",
                            ProjectCompletedEvent(
                                project_id=project.id,
                                project_name=project.project_name,
                                completion_date=datetime.now(),
                                compilation_url=compilation_url
                            )
                        )
                    
                    await session.commit()
                    return True
                
                return False
                
            except Exception as e:
                logger.error(f"Error processing project completion for project {project_id}: {e}", exc_info=True)
                await session.rollback()
                return False