# src/api/task_management/controllers.py

from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db_session
from src.middleware.auth_middleware import AuthContext, require_auth
from src.services.task_management_service import TaskManagementService
from src.models.internal_task import TaskStatus

import logging
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/task-management",
    tags=["Task Management"],
    redirect_slashes=False,
)


# --- Request/Response Models ---

class ProjectLevelTaskRequest(BaseModel):
    """Request model for creating project-level tasks."""
    
    title: str = Field(..., min_length=1, max_length=255, description="Task title")
    description: Optional[str] = Field(None, max_length=2000, description="Task description")
    estimated_hours: Optional[float] = Field(None, gt=0, description="Estimated hours for completion")
    priority: str = Field("MEDIUM", pattern="^(HIGH|MEDIUM|LOW)$", description="Task priority")
    deliverable_ids: Optional[List[UUID]] = Field(None, description="List of deliverable IDs to associate with this task")


class TaskDeliverableAssociationRequest(BaseModel):
    """Request model for associating tasks with deliverables."""
    
    deliverable_id: UUID = Field(..., description="Deliverable ID to associate with the task")
    is_primary_deliverable: bool = Field(False, description="Whether this is the primary deliverable for the task")
    estimated_hours: Optional[float] = Field(None, gt=0, description="Estimated hours for this specific association")


class TaskSharingAnalysisRequest(BaseModel):
    """Request model for analyzing task sharing opportunities."""
    
    task_title: str = Field(..., min_length=1, max_length=255, description="Task title to analyze")
    deliverable_id: UUID = Field(..., description="Deliverable requesting the task")


class SmartTaskCreationRequest(BaseModel):
    """Request model for smart task creation with sharing consideration."""
    
    title: str = Field(..., min_length=1, max_length=255, description="Task title")
    deliverable_id: UUID = Field(..., description="Deliverable requesting the task")
    description: Optional[str] = Field(None, max_length=2000, description="Task description")
    estimated_hours: Optional[float] = Field(None, gt=0, description="Estimated hours")
    priority: str = Field("MEDIUM", pattern="^(HIGH|MEDIUM|LOW)$", description="Task priority")
    force_create_new: bool = Field(False, description="Force creation of new task even if similar exists")


class SharedTaskResponse(BaseModel):
    """Response model for shared tasks."""
    
    id: UUID
    title: str
    description: Optional[str]
    status: TaskStatus
    priority: str
    estimated_hours: Optional[float]
    actual_hours: Optional[float]
    is_project_level: bool
    created_at: datetime
    updated_at: datetime
    associated_deliverables: List[Dict[str, Any]]
    
    class Config:
        from_attributes = True


class TaskAssociationResponse(BaseModel):
    """Response model for task-deliverable associations."""
    
    id: UUID
    task_id: UUID
    deliverable_id: UUID
    is_primary_deliverable: bool
    estimated_hours: Optional[float]
    actual_hours: Optional[float]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class TaskSharingAnalysisResponse(BaseModel):
    """Response model for task sharing analysis."""
    
    should_share: bool
    similar_tasks: List[Dict[str, Any]]
    recommendation: str
    reasoning: str


class SmartTaskCreationResponse(BaseModel):
    """Response model for smart task creation."""
    
    task: SharedTaskResponse
    was_shared: bool
    action_taken: str


# --- API Endpoints ---

@router.post("/projects/{project_id}/tasks/project-level", response_model=SharedTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_project_level_task(
    project_id: UUID,
    task_data: ProjectLevelTaskRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Create a new project-level task that can be shared across multiple deliverables.
    """
    auth_context = require_auth(request)
    
    try:
        task_service = TaskManagementService(db_session)
        
        # Create project-level task
        task = await task_service.create_project_level_task(
            project_id=project_id,
            title=task_data.title,
            description=task_data.description,
            estimated_hours=Decimal(str(task_data.estimated_hours)) if task_data.estimated_hours else None,
            priority=task_data.priority,
            created_by=UUID(auth_context.user_id) if auth_context.user_id else None,
            deliverable_ids=task_data.deliverable_ids,
        )
        
        # Get associated deliverables for response
        deliverables = await task_service.get_deliverables_for_task(task.id)
        
        # Format response
        return SharedTaskResponse(
            id=task.id,
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            estimated_hours=float(task.estimated_hours) if task.estimated_hours else None,
            actual_hours=float(task.actual_hours) if task.actual_hours else None,
            is_project_level=task.is_project_level,
            created_at=task.created_at,
            updated_at=task.updated_at,
            associated_deliverables=[
                {
                    "id": str(d.id),
                    "deliverable_type": d.deliverable_type,
                    "deliverable_sub_type": d.deliverable_sub_type,
                }
                for d in deliverables
            ],
        )
        
    except ValueError as ve:
        logger.error(f"Validation error creating project-level task: {ve}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve),
        )
    except Exception as e:
        logger.error(f"Error creating project-level task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create project-level task: {str(e)}",
        )


@router.get("/projects/{project_id}/tasks/shared", response_model=List[SharedTaskResponse])
async def get_shared_project_tasks(
    project_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get all shared (project-level) tasks for a project.
    """
    auth_context = require_auth(request)
    
    try:
        task_service = TaskManagementService(db_session)
        tasks = await task_service.get_shared_tasks_for_project(project_id)
        
        # Format response with associated deliverables
        response_tasks = []
        for task in tasks:
            deliverables = await task_service.get_deliverables_for_task(task.id)
            
            response_tasks.append(SharedTaskResponse(
                id=task.id,
                title=task.title,
                description=task.description,
                status=task.status,
                priority=task.priority,
                estimated_hours=float(task.estimated_hours) if task.estimated_hours else None,
                actual_hours=float(task.actual_hours) if task.actual_hours else None,
                is_project_level=task.is_project_level,
                created_at=task.created_at,
                updated_at=task.updated_at,
                associated_deliverables=[
                    {
                        "id": str(d.id),
                        "deliverable_type": d.deliverable_type,
                        "deliverable_sub_type": d.deliverable_sub_type,
                    }
                    for d in deliverables
                ],
            ))
        
        return response_tasks
        
    except Exception as e:
        logger.error(f"Error fetching shared tasks for project {project_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch shared tasks: {str(e)}",
        )


@router.post("/tasks/{task_id}/deliverables", response_model=TaskAssociationResponse, status_code=status.HTTP_201_CREATED)
async def associate_task_with_deliverable(
    task_id: UUID,
    association_data: TaskDeliverableAssociationRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Associate an existing task with a deliverable.
    """
    auth_context = require_auth(request)
    
    try:
        task_service = TaskManagementService(db_session)
        
        association = await task_service.associate_task_with_deliverable(
            task_id=task_id,
            deliverable_id=association_data.deliverable_id,
            is_primary_deliverable=association_data.is_primary_deliverable,
            estimated_hours=Decimal(str(association_data.estimated_hours)) if association_data.estimated_hours else None,
        )
        
        return TaskAssociationResponse(
            id=association.id,
            task_id=association.task_id,
            deliverable_id=association.deliverable_id,
            is_primary_deliverable=association.is_primary_deliverable,
            estimated_hours=float(association.estimated_hours) if association.estimated_hours else None,
            actual_hours=float(association.actual_hours) if association.actual_hours else None,
            created_at=association.created_at,
            updated_at=association.updated_at,
        )
        
    except ValueError as ve:
        logger.error(f"Validation error associating task with deliverable: {ve}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve),
        )
    except Exception as e:
        logger.error(f"Error associating task {task_id} with deliverable: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to associate task with deliverable: {str(e)}",
        )


@router.delete("/tasks/{task_id}/deliverables/{deliverable_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_task_deliverable_association(
    task_id: UUID,
    deliverable_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Remove association between a task and deliverable.
    """
    auth_context = require_auth(request)
    
    try:
        task_service = TaskManagementService(db_session)
        
        removed = await task_service.remove_task_deliverable_association(
            task_id=task_id,
            deliverable_id=deliverable_id,
        )
        
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task-deliverable association not found",
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing task-deliverable association: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove association: {str(e)}",
        )


@router.get("/tasks/{task_id}/deliverables", response_model=List[Dict[str, Any]])
async def get_task_deliverable_associations(
    task_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get all deliverables associated with a specific task.
    """
    auth_context = require_auth(request)
    
    try:
        task_service = TaskManagementService(db_session)
        deliverables = await task_service.get_deliverables_for_task(task_id)
        
        return [
            {
                "id": str(d.id),
                "deliverable_type": d.deliverable_type,
                "deliverable_sub_type": d.deliverable_sub_type,
                "deliverable_quantity": d.deliverable_quantity,  # NEW: For rendered images quantity
                "current_status": d.current_status,
                "tentative_timeline_days": d.tentative_timeline_days,
            }
            for d in deliverables
        ]
        
    except Exception as e:
        logger.error(f"Error fetching deliverables for task {task_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch task deliverables: {str(e)}",
        )


@router.get("/deliverables/{deliverable_id}/tasks", response_model=List[SharedTaskResponse])
async def get_deliverable_associated_tasks(
    deliverable_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get all tasks associated with a specific deliverable.
    """
    auth_context = require_auth(request)
    
    try:
        from sqlalchemy import select
        from src.models.internal_task import InternalTask
        from src.models.task_deliverable_association import TaskDeliverableAssociation
        
        # Get tasks associated with the deliverable
        result = await db_session.execute(
            select(InternalTask)
            .join(TaskDeliverableAssociation)
            .filter(TaskDeliverableAssociation.deliverable_id == deliverable_id)
        )
        tasks = result.scalars().all()
        
        # Also get deliverable-specific tasks (legacy)
        result = await db_session.execute(
            select(InternalTask)
            .filter(InternalTask.deliverable_id == deliverable_id)
        )
        deliverable_tasks = result.scalars().all()
        
        # Combine and deduplicate
        all_tasks = list({task.id: task for task in tasks + deliverable_tasks}.values())
        
        # Format response
        task_service = TaskManagementService(db_session)
        response_tasks = []
        
        for task in all_tasks:
            deliverables = await task_service.get_deliverables_for_task(task.id)
            
            response_tasks.append(SharedTaskResponse(
                id=task.id,
                title=task.title,
                description=task.description,
                status=task.status,
                priority=task.priority,
                estimated_hours=float(task.estimated_hours) if task.estimated_hours else None,
                actual_hours=float(task.actual_hours) if task.actual_hours else None,
                is_project_level=task.is_project_level,
                created_at=task.created_at,
                updated_at=task.updated_at,
                associated_deliverables=[
                    {
                        "id": str(d.id),
                        "deliverable_type": d.deliverable_type,
                        "deliverable_sub_type": d.deliverable_sub_type,
                    }
                    for d in deliverables
                ],
            ))
        
        return response_tasks
        
    except Exception as e:
        logger.error(f"Error fetching tasks for deliverable {deliverable_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch deliverable tasks: {str(e)}",
        )


@router.post("/projects/{project_id}/tasks/analyze-sharing", response_model=TaskSharingAnalysisResponse)
async def analyze_task_sharing(
    project_id: UUID,
    analysis_data: TaskSharingAnalysisRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Analyze task sharing opportunities for a given task title and deliverable.
    """
    auth_context = require_auth(request)
    
    try:
        task_service = TaskManagementService(db_session)
        
        suggestions = await task_service.suggest_task_sharing(
            project_id=project_id,
            task_title=analysis_data.task_title,
            deliverable_id=analysis_data.deliverable_id,
        )
        
        return TaskSharingAnalysisResponse(**suggestions)
        
    except Exception as e:
        logger.error(f"Error analyzing task sharing: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze task sharing: {str(e)}",
        )


@router.post("/projects/{project_id}/tasks/smart-create", response_model=SmartTaskCreationResponse, status_code=status.HTTP_201_CREATED)
async def smart_task_creation(
    project_id: UUID,
    task_data: SmartTaskCreationRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Smart task creation that considers sharing existing tasks.
    """
    auth_context = require_auth(request)
    
    try:
        task_service = TaskManagementService(db_session)
        
        task, was_shared, action_taken = await task_service.create_or_share_task(
            project_id=project_id,
            title=task_data.title,
            deliverable_id=task_data.deliverable_id,
            description=task_data.description,
            estimated_hours=Decimal(str(task_data.estimated_hours)) if task_data.estimated_hours else None,
            priority=task_data.priority,
            created_by=UUID(auth_context.user_id) if auth_context.user_id else None,
            force_create_new=task_data.force_create_new,
        )
        
        # Get associated deliverables for response
        deliverables = await task_service.get_deliverables_for_task(task.id)
        
        return SmartTaskCreationResponse(
            task=SharedTaskResponse(
                id=task.id,
                title=task.title,
                description=task.description,
                status=task.status,
                priority=task.priority,
                estimated_hours=float(task.estimated_hours) if task.estimated_hours else None,
                actual_hours=float(task.actual_hours) if task.actual_hours else None,
                is_project_level=task.is_project_level,
                created_at=task.created_at,
                updated_at=task.updated_at,
                associated_deliverables=[
                    {
                        "id": str(d.id),
                        "deliverable_type": d.deliverable_type,
                        "deliverable_sub_type": d.deliverable_sub_type,
                    }
                    for d in deliverables
                ],
            ),
            was_shared=was_shared,
            action_taken=action_taken,
        )
        
    except ValueError as ve:
        logger.error(f"Validation error in smart task creation: {ve}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve),
        )
    except Exception as e:
        logger.error(f"Error in smart task creation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create task: {str(e)}",
        ) 