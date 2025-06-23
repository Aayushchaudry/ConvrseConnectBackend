from typing import List, Optional
from datetime import datetime, timedelta
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_, or_
from sqlalchemy.orm import selectinload

from src.models.project import Project, ProjectStatus
from src.models.deliverable import Deliverable
from src.models.client_feedback import ClientFeedback
from src.models.internal_task import InternalTask
from src.models.review_item import ReviewItem
from src.models.dashboard import (
    KPIItem, 
    TimelineItem, 
    RecentCommentItem, 
    ProjectSummary,
    DashboardResponse,
    ProjectDashboardResponse
)
from src.services.cache_service import cache_service


class DashboardService:
    """Service for aggregating dashboard data including KPIs, timelines, and recent activity."""
    
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def get_dashboard_data(self, business_id: int) -> DashboardResponse:
        """Get main dashboard data with KPIs, recent comments, timeline, and projects."""
        
        # Try to get from cache first
        cached_data = cache_service.get_dashboard_data(business_id)
        if cached_data:
            return DashboardResponse(**cached_data)
        
        # Get all accessible projects for this business
        projects = await self.get_projects_for_business(business_id)
        
        # Calculate KPIs
        kpis = await self.calculate_dashboard_kpis(business_id)
        
        # Get recent comments across all projects
        recent_comments = await self.get_recent_comments_across_projects(business_id)
        
        # Get timeline events
        timeline = await self.get_dashboard_timeline(business_id)
        
        # Convert projects to summary format
        project_summaries = [self._project_to_summary(project) for project in projects]
        
        dashboard_response = DashboardResponse(
            kpis=kpis,
            recent_comments=recent_comments,
            timeline=timeline,
            projects=project_summaries
        )
        
        # Cache the response for 5 minutes
        cache_service.set_dashboard_data(
            business_id, 
            dashboard_response.dict(), 
            ttl_seconds=300
        )
        
        return dashboard_response

    async def get_project_dashboard_data(self, project_id: UUID, business_id: int) -> ProjectDashboardResponse:
        """Get project-specific dashboard data."""
        
        # Try to get from cache first
        cached_data = cache_service.get_project_dashboard_data(business_id, str(project_id))
        if cached_data:
            return ProjectDashboardResponse(**cached_data)
        
        # Get project details
        project = await self.get_project_by_id(project_id, business_id)
        if not project:
            raise ValueError(f"Project {project_id} not found or not accessible")
        
        # Calculate project-specific KPIs
        kpis = await self.calculate_project_kpis(project_id)
        
        # Get recent comments for this project
        recent_comments = await self.get_recent_comments_for_project(project_id)
        
        # Get timeline for this project
        timeline = await self.get_project_timeline(project_id)
        
        project_dashboard = ProjectDashboardResponse(
            project=self._project_to_summary(project),
            kpis=kpis,
            recent_comments=recent_comments,
            timeline=timeline
        )
        
        # Cache the response for 5 minutes
        cache_service.set_project_dashboard_data(
            business_id,
            str(project_id),
            project_dashboard.dict(),
            ttl_seconds=300
        )
        
        return project_dashboard

    async def get_recent_comments_across_projects(self, business_id: int, limit: int = 10) -> List[RecentCommentItem]:
        """Get recent comments across all projects with navigation links."""
        
        # Try to get from cache first
        cached_comments = cache_service.get_recent_comments(business_id, limit)
        if cached_comments:
            return [RecentCommentItem(**comment) for comment in cached_comments]
        
        query = (
            select(ClientFeedback, ReviewItem, Deliverable, Project)
            .join(ReviewItem, ClientFeedback.review_item_id == ReviewItem.id)
            .join(Deliverable, ReviewItem.deliverable_id == Deliverable.id)
            .join(Project, Deliverable.project_id == Project.id)
            .where(Project.business_id == business_id)
            .order_by(desc(ClientFeedback.created_at))
            .limit(limit)
        )
        
        result = await self.db_session.execute(query)
        rows = result.fetchall()
        
        recent_comments = []
        for feedback, review_item, deliverable, project in rows:
            recent_comments.append(RecentCommentItem(
                id=str(feedback.id),
                project_id=str(project.id),
                project_name=project.name,
                deliverable_id=str(deliverable.id),
                deliverable_name=f"{deliverable.deliverable_type} - {deliverable.deliverable_sub_type}",
                comment_text=feedback.comment_text or "",
                created_at=feedback.created_at,
                context_coordinates=feedback.context_coordinates,
                timestamp_seconds=feedback.timestamp_seconds,
                review_item_id=str(review_item.id)
            ))
        
        # Cache the comments for 3 minutes (shorter TTL for recent data)
        cache_service.set_recent_comments(
            business_id,
            [comment.dict() for comment in recent_comments],
            limit,
            ttl_seconds=180
        )
        
        return recent_comments

    async def calculate_dashboard_kpis(self, business_id: int) -> List[KPIItem]:
        """Calculate main dashboard KPIs."""
        
        # Active projects count
        active_projects_query = select(func.count(Project.id)).where(
            and_(
                Project.business_id == business_id,
                Project.status == ProjectStatus.IN_PROGRESS
            )
        )
        active_projects_result = await self.db_session.execute(active_projects_query)
        active_projects = active_projects_result.scalar() or 0

        # Pending reviews count
        pending_reviews_query = (
            select(func.count(ReviewItem.id))
            .join(Deliverable, ReviewItem.deliverable_id == Deliverable.id)
            .join(Project, Deliverable.project_id == Project.id)
            .where(
                and_(
                    Project.business_id == business_id,
                    ReviewItem.status == "pending"
                )
            )
        )
        pending_reviews_result = await self.db_session.execute(pending_reviews_query)
        pending_reviews = pending_reviews_result.scalar() or 0

        # Completed tasks count
        completed_tasks_query = (
            select(func.count(InternalTask.id))
            .join(Project, InternalTask.project_id == Project.id)
            .where(
                and_(
                    Project.business_id == business_id,
                    InternalTask.status == "completed"
                )
            )
        )
        completed_tasks_result = await self.db_session.execute(completed_tasks_query)
        completed_tasks = completed_tasks_result.scalar() or 0

        # Total deliverables count
        total_deliverables_query = (
            select(func.count(Deliverable.id))
            .join(Project, Deliverable.project_id == Project.id)
            .where(Project.business_id == business_id)
        )
        total_deliverables_result = await self.db_session.execute(total_deliverables_query)
        total_deliverables = total_deliverables_result.scalar() or 0

        return [
            KPIItem(
                title="Active Projects",
                value=active_projects,
                icon="📊"
            ),
            KPIItem(
                title="Pending Reviews",
                value=pending_reviews,
                icon="📝"
            ),
            KPIItem(
                title="Completed Tasks",
                value=completed_tasks,
                icon="✅"
            ),
            KPIItem(
                title="Total Deliverables",
                value=total_deliverables,
                icon="📦"
            )
        ]

    async def calculate_project_kpis(self, project_id: UUID) -> List[KPIItem]:
        """Calculate project-specific KPIs."""
        
        # Total deliverables for project
        total_deliverables_query = select(func.count(Deliverable.id)).where(
            Deliverable.project_id == project_id
        )
        total_deliverables_result = await self.db_session.execute(total_deliverables_query)
        total_deliverables = total_deliverables_result.scalar() or 0

        # Completed deliverables
        completed_deliverables_query = select(func.count(Deliverable.id)).where(
            and_(
                Deliverable.project_id == project_id,
                Deliverable.current_status == "completed"
            )
        )
        completed_deliverables_result = await self.db_session.execute(completed_deliverables_query)
        completed_deliverables = completed_deliverables_result.scalar() or 0

        # Pending deliverables
        pending_deliverables_query = select(func.count(Deliverable.id)).where(
            and_(
                Deliverable.project_id == project_id,
                Deliverable.current_status == "pending"
            )
        )
        pending_deliverables_result = await self.db_session.execute(pending_deliverables_query)
        pending_deliverables = pending_deliverables_result.scalar() or 0

        # Project tasks
        project_tasks_query = select(func.count(InternalTask.id)).where(
            InternalTask.project_id == project_id
        )
        project_tasks_result = await self.db_session.execute(project_tasks_query)
        project_tasks = project_tasks_result.scalar() or 0

        return [
            KPIItem(
                title="Total Deliverables",
                value=total_deliverables,
                icon="📦"
            ),
            KPIItem(
                title="Completed Deliverables",
                value=completed_deliverables,
                icon="✅"
            ),
            KPIItem(
                title="Pending Deliverables",
                value=pending_deliverables,
                icon="⏳"
            ),
            KPIItem(
                title="Project Tasks",
                value=project_tasks,
                icon="📋"
            )
        ]

    async def get_dashboard_timeline(self, business_id: int, limit: int = 10) -> List[TimelineItem]:
        """Get timeline events for dashboard overview with granular activity tracking."""
        
        timeline_events = []
        
        try:
            # Get recent task completions (last 30 days)
            since_date = datetime.now() - timedelta(days=30)
            
            completed_tasks_query = (
                select(InternalTask)
                .join(Project)
                .where(
                    and_(
                        Project.business_id == business_id,
                        InternalTask.status == "DONE",
                        InternalTask.actual_end_date >= since_date
                    )
                )
                .order_by(InternalTask.actual_end_date.desc())
                .limit(limit)
            )
            
            # Execute query without causing rollbacks
            result = await self.db_session.execute(completed_tasks_query)
            completed_tasks = result.scalars().all()
            
            for task in completed_tasks:
                timeline_events.append(TimelineItem(
                    id=f"task-completed-{task.id}",
                    project_id=str(task.project_id),
                    project_name=f"Project Task",  # We'd need to join to get project name
                    deliverable_id=str(task.deliverable_id) if task.deliverable_id else None,
                    deliverable_name=None,
                    event_type="task_completed",
                    event_date=task.actual_end_date or task.updated_at,
                    status="completed",
                    description=f"{task.task_type} task completed: {task.task_name}"
                ))
            
            # Get recent review submissions (last 30 days)
            review_submissions_query = (
                select(ReviewItem)
                .join(Project)
                .where(
                    and_(
                        Project.business_id == business_id,
                        ReviewItem.presented_at >= since_date
                    )
                )
                .order_by(ReviewItem.presented_at.desc())
                .limit(limit)
            )
            
            result = await self.db_session.execute(review_submissions_query)
            review_items = result.scalars().all()
            
            for review in review_items:
                timeline_events.append(TimelineItem(
                    id=f"review-submitted-{review.id}",
                    project_id=str(review.project_id),
                    project_name=f"Review Item",
                    deliverable_id=str(review.deliverable_id) if review.deliverable_id else None,
                    deliverable_name=None,
                    event_type="review_submitted",
                    event_date=review.presented_at,
                    status=review.review_status.value,
                    description=f"Review item submitted: {review.description or review.item_type.value}"
                ))
            
            # Get recent project starts (last 30 days)
            project_starts_query = (
                select(Project)
                .where(
                    and_(
                        Project.business_id == business_id,
                        Project.start_date >= since_date
                    )
                )
                .order_by(Project.start_date.desc())
                .limit(limit)
            )
            
            result = await self.db_session.execute(project_starts_query)
            projects = result.scalars().all()
        
            for project in projects:
                timeline_events.append(TimelineItem(
                    id=f"project-started-{project.id}",
                    project_id=str(project.id),
                    project_name=project.name,
                    deliverable_id=None,
                    deliverable_name=None,
                    event_type="project_started",
                    event_date=project.start_date,
                    status="active",
                    description=f"Project '{project.name}' started"
                ))
        
            # Sort all events by date (most recent first)
            timeline_events.sort(key=lambda x: x.event_date, reverse=True)
            
            # Return only the most recent events up to the limit
            return timeline_events[:limit]
            
        except Exception as e:
            logger.error(f"Error fetching timeline events: {e}", exc_info=True)
            # Return empty list on error instead of raising
            return []

    async def get_project_timeline(self, project_id: UUID, limit: int = 10) -> List[TimelineItem]:
        """Get timeline events for a specific project."""
        
        timeline_events = []
        
        # Get project details
        project_query = select(Project).where(Project.id == project_id)
        project_result = await self.db_session.execute(project_query)
        project = project_result.scalar_one_or_none()
        
        if not project:
            return []
        
        # Add project start/end events
        if project.start_date:
            timeline_events.append(TimelineItem(
                id=f"project_start_{project.id}",
                project_id=str(project.id),
                project_name=project.name,
                event_type="project_start",
                event_date=project.start_date,
                status=project.status.value,
                description=f"Project started"
            ))
        
        if project.end_date:
            timeline_events.append(TimelineItem(
                id=f"project_end_{project.id}",
                project_id=str(project.id),
                project_name=project.name,
                event_type="project_end",
                event_date=project.end_date,
                status=project.status.value,
                description=f"Project deadline"
            ))
        
        # Get deliverable milestones
        deliverables_query = (
            select(Deliverable)
            .where(Deliverable.project_id == project_id)
            .order_by(Deliverable.created_at)
        )
        deliverables_result = await self.db_session.execute(deliverables_query)
        deliverables = deliverables_result.scalars().all()
        
        for deliverable in deliverables:
            # Calculate estimated due date based on tentative timeline
            if deliverable.tentative_timeline_days and project.start_date:
                estimated_due = project.start_date + timedelta(days=deliverable.tentative_timeline_days)
                timeline_events.append(TimelineItem(
                    id=f"deliverable_due_{deliverable.id}",
                    project_id=str(project.id),
                    project_name=project.name,
                    deliverable_id=str(deliverable.id),
                    deliverable_name=f"{deliverable.deliverable_type} - {deliverable.deliverable_sub_type}",
                    event_type="deliverable_due",
                    event_date=estimated_due,
                    status=deliverable.current_status,
                    description=f"Deliverable due: {deliverable.deliverable_sub_type}"
                ))
        
        # Sort by date and limit
        timeline_events.sort(key=lambda x: x.event_date)
        return timeline_events[:limit]

    async def get_recent_comments_for_project(self, project_id: UUID, limit: int = 10) -> List[RecentCommentItem]:
        """Get recent comments for a specific project."""
        
        query = (
            select(ClientFeedback, ReviewItem, Deliverable, Project)
            .join(ReviewItem, ClientFeedback.review_item_id == ReviewItem.id)
            .join(Deliverable, ReviewItem.deliverable_id == Deliverable.id)
            .join(Project, Deliverable.project_id == Project.id)
            .where(Project.id == project_id)
            .order_by(desc(ClientFeedback.created_at))
            .limit(limit)
        )
        
        result = await self.db_session.execute(query)
        rows = result.fetchall()
        
        recent_comments = []
        for feedback, review_item, deliverable, project in rows:
            recent_comments.append(RecentCommentItem(
                id=str(feedback.id),
                project_id=str(project.id),
                project_name=project.name,
                deliverable_id=str(deliverable.id),
                deliverable_name=f"{deliverable.deliverable_type} - {deliverable.deliverable_sub_type}",
                comment_text=feedback.comment_text or "",
                created_at=feedback.created_at,
                context_coordinates=feedback.context_coordinates,
                timestamp_seconds=feedback.timestamp_seconds,
                review_item_id=str(review_item.id)
            ))
        
        return recent_comments

    async def get_projects_for_business(self, business_id: int) -> List[Project]:
        """Get all projects for a specific business."""
        
        query = (
            select(Project)
            .where(Project.business_id == business_id)
            .order_by(desc(Project.created_at))
        )
        
        result = await self.db_session.execute(query)
        return result.scalars().all()

    async def get_project_by_id(self, project_id: UUID, business_id: int) -> Optional[Project]:
        """Get a specific project by ID with business access check."""
        
        query = select(Project).where(
            and_(
                Project.id == project_id,
                Project.business_id == business_id
            )
        )
        
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    def _project_to_summary(self, project: Project) -> ProjectSummary:
        """Convert a Project ORM object to ProjectSummary Pydantic model."""
        
        return ProjectSummary(
            id=str(project.id),
            name=project.name,
            status=project.status.value,
            budget=float(project.budget) if project.budget else None,
            start_date=project.start_date,
            end_date=project.end_date,
            created_at=project.created_at
        ) 