# src/api/internal_tasks/controllers.py

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db_session
from src.config.event_bus import get_event_bus
from src.events.event_bus_interface import EventBus
from src.models.internal_task import Priority, TaskStatus, TaskType
from src.services.production_management_service import ProductionManagementService

router = APIRouter(prefix="/internal-tasks", tags=["Internal Tasks"])


# --- Pydantic Schema for Request Body ---
class CreateInternalTaskRequest(BaseModel):
    """
    Schema for the request body when creating a new internal task.
    """

    project_id: UUID
    deliverable_id: UUID
    parent_task_id: Optional[UUID] = None
    task_name: str = Field(..., min_length=1, max_length=255)
    task_type: TaskType
    status: TaskStatus = TaskStatus.TODO
    priority: Priority = Priority.NORMAL
    start_date: Optional[datetime] = None
    tentative_end_date: Optional[datetime] = None
    description: Optional[str] = None


# --- Pydantic Schema for Response Body (Internal Task Details) ---
class InternalTaskResponse(BaseModel):
    """
    Schema for the response body when returning InternalTask details.
    """

    id: UUID
    project_id: UUID
    deliverable_id: UUID
    parent_task_id: Optional[UUID]
    task_name: str
    task_type: TaskType
    status: TaskStatus
    priority: Priority
    start_date: Optional[datetime]
    tentative_end_date: Optional[datetime]
    actual_end_date: Optional[datetime]
    description: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- API Endpoints ---


@router.post(
    "/", response_model=InternalTaskResponse, status_code=status.HTTP_201_CREATED
)
async def create_internal_task(
    task_data: CreateInternalTaskRequest,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
):
    """
    Creates a new internal task.
    """
    try:
        import uuid

        from src.models.internal_task import InternalTask

        # Create the internal task
        task = InternalTask(
            id=uuid.uuid4(),
            project_id=task_data.project_id,
            deliverable_id=task_data.deliverable_id,
            parent_task_id=task_data.parent_task_id,
            task_name=task_data.task_name,
            task_type=task_data.task_type,
            status=task_data.status,
            priority=task_data.priority,
            start_date=task_data.start_date,
            tentative_end_date=task_data.tentative_end_date,
            description=task_data.description,
        )

        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)

        return task

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error creating internal task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create internal task: {str(e)}",
        )


@router.post("/{task_id}/complete", response_model=InternalTaskResponse)
async def complete_internal_task_api(
    task_id: UUID,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
):
    """
    API endpoint to manually mark an internal task as complete.
    For testing purposes to trigger the SAGA's next phase.
    """
    try:
        production_service = ProductionManagementService(
            db_session_factory=lambda: db_session, event_bus=event_bus
        )
        completed_task = await production_service.complete_internal_task(
            task_id=task_id, actual_end_date=datetime.utcnow()
        )
        return completed_task
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error completing internal task {task_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete task: {str(e)}",
        )


@router.get(
    "/deliverables/{deliverable_id}/tasks/", response_model=List[InternalTaskResponse]
)
async def list_tasks_for_deliverable(
    deliverable_id: UUID,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
):
    """
    Retrieves a list of all internal tasks for a specific deliverable.
    """
    from sqlalchemy import select

    from src.models.internal_task import InternalTask

    result = await db_session.execute(
        select(InternalTask).filter(InternalTask.deliverable_id == deliverable_id)
    )
    return result.scalars().all()
