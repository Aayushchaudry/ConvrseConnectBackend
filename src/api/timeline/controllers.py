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


class UpdateActualDatesRequest(BaseModel):
    """Request model for updating actual start and end dates."""
    
    actual_start_date: Optional[date] = Field(None, description="Actual start date")
    actual_end_date: Optional[date] = Field(None, description="Actual end date")
    notes: Optional[str] = Field(None, max_length=1000, description="Notes about the date changes")


class TimelinePhaseUpdateResponse(BaseModel):
    """Response model for timeline phase updates."""
    
    id: UUID
    phase_name: str
    planned_start_date: Optional[date]
    planned_end_date: Optional[date]
    actual_start_date: Optional[date]
    actual_end_date: Optional[date]
    variance_days: Optional[int]
    variance_status: str
    notes: Optional[str]
    
    class Config:
        from_attributes = True


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
    timeline_type: str
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
                timeline_type=timeline.timeline_type,
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
    # auth_context = require_auth(request)
    
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
                timeline_type=timeline.timeline_type,
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
    # Temporarily bypass auth for testing
    # auth_context = require_auth(request)
    
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
                timeline_type=timeline.timeline_type,
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
                timeline_type=timeline.timeline_type,
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
            timeline_type=created_milestone.timeline_type,
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
                timeline_type=milestone.timeline_type,
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


@router.put("/{timeline_id}/actual-dates", response_model=TimelinePhaseUpdateResponse)
async def update_timeline_actual_dates(
    timeline_id: UUID,
    update_data: UpdateActualDatesRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Update actual start and end dates for a timeline phase.
    """
    auth_context = require_auth(request)
    
    try:
        timeline_service = TimelineTrackingService(db_session)
        
        # Update the timeline phase with actual dates
        updated_timeline = await timeline_service.update_timeline_actual_dates(
            timeline_id=timeline_id,
            actual_start_date=update_data.actual_start_date,
            actual_end_date=update_data.actual_end_date,
            notes=update_data.notes
        )
        
        # Calculate variance
        variance_days = None
        variance_status = "on_track"
        
        if updated_timeline.actual_end_date and updated_timeline.planned_end_date:
            variance_days = (updated_timeline.actual_end_date - updated_timeline.planned_end_date).days
            if variance_days > 0:
                variance_status = "delayed"
            elif variance_days < 0:
                variance_status = "ahead"
        
        return TimelinePhaseUpdateResponse(
            id=updated_timeline.id,
            phase_name=updated_timeline.phase_name,
            planned_start_date=updated_timeline.planned_start_date,
            planned_end_date=updated_timeline.planned_end_date,
            actual_start_date=updated_timeline.actual_start_date,
            actual_end_date=updated_timeline.actual_end_date,
            variance_days=variance_days,
            variance_status=variance_status,
            notes=update_data.notes
        )
        
    except ValueError as e:
        logger.warning(f"Invalid data for timeline update: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating timeline actual dates: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update timeline actual dates: {str(e)}"
        )


@router.get("/projects/{project_id}/variance-analysis")
async def get_project_timeline_variance_analysis(
    project_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get detailed variance analysis for all timeline phases in a project.
    """
    auth_context = require_auth(request)
    
    try:
        timeline_service = TimelineTrackingService(db_session)
        
        # Get all timeline phases for the project
        project_timeline = await timeline_service.get_project_timeline(project_id)
        
        variance_analysis = []
        total_variance_days = 0
        phases_with_variance = 0
        
        for phase in project_timeline:
            phase_analysis = {
                "timeline_id": phase.id,
                "phase_name": phase.phase_name,
                "planned_start_date": phase.planned_start_date,
                "planned_end_date": phase.planned_end_date,
                "actual_start_date": phase.actual_start_date,
                "actual_end_date": phase.actual_end_date,
                "variance_days": None,
                "variance_status": "pending"
            }
            
            # Calculate variance if actual dates are available
            if phase.actual_end_date and phase.planned_end_date:
                variance_days = (phase.actual_end_date - phase.planned_end_date).days
                phase_analysis["variance_days"] = variance_days
                
                if variance_days > 0:
                    phase_analysis["variance_status"] = "delayed"
                    total_variance_days += variance_days
                    phases_with_variance += 1
                elif variance_days < 0:
                    phase_analysis["variance_status"] = "ahead"
                    total_variance_days += variance_days
                    phases_with_variance += 1
                else:
                    phase_analysis["variance_status"] = "on_track"
            
            variance_analysis.append(phase_analysis)
        
        # Overall project variance summary
        summary = {
            "total_phases": len(project_timeline),
            "completed_phases": len([p for p in project_timeline if p.actual_end_date]),
            "average_variance_days": total_variance_days / phases_with_variance if phases_with_variance > 0 else 0,
            "project_status": "on_track" if total_variance_days <= 0 else "delayed"
        }
        
        return {
            "project_id": project_id,
            "variance_analysis": variance_analysis,
            "summary": summary,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error generating variance analysis: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate variance analysis: {str(e)}"
        )


@router.get("/projects/{project_id}/timeline/health", response_model=Dict[str, Any])
async def get_timeline_health(
    project_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get timeline health metrics and status.
    """
    auth_context = require_auth(request)
    
    try:
        timeline_service = TimelineTrackingService(db_session)
        
        # Get timeline variance data
        variance_data = await timeline_service.get_timeline_variance(project_id)
        
        # Calculate health metrics
        total_phases = len(variance_data.get("phases", []))
        delayed_phases = len([p for p in variance_data.get("phases", []) if p.get("is_delayed", False)])
        on_time_phases = total_phases - delayed_phases
        
        health_score = (on_time_phases / total_phases * 100) if total_phases > 0 else 100
        
        health_status = "healthy" if health_score >= 80 else "warning" if health_score >= 60 else "critical"
        
        return {
            "project_id": project_id,
            "health_score": round(health_score, 2),
            "health_status": health_status,
            "total_phases": total_phases,
            "delayed_phases": delayed_phases,
            "on_time_phases": on_time_phases,
            "average_variance_days": variance_data.get("average_variance_days", 0),
            "max_variance_days": variance_data.get("max_variance_days", 0),
            "variance_breakdown": variance_data.get("variance_breakdown", {}),
        }
        
    except Exception as e:
        logger.error(f"Error fetching timeline health: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch timeline health: {str(e)}",
        ) 