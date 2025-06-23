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
    assigned_to: Optional[str] = Field(None, description="User ID (UUID) of the project manager assigned to this project")

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

    class Config:
        orm_mode = (
            True  # Enables Pydantic to read directly from ORM models (SQLAlchemy)
        )


# --- API Endpoints ---


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)  # Handle both with and without trailing slash
async def create_project(
    project_data: CreateProjectRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),  # Inject DB session
    event_bus: EventBus = Depends(get_event_bus),  # Inject Event Bus
    auth_context: AuthContext = Depends(require_resource_permission("projects", "create")),
):
    """
    Creates a new project and initiates the Project Lifecycle SAGA.
    Requires 'projects.create' permission.
    """

    try:
        # Validate the input data
        logger.info(f"Creating project with data: {project_data}")
        
        # Create an instance of ProjectService
        project_service = ProjectService(db_session=db_session, event_bus=event_bus)

        # Ensure we have proper fallback values for business_id and created_by
        business_id = project_data.business_id or auth_context.business_id or "biz_convrse_default"
        created_by = auth_context.user_id or "default-user-id"
        
        # Validate that the business_id and created_by are proper strings
        if not isinstance(business_id, str) or not business_id.strip():
            business_id = "biz_convrse_default"
            
        if not isinstance(created_by, str) or not created_by.strip():
            created_by = "default-user-id"

        logger.info(f"Using business_id: {business_id}, created_by: {created_by}")

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
        )

        # Return the created project (Pydantic will automatically convert ORM model)
        return created_project
    except ValueError as ve:
        # Log the specific validation error
        logger.error(f"Validation error creating project: {ve}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Validation error: {str(ve)}",
        )
    except Exception as e:
        # Log the error for debugging
        logger.error(f"Error creating project: {e}", exc_info=True)
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
    auth_context: AuthContext = Depends(require_resource_permission("projects", "read")),
):
    """
    Retrieves details of a specific project by its ID.
    Requires 'projects.read' permission and access to the business that owns the project.
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

    return project


@router.get("/", response_model=list[ProjectResponse])
@router.get("", response_model=list[ProjectResponse])  # Handle both with and without trailing slash
async def list_projects(
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
    auth_context: AuthContext = Depends(require_resource_permission("projects", "read")),
):
    """
    Retrieves a list of projects accessible to the authenticated user.
    Requires 'projects.read' permission and filters by business access.
    """
    try:
        project_service = ProjectService(db_session=db_session, event_bus=event_bus)
        all_projects = await project_service.get_all_projects()

        # Filter projects by business access - only return projects the user has access to
        accessible_projects = [
            project
            for project in all_projects
            if auth_context.has_business_access(project.business_id)
        ]

        return accessible_projects
        
    except Exception as e:
        logger.error(f"Error fetching projects: {e}", exc_info=True)
        # Don't rollback here - let the dependency handle session lifecycle
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
