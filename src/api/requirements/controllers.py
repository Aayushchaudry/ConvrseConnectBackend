"""
Requirements endpoint controllers.
Handles Requirement updates, file uploads, and management.
"""

# TODO: Import web framework decorators and request/response classes
# TODO: Import requirements service and file handling utilities
# TODO: Define GET /requirements endpoint (list requirements)
# TODO: Define POST /requirements endpoint (create requirement)
# TODO: Define PUT /requirements/{id} endpoint (update requirement)
# TODO: Define POST /requirements/{id}/files endpoint (upload files)
# TODO: Define GET /projects/{project_id}/requirements endpoint
# TODO: Add proper file validation and security

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.config.database import get_db_session
from src.config.event_bus import get_event_bus
from src.events.event_bus_interface import EventBus
from src.events.deliverable_events import RequirementUpdatedEvent
from src.models.requirement import Requirement, RequirementStatus, RequirementType
from src.models.deliverable import Deliverable, DeliverableType
from src.models.project import Project
from src.middleware.auth_middleware import require_auth, AuthContext
from src.middleware.permissions_middleware import (
    require_resource_permission, 
    require_resource_business_permission
)
from src.services.requirement_service import RequirementService

router = APIRouter(
    prefix="/requirements",
    tags=["Requirements Management"],
    redirect_slashes=False,
)
logger = logging.getLogger(__name__)


# --- Pydantic Schemas ---
class RequirementResponse(BaseModel):
    """Schema for requirement response"""
    id: UUID
    deliverable_id: UUID
    project_id: UUID
    requirement_name: str
    requirement_type: RequirementType
    status: RequirementStatus
    is_mandatory: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectRequirementSummary(BaseModel):
    """Schema for project requirement summary for information gathering"""
    id: str  # Project ID as string for frontend
    name: str  # Project name
    requiredFiles: Dict[str, Any] = Field(alias="required_files")  # Camelcase for frontend
    
    class Config:
        populate_by_name = True


class BusinessRequirementsResponse(BaseModel):
    """Schema for business requirements response"""
    requirements: List[ProjectRequirementSummary]


class RequirementGenerationRequest(BaseModel):
    """Request model for auto-generating requirements."""
    
    project_id: Optional[UUID] = Field(None, description="Project ID for project-level requirements")
    deliverable_id: Optional[UUID] = Field(None, description="Deliverable ID for deliverable-specific requirements")
    category_filter: Optional[List[str]] = Field(None, description="Filter by requirement categories")
    use_custom_templates: bool = Field(False, description="Use custom templates in addition to standard ones")


class CustomRequirementRequest(BaseModel):
    """Request model for creating custom requirements."""
    
    project_id: Optional[UUID] = Field(None, description="Project ID for project-level requirement")
    deliverable_id: Optional[UUID] = Field(None, description="Deliverable ID for deliverable-specific requirement")
    title: str = Field(..., min_length=1, max_length=255, description="Requirement title")
    description: str = Field(..., min_length=1, description="Requirement description")
    category: str = Field(..., description="Requirement category")
    priority: str = Field("medium", description="Requirement priority (high, medium, low)")
    acceptance_criteria: Optional[str] = Field(None, description="Acceptance criteria")
    is_mandatory: bool = Field(True, description="Whether this is a mandatory requirement")


class RequirementTemplateResponse(BaseModel):
    """Response model for requirement template data."""
    
    id: UUID
    name: str
    description: Optional[str]
    category: str
    priority: str
    template_text: str
    is_active: bool
    applicable_project_types: Optional[List[str]]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class RequirementsSummaryResponse(BaseModel):
    """Response model for requirements summary."""
    
    project_id: Optional[UUID]
    deliverable_id: Optional[UUID]
    total_requirements: int
    mandatory_requirements: int
    optional_requirements: int
    completed_requirements: int
    pending_requirements: int
    requirements_by_category: Dict[str, int]
    requirements_by_priority: Dict[str, int]
    completion_percentage: float


class RequirementGenerationResponse(BaseModel):
    """Response model for requirement generation results."""
    
    generated_count: int
    skipped_count: int
    generated_requirements: List[RequirementResponse]
    generation_summary: Dict[str, Any]


class UpdateRequirementRequest(BaseModel):
    """Request model for updating requirements."""
    
    title: Optional[str] = Field(None, min_length=1, max_length=255, description="Updated title")
    description: Optional[str] = Field(None, min_length=1, description="Updated description")
    category: Optional[str] = Field(None, description="Updated category")
    priority: Optional[str] = Field(None, description="Updated priority")
    acceptance_criteria: Optional[str] = Field(None, description="Updated acceptance criteria")
    is_mandatory: Optional[bool] = Field(None, description="Updated mandatory status")
    status: Optional[str] = Field(None, description="Updated status")


# --- API Endpoints ---

@router.get("/", response_model=List[RequirementResponse])
async def list_requirements(
    project_id: Optional[UUID] = None,
    deliverable_id: Optional[UUID] = None,
    request: Request = None,
    auth_context: AuthContext = Depends(require_resource_permission("requirements", "read")),
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    List requirements, optionally filtered by project or deliverable.
    Requires 'requirements.read' permission.
    """
    query = select(Requirement)
    
    if project_id:
        query = query.filter(Requirement.project_id == project_id)
    
    if deliverable_id:
        query = query.filter(Requirement.deliverable_id == deliverable_id)
    
    result = await db_session.execute(query)
    requirements = result.scalars().all()
    
    return requirements


@router.get("/{requirement_id}", response_model=RequirementResponse)
async def get_requirement(
    requirement_id: UUID,
    request: Request = None,
    auth_context: AuthContext = Depends(require_resource_permission("requirements", "read")),
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get a specific requirement by ID.
    Requires 'requirements.read' permission.
    """
    result = await db_session.execute(
        select(Requirement).filter(Requirement.id == requirement_id)
    )
    requirement = result.scalar_one_or_none()
    
    if not requirement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requirement not found"
        )
    
    return requirement


@router.get("/business/{business_id}/summary", response_model=BusinessRequirementsResponse)
async def get_business_requirements_summary(
    business_id: str,
    request: Request = None,
    auth_context: AuthContext = Depends(require_resource_business_permission("requirements", "read")),
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get aggregated requirements summary for a business for information gathering.
    Returns projects with their deliverable requirements aggregated.
    Requires 'requirements.read' permission and access to the specified business.
    """
    
    # Validate business access
    if not auth_context.has_business_access(business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to requested business"
        )
    # First, get all projects for this business
    projects_result = await db_session.execute(
        select(Project)
        .filter(Project.business_id == business_id)
        .options(selectinload(Project.deliverables).selectinload(Deliverable.requirements))
    )
    projects = projects_result.scalars().all()
    
    if not projects:
        # Return empty requirements if no projects found
        return BusinessRequirementsResponse(requirements=[])
    
    project_summaries = []
    
    for project in projects:
        # Count requirements across all deliverables for this project
        total_files = 0
        mandatory_files = 0
        file_types = set()
        
        for deliverable in project.deliverables:
            for requirement in deliverable.requirements:
                if requirement.requirement_type == RequirementType.FILE_UPLOAD:
                    total_files += 1
                    if requirement.is_mandatory:
                        mandatory_files += 1
                    
                    # Add common file types based on deliverable type
                    if deliverable.deliverable_type == DeliverableType.RENDERED_IMAGES:
                        file_types.update(['PDF', 'PNG', 'JPG', 'CAD'])
                    elif deliverable.deliverable_type == DeliverableType.INVENTORY_MODULE:
                        file_types.update(['PDF', 'XLS', 'CSV'])
                    elif deliverable.deliverable_type == DeliverableType.INTERACTIVE_SALES_APP:
                        file_types.update(['PDF', 'DOC', 'PNG', 'JPG'])
                    else:
                        file_types.update(['PDF', 'PNG', 'JPG'])
        
        # If no file requirements, add some defaults for UI purposes
        if total_files == 0:
            total_files = 2
            mandatory_files = 1
            file_types = ['PDF', 'PNG']
        
        project_summary = ProjectRequirementSummary(
            id=str(project.id),
            name=project.name,
            required_files={
                "total": total_files,
                "mandatory": mandatory_files,
                "types": list(file_types)
            }
        )
        
        project_summaries.append(project_summary)
    
    return BusinessRequirementsResponse(requirements=project_summaries)


@router.patch("/{requirement_id}/status")
async def update_requirement_status(
    requirement_id: UUID,
    status_data: dict,
    request: Request = None,
    auth_context: AuthContext = Depends(require_resource_permission("requirements", "update")),
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
):
    """
    Update requirement status and optionally store platform-service content_id.
    Requires 'requirements.update' permission.
    """
    result = await db_session.execute(
        select(Requirement).filter(Requirement.id == requirement_id)
    )
    requirement = result.scalar_one_or_none()
    
    if not requirement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requirement not found"
        )
    
    # Store old status for event
    old_status = requirement.status
    
    # Update status
    new_status = RequirementStatus(status_data["status"])
    requirement.status = new_status
    requirement.updated_at = datetime.utcnow()
    
    # Update value if provided (e.g., platform-service content_id for file uploads)
    if "value" in status_data:
        requirement.value = status_data["value"]
    
    await db_session.commit()
    await db_session.refresh(requirement)
    
    # Publish requirement updated event if status actually changed
    if old_status != new_status:
        try:
            requirement_event = RequirementUpdatedEvent(
                project_id=requirement.project_id,
                deliverable_id=requirement.deliverable_id,
                requirement_id=requirement.id,
                new_status=new_status.value,
            )
            
            await event_bus.publish(
                topic="requirement.updated",
                message=requirement_event.__dict__,
            )
            
            logger.info(f"Published RequirementUpdatedEvent for requirement {requirement_id}: {old_status.value} -> {new_status.value}")
            
        except Exception as e:
            logger.warning(f"Failed to publish requirement update event: {e}")
            # Don't fail the request if event publishing fails
    
    return {"message": "Requirement status updated successfully"}


@router.post("/generate", response_model=RequirementGenerationResponse, status_code=status.HTTP_201_CREATED)
async def auto_generate_requirements(
    generation_data: RequirementGenerationRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Auto-generate requirements from templates for a project or deliverable.
    """
    auth_context = require_auth(request)
    
    try:
        requirement_service = RequirementService(db_session)
        
        # Validate that either project_id or deliverable_id is provided
        if not generation_data.project_id and not generation_data.deliverable_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Either project_id or deliverable_id must be provided",
            )
        
        # Auto-generate requirements
        generated_requirements = await requirement_service.auto_generate_requirements(
            project_id=generation_data.project_id,
            deliverable_id=generation_data.deliverable_id,
            category_filter=generation_data.category_filter,
            use_custom_templates=generation_data.use_custom_templates,
        )
        
        # Convert to response models
        requirements_response = [
            RequirementResponse(
                id=req.id,
                project_id=req.project_id,
                deliverable_id=req.deliverable_id,
                template_id=req.template_id,
                title=req.title,
                description=req.description,
                category=req.category,
                priority=req.priority,
                acceptance_criteria=req.acceptance_criteria,
                is_mandatory=req.is_mandatory,
                status=req.status,
                created_at=req.created_at,
                updated_at=req.updated_at,
            )
            for req in generated_requirements
        ]
        
        return RequirementGenerationResponse(
            generated_count=len(generated_requirements),
            skipped_count=0,  # This would come from the service if duplicates were skipped
            generated_requirements=requirements_response,
            generation_summary={
                "target_type": "project" if generation_data.project_id else "deliverable",
                "target_id": str(generation_data.project_id or generation_data.deliverable_id),
                "category_filter": generation_data.category_filter,
                "use_custom_templates": generation_data.use_custom_templates,
            },
        )
        
    except ValueError as ve:
        logger.error(f"Validation error auto-generating requirements: {ve}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve),
        )
    except Exception as e:
        logger.error(f"Error auto-generating requirements: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to auto-generate requirements: {str(e)}",
        )


@router.post("/custom", response_model=RequirementResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_requirement(
    requirement_data: CustomRequirementRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Create a custom requirement for a project or deliverable.
    """
    auth_context = require_auth(request)
    
    try:
        requirement_service = RequirementService(db_session)
        
        # Validate that either project_id or deliverable_id is provided
        if not requirement_data.project_id and not requirement_data.deliverable_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Either project_id or deliverable_id must be provided",
            )
        
        # Create custom requirement
        requirement = await requirement_service.create_custom_requirement(
            project_id=requirement_data.project_id,
            deliverable_id=requirement_data.deliverable_id,
            title=requirement_data.title,
            description=requirement_data.description,
            category=requirement_data.category,
            priority=requirement_data.priority,
            acceptance_criteria=requirement_data.acceptance_criteria,
            is_mandatory=requirement_data.is_mandatory,
        )
        
        return RequirementResponse(
            id=requirement.id,
            project_id=requirement.project_id,
            deliverable_id=requirement.deliverable_id,
            template_id=requirement.template_id,
            title=requirement.title,
            description=requirement.description,
            category=requirement.category,
            priority=requirement.priority,
            acceptance_criteria=requirement.acceptance_criteria,
            is_mandatory=requirement.is_mandatory,
            status=requirement.status,
            created_at=requirement.created_at,
            updated_at=requirement.updated_at,
        )
        
    except ValueError as ve:
        logger.error(f"Validation error creating custom requirement: {ve}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve),
        )
    except Exception as e:
        logger.error(f"Error creating custom requirement: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create custom requirement: {str(e)}",
        )


@router.get("/projects/{project_id}", response_model=List[RequirementResponse])
async def get_project_requirements(
    project_id: UUID,
    request: Request,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get all requirements for a specific project.
    """
    auth_context = require_auth(request)
    
    try:
        requirement_service = RequirementService(db_session)
        
        # Get project requirements
        requirements = await requirement_service.get_project_requirements(
            project_id=project_id,
            category_filter=category,
            priority_filter=priority,
            status_filter=status,
        )
        
        return [
            RequirementResponse(
                id=req.id,
                project_id=req.project_id,
                deliverable_id=req.deliverable_id,
                template_id=req.template_id,
                title=req.title,
                description=req.description,
                category=req.category,
                priority=req.priority,
                acceptance_criteria=req.acceptance_criteria,
                is_mandatory=req.is_mandatory,
                status=req.status,
                created_at=req.created_at,
                updated_at=req.updated_at,
            )
            for req in requirements
        ]
        
    except Exception as e:
        logger.error(f"Error fetching project requirements: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch project requirements: {str(e)}",
        )


@router.get("/deliverables/{deliverable_id}", response_model=List[RequirementResponse])
async def get_deliverable_requirements(
    deliverable_id: UUID,
    request: Request,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get all requirements for a specific deliverable.
    """
    auth_context = require_auth(request)
    
    try:
        requirement_service = RequirementService(db_session)
        
        # Get deliverable requirements
        requirements = await requirement_service.get_deliverable_requirements(
            deliverable_id=deliverable_id,
            category_filter=category,
            priority_filter=priority,
            status_filter=status,
        )
        
        return [
            RequirementResponse(
                id=req.id,
                project_id=req.project_id,
                deliverable_id=req.deliverable_id,
                template_id=req.template_id,
                title=req.title,
                description=req.description,
                category=req.category,
                priority=req.priority,
                acceptance_criteria=req.acceptance_criteria,
                is_mandatory=req.is_mandatory,
                status=req.status,
                created_at=req.created_at,
                updated_at=req.updated_at,
            )
            for req in requirements
        ]
        
    except Exception as e:
        logger.error(f"Error fetching deliverable requirements: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch deliverable requirements: {str(e)}",
        )


@router.put("/{requirement_id}", response_model=RequirementResponse)
async def update_requirement(
    requirement_id: UUID,
    update_data: UpdateRequirementRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Update a specific requirement.
    """
    auth_context = require_auth(request)
    
    try:
        from sqlalchemy import select, update
        from src.models.requirement import Requirement
        
        # Check if requirement exists
        result = await db_session.execute(
            select(Requirement).filter(Requirement.id == requirement_id)
        )
        requirement = result.scalar_one_or_none()
        
        if not requirement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Requirement not found",
            )
        
        # Build update values
        update_values = {}
        if update_data.title is not None:
            update_values["title"] = update_data.title
        if update_data.description is not None:
            update_values["description"] = update_data.description
        if update_data.category is not None:
            update_values["category"] = update_data.category
        if update_data.priority is not None:
            update_values["priority"] = update_data.priority
        if update_data.acceptance_criteria is not None:
            update_values["acceptance_criteria"] = update_data.acceptance_criteria
        if update_data.is_mandatory is not None:
            update_values["is_mandatory"] = update_data.is_mandatory
        if update_data.status is not None:
            update_values["status"] = update_data.status
        
        if update_values:
            update_values["updated_at"] = datetime.utcnow()
            
            # Update requirement
            await db_session.execute(
                update(Requirement)
                .filter(Requirement.id == requirement_id)
                .values(**update_values)
            )
            await db_session.commit()
            
            # Refresh requirement
            await db_session.refresh(requirement)
        
        return RequirementResponse(
            id=requirement.id,
            project_id=requirement.project_id,
            deliverable_id=requirement.deliverable_id,
            template_id=requirement.template_id,
            title=requirement.title,
            description=requirement.description,
            category=requirement.category,
            priority=requirement.priority,
            acceptance_criteria=requirement.acceptance_criteria,
            is_mandatory=requirement.is_mandatory,
            status=requirement.status,
            created_at=requirement.created_at,
            updated_at=requirement.updated_at,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating requirement: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update requirement: {str(e)}",
        )


@router.delete("/{requirement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_requirement(
    requirement_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Delete a specific requirement.
    """
    auth_context = require_auth(request)
    
    try:
        from sqlalchemy import select, delete
        from src.models.requirement import Requirement
        
        # Check if requirement exists
        result = await db_session.execute(
            select(Requirement).filter(Requirement.id == requirement_id)
        )
        requirement = result.scalar_one_or_none()
        
        if not requirement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Requirement not found",
            )
        
        # Delete requirement
        await db_session.execute(
            delete(Requirement).filter(Requirement.id == requirement_id)
        )
        await db_session.commit()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting requirement: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete requirement: {str(e)}",
        )


@router.get("/templates", response_model=List[RequirementTemplateResponse])
async def get_requirement_templates(
    request: Request,
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get all available requirement templates.
    """
    auth_context = require_auth(request)
    
    try:
        requirement_service = RequirementService(db_session)
        
        # Get requirement templates
        templates = await requirement_service.get_requirement_templates(
            category_filter=category,
            active_only=is_active,
        )
        
        return [
            RequirementTemplateResponse(
                id=template.id,
                name=template.name,
                description=template.description,
                category=template.category,
                priority=template.priority,
                template_text=template.template_text,
                is_active=template.is_active,
                applicable_project_types=template.applicable_project_types,
                created_at=template.created_at,
                updated_at=template.updated_at,
            )
            for template in templates
        ]
        
    except Exception as e:
        logger.error(f"Error fetching requirement templates: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch requirement templates: {str(e)}",
        )


@router.get("/projects/{project_id}/summary", response_model=RequirementsSummaryResponse)
async def get_project_requirements_summary(
    project_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get requirements summary for a project.
    """
    auth_context = require_auth(request)
    
    try:
        requirement_service = RequirementService(db_session)
        
        # Get requirements summary
        summary = await requirement_service.get_requirements_summary(
            project_id=project_id,
            deliverable_id=None,
        )
        
        return RequirementsSummaryResponse(
            project_id=project_id,
            deliverable_id=None,
            total_requirements=summary["total_requirements"],
            mandatory_requirements=summary["mandatory_requirements"],
            optional_requirements=summary["optional_requirements"],
            completed_requirements=summary["completed_requirements"],
            pending_requirements=summary["pending_requirements"],
            requirements_by_category=summary["requirements_by_category"],
            requirements_by_priority=summary["requirements_by_priority"],
            completion_percentage=summary["completion_percentage"],
        )
        
    except Exception as e:
        logger.error(f"Error fetching project requirements summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch project requirements summary: {str(e)}",
        )


@router.get("/deliverables/{deliverable_id}/summary", response_model=RequirementsSummaryResponse)
async def get_deliverable_requirements_summary(
    deliverable_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get requirements summary for a deliverable.
    """
    auth_context = require_auth(request)
    
    try:
        requirement_service = RequirementService(db_session)
        
        # Get requirements summary
        summary = await requirement_service.get_requirements_summary(
            project_id=None,
            deliverable_id=deliverable_id,
        )
        
        return RequirementsSummaryResponse(
            project_id=None,
            deliverable_id=deliverable_id,
            total_requirements=summary["total_requirements"],
            mandatory_requirements=summary["mandatory_requirements"],
            optional_requirements=summary["optional_requirements"],
            completed_requirements=summary["completed_requirements"],
            pending_requirements=summary["pending_requirements"],
            requirements_by_category=summary["requirements_by_category"],
            requirements_by_priority=summary["requirements_by_priority"],
            completion_percentage=summary["completion_percentage"],
        )
        
    except Exception as e:
        logger.error(f"Error fetching deliverable requirements summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch deliverable requirements summary: {str(e)}",
        )
