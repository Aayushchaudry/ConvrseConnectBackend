from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

from src.config.database import get_db_session
from src.middleware.auth_middleware import require_auth
from src.models.project import Project
from src.models.deliverable import Deliverable
from src.models.internal_task import InternalTask, TaskStatus
from src.models.review_item import ReviewItem, ReviewStatus

# Create a logger
logger = logging.getLogger(__name__)

# Create a FastAPI APIRouter instance
router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
    redirect_slashes=False,  # Prevent automatic redirects
)

# Simple in-memory cache for dashboard data (consider Redis for production)
_dashboard_cache: Dict[str, Any] = {}
CACHE_TTL = 30  # Cache for 30 seconds

def get_cache_key(business_id: int) -> str:
    """Generate cache key for dashboard data"""
    return f"dashboard_data_{business_id}"

def is_cache_valid(cache_entry: Dict[str, Any]) -> bool:
    """Check if cache entry is still valid"""
    if not cache_entry:
        return False
    return time.time() - cache_entry.get('timestamp', 0) < CACHE_TTL

# --- Response Models ---
class KPIData(BaseModel):
    title: str
    value: str | int | float
    change: Optional[float] = None
    changeType: Optional[str] = None
    icon: Optional[str] = None


class RecentComment(BaseModel):
    id: str
    project_id: str
    project_name: str
    deliverable_id: str
    deliverable_name: str
    comment_text: str
    created_at: datetime
    user_name: Optional[str] = None
    context_coordinates: Optional[str] = None
    timestamp_seconds: Optional[float] = None


class ProjectTimelineItem(BaseModel):
    id: str
    project_id: str
    project_name: str
    deliverable_id: Optional[str] = None
    deliverable_name: Optional[str] = None
    event_type: str
    event_date: str
    status: str
    description: Optional[str] = None


class DashboardData(BaseModel):
    kpis: List[KPIData]
    recent_comments: List[RecentComment]
    timeline: List[ProjectTimelineItem]
    projects: List[dict]


class ProjectDashboardData(BaseModel):
    project: dict
    kpis: List[KPIData]
    recent_comments: List[RecentComment]
    timeline: List[ProjectTimelineItem]


@router.get("/", response_model=DashboardData)
@router.get("", response_model=DashboardData)  # Handle both with and without trailing slash
async def get_dashboard_data(
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get main dashboard data with KPIs, recent comments, and timeline.
    """
    # Get auth context
    auth_context = require_auth(request)
    
    try:
        from src.services.dashboard_service import DashboardService
        
        # Use the dashboard service for better data aggregation
        dashboard_service = DashboardService(db_session)
        
        # Get business_id from auth context (assuming it's available)
        business_id = getattr(auth_context, 'business_id', 1)  # Default to 1 if not available
        
        # Check cache
        cache_key = get_cache_key(business_id)
        if cache_key in _dashboard_cache and is_cache_valid(_dashboard_cache[cache_key]):
            logger.info("Using cached dashboard data")
            cached_data = _dashboard_cache[cache_key]
            return DashboardData(
                kpis=cached_data["kpis"],
                recent_comments=cached_data["recent_comments"],
                timeline=cached_data["timeline"],
                projects=cached_data["projects"]
            )
        
        # Get comprehensive dashboard data from service
        dashboard_response = await dashboard_service.get_dashboard_data(business_id)
        
        # Convert to API response format
        kpis = [
            KPIData(
                title=kpi.title,
                value=kpi.value,
                icon=kpi.icon,
                change=kpi.change,
                changeType=kpi.change_type
            ) for kpi in dashboard_response.kpis
        ]
        
        # Convert timeline items
        timeline = [
            ProjectTimelineItem(
                id=item.id,
                project_id=item.project_id,
                project_name=item.project_name,
                deliverable_id=item.deliverable_id,
                deliverable_name=item.deliverable_name,
                event_type=item.event_type,
                event_date=item.event_date.isoformat() if isinstance(item.event_date, datetime) else item.event_date,
                status=item.status,
                description=item.description
            ) for item in dashboard_response.timeline
        ]
        
        # Convert projects to dict format
        projects_data = []
        for project in dashboard_response.projects:
            projects_data.append({
                "id": str(project.id),
                "name": project.name,
                "status": project.status,
                "start_date": project.start_date.isoformat() if project.start_date else None,
                "end_date": project.end_date.isoformat() if project.end_date else None,
                "created_at": project.created_at.isoformat() if project.created_at else None,
                "updated_at": project.updated_at.isoformat() if project.updated_at else None,
                "description": getattr(project, 'description', None)
            })

        # Cache the result
        _dashboard_cache[cache_key] = {
            "kpis": kpis,
            "recent_comments": dashboard_response.recent_comments,
            "timeline": timeline,
            "projects": projects_data,
            "timestamp": time.time()
        }

        return DashboardData(
            kpis=kpis,
            recent_comments=dashboard_response.recent_comments,
            timeline=timeline,
            projects=projects_data
        )
        
    except Exception as e:
        logger.error(f"Error fetching dashboard data: {e}", exc_info=True)
        
        # Fallback to basic implementation if service fails
        try:
            # Get projects without causing rollbacks
            projects_result = await db_session.execute(
                select(Project).order_by(Project.created_at.desc())
            )
            projects = projects_result.scalars().all()
            
            # Calculate KPIs
            # Active projects
            active_projects = len([p for p in projects if p.status == 'active'])
            total_projects = len(projects)
            
            # Get completed tasks count
            completed_tasks_result = await db_session.execute(
                select(func.count(InternalTask.id)).filter(
                    InternalTask.status == TaskStatus.DONE.value
                )
            )
            completed_tasks = completed_tasks_result.scalar() or 0
            
            # Get pending reviews count
            pending_reviews_result = await db_session.execute(
                select(func.count(ReviewItem.id)).filter(
                    ReviewItem.review_status == ReviewStatus.PENDING_REVIEW.value
                )
            )
            pending_reviews = pending_reviews_result.scalar() or 0
            
            kpis = [
                KPIData(
                    title="Active Projects",
                    value=active_projects,
                    icon="📊"
                ),
                KPIData(
                    title="Total Projects", 
                    value=total_projects,
                    icon="📁"
                ),
                KPIData(
                    title="Pending Reviews",
                    value=pending_reviews,
                    icon="📝"
                ),
                KPIData(
                    title="Completed Tasks",
                    value=completed_tasks,
                    icon="✓"
                )
            ]
            
            # Generate basic timeline from projects (fallback)
            timeline = []
            for project in projects[:5]:  # Limit to recent projects
                if project.start_date:
                    timeline.append(ProjectTimelineItem(
                        id=f"project-start-{project.id}",
                        project_id=str(project.id),
                        project_name=project.name,
                        event_type="project_start",
                        event_date=project.start_date.isoformat() if isinstance(project.start_date, datetime) else project.start_date,
                        status="active",
                        description=f"Project {project.name} started"
                    ))
            
            # Sort timeline by date
            timeline.sort(key=lambda x: x.event_date, reverse=True)
            
            # Convert projects to dict format
            projects_data = []
            for project in projects:
                projects_data.append({
                    "id": str(project.id),
                    "name": project.name,
                    "status": project.status,
                    "start_date": project.start_date.isoformat() if project.start_date else None,
                    "end_date": project.end_date.isoformat() if project.end_date else None,
                    "created_at": project.created_at.isoformat() if project.created_at else None,
                    "updated_at": project.updated_at.isoformat() if project.updated_at else None,
                    "description": getattr(project, 'description', None)
                })

            # Cache the fallback result
            cache_key = get_cache_key(getattr(auth_context, 'business_id', 1))
            _dashboard_cache[cache_key] = {
                "kpis": kpis,
                "recent_comments": [],
                "timeline": timeline,
                "projects": projects_data,
                "timestamp": time.time()
            }

            return DashboardData(
                kpis=kpis,
                recent_comments=[],  # Will be populated by separate endpoint
                timeline=timeline,
                projects=projects_data
            )
            
        except Exception as fallback_error:
            logger.error(f"Fallback dashboard data fetch also failed: {fallback_error}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch dashboard data"
            )


@router.get("/recent-comments", response_model=List[RecentComment])
async def get_recent_comments(
    request: Request,
    limit: int = 10,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get recent comments across all projects.
    """
    # Get auth context
    auth_context = require_auth(request)
    
    try:
        # For now, return empty list as we don't have a comments table yet
        # TODO: Implement when comments system is added
        return []
        
    except Exception as e:
        logger.error(f"Error fetching recent comments: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch recent comments: {str(e)}"
        )


@router.get("/projects/{project_id}/dashboard", response_model=ProjectDashboardData)
async def get_project_dashboard(
    project_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get project-specific dashboard data.
    """
    # Get auth context
    auth_context = require_auth(request)
    
    try:
        # Get project details
        project_result = await db_session.execute(
            select(Project).filter(Project.id == project_id)
        )
        project = project_result.scalar_one_or_none()
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Get deliverables for this project
        deliverables_result = await db_session.execute(
            select(Deliverable).filter(Deliverable.project_id == project_id)
        )
        deliverables = deliverables_result.scalars().all()
        
        # Calculate project-specific KPIs
        total_deliverables = len(deliverables)
        completed_deliverables = len([d for d in deliverables if d.current_status == 'completed'])
        pending_deliverables = len([d for d in deliverables if d.current_status == 'pending'])
        
        progress_percentage = 0
        if total_deliverables > 0:
            progress_percentage = round((completed_deliverables / total_deliverables) * 100)
        
        kpis = [
            KPIData(
                title="Total Deliverables",
                value=total_deliverables,
                icon="📦"
            ),
            KPIData(
                title="Completed",
                value=completed_deliverables,
                icon="✅"
            ),
            KPIData(
                title="Pending",
                value=pending_deliverables,
                icon="⏳"
            ),
            KPIData(
                title="Progress",
                value=f"{progress_percentage}%",
                icon="📈"
            )
        ]
        
        # Generate project timeline
        timeline = []
        if project.start_date:
            timeline.append(ProjectTimelineItem(
                id=f"project-start-{project.id}",
                project_id=str(project.id),
                project_name=project.name,
                event_type="project_start",
                event_date=project.start_date.isoformat() if isinstance(project.start_date, datetime) else project.start_date,
                status="completed",
                description="Project started"
            ))
        
        for deliverable in deliverables:
            if hasattr(deliverable, 'tentative_timeline_days') and deliverable.tentative_timeline_days and project.start_date:
                due_date = project.start_date + timedelta(days=deliverable.tentative_timeline_days)
                timeline.append(ProjectTimelineItem(
                    id=f"deliverable-due-{deliverable.id}",
                    project_id=str(project.id),
                    project_name=project.name,
                    deliverable_id=str(deliverable.id),
                    deliverable_name=getattr(deliverable, 'deliverable_sub_type', None) or getattr(deliverable, 'deliverable_type', 'Deliverable'),
                    event_type="deliverable_due",
                    event_date=due_date.isoformat(),
                    status=deliverable.current_status or "pending",
                    description=f"Deliverable due"
                ))
        
        if project.end_date:
            timeline.append(ProjectTimelineItem(
                id=f"project-end-{project.id}",
                project_id=str(project.id),
                project_name=project.name,
                event_type="project_end",
                event_date=project.end_date.isoformat() if isinstance(project.end_date, datetime) else project.end_date,
                status=project.status or "pending",
                description="Project completion"
            ))
        
        # Sort timeline by date
        timeline.sort(key=lambda x: x.event_date)
        
        # Convert project to dict
        project_data = {
            "id": str(project.id),
            "name": project.name,
            "status": project.status,
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "end_date": project.end_date.isoformat() if project.end_date else None,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
            "description": getattr(project, 'description', None)
        }
        
        return ProjectDashboardData(
            project=project_data,
            kpis=kpis,
            recent_comments=[],  # Will be populated when comments system is implemented
            timeline=timeline
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching project dashboard: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch project dashboard: {str(e)}"
        )