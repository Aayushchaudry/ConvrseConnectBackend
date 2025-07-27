# src/services/requirement_service.py

import logging
from typing import List, Optional, Dict, Any, Set
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload

from src.models.requirement import Requirement, RequirementType, RequirementStatus
from src.models.requirement_file import RequirementFile
from src.models.requirement_template import RequirementTemplate
from src.models.project import Project
from src.models.deliverable import Deliverable

logger = logging.getLogger(__name__)


class RequirementService:
    """
    Service layer for requirement management with auto-generation from templates.
    Handles project-level requirements and deliverable-specific requirements.
    """

    def __init__(self, db_session: AsyncSession):
        """
        Initialize the RequirementService.
        
        Args:
            db_session: An asynchronous SQLAlchemy database session.
        """
        self.db_session = db_session
        logger.info("RequirementService initialized")

    async def auto_generate_requirements(
        self,
        project_id: UUID,
        deliverable_types: List[str],
        include_project_level: bool = True,
        force_recreate: bool = False,
    ) -> Dict[str, List[Requirement]]:
        """
        Auto-generate requirements based on deliverable types and templates.
        
        Args:
            project_id: ID of the project
            deliverable_types: List of deliverable types to generate requirements for
            include_project_level: Whether to include project-level requirements
            force_recreate: Whether to remove existing auto-generated requirements first
            
        Returns:
            Dict containing created requirements organized by category
        """
        logger.info(f"Auto-generating requirements for project {project_id}")
        logger.info(f"Deliverable types: {deliverable_types}")

        # Validate project exists
        project = await self._get_project_by_id(project_id)
        if not project:
            raise ValueError(f"Project with ID {project_id} not found")

        # Remove existing auto-generated requirements if force recreate
        if force_recreate:
            await self._remove_auto_generated_requirements(project_id)

        # Get requirement templates for the deliverable types
        templates = await self._get_templates_for_deliverable_types(deliverable_types)
        
        if not templates:
            logger.warning(f"No templates found for deliverable types: {deliverable_types}")
            return {"project_level": [], "deliverable_specific": []}

        created_requirements = {
            "project_level": [],
            "deliverable_specific": [],
        }

        # Generate project-level requirements
        if include_project_level:
            project_templates = [t for t in templates if t.is_project_level]
            for template in project_templates:
                # Check if requirement already exists
                existing = await self._check_existing_requirement(
                    project_id, None, template.requirement_name, template.requirement_type
                )
                
                if not existing:
                    requirement = await self._create_requirement_from_template(
                        project_id, None, template
                    )
                    created_requirements["project_level"].append(requirement)

        # Generate deliverable-specific requirements
        deliverable_templates = [t for t in templates if not t.is_project_level]
        
        # Get project deliverables that match the types
        project_deliverables = await self._get_project_deliverables_by_types(
            project_id, deliverable_types
        )

        for deliverable in project_deliverables:
            deliverable_type_templates = [
                t for t in deliverable_templates 
                if t.deliverable_type == deliverable.deliverable_type
            ]
            
            for template in deliverable_type_templates:
                # Check if requirement already exists for this deliverable
                existing = await self._check_existing_requirement(
                    project_id, deliverable.id, template.requirement_name, template.requirement_type
                )
                
                if not existing:
                    requirement = await self._create_requirement_from_template(
                        project_id, deliverable.id, template
                    )
                    created_requirements["deliverable_specific"].append(requirement)

        total_created = len(created_requirements["project_level"]) + len(created_requirements["deliverable_specific"])
        logger.info(f"Created {total_created} new requirements")
        
        return created_requirements

    async def create_custom_requirement(
        self,
        project_id: UUID,
        deliverable_id: Optional[UUID],
        requirement_name: str,
        requirement_type: RequirementType,
        requirement_description: str,
        is_mandatory: bool = True,
        priority: str = "medium",
        notes: Optional[str] = None,
    ) -> Requirement:
        """
        Create a custom requirement not based on templates.
        
        Args:
            project_id: ID of the project
            deliverable_id: ID of the deliverable (None for project-level)
            requirement_name: Name of the requirement
            requirement_type: Type of requirement
            requirement_description: Detailed description
            is_mandatory: Whether requirement is mandatory
            priority: Priority level
            notes: Additional notes
            
        Returns:
            Requirement: The created requirement
        """
        logger.info(f"Creating custom requirement '{requirement_name}' for project {project_id}")

        # Validate project exists
        project = await self._get_project_by_id(project_id)
        if not project:
            raise ValueError(f"Project with ID {project_id} not found")

        # Validate deliverable if provided
        if deliverable_id:
            deliverable = await self._get_deliverable_by_id(deliverable_id)
            if not deliverable or deliverable.project_id != project_id:
                raise ValueError(f"Deliverable {deliverable_id} not found or doesn't belong to project {project_id}")

        # Check for duplicate requirement
        existing = await self._check_existing_requirement(
            project_id, deliverable_id, requirement_name, requirement_type
        )
        if existing:
            raise ValueError(f"Requirement '{requirement_name}' already exists for this scope")

        # Create requirement
        requirement = Requirement(
            project_id=project_id,
            deliverable_id=deliverable_id,
            requirement_name=requirement_name,
            requirement_type=requirement_type,
            requirement_description=requirement_description,
            is_mandatory=is_mandatory,
            priority=priority,
            notes=notes,
            is_project_level=deliverable_id is None,
            template_id=None,  # Custom requirement, no template
        )

        self.db_session.add(requirement)
        await self.db_session.commit()
        await self.db_session.refresh(requirement)

        logger.info(f"Created custom requirement with ID: {requirement.id}")
        return requirement

    async def update_requirement(
        self,
        requirement_id: UUID,
        requirement_name: Optional[str] = None,
        requirement_description: Optional[str] = None,
        is_mandatory: Optional[bool] = None,
        priority: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Requirement:
        """
        Update an existing requirement.
        
        Args:
            requirement_id: ID of the requirement to update
            requirement_name: New name (if provided)
            requirement_description: New description (if provided)
            is_mandatory: New mandatory status (if provided)
            priority: New priority (if provided)
            notes: New notes (if provided)
            
        Returns:
            Requirement: The updated requirement
        """
        logger.info(f"Updating requirement {requirement_id}")

        # Get existing requirement
        requirement = await self._get_requirement_by_id(requirement_id)
        if not requirement:
            raise ValueError(f"Requirement with ID {requirement_id} not found")

        # Update fields if provided
        if requirement_name is not None:
            requirement.requirement_name = requirement_name
        if requirement_description is not None:
            requirement.requirement_description = requirement_description
        if is_mandatory is not None:
            requirement.is_mandatory = is_mandatory
        if priority is not None:
            requirement.priority = priority
        if notes is not None:
            requirement.notes = notes

        await self.db_session.commit()
        await self.db_session.refresh(requirement)

        logger.info(f"Updated requirement: {requirement.requirement_name}")
        return requirement

    async def get_project_requirements(
        self,
        project_id: UUID,
        include_deliverable_specific: bool = True,
        requirement_type: Optional[RequirementType] = None,
        is_mandatory: Optional[bool] = None,
    ) -> Dict[str, List[Requirement]]:
        """
        Get all requirements for a project.
        
        Args:
            project_id: ID of the project
            include_deliverable_specific: Whether to include deliverable-specific requirements
            requirement_type: Filter by requirement type
            is_mandatory: Filter by mandatory status
            
        Returns:
            Dict containing requirements organized by category
        """
        logger.info(f"Getting requirements for project {project_id}")

        # Build filter conditions
        filters = [Requirement.project_id == project_id]
        
        if requirement_type:
            filters.append(Requirement.requirement_type == requirement_type)
        if is_mandatory is not None:
            filters.append(Requirement.is_mandatory == is_mandatory)

        # Get project-level requirements
        project_filters = filters + [Requirement.is_project_level == True]
        project_result = await self.db_session.execute(
            select(Requirement)
            .filter(and_(*project_filters))
            .order_by(Requirement.requirement_name)
        )
        project_requirements = project_result.scalars().all()

        result = {
            "project_level": project_requirements,
            "deliverable_specific": [],
        }

        # Get deliverable-specific requirements if requested
        if include_deliverable_specific:
            deliverable_filters = filters + [Requirement.is_project_level == False]
            deliverable_result = await self.db_session.execute(
                select(Requirement)
                .filter(and_(*deliverable_filters))
                .order_by(Requirement.requirement_name)
            )
            result["deliverable_specific"] = deliverable_result.scalars().all()

        total_requirements = len(result["project_level"]) + len(result["deliverable_specific"])
        logger.info(f"Found {total_requirements} requirements for project {project_id}")
        
        return result

    async def get_deliverable_requirements(
        self,
        deliverable_id: UUID,
        include_project_level: bool = True,
    ) -> Dict[str, List[Requirement]]:
        """
        Get requirements for a specific deliverable.
        
        Args:
            deliverable_id: ID of the deliverable
            include_project_level: Whether to include project-level requirements
            
        Returns:
            Dict containing requirements organized by category
        """
        logger.info(f"Getting requirements for deliverable {deliverable_id}")

        # Get deliverable to get project ID
        deliverable = await self._get_deliverable_by_id(deliverable_id)
        if not deliverable:
            raise ValueError(f"Deliverable with ID {deliverable_id} not found")

        # Get deliverable-specific requirements
        deliverable_result = await self.db_session.execute(
            select(Requirement)
            .filter(Requirement.deliverable_id == deliverable_id)
            .order_by(Requirement.requirement_name)
        )
        deliverable_requirements = deliverable_result.scalars().all()

        result = {
            "deliverable_specific": deliverable_requirements,
            "project_level": [],
        }

        # Get project-level requirements if requested
        if include_project_level:
            project_result = await self.db_session.execute(
                select(Requirement)
                .filter(
                    and_(
                        Requirement.project_id == deliverable.project_id,
                        Requirement.is_project_level == True,
                    )
                )
                .order_by(Requirement.requirement_name)
            )
            result["project_level"] = project_result.scalars().all()

        total_requirements = len(result["deliverable_specific"]) + len(result["project_level"])
        logger.info(f"Found {total_requirements} requirements for deliverable {deliverable_id}")
        
        return result

    async def delete_requirement(self, requirement_id: UUID) -> bool:
        """
        Delete a requirement.
        
        Args:
            requirement_id: ID of the requirement to delete
            
        Returns:
            bool: True if deleted, False if not found
        """
        logger.info(f"Deleting requirement {requirement_id}")

        requirement = await self._get_requirement_by_id(requirement_id)
        if not requirement:
            logger.warning(f"Requirement {requirement_id} not found")
            return False

        await self.db_session.delete(requirement)
        await self.db_session.commit()

        logger.info(f"Deleted requirement: {requirement.requirement_name}")
        return True

    async def get_requirement_templates(
        self,
        deliverable_type: Optional[str] = None,
        requirement_type: Optional[RequirementType] = None,
        is_project_level: Optional[bool] = None,
    ) -> List[RequirementTemplate]:
        """
        Get available requirement templates.
        
        Args:
            deliverable_type: Filter by deliverable type
            requirement_type: Filter by requirement type
            is_project_level: Filter by project level status
            
        Returns:
            List[RequirementTemplate]: Available templates
        """
        logger.info("Getting requirement templates")

        # Build filter conditions
        filters = []
        
        if deliverable_type:
            filters.append(RequirementTemplate.deliverable_type == deliverable_type)
        if requirement_type:
            filters.append(RequirementTemplate.requirement_type == requirement_type)
        if is_project_level is not None:
            filters.append(RequirementTemplate.is_project_level == is_project_level)

        query = select(RequirementTemplate).filter(and_(*filters)) if filters else select(RequirementTemplate)
        result = await self.db_session.execute(query.order_by(RequirementTemplate.deliverable_type, RequirementTemplate.requirement_name))
        
        templates = result.scalars().all()
        logger.info(f"Found {len(templates)} requirement templates")
        return templates

    async def upload_requirement_files(
        self,
        requirement_id: UUID,
        files: List[UploadFile],
        user_context: Optional[Dict[str, Any]] = None
    ) -> List[RequirementFile]:
        """
        Upload files for a requirement with platform-service integration.
        
        Args:
            requirement_id: ID of the requirement
            files: List of files to upload
            user_context: User context containing user_id and other auth info
            
        Returns:
            List[RequirementFile]: Created requirement file records
        """
        logger.info(f"Uploading {len(files)} files for requirement {requirement_id}")

        # Validate requirement exists and is of FILE_UPLOAD type
        requirement = await self._get_requirement_by_id(requirement_id)
        if not requirement:
            raise ValueError(f"Requirement with ID {requirement_id} not found")
        
        if requirement.requirement_type != RequirementType.FILE_UPLOAD:
            raise ValueError(f"Requirement {requirement_id} is not of type FILE_UPLOAD")

        # Validate file types for requirement context
        await self._validate_requirement_files(files)

        # Use file upload integration service for platform-service integration
        from src.services.file_upload_integration_service import (
            FileUploadIntegrationService, 
            RequirementFileMetadata
        )
        
        file_upload_service = FileUploadIntegrationService(self.db_session)
        
        metadata = RequirementFileMetadata(
            requirement_id=requirement_id,
            uploaded_by=UUID(user_context.get('user_id')) if user_context and user_context.get('user_id') else None
        )
        
        # Upload files and create records
        upload_result = await file_upload_service.upload_requirement_files(
            requirement_id, files, metadata
        )
        
        # Update requirement status to RECEIVED
        await self.update_requirement_status(requirement_id, RequirementStatus.RECEIVED, upload_result.platform_file_ids)
        
        # Get created requirement files
        requirement_files = await self.get_requirement_files(requirement_id)
        
        logger.info(f"Successfully uploaded {len(files)} files for requirement {requirement_id}")
        return requirement_files

    async def update_requirement_status(
        self,
        requirement_id: UUID,
        status: RequirementStatus,
        file_ids: Optional[List[UUID]] = None
    ) -> Requirement:
        """
        Update requirement status, typically when files are uploaded.
        
        Args:
            requirement_id: ID of the requirement
            status: New status
            file_ids: Optional list of file IDs for reference
            
        Returns:
            Requirement: Updated requirement
        """
        logger.info(f"Updating requirement {requirement_id} status to {status.value}")

        requirement = await self._get_requirement_by_id(requirement_id)
        if not requirement:
            raise ValueError(f"Requirement with ID {requirement_id} not found")

        requirement.status = status
        
        # Add note about file upload if files were provided
        if file_ids and status == RequirementStatus.RECEIVED:
            file_count = len(file_ids)
            note = f"Status updated to RECEIVED - {file_count} file(s) uploaded"
            if requirement.notes:
                requirement.notes += f"\n{note}"
            else:
                requirement.notes = note

        await self.db_session.commit()
        await self.db_session.refresh(requirement)

        logger.info(f"Updated requirement {requirement_id} status to {status.value}")
        return requirement

    async def get_requirement_files(
        self,
        requirement_id: UUID,
        include_inactive: bool = False
    ) -> List[RequirementFile]:
        """
        Get all files for a requirement.
        
        Args:
            requirement_id: ID of the requirement
            include_inactive: Whether to include inactive (deleted) files
            
        Returns:
            List[RequirementFile]: List of requirement files
        """
        logger.info(f"Getting files for requirement {requirement_id}")

        filters = [RequirementFile.requirement_id == requirement_id]
        if not include_inactive:
            filters.append(RequirementFile.is_active == True)

        result = await self.db_session.execute(
            select(RequirementFile)
            .filter(and_(*filters))
            .order_by(RequirementFile.upload_timestamp.desc())
        )
        
        files = result.scalars().all()
        logger.info(f"Found {len(files)} files for requirement {requirement_id}")
        return files

    async def delete_requirement_file(
        self,
        requirement_id: UUID,
        file_id: UUID,
        user_context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Soft delete a requirement file.
        
        Args:
            requirement_id: ID of the requirement
            file_id: ID of the file to delete
            user_context: User context for audit
            
        Returns:
            bool: True if deleted, False if not found
        """
        logger.info(f"Deleting file {file_id} from requirement {requirement_id}")

        # Find the file
        result = await self.db_session.execute(
            select(RequirementFile).filter(
                and_(
                    RequirementFile.id == file_id,
                    RequirementFile.requirement_id == requirement_id,
                    RequirementFile.is_active == True
                )
            )
        )
        
        requirement_file = result.scalar_one_or_none()
        if not requirement_file:
            logger.warning(f"File {file_id} not found or already deleted")
            return False

        # Soft delete
        requirement_file.is_active = False
        
        await self.db_session.commit()
        
        logger.info(f"Soft deleted file {file_id} from requirement {requirement_id}")
        return True

    async def _validate_requirement_files(self, files: List[UploadFile]) -> None:
        """
        Validate files for requirement upload context.
        
        Args:
            files: List of files to validate
            
        Raises:
            ValueError: If validation fails
        """
        if not files:
            raise ValueError("No files provided for upload")

        # Define allowed file types for requirements
        allowed_extensions = {
            'pdf', 'doc', 'docx', 'txt', 'rtf',  # Documents
            'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'webp', 'svg',  # Images
            'cad', 'dwg', 'step', 'iges', 'obj', 'fbx', '3ds', 'max', 'blend',  # CAD files
            'xls', 'xlsx', 'csv', 'ods',  # Spreadsheets
            'zip', 'rar', '7z', 'tar', 'gz'  # Archives
        }
        
        max_file_size = 100 * 1024 * 1024  # 100MB
        max_total_size = 500 * 1024 * 1024  # 500MB
        
        total_size = 0
        filenames = set()
        
        for file in files:
            # Check filename
            if not file.filename:
                raise ValueError("File must have a filename")
            
            if file.filename in filenames:
                raise ValueError(f"Duplicate filename: {file.filename}")
            filenames.add(file.filename)
            
            # Check file extension
            if '.' not in file.filename:
                raise ValueError(f"File must have an extension: {file.filename}")
            
            extension = file.filename.split('.')[-1].lower()
            if extension not in allowed_extensions:
                raise ValueError(
                    f"File type '{extension}' not allowed for requirements. "
                    f"Allowed types: {', '.join(sorted(allowed_extensions))}"
                )
            
            # Check file size
            file_size = getattr(file, 'size', 0)
            if file_size > max_file_size:
                raise ValueError(
                    f"File '{file.filename}' exceeds maximum size limit "
                    f"({max_file_size / (1024*1024):.1f}MB)"
                )
            
            total_size += file_size
        
        # Check total size
        if total_size > max_total_size:
            raise ValueError(
                f"Total upload size exceeds limit "
                f"({max_total_size / (1024*1024):.1f}MB)"
            )

    async def get_requirements_summary(self, project_id: UUID) -> Dict[str, Any]:
        """
        Get summary statistics for project requirements.
        
        Args:
            project_id: ID of the project
            
        Returns:
            Dict containing requirement statistics
        """
        logger.info(f"Getting requirements summary for project {project_id}")

        # Get all project requirements
        requirements = await self.get_project_requirements(project_id)
        
        all_requirements = requirements["project_level"] + requirements["deliverable_specific"]
        
        # Calculate statistics
        total_requirements = len(all_requirements)
        mandatory_count = len([r for r in all_requirements if r.is_mandatory])
        optional_count = total_requirements - mandatory_count
        
        # Count by type
        type_counts = {}
        for req_type in RequirementType:
            count = len([r for r in all_requirements if r.requirement_type == req_type])
            if count > 0:
                type_counts[req_type.value] = count

        # Count by priority
        priority_counts = {}
        for req in all_requirements:
            priority = req.priority or "medium"
            priority_counts[priority] = priority_counts.get(priority, 0) + 1

        # Count auto-generated vs custom
        auto_generated = len([r for r in all_requirements if r.template_id is not None])
        custom_created = total_requirements - auto_generated

        summary = {
            "project_id": str(project_id),
            "total_requirements": total_requirements,
            "project_level_count": len(requirements["project_level"]),
            "deliverable_specific_count": len(requirements["deliverable_specific"]),
            "mandatory_count": mandatory_count,
            "optional_count": optional_count,
            "auto_generated_count": auto_generated,
            "custom_created_count": custom_created,
            "by_type": type_counts,
            "by_priority": priority_counts,
        }

        logger.info(f"Requirements summary: {total_requirements} total, {mandatory_count} mandatory")
        return summary

    # Helper methods

    async def _get_project_by_id(self, project_id: UUID) -> Optional[Project]:
        """Get project by ID."""
        result = await self.db_session.execute(
            select(Project).filter(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def _get_deliverable_by_id(self, deliverable_id: UUID) -> Optional[Deliverable]:
        """Get deliverable by ID."""
        result = await self.db_session.execute(
            select(Deliverable).filter(Deliverable.id == deliverable_id)
        )
        return result.scalar_one_or_none()

    async def _get_requirement_by_id(self, requirement_id: UUID) -> Optional[Requirement]:
        """Get requirement by ID."""
        result = await self.db_session.execute(
            select(Requirement).filter(Requirement.id == requirement_id)
        )
        return result.scalar_one_or_none()

    async def _get_templates_for_deliverable_types(
        self, deliverable_types: List[str]
    ) -> List[RequirementTemplate]:
        """Get requirement templates for specific deliverable types."""
        result = await self.db_session.execute(
            select(RequirementTemplate).filter(
                or_(
                    RequirementTemplate.deliverable_type.in_(deliverable_types),
                    RequirementTemplate.is_project_level == True,
                )
            )
        )
        return result.scalars().all()

    async def _get_project_deliverables_by_types(
        self, project_id: UUID, deliverable_types: List[str]
    ) -> List[Deliverable]:
        """Get project deliverables that match the specified types."""
        result = await self.db_session.execute(
            select(Deliverable).filter(
                and_(
                    Deliverable.project_id == project_id,
                    Deliverable.deliverable_type.in_(deliverable_types),
                )
            )
        )
        return result.scalars().all()

    async def _check_existing_requirement(
        self,
        project_id: UUID,
        deliverable_id: Optional[UUID],
        requirement_name: str,
        requirement_type: RequirementType,
    ) -> Optional[Requirement]:
        """Check if a requirement already exists with the same name and type."""
        filters = [
            Requirement.project_id == project_id,
            Requirement.requirement_name == requirement_name,
            Requirement.requirement_type == requirement_type,
        ]
        
        if deliverable_id:
            filters.append(Requirement.deliverable_id == deliverable_id)
        else:
            filters.append(Requirement.deliverable_id.is_(None))

        result = await self.db_session.execute(
            select(Requirement).filter(and_(*filters))
        )
        return result.scalar_one_or_none()

    async def _create_requirement_from_template(
        self,
        project_id: UUID,
        deliverable_id: Optional[UUID],
        template: RequirementTemplate,
    ) -> Requirement:
        """Create a requirement from a template."""
        requirement = Requirement(
            project_id=project_id,
            deliverable_id=deliverable_id,
            requirement_name=template.requirement_name,
            requirement_type=template.requirement_type,
            requirement_description=template.requirement_description,
            is_mandatory=template.is_mandatory,
            priority=template.default_priority,
            notes=f"Auto-generated from template: {template.requirement_name}",
            is_project_level=template.is_project_level,
            template_id=template.id,
        )

        self.db_session.add(requirement)
        await self.db_session.commit()
        await self.db_session.refresh(requirement)

        return requirement

    async def _remove_auto_generated_requirements(self, project_id: UUID) -> int:
        """Remove all auto-generated requirements for a project."""
        result = await self.db_session.execute(
            select(Requirement).filter(
                and_(
                    Requirement.project_id == project_id,
                    Requirement.template_id.is_not(None),
                )
            )
        )
        
        requirements_to_delete = result.scalars().all()
        count = len(requirements_to_delete)
        
        for requirement in requirements_to_delete:
            await self.db_session.delete(requirement)
        
        await self.db_session.commit()
        
        logger.info(f"Removed {count} auto-generated requirements")
        return count 