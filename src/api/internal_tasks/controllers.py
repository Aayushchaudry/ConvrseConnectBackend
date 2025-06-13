# src/api/internal_tasks/controllers.py

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db_session
from src.config.event_bus import get_event_bus
from src.events.event_bus_interface import EventBus
from src.models.internal_task import Priority, TaskStatus, TaskType
from src.services.production_management_service import ProductionManagementService
from src.middleware.auth_middleware import require_auth

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


# --- Simplified Schema for Project-Level Tasks (Frontend Interface) ---
class CreateProjectTaskRequest(BaseModel):
    """
    Simplified schema for creating project-level tasks from the frontend.
    """
    description: str = Field(..., min_length=1, max_length=1000, description="Task description")
    status: str = Field(default="todo", pattern="^(todo|in-progress|done)$", description="Task status")


class ProjectTaskResponse(BaseModel):
    """
    Simplified response schema for project-level tasks (frontend interface).
    """
    id: str  # UUID as string for frontend
    description: str
    status: str  # Simple status mapping
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UpdateProjectTaskRequest(BaseModel):
    """
    Schema for updating project-level task status.
    """
    status: str = Field(..., pattern="^(todo|in-progress|done)$", description="New task status")


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


# --- Helper Functions for Status Mapping ---
def map_frontend_status_to_task_status(frontend_status: str) -> TaskStatus:
    """Map simple frontend status to TaskStatus enum."""
    mapping = {
        "todo": TaskStatus.TODO,
        "in-progress": TaskStatus.IN_PROGRESS,
        "done": TaskStatus.DONE
    }
    return mapping.get(frontend_status, TaskStatus.TODO)


def map_task_status_to_frontend(task_status: TaskStatus) -> str:
    """Map TaskStatus enum to simple frontend status."""
    mapping = {
        TaskStatus.TODO: "todo",
        TaskStatus.IN_PROGRESS: "in-progress",
        TaskStatus.DONE: "done",
        TaskStatus.AWAITING_REVIEW: "done",  # Treat as done for frontend
        TaskStatus.BLOCKED: "todo",  # Treat as todo for frontend
        TaskStatus.ON_HOLD: "todo",  # Treat as todo for frontend
        TaskStatus.REJECTED_TERMINATED: "todo"  # Treat as todo for frontend
    }
    return mapping.get(task_status, "todo")


# --- NEW API Endpoints for Project-Level Tasks (Frontend Interface) ---

@router.get("/projects/{project_id}/tasks", response_model=List[ProjectTaskResponse])
async def get_project_tasks(
    project_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get all project-level tasks for a specific project.
    Returns simplified task data for the frontend TaskList component.
    """
    # Get auth context
    auth_context = require_auth(request)
    
    try:
        from sqlalchemy import select, and_
        from src.models.internal_task import InternalTask
        
        # Query project-level tasks (those with task_type="OTHER" and no specific deliverable requirement)
        # For now, we'll get all tasks for the project, but you could filter by task_type=OTHER
        result = await db_session.execute(
            select(InternalTask).filter(
                and_(
                    InternalTask.project_id == project_id,
                    InternalTask.task_type == TaskType.OTHER  # Only general project tasks
                )
            ).order_by(InternalTask.created_at.desc())
        )
        tasks = result.scalars().all()
        
        # Convert to simplified frontend format
        simplified_tasks = []
        for task in tasks:
            simplified_tasks.append(ProjectTaskResponse(
                id=str(task.id),
                description=task.description or task.task_name,
                status=map_task_status_to_frontend(task.status),
                created_at=task.created_at,
                updated_at=task.updated_at
            ))
        
        return simplified_tasks
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching project tasks: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch project tasks: {str(e)}"
        )


@router.post("/projects/{project_id}/tasks", response_model=ProjectTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_project_task(
    project_id: UUID,
    task_data: CreateProjectTaskRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Create a new project-level task.
    Uses the existing InternalTask model with simplified frontend interface.
    """
    # Get auth context
    auth_context = require_auth(request)
    
    try:
        import uuid
        from src.models.internal_task import InternalTask
        
        # Create the internal task with project-level defaults
        task = InternalTask(
            id=uuid.uuid4(),
            project_id=project_id,
            deliverable_id=None,  # Project-level tasks don't need a specific deliverable
            parent_task_id=None,
            task_name=task_data.description[:255],  # Truncate if needed for task_name
            task_type=TaskType.OTHER,  # Use OTHER for general project tasks
            status=map_frontend_status_to_task_status(task_data.status),
            priority=Priority.NORMAL,
            description=task_data.description,
            start_date=None,
            tentative_end_date=None,
        )

        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)

        # Return simplified response
        return ProjectTaskResponse(
            id=str(task.id),
            description=task.description or task.task_name,
            status=map_task_status_to_frontend(task.status),
            created_at=task.created_at,
            updated_at=task.updated_at
        )

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error creating project task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create project task: {str(e)}"
        )


@router.patch("/projects/{project_id}/tasks/{task_id}", response_model=ProjectTaskResponse)
async def update_project_task_status(
    project_id: UUID,
    task_id: UUID,
    update_data: UpdateProjectTaskRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Update the status of a project-level task.
    """
    # Get auth context
    auth_context = require_auth(request)
    
    try:
        from sqlalchemy import select, and_
        from src.models.internal_task import InternalTask
        
        # Get the task
        result = await db_session.execute(
            select(InternalTask).filter(
                and_(
                    InternalTask.id == task_id,
                    InternalTask.project_id == project_id,
                    InternalTask.task_type == TaskType.OTHER
                )
            )
        )
        task = result.scalar_one_or_none()
        
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        
        # Update the status
        task.status = map_frontend_status_to_task_status(update_data.status)
        
        # Set actual_end_date if marking as done
        if update_data.status == "done" and not task.actual_end_date:
            task.actual_end_date = datetime.utcnow()
        elif update_data.status != "done":
            task.actual_end_date = None  # Clear if moving back from done
        
        await db_session.commit()
        await db_session.refresh(task)
        
        # Return simplified response
        return ProjectTaskResponse(
            id=str(task.id),
            description=task.description or task.task_name,
            status=map_task_status_to_frontend(task.status),
            created_at=task.created_at,
            updated_at=task.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating project task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update project task: {str(e)}"
        )


@router.delete("/projects/{project_id}/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_task(
    project_id: UUID,
    task_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Delete a project-level task.
    """
    # Get auth context
    auth_context = require_auth(request)
    
    try:
        from sqlalchemy import select, and_
        from src.models.internal_task import InternalTask
        
        # Get the task
        result = await db_session.execute(
            select(InternalTask).filter(
                and_(
                    InternalTask.id == task_id,
                    InternalTask.project_id == project_id,
                    InternalTask.task_type == TaskType.OTHER
                )
            )
        )
        task = result.scalar_one_or_none()
        
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        
        await db_session.delete(task)
        await db_session.commit()
        
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error deleting project task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete project task: {str(e)}"
        )


# --- EXISTING API Endpoints (keeping for production tasks) ---

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
