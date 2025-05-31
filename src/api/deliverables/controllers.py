# src/api/deliverables/controllers.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from src.config.database import get_db_session # Dependency for database session
from src.config.event_bus import get_event_bus # Dependency for Event Bus
from src.events.event_bus_interface import EventBus # Import the interface type
from src.services.deliverable_service import DeliverableService # Import your DeliverableService
from src.models.deliverable import DeliverableType, DeliverableStatus # Import Deliverable Enums
from src.models.project import ProjectStatus # Import ProjectStatus for context, though not directly used here

# Create a FastAPI APIRouter instance
router = APIRouter(
    tags=["Deliverables"] # Tags for API documentation (Swagger UI)
)

# --- Pydantic Schema for Request Body ---
class CreateDeliverableRequest(BaseModel):
    """
    Schema for the request body when creating a new deliverable.
    """
    deliverable_type: DeliverableType = Field(..., description="Type of deliverable (enum)")
    deliverable_sub_type: Optional[str] = Field(None, max_length=100, description="Optional sub-type (e.g., 'Interior', 'Exterior')")
    tentative_timeline_days: Optional[int] = Field(None, gt=0, description="Tentative timeline in days")

# --- Pydantic Schema for Response Body ---
class DeliverableResponse(BaseModel):
    """
    Schema for the response body when returning deliverable details.
    """
    id: UUID
    project_id: UUID
    deliverable_type: DeliverableType
    deliverable_sub_type: Optional[str]
    current_status: DeliverableStatus
    tentative_timeline_days: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True # Pydantic V2 equivalent of orm_mode = True

# --- API Endpoints ---

@router.post("/projects/{project_id}/deliverables/", response_model=DeliverableResponse, status_code=status.HTTP_201_CREATED)
async def create_deliverable_for_project(
    project_id: UUID, # Path parameter for project_id
    deliverable_data: CreateDeliverableRequest,
    db_session: AsyncSession = Depends(get_db_session), # Inject DB session
    event_bus: EventBus = Depends(get_event_bus)       # Inject Event Bus
):
    """
    Creates a new deliverable associated with a specific project.
    """
    try:
        # Create an instance of DeliverableService
        deliverable_service = DeliverableService(db_session=db_session, event_bus=event_bus)
        
        # Call the service method to create the deliverable
        created_deliverable = await deliverable_service.create_deliverable(
            project_id=project_id,
            deliverable_type=deliverable_data.deliverable_type,
            deliverable_sub_type=deliverable_data.deliverable_sub_type,
            tentative_timeline_days=deliverable_data.tentative_timeline_days
        )
        
        return created_deliverable
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, # 404 if project not found
            detail=str(ve)
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error creating deliverable for project {project_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create deliverable: {str(e)}"
        )

# Optional: Add a GET endpoint to list deliverables for a project
@router.get("/projects/{project_id}/deliverables/", response_model=List[DeliverableResponse])
async def get_deliverables_by_project(
    project_id: UUID,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus)
):
    """
    Retrieves all deliverables associated with a specific project.
    """
    deliverable_service = DeliverableService(db_session=db_session, event_bus=event_bus)
    deliverables = await deliverable_service.get_deliverables_for_project(project_id)
    return deliverables

# Optional: Add a GET endpoint to get a single deliverable by ID
@router.get("/deliverables/{deliverable_id}", response_model=DeliverableResponse)
async def get_deliverable_details(
    deliverable_id: UUID,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus)
):
    """
    Retrieves details of a specific deliverable by its ID.
    """
    deliverable_service = DeliverableService(db_session=db_session, event_bus=event_bus)
    deliverable = await deliverable_service.get_deliverable_by_id(deliverable_id)
    
    if not deliverable:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deliverable not found"
        )
    return deliverable