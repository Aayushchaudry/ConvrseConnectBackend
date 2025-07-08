# src/api/timeline/controllers.py

from datetime import datetime, date
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db_session
from src.middleware.auth_middleware import AuthContext, require_auth
from src.services.timeline_tracking_service import TimelineTrackingService

import logging
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/timeline",
    tags=["Timeline Tracking"],
    redirect_slashes=False,
)


# --- Request/Response Models ---

class TaskProgressRequest(BaseModel):
    """Request model for logging task progress."""
    
    progress_date: date = Field(..., description="Date of progress entry")
    percentage_complete: int = Field(..., ge=0, le=100, description="Percentage completion (0-100)")
    hours_spent: Optional[float] = Field(None, ge=0, description="Hours spent on this date")
    notes: Optional[str] = Field(None, max_length=1000, description="Progress notes")


class TaskProgressResponse(BaseModel):
    """Response model for task progress data."""
    
    id: UUID
    task_id: UUID
    progress_date: date
    percentage_complete: int
    hours_spent: Optional[float]
    notes: Optional[str]
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ProjectTimelineResponse(BaseModel):
    """Response model for project timeline data."""
    
    id: UUID
    project_id: UUID
    phase_name: str
    planned_start_date: Optional[date]
    planned_end_date: Optional[date]
    actual_start_date: Optional[date]
    actual_end_date: Optional[date]
    is_milestone: bool
    percentage_complete: Optional[int]
    dependencies: Optional[Dict[str, Any]]
    phase_order: Optional[int]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class TimelineComparisonResponse(BaseModel):
    """Response model for timeline comparison."""
    
    project_id: UUID
    planned_timeline: List[ProjectTimelineResponse]
    actual_timeline: List[ProjectTimelineResponse]
    variance_analysis: Dict[str, Any]
    timeline_health: Dict[str, Any]


class MilestoneRequest(BaseModel):
    """Request model for creating milestones."""
    
    phase_name: str = Field(..., min_length=1, max_length=255, description="Milestone name")
    planned_start_date: Optional[date] = Field(None, description="Planned start date")
    planned_end_date: Optional[date] = Field(None, description="Planned end date")
    dependencies: Optional[Dict[str, Any]] = Field(None, description="Dependencies information")
    phase_order: Optional[int] = Field(None, description="Order of this phase")


class ProgressSummaryResponse(BaseModel):
    """Response model for project progress summary."""
    
    project_id: UUID
    overall_completion_percentage: float
    tasks_summary: Dict[str, Any]
    timeline_summary: Dict[str, Any]
    milestone_summary: Dict[str, Any]
    completion_prediction: Dict[str, Any]


class UpdateProgressRequest(BaseModel):
    """Request model for updating progress."""
    
    percentage_complete: int = Field(..., ge=0, le=100, description="Updated percentage completion")
    hours_spent: Optional[float] = Field(None, ge=0, description="Updated hours spent")
    notes: Optional[str] = Field(None, max_length=1000, description="Updated notes")


# --- API Endpoints ---

@router.post("/tasks/{task_id}/progress", response_model=TaskProgressResponse, status_code=status.HTTP_201_CREATED)
async def log_task_progress(
    task_id: UUID,
    progress_data: TaskProgressRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Log daily progress for a specific task.
    """
    auth_context = require_auth(request)
    
    try:
        timeline_service = TimelineTrackingService(db_session)
        
        # Log daily progress
        progress = await timeline_service.log_daily_progress(
            task_id=task_id,
            progress_date=progress_data.progress_date,
            percentage_complete=progress_data.percentage_complete,
            hours_spent=progress_data.hours_spent,
            notes=progress_data.notes,
            created_by=UUID(auth_context.user_id) if auth_context.user_id else None,
        )
        
        return TaskProgressResponse(
            id=progress.id,
            task_id=progress.task_id,
            progress_date=progress.progress_date,
            percentage_complete=progress.percentage_complete,
            hours_spent=float(progress.hours_spent) if progress.hours_spent else None,
            notes=progress.notes,
            created_by=progress.created_by,
            created_at=progress.created_at,
            updated_at=progress.updated_at,
        )
        
    except ValueError as ve:
        logger.error(f"Validation error logging task progress: {ve}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve),
        )
    except Exception as e:
        logger.error(f"Error logging task progress: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to log task progress: {str(e)}",
        )


@router.get("/tasks/{task_id}/progress", response_model=List[TaskProgressResponse])
async def get_task_progress_history(
    task_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get progress history for a specific task.
    """
    auth_context = require_auth(request)
    
    try:
        from sqlalchemy import select
        from src.models.task_progress import TaskProgress
        
        result = await db_session.execute(
            select(TaskProgress)
            .filter(TaskProgress.task_id == task_id)
            .order_by(TaskProgress.progress_date.desc())
        )
        progress_records = result.scalars().all()
        
        return [
            TaskProgressResponse(
                id=progress.id,
                task_id=progress.task_id,
                progress_date=progress.progress_date,
                percentage_complete=progress.percentage_complete,
                hours_spent=float(progress.hours_spent) if progress.hours_spent else None,
                notes=progress.notes,
                created_by=progress.created_by,
                created_at=progress.created_at,
                updated_at=progress.updated_at,
            )
            for progress in progress_records
        ]
        
    except Exception as e:
        logger.error(f"Error fetching task progress history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch task progress history: {str(e)}",
        )


@router.put("/tasks/{task_id}/progress/{progress_date}", response_model=TaskProgressResponse)
async def update_task_progress(
    task_id: UUID,
    progress_date: date,
    update_data: UpdateProgressRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Update progress for a specific date.
    """
    auth_context = require_auth(request)
    
    try:
        from sqlalchemy import select, update
        from src.models.task_progress import TaskProgress
        
        # Check if progress entry exists
        result = await db_session.execute(
            select(TaskProgress).filter(
                TaskProgress.task_id == task_id,
                TaskProgress.progress_date == progress_date
            )
        )
        progress = result.scalar_one_or_none()
        
        if not progress:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Progress entry not found for this date",
            )
        
        # Update progress
        await db_session.execute(
            update(TaskProgress)
            .filter(
                TaskProgress.task_id == task_id,
                TaskProgress.progress_date == progress_date
            )
            .values(
                percentage_complete=update_data.percentage_complete,
                hours_spent=update_data.hours_spent,
                notes=update_data.notes,
                updated_at=datetime.utcnow(),
            )
        )
        await db_session.commit()
        
        # Refresh and return updated progress
        await db_session.refresh(progress)
        
        return TaskProgressResponse(
            id=progress.id,
            task_id=progress.task_id,
            progress_date=progress.progress_date,
            percentage_complete=progress.percentage_complete,
            hours_spent=float(progress.hours_spent) if progress.hours_spent else None,
            notes=progress.notes,
            created_by=progress.created_by,
            created_at=progress.created_at,
            updated_at=progress.updated_at,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating task progress: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update task progress: {str(e)}",
        )


@router.get("/projects/{project_id}/progress", response_model=ProgressSummaryResponse)
async def get_project_progress(
    project_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get overall project progress summary.
    """
    auth_context = require_auth(request)
    
    try:
        timeline_service = TimelineTrackingService(db_session)
        
        # Calculate overall project completion
        completion_percentage = await timeline_service.calculate_project_completion(project_id)
        
        # Get project timeline summary
        timeline_summary = await timeline_service.get_project_timeline_summary(project_id)
        
        # Get upcoming milestones
        upcoming_milestones = await timeline_service.get_upcoming_milestones(project_id, limit=5)
        
        return ProgressSummaryResponse(
            project_id=project_id,
            overall_completion_percentage=float(completion_percentage),
            tasks_summary=timeline_summary.get("tasks_summary", {}),
            timeline_summary=timeline_summary.get("timeline_summary", {}),
            milestone_summary={
                "upcoming_milestones": [
                    {
                        "id": str(milestone.id),
                        "phase_name": milestone.phase_name,
                        "planned_end_date": milestone.planned_end_date.isoformat() if milestone.planned_end_date else None,
                        "percentage_complete": milestone.percentage_complete,
                        "is_milestone": milestone.is_milestone,
                    }
                    for milestone in upcoming_milestones
                ],
                "total_milestones": len(upcoming_milestones),
            },
            completion_prediction=timeline_summary.get("completion_prediction", {}),
        )
        
    except Exception as e:
        logger.error(f"Error fetching project progress: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch project progress: {str(e)}",
        )


@router.get("/projects/{project_id}/timeline/actual", response_model=List[ProjectTimelineResponse])
async def get_actual_timeline(
    project_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get actual timeline for a project.
    """
    auth_context = require_auth(request)
    
    try:
        from sqlalchemy import select
        from src.models.project_timeline import ProjectTimeline
        
        result = await db_session.execute(
            select(ProjectTimeline)
            .filter(ProjectTimeline.project_id == project_id)
            .order_by(ProjectTimeline.phase_order)
        )
        timeline_records = result.scalars().all()
        
        return [
            ProjectTimelineResponse(
                id=timeline.id,
                project_id=timeline.project_id,
                phase_name=timeline.phase_name,
                planned_start_date=timeline.planned_start_date,
                planned_end_date=timeline.planned_end_date,
                actual_start_date=timeline.actual_start_date,
                actual_end_date=timeline.actual_end_date,
                is_milestone=timeline.is_milestone,
                percentage_complete=timeline.percentage_complete,
                dependencies=timeline.dependencies,
                phase_order=timeline.phase_order,
                created_at=timeline.created_at,
                updated_at=timeline.updated_at,
            )
            for timeline in timeline_records
        ]
        
    except Exception as e:
        logger.error(f"Error fetching actual timeline: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch actual timeline: {str(e)}",
        )


@router.get("/projects/{project_id}/timeline/planned", response_model=List[ProjectTimelineResponse])
async def get_planned_timeline(
    project_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get planned timeline for a project.
    """
    auth_context = require_auth(request)
    
    try:
        from sqlalchemy import select
        from src.models.project_timeline import ProjectTimeline
        
        result = await db_session.execute(
            select(ProjectTimeline)
            .filter(ProjectTimeline.project_id == project_id)
            .order_by(ProjectTimeline.phase_order)
        )
        timeline_records = result.scalars().all()
        
        # Filter to show only planned dates
        return [
            ProjectTimelineResponse(
                id=timeline.id,
                project_id=timeline.project_id,
                phase_name=timeline.phase_name,
                planned_start_date=timeline.planned_start_date,
                planned_end_date=timeline.planned_end_date,
                actual_start_date=None,  # Don't include actual dates in planned view
                actual_end_date=None,
                is_milestone=timeline.is_milestone,
                percentage_complete=timeline.percentage_complete,
                dependencies=timeline.dependencies,
                phase_order=timeline.phase_order,
                created_at=timeline.created_at,
                updated_at=timeline.updated_at,
            )
            for timeline in timeline_records
        ]
        
    except Exception as e:
        logger.error(f"Error fetching planned timeline: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch planned timeline: {str(e)}",
        )


@router.get("/projects/{project_id}/timeline/comparison", response_model=TimelineComparisonResponse)
async def get_timeline_comparison(
    project_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Compare actual vs planned timeline.
    """
    auth_context = require_auth(request)
    
    try:
        timeline_service = TimelineTrackingService(db_session)
        
        # Get timeline variance
        variance_analysis = await timeline_service.get_timeline_variance(project_id)
        
        # Get timeline records
        from sqlalchemy import select
        from src.models.project_timeline import ProjectTimeline
        
        result = await db_session.execute(
            select(ProjectTimeline)
            .filter(ProjectTimeline.project_id == project_id)
            .order_by(ProjectTimeline.phase_order)
        )
        timeline_records = result.scalars().all()
        
        # Create planned and actual timeline representations
        planned_timeline = [
            ProjectTimelineResponse(
                id=timeline.id,
                project_id=timeline.project_id,
                phase_name=timeline.phase_name,
                planned_start_date=timeline.planned_start_date,
                planned_end_date=timeline.planned_end_date,
                actual_start_date=None,
                actual_end_date=None,
                is_milestone=timeline.is_milestone,
                percentage_complete=timeline.percentage_complete,
                dependencies=timeline.dependencies,
                phase_order=timeline.phase_order,
                created_at=timeline.created_at,
                updated_at=timeline.updated_at,
            )
            for timeline in timeline_records
        ]
        
        actual_timeline = [
            ProjectTimelineResponse(
                id=timeline.id,
                project_id=timeline.project_id,
                phase_name=timeline.phase_name,
                planned_start_date=timeline.planned_start_date,
                planned_end_date=timeline.planned_end_date,
                actual_start_date=timeline.actual_start_date,
                actual_end_date=timeline.actual_end_date,
                is_milestone=timeline.is_milestone,
                percentage_complete=timeline.percentage_complete,
                dependencies=timeline.dependencies,
                phase_order=timeline.phase_order,
                created_at=timeline.created_at,
                updated_at=timeline.updated_at,
            )
            for timeline in timeline_records
        ]
        
        return TimelineComparisonResponse(
            project_id=project_id,
            planned_timeline=planned_timeline,
            actual_timeline=actual_timeline,
            variance_analysis=variance_analysis,
            timeline_health={
                "overall_status": variance_analysis.get("overall_status", "unknown"),
                "at_risk_phases": variance_analysis.get("at_risk_phases", []),
                "delayed_phases": variance_analysis.get("delayed_phases", []),
            },
        )
        
    except Exception as e:
        logger.error(f"Error fetching timeline comparison: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch timeline comparison: {str(e)}",
        )


@router.post("/projects/{project_id}/milestones", response_model=ProjectTimelineResponse, status_code=status.HTTP_201_CREATED)
async def create_project_milestone(
    project_id: UUID,
    milestone_data: MilestoneRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Create a project milestone.
    """
    auth_context = require_auth(request)
    
    try:
        timeline_service = TimelineTrackingService(db_session)
        
        # Create milestone
        milestone = await timeline_service.create_project_milestones(
            project_id=project_id,
            milestone_config={
                "milestones": [{
                    "phase_name": milestone_data.phase_name,
                    "planned_start_date": milestone_data.planned_start_date,
                    "planned_end_date": milestone_data.planned_end_date,
                    "dependencies": milestone_data.dependencies,
                    "phase_order": milestone_data.phase_order,
                    "is_milestone": True,
                }]
            }
        )
        
        # Return the first (and only) created milestone
        created_milestone = milestone[0] if milestone else None
        if not created_milestone:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create milestone",
            )
        
        return ProjectTimelineResponse(
            id=created_milestone.id,
            project_id=created_milestone.project_id,
            phase_name=created_milestone.phase_name,
            planned_start_date=created_milestone.planned_start_date,
            planned_end_date=created_milestone.planned_end_date,
            actual_start_date=created_milestone.actual_start_date,
            actual_end_date=created_milestone.actual_end_date,
            is_milestone=created_milestone.is_milestone,
            percentage_complete=created_milestone.percentage_complete,
            dependencies=created_milestone.dependencies,
            phase_order=created_milestone.phase_order,
            created_at=created_milestone.created_at,
            updated_at=created_milestone.updated_at,
        )
        
    except ValueError as ve:
        logger.error(f"Validation error creating milestone: {ve}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve),
        )
    except Exception as e:
        logger.error(f"Error creating milestone: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create milestone: {str(e)}",
        )


@router.get("/projects/{project_id}/milestones/upcoming", response_model=List[ProjectTimelineResponse])
async def get_upcoming_milestones(
    project_id: UUID,
    request: Request,
    limit: int = 10,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get upcoming milestones for a project.
    """
    auth_context = require_auth(request)
    
    try:
        timeline_service = TimelineTrackingService(db_session)
        
        milestones = await timeline_service.get_upcoming_milestones(project_id, limit=limit)
        
        return [
            ProjectTimelineResponse(
                id=milestone.id,
                project_id=milestone.project_id,
                phase_name=milestone.phase_name,
                planned_start_date=milestone.planned_start_date,
                planned_end_date=milestone.planned_end_date,
                actual_start_date=milestone.actual_start_date,
                actual_end_date=milestone.actual_end_date,
                is_milestone=milestone.is_milestone,
                percentage_complete=milestone.percentage_complete,
                dependencies=milestone.dependencies,
                phase_order=milestone.phase_order,
                created_at=milestone.created_at,
                updated_at=milestone.updated_at,
            )
            for milestone in milestones
        ]
        
    except Exception as e:
        logger.error(f"Error fetching upcoming milestones: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch upcoming milestones: {str(e)}",
        ) 