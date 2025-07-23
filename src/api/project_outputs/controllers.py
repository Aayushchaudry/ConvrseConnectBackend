"""
API controllers for project outputs.
"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db_session, get_event_bus
from src.events.event_bus_interface import EventBus
from src.models.project_output import ProjectOutput
from src.schemas.project_output import (
    ProjectOutputCreate,
    ProjectOutputResponse,
    ProjectOutputUpdate,
    ProjectCompilationResponse
)
from src.services.project_output_service import ProjectOutputService

router = APIRouter(prefix="/api/v1", tags=["project-outputs"])
logger = logging.getLogger(__name__)


@router.post("/project-outputs", response_model=ProjectOutputResponse, status_code=status.HTTP_201_CREATED)
async def create_project_output(
    project_output: ProjectOutputCreate,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
):
    """Create a new project output."""
    service = ProjectOutputService(lambda: db_session, event_bus)
    
    output = await service.generate_project_output_for_deliverable(
        deliverable_id=project_output.deliverable_id,
        output_name=project_output.name
    )
    
    if not output:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create project output"
        )
    
    return output


@router.get("/projects/{project_id}/outputs", response_model=List[ProjectOutputResponse])
async def list_project_outputs(
    project_id: UUID,
    db_session: AsyncSession = Depends(get_db_session),
):
    """List all project outputs for a project."""
    from sqlalchemy import select
    
    result = await db_session.execute(
        select(ProjectOutput).filter(ProjectOutput.project_id == project_id)
    )
    outputs = result.scalars().all()
    
    return outputs


@router.get("/deliverables/{deliverable_id}/outputs", response_model=List[ProjectOutputResponse])
async def list_deliverable_outputs(
    deliverable_id: UUID,
    db_session: AsyncSession = Depends(get_db_session),
):
    """List all project outputs for a deliverable."""
    from sqlalchemy import select
    
    result = await db_session.execute(
        select(ProjectOutput).filter(ProjectOutput.deliverable_id == deliverable_id)
    )
    outputs = result.scalars().all()
    
    return outputs


@router.post("/projects/{project_id}/compile", response_model=ProjectCompilationResponse)
async def compile_project(
    project_id: UUID,
    background_tasks: BackgroundTasks,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
):
    """Compile all project outputs into a comprehensive project package."""
    service = ProjectOutputService(lambda: db_session, event_bus)
    
    # Start compilation in background
    background_tasks.add_task(service.create_project_compilation, project_id)
    
    return {
        "project_id": project_id,
        "compilation_started": True,
        "compilation_url": f"https://example.com/api/project-compilations/{project_id}"
    }


@router.post("/deliverables/{deliverable_id}/generate-output", response_model=ProjectOutputResponse)
async def generate_deliverable_output(
    deliverable_id: UUID,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
):
    """Generate a project output for a deliverable with all reviews approved."""
    service = ProjectOutputService(lambda: db_session, event_bus)
    
    output = await service.generate_project_output_for_deliverable(deliverable_id)
    
    if not output:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to generate project output. Check if all reviews are approved."
        )
    
    # Compile the output in the background
    background_tasks = BackgroundTasks()
    background_tasks.add_task(service.compile_final_deliverable, deliverable_id, output.id)
    
    return output


@router.post("/check-pending-outputs", response_model=dict)
async def check_pending_outputs(
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
):
    """Check for deliverables with all reviews approved and generate outputs."""
    service = ProjectOutputService(lambda: db_session, event_bus)
    
    created_outputs = await service.generate_outputs_for_approved_deliverables()
    
    return {
        "outputs_created": len(created_outputs),
        "deliverable_ids": [str(d_id) for d_id in created_outputs.keys()]
    }