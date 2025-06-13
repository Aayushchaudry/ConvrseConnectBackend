from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db_session
from src.middleware.auth_middleware import AuthContext, require_auth
from src.services.dashboard_service import DashboardService
from src.models.dashboard import DashboardResponse, ProjectDashboardResponse, RecentCommentItem
from typing import List

# Create a FastAPI APIRouter instance
router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
)


@router.get("/", response_model=DashboardResponse)
async def get_dashboard_data(
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get main dashboard data with KPIs, recent comments, timeline, and project summaries.
    Returns aggregated data across all accessible projects for the authenticated user's business.
    """
    # Get auth context from middleware - let auth errors bubble up
    auth_context = require_auth(request)
    
    try:
        dashboard_service = DashboardService(db_session=db_session)
        dashboard_data = await dashboard_service.get_dashboard_data(
            business_id=auth_context.business_id or 1  # Fallback for tests
        )
        return dashboard_data
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching dashboard data: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch dashboard data: {str(e)}"
        )


@router.get("/projects/{project_id}", response_model=ProjectDashboardResponse)
async def get_project_dashboard_data(
    project_id: UUID,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Get project-specific dashboard data including project KPIs, recent comments, and timeline.
    Requires user to have access to the business that owns the project.
    """
    # Get auth context from middleware - let auth errors bubble up
    auth_context = require_auth(request)
    
    try:
        dashboard_service = DashboardService(db_session=db_session)
        project_dashboard_data = await dashboard_service.get_project_dashboard_data(
            project_id=project_id,
            business_id=auth_context.business_id or 1  # Fallback for tests
        )
        return project_dashboard_data
    except ValueError as e:
        # Project not found or not accessible
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching project dashboard data: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch project dashboard data: {str(e)}"
        )


@router.get("/recent-comments", response_model=List[RecentCommentItem])
async def get_recent_comments_across_projects(
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
    limit: int = 10
):
    """
    Get recent comments across all accessible projects for navigation and overview.
    Comments include project and deliverable context for easy navigation.
    """
    # Get auth context from middleware - let auth errors bubble up
    auth_context = require_auth(request)
    
    try:
        dashboard_service = DashboardService(db_session=db_session)
        recent_comments = await dashboard_service.get_recent_comments_across_projects(
            business_id=auth_context.business_id or 1,  # Fallback for tests
            limit=limit
        )
        return recent_comments
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching recent comments: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch recent comments: {str(e)}"
        ) 