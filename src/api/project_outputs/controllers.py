# src/api/project_outputs/controllers.py

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db_session  # Dependency for database session
from src.config.event_bus import (
    get_event_bus,
)  # Dependency for Event Bus (not directly used in GETs, but common pattern)
from src.events.event_bus_interface import EventBus  # Import the interface type
from src.models.deliverable import Deliverable  # For relationship check if needed
from src.models.project_output import ProjectOutput  # Import the ProjectOutput model

# Create a FastAPI APIRouter instance
router = APIRouter(tags=["Project Outputs"])  # Tags for API documentation (Swagger UI)


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
        from_attributes = True  # Pydantic V2 equivalent of orm_mode = True


# --- Pydantic Schema for Request Body (Creating ProjectOutput) ---
class CreateProjectOutputRequest(BaseModel):
    """
    Schema for the request body when creating a new project output.
    """

    deliverable_id: UUID
    project_id: UUID
    output_name: str
    output_url: str
    delivery_date: Optional[datetime] = None
    comments_allowed_on_output: bool = True


# --- API Endpoints ---


@router.get(
    "/projects/{project_id}/deliverables/{deliverable_id}/outputs/",
    response_model=List[ProjectOutputResponse],
)
async def list_project_outputs_for_deliverable(
    project_id: UUID,
    deliverable_id: UUID,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
):
    """
    Retrieves all final outputs (ProjectOutput) for a specific deliverable within a project.
    """
    from sqlalchemy import select

    # Fetch ProjectOutputs directly
    result = await db_session.execute(
        select(ProjectOutput).filter(
            ProjectOutput.project_id == project_id,
            ProjectOutput.deliverable_id == deliverable_id,
        )
    )
    outputs = result.scalars().all()
    if not outputs:
        # Optionally raise 404 if no outputs exist, or return empty list
        logger = logging.getLogger(__name__)
        logger.info(
            f"No ProjectOutputs found for deliverable {deliverable_id} in project {project_id}"
        )
    return outputs


@router.get("/outputs/{output_id}", response_model=ProjectOutputResponse)
async def get_project_output_details(
    output_id: UUID,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
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
            status_code=status.HTTP_404_NOT_FOUND, detail="Project Output not found"
        )
    return project_output


@router.post(
    "/project-outputs/",
    response_model=ProjectOutputResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_output(
    output_data: CreateProjectOutputRequest,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
):
    """
    Creates a new project output.
    """
    try:
        import uuid

        project_output = ProjectOutput(
            id=uuid.uuid4(),
            deliverable_id=output_data.deliverable_id,
            project_id=output_data.project_id,
            output_name=output_data.output_name,
            output_url=output_data.output_url,
            delivery_date=output_data.delivery_date or datetime.utcnow(),
            comments_allowed_on_output=output_data.comments_allowed_on_output,
        )

        db_session.add(project_output)
        await db_session.commit()
        await db_session.refresh(project_output)

        return project_output

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error creating project output: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create project output: {str(e)}",
        )
