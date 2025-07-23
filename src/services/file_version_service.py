# src/services/file_version_service.py

import logging
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from sqlalchemy.orm import selectinload

from src.models.file_version import FileVersion, VersionType

logger = logging.getLogger(__name__)


class FileVersionService:
    """
    Service for managing file versions and history tracking.
    Handles version creation, retrieval, and management operations.
    """

    def __init__(self, db_session: AsyncSession):
        """
        Initialize the FileVersionService.
        
        Args:
            db_session: An asynchronous SQLAlchemy database session.
        """
        self.db_session = db_session
        logger.info("FileVersionService initialized")

    async def create_file_version(
        self,
        original_file_id: UUID,
        new_file_id: UUID,
        version_type: VersionType,
        created_by: Optional[UUID] = None,
        version_notes: Optional[str] = None
    ) -> FileVersion:
        """
        Create a new file version record.
        
        Args:
            original_file_id: ID of the original file in platform-service
            new_file_id: ID of the new version file in platform-service
            version_type: Type of version (INITIAL, REVISION, FINAL)
            created_by: ID of user who created this version
            version_notes: Optional notes about this version
            
        Returns:
            FileVersion: The created file version record
        """
        logger.info(f"Creating file version for original file {original_file_id}")
        
        try:
            # Get the current highest version number for this original file
            result = await self.db_session.execute(
                select(FileVersion.version_number)
                .filter(FileVersion.original_file_id == original_file_id)
                .order_by(desc(FileVersion.version_number))
                .limit(1)
            )
            
            max_version = result.scalar_one_or_none()
            next_version_number = (max_version or 0) + 1
            
            # Create new file version
            file_version = FileVersion(
                original_file_id=original_file_id,
                current_file_id=new_file_id,
                version_number=next_version_number,
                version_type=version_type.value,
                version_notes=version_notes,
                created_by=created_by,
                is_final=(version_type == VersionType.FINAL),
                is_active=True
            )
            
            self.db_session.add(file_version)
            await self.db_session.commit()
            await self.db_session.refresh(file_version)
            
            logger.info(f"Created file version {file_version.id} (v{next_version_number})")
            return file_version
            
        except Exception as e:
            await self.db_session.rollback()
            logger.error(f"Error creating file version: {e}", exc_info=True)
            raise

    async def get_file_history(
        self,
        original_file_id: UUID,
        include_inactive: bool = False
    ) -> List[FileVersion]:
        """
        Get the complete version history for a file.
        
        Args:
            original_file_id: ID of the original file
            include_inactive: Whether to include inactive versions
            
        Returns:
            List[FileVersion]: List of file versions ordered by version number
        """
        logger.info(f"Getting file history for {original_file_id}")
        
        try:
            filters = [FileVersion.original_file_id == original_file_id]
            
            if not include_inactive:
                filters.append(FileVersion.is_active == True)
            
            result = await self.db_session.execute(
                select(FileVersion)
                .filter(and_(*filters))
                .order_by(FileVersion.version_number)
            )
            
            versions = result.scalars().all()
            logger.info(f"Found {len(versions)} versions for file {original_file_id}")
            return versions
            
        except Exception as e:
            logger.error(f"Error getting file history: {e}", exc_info=True)
            raise

    async def get_latest_version(
        self,
        original_file_id: UUID
    ) -> Optional[FileVersion]:
        """
        Get the latest active version of a file.
        
        Args:
            original_file_id: ID of the original file
            
        Returns:
            Optional[FileVersion]: Latest version or None if not found
        """
        logger.info(f"Getting latest version for file {original_file_id}")
        
        try:
            result = await self.db_session.execute(
                select(FileVersion)
                .filter(
                    and_(
                        FileVersion.original_file_id == original_file_id,
                        FileVersion.is_active == True
                    )
                )
                .order_by(desc(FileVersion.version_number))
                .limit(1)
            )
            
            latest_version = result.scalar_one_or_none()
            
            if latest_version:
                logger.info(f"Found latest version {latest_version.version_number} for file {original_file_id}")
            else:
                logger.info(f"No versions found for file {original_file_id}")
                
            return latest_version
            
        except Exception as e:
            logger.error(f"Error getting latest version: {e}", exc_info=True)
            raise

    async def mark_file_as_final(
        self,
        file_version_id: UUID,
        marked_by: Optional[UUID] = None
    ) -> FileVersion:
        """
        Mark a specific file version as final.
        
        Args:
            file_version_id: ID of the file version to mark as final
            marked_by: ID of user marking the file as final
            
        Returns:
            FileVersion: The updated file version
        """
        logger.info(f"Marking file version {file_version_id} as final")
        
        try:
            # Get the file version
            result = await self.db_session.execute(
                select(FileVersion).filter(FileVersion.id == file_version_id)
            )
            
            file_version = result.scalar_one_or_none()
            if not file_version:
                raise ValueError(f"File version {file_version_id} not found")
            
            # Update version to final
            file_version.is_final = True
            file_version.version_type = VersionType.FINAL.value
            file_version.updated_at = datetime.utcnow()
            
            if marked_by:
                file_version.created_by = marked_by
            
            await self.db_session.commit()
            await self.db_session.refresh(file_version)
            
            logger.info(f"Marked file version {file_version_id} as final")
            return file_version
            
        except Exception as e:
            await self.db_session.rollback()
            logger.error(f"Error marking file as final: {e}", exc_info=True)
            raise

    async def deactivate_version(
        self,
        file_version_id: UUID,
        deactivated_by: Optional[UUID] = None
    ) -> FileVersion:
        """
        Deactivate a file version (soft delete).
        
        Args:
            file_version_id: ID of the file version to deactivate
            deactivated_by: ID of user deactivating the version
            
        Returns:
            FileVersion: The deactivated file version
        """
        logger.info(f"Deactivating file version {file_version_id}")
        
        try:
            # Get the file version
            result = await self.db_session.execute(
                select(FileVersion).filter(FileVersion.id == file_version_id)
            )
            
            file_version = result.scalar_one_or_none()
            if not file_version:
                raise ValueError(f"File version {file_version_id} not found")
            
            # Deactivate version
            file_version.is_active = False
            file_version.updated_at = datetime.utcnow()
            
            await self.db_session.commit()
            await self.db_session.refresh(file_version)
            
            logger.info(f"Deactivated file version {file_version_id}")
            return file_version
            
        except Exception as e:
            await self.db_session.rollback()
            logger.error(f"Error deactivating file version: {e}", exc_info=True)
            raise

    async def get_final_versions(
        self,
        original_file_ids: List[UUID]
    ) -> List[FileVersion]:
        """
        Get final versions for multiple files.
        
        Args:
            original_file_ids: List of original file IDs
            
        Returns:
            List[FileVersion]: List of final versions
        """
        logger.info(f"Getting final versions for {len(original_file_ids)} files")
        
        try:
            result = await self.db_session.execute(
                select(FileVersion)
                .filter(
                    and_(
                        FileVersion.original_file_id.in_(original_file_ids),
                        FileVersion.is_final == True,
                        FileVersion.is_active == True
                    )
                )
                .order_by(FileVersion.original_file_id, desc(FileVersion.version_number))
            )
            
            final_versions = result.scalars().all()
            logger.info(f"Found {len(final_versions)} final versions")
            return final_versions
            
        except Exception as e:
            logger.error(f"Error getting final versions: {e}", exc_info=True)
            raise

    async def create_revision_from_feedback(
        self,
        original_file_id: UUID,
        new_file_id: UUID,
        feedback_notes: str,
        created_by: Optional[UUID] = None
    ) -> FileVersion:
        """
        Create a revision version based on feedback.
        
        Args:
            original_file_id: ID of the original file
            new_file_id: ID of the revised file
            feedback_notes: Notes from the feedback that prompted this revision
            created_by: ID of user creating the revision
            
        Returns:
            FileVersion: The created revision version
        """
        logger.info(f"Creating revision for file {original_file_id} based on feedback")
        
        return await self.create_file_version(
            original_file_id=original_file_id,
            new_file_id=new_file_id,
            version_type=VersionType.REVISION,
            created_by=created_by,
            version_notes=f"Revision based on feedback: {feedback_notes}"
        )

    async def get_version_statistics(
        self,
        original_file_ids: Optional[List[UUID]] = None
    ) -> dict:
        """
        Get statistics about file versions.
        
        Args:
            original_file_ids: Optional list to filter by specific files
            
        Returns:
            dict: Statistics about file versions
        """
        logger.info("Getting version statistics")
        
        try:
            filters = [FileVersion.is_active == True]
            
            if original_file_ids:
                filters.append(FileVersion.original_file_id.in_(original_file_ids))
            
            # Get all active versions
            result = await self.db_session.execute(
                select(FileVersion).filter(and_(*filters))
            )
            
            versions = result.scalars().all()
            
            # Calculate statistics
            total_versions = len(versions)
            final_versions = len([v for v in versions if v.is_final])
            revision_versions = len([v for v in versions if v.version_type == VersionType.REVISION.value])
            initial_versions = len([v for v in versions if v.version_type == VersionType.INITIAL.value])
            
            # Group by original file to get version counts per file
            file_version_counts = {}
            for version in versions:
                file_id = str(version.original_file_id)
                if file_id not in file_version_counts:
                    file_version_counts[file_id] = 0
                file_version_counts[file_id] += 1
            
            avg_versions_per_file = (
                sum(file_version_counts.values()) / len(file_version_counts)
                if file_version_counts else 0
            )
            
            statistics = {
                "total_versions": total_versions,
                "final_versions": final_versions,
                "revision_versions": revision_versions,
                "initial_versions": initial_versions,
                "unique_files": len(file_version_counts),
                "average_versions_per_file": round(avg_versions_per_file, 2),
                "files_with_multiple_versions": len([c for c in file_version_counts.values() if c > 1])
            }
            
            logger.info(f"Version statistics: {statistics}")
            return statistics
            
        except Exception as e:
            logger.error(f"Error getting version statistics: {e}", exc_info=True)
            raise