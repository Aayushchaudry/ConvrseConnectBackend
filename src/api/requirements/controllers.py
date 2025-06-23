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

router = APIRouter(prefix="/requirements", tags=["Requirements"])
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
