# src/api/project_outputs/controllers.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime
import logging

from src.config.database import get_db_session # Dependency for database session
from src.config.event_bus import get_event_bus # Dependency for Event Bus (not directly used in GETs, but common pattern)
from src.events.event_bus_interface import EventBus # Import the interface type
from src.models.project_output import ProjectOutput # Import the ProjectOutput model
from src.models.deliverable import Deliverable # For relationship check if needed

# Create a FastAPI APIRouter instance
router = APIRouter(
    tags=["Project Outputs"] # Tags for API documentation (Swagger UI)
)

# --- Pydantic Schema for Response Body (ProjectOutput Details) ---
class ProjectOutputResponse(BaseModel):
    """
    Schema for the response body when returning ProjectOutput details.
    """
    id: UUID
    deliverable_id: UUID
    project_id: UUID
    output_name: str
    output_url: str
    delivery_date: datetime
    comments_allowed_on_output: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True # Pydantic V2 equivalent of orm_mode = True

# --- API Endpoints ---

@router.get("/projects/{project_id}/deliverables/{deliverable_id}/outputs/", response_model=List[ProjectOutputResponse])
async def list_project_outputs_for_deliverable(
    project_id: UUID,
    deliverable_id: UUID,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus)
):
    """
    Retrieves all final outputs (ProjectOutput) for a specific deliverable within a project.
    """
    from sqlalchemy import select
    # Fetch ProjectOutputs directly
    result = await db_session.execute(
        select(ProjectOutput).filter(
            ProjectOutput.project_id == project_id,
            ProjectOutput.deliverable_id == deliverable_id
        )
    )
    outputs = result.scalars().all()
    if not outputs:
        # Optionally raise 404 if no outputs exist, or return empty list
        logger = logging.getLogger(__name__)
        logger.info(f"No ProjectOutputs found for deliverable {deliverable_id} in project {project_id}")
    return outputs

@router.get("/outputs/{output_id}", response_model=ProjectOutputResponse)
async def get_project_output_details(
    output_id: UUID,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus)
):
    """
    Retrieves details of a specific ProjectOutput by its ID.
    """
    from sqlalchemy import select
    result = await db_session.execute(
        select(ProjectOutput).filter(ProjectOutput.id == output_id)
    )
    project_output = result.scalar_one_or_none()
    
    if not project_output:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project Output not found"
        )
    return project_output 