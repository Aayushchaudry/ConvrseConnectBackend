# src/api/projects/controllers.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from datetime import datetime, date # Import datetime for parsing dates
from typing import Optional
from uuid import UUID

from src.config.database import get_db_session # Dependency for database session
from src.config.event_bus import get_event_bus # Dependency for Event Bus
from src.events.event_bus_interface import EventBus # Import the interface type
from src.services.project_service import ProjectService # Import your ProjectService
from src.models.project import ProjectStatus # Import ProjectStatus Enum

# Create a FastAPI APIRouter instance
router = APIRouter(
    prefix="/projects", # All endpoints in this router will start with /projects
    tags=["Projects"]   # Tags for API documentation (Swagger UI)
)

# --- Pydantic Schema for Request Body ---
# This defines the expected structure and validation for incoming JSON data
class CreateProjectRequest(BaseModel):
    """
    Schema for the request body when creating a new project.
    """
    name: str = Field(..., min_length=3, max_length=255, description="Name of the project")
    budget: float = Field(..., gt=0, description="Total budget for the project")
    start_date: date = Field(..., description="Project start date (YYYY-MM-DD)")
    end_date: date = Field(..., description="Project end date (YYYY-MM-DD)")

    # Example of optional fields if you want to include them in creation
    # payment_option: Optional[str] = Field(None, description="Chosen payment option for the project")

# --- Pydantic Schema for Response Body (Optional, but good practice) ---
class ProjectResponse(BaseModel):
    """
    Schema for the response body when returning project details.
    """
    id: UUID
    name: str
    status: ProjectStatus # Use the Enum directly if Pydantic can handle it, or str
    budget: float
    start_date: datetime # Use datetime for consistency with DB model
    end_date: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True # Enables Pydantic to read directly from ORM models (SQLAlchemy)

# --- API Endpoints ---

@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: CreateProjectRequest,
    db_session: AsyncSession = Depends(get_db_session), # Inject DB session
    event_bus: EventBus = Depends(get_event_bus)       # Inject Event Bus
):
    """
    Creates a new project and initiates the Project Lifecycle SAGA.
    """
    try:
        # Create an instance of ProjectService
        project_service = ProjectService(db_session=db_session, event_bus=event_bus)
        
        # Call the service method to create the project and publish the event
        # Convert date objects from Pydantic to string for now, ProjectService expects string based on current code
        # In a real app, you'd handle datetime objects consistently.
        created_project = await project_service.create_new_project(
            name=project_data.name,
            budget=project_data.budget,
            start_date=project_data.start_date.isoformat(), # Convert date to ISO string
            end_date=project_data.end_date.isoformat()       # Convert date to ISO string
        )
        
        # Return the created project (Pydantic will automatically convert ORM model)
        return created_project
    except Exception as e:
        # Log the error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error creating project: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create project: {str(e)}"
        )

# Example of a GET endpoint (you can implement this later)
@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project_details(
    project_id: UUID,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus)
):
    """
    Retrieves details of a specific project by its ID.
    """
    project_service = ProjectService(db_session=db_session, event_bus=event_bus)
    project = await project_service.get_project_by_id(project_id)
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    return project