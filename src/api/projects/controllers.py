# src/api/projects/controllers.py

from datetime import date, datetime  # Import datetime for parsing dates
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db_session  # Dependency for database session
from src.config.event_bus import get_event_bus  # Dependency for Event Bus
from src.events.event_bus_interface import EventBus  # Import the interface type
from src.middleware.auth_middleware import (
    AuthContext,  # Auth dependencies
    require_auth,
)
from src.middleware.permissions_middleware import (
    require_resource_permission, 
    require_resource_business_permission
)
from src.models.project import ProjectStatus  # Import ProjectStatus Enum
from src.services.project_service import ProjectService  # Import your ProjectService

import logging
logger = logging.getLogger(__name__)
        
# Create a FastAPI APIRouter instance
router = APIRouter(
    prefix="/projects",  # All endpoints in this router will start with /projects
    tags=["Projects"],  # Tags for API documentation (Swagger UI)
    redirect_slashes=False,  # Prevent automatic redirects - be explicit about trailing slashes
)


# --- Pydantic Schema for Request Body ---
# This defines the expected structure and validation for incoming JSON data
class CreateProjectRequest(BaseModel):
    """
    Schema for the request body when creating a new project.
    """

    name: str = Field(
        ..., min_length=3, max_length=255, description="Name of the project"
    )
    budget: float = Field(..., gt=0, description="Total budget for the project")
    start_date: date = Field(..., description="Project start date (YYYY-MM-DD)")
    end_date: date = Field(..., description="Project end date (YYYY-MM-DD)")
    business_id: Optional[str] = Field(None, description="Target business ID (for convrse platform users creating projects for clients)")
    created_by: str = Field(..., description="User ID (UUID) of the user creating this project")
    assigned_to: Optional[str] = Field(None, description="User ID (UUID) of the project manager assigned to this project")
    deliverable_types: Optional[list[str]] = Field(
        default=[], 
        description="List of deliverable types to be auto-created by orchestrator (e.g., ['rendered_images', 'vr_tour'])"
    )
    deliverable_sub_types: Optional[dict[str, str]] = Field(
        default={},
        description="Dictionary mapping deliverable types to their sub types (e.g., {'rendered_images': 'exterior', 'vr_tour': 'interior'})"
    )
    deliverable_timeline_days: Optional[dict[str, int]] = Field(
        default={},
        description="Dictionary mapping deliverable types to their custom timeline days (e.g., {'rendered_images': 14, 'vr_tour': 21})"
    )

    # Example of optional fields if you want to include them in creation
    # payment_option: Optional[str] = Field(None, description="Chosen payment option for the project")


# --- Pydantic Schema for Response Body (Optional, but good practice) ---
class ProjectResponse(BaseModel):
    """
    Schema for the response body when returning project details.
    """

    id: UUID
    name: str
    status: ProjectStatus  # Use the Enum directly if Pydantic can handle it, or str
    budget: float
    start_date: datetime  # Use datetime for consistency with DB model
    end_date: datetime
    created_at: datetime
    updated_at: datetime
    business_id: str  # <-- Added field to include business_id in response

    class Config:
        from_attributes = True  # Updated from orm_mode for Pydantic V2


# --- API Endpoints ---


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)  # Handle both with and without trailing slash
async def create_project(
    project_data: CreateProjectRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),  # Inject DB session
    event_bus: EventBus = Depends(get_event_bus),  # Inject Event Bus
    auth_context: AuthContext = Depends(require_resource_permission("projects", "create")),  # Temporarily disabled for testing
):
    """
    Creates a new project and initiates the Project Lifecycle SAGA.
    Backend orchestration: deliverables will be auto-created via ProjectCreatedEvent.
    Requires 'projects.create' permission.
    """

    try:
        # Log the backend orchestration process
        logger.info(f"🛠️ Backend orchestration - Creating project: {project_data.name}")
        logger.info(f"🛠️ Backend orchestration - Deliverable types: {project_data.deliverable_types}")
        logger.info(f"🛠️ Backend orchestration - Full request data: {project_data}")
        
        # Create an instance of ProjectService
        project_service = ProjectService(db_session=db_session, event_bus=event_bus)

        # Ensure we have proper fallback values for business_id and created_by
        business_id = project_data.business_id or "biz_convrse_default"  # Use default since no auth context
        created_by = project_data.created_by  # Use the value from request body
        
        # Validate that the business_id and created_by are proper strings
        if not isinstance(business_id, str) or not business_id.strip():
            business_id = "biz_convrse_default"
            
        if not isinstance(created_by, str) or not created_by.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="created_by is required and must be a valid UUID"
            )

        logger.info(f"🛠️ Backend orchestration - Using business_id: {business_id}, created_by: {created_by}")

        # Call the service method to create the project and publish the event
        # Convert date objects from Pydantic to string for now, ProjectService expects string based on current code
        # In a real app, you'd handle datetime objects consistently.
        created_project = await project_service.create_new_project(
            name=project_data.name,
            budget=project_data.budget,
            start_date=project_data.start_date.isoformat(),  # Convert date to ISO string
            end_date=project_data.end_date.isoformat(),  # Convert date to ISO string
            business_id=business_id,
            created_by=created_by,
            assigned_to=project_data.assigned_to,  # Project manager user ID (UUID)
            deliverable_types=project_data.deliverable_types or [],  # Pass deliverable types for orchestration
            deliverable_sub_types=project_data.deliverable_sub_types or {},  # Pass sub types for orchestration
            deliverable_timeline_days=project_data.deliverable_timeline_days or {},  # Pass timeline days
        )

        logger.info(f"✅ Backend orchestration - Project created: {created_project.id}")
        logger.info(f"✅ Backend orchestration - ProjectCreatedEvent will trigger deliverable creation")

        # Return the created project (Pydantic will automatically convert ORM model)
        return created_project
    except ValueError as ve:
        # Log the specific validation error
        logger.error(f"❌ Backend orchestration - Validation error: {ve}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Validation error: {str(ve)}",
        )
    except Exception as e:
        # Log the error for debugging
        logger.error(f"❌ Backend orchestration - Error creating project: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create project: {str(e)}",
        )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project_details(
    project_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
    auth_context: AuthContext = Depends(require_resource_permission("projects", "read")),  # Temporarily disabled for testing
):
    """
    Retrieves details of a specific project by its ID.
    Auth temporarily disabled for testing.
    """

    project_service = ProjectService(db_session=db_session, event_bus=event_bus)
    project = await project_service.get_project_by_id(project_id)

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    # Auth check temporarily disabled for testing
    if not auth_context.has_business_access(project.business_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    return project


@router.get("/", response_model=list[ProjectResponse])
@router.get("", response_model=list[ProjectResponse])  # Handle both with and without trailing slash
async def list_projects(
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
    auth_context: AuthContext = Depends(require_resource_permission("projects", "read")),  # Temporarily disabled for testing
):
    """
    Retrieves a list of projects.
    Auth temporarily disabled for testing.
    """
    try:
        project_service = ProjectService(db_session=db_session, event_bus=event_bus)
        all_projects = await project_service.get_all_projects()

        # Auth check temporarily disabled for testing
        accessible_projects = [
            project
            for project in all_projects
            if auth_context.has_business_access(project.business_id)
        ]
        return accessible_projects
        return all_projects
        
    except Exception as e:
        logger.error(f"Error fetching projects: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch projects: {str(e)}"
        )


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    update_data: dict,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
    auth_context: AuthContext = Depends(require_resource_permission("projects", "update")),
):
    """
    Updates a project with new data.
    Requires 'projects.update' permission and access to the business that owns the project.
    """

    project_service = ProjectService(db_session=db_session, event_bus=event_bus)

    project = await project_service.get_project_by_id(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    # Check if user has access to the business that owns this project
    if not auth_context.has_business_access(project.business_id):
        # Return 404 instead of 403 to avoid leaking information about project existence
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    # Update the project fields
    for field, value in update_data.items():
        if hasattr(project, field):
            setattr(project, field, value)

    await db_session.commit()
    await db_session.refresh(project)

    return project
