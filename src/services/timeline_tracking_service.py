# src/services/timeline_tracking_service.py

import logging
from typing import List, Optional, Dict, Any
from uuid import UUID
from decimal import Decimal
from datetime import datetime, date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, update, or_
from sqlalchemy.orm import selectinload

from src.models.internal_task import InternalTask, TaskStatus
from src.models.project import Project
from src.models.task_progress import TaskProgress
from src.models.project_timeline import ProjectTimeline

logger = logging.getLogger(__name__)


class TimelineTrackingService:
    """
    Service layer for timeline tracking, progress management, and milestone monitoring.
    Handles daily progress logging, timeline analytics, and project completion calculations.
    """

    def __init__(self, db_session: AsyncSession):
        """
        Initialize the TimelineTrackingService.
        
        Args:
            db_session: An asynchronous SQLAlchemy database session.
        """
        self.db_session = db_session
        logger.info("TimelineTrackingService initialized")

    async def log_daily_progress(
        self,
        task_id: UUID,
        progress_date: date,
        percentage_complete: Decimal,
        hours_spent: Decimal,
        notes: Optional[str] = None,
        created_by: Optional[UUID] = None,
    ) -> TaskProgress:
        """
        Log daily progress for a task.
        
        Args:
            task_id: ID of the task
            progress_date: Date of the progress entry
            percentage_complete: Percentage completion (0-100)
            hours_spent: Hours spent on this date
            notes: Optional progress notes
            created_by: User who logged the progress
            
        Returns:
            TaskProgress: The created or updated progress entry
        """
        logger.info(f"Logging progress for task {task_id} on {progress_date}")

        # Validate task exists
        task = await self._get_task_by_id(task_id)
        if not task:
            raise ValueError(f"Task with ID {task_id} not found")

        # Validate percentage range
        if percentage_complete < 0 or percentage_complete > 100:
            raise ValueError("Percentage complete must be between 0 and 100")

        # Check if progress entry already exists for this date
        existing_progress = await self._get_task_progress_by_date(task_id, progress_date)
        
        if existing_progress:
            # Update existing entry
            existing_progress.percentage_complete = percentage_complete
            existing_progress.hours_spent = hours_spent
            existing_progress.notes = notes
            existing_progress.updated_at = datetime.utcnow()
            
            await self.db_session.commit()
            await self.db_session.refresh(existing_progress)
            
            logger.info(f"Updated existing progress entry: {percentage_complete}% complete")
            progress_entry = existing_progress
        else:
            # Create new progress entry
            progress_entry = TaskProgress(
                task_id=task_id,
                progress_date=progress_date,
                percentage_complete=percentage_complete,
                hours_spent=hours_spent,
                notes=notes,
                created_by=created_by,
            )
            
            self.db_session.add(progress_entry)
            await self.db_session.commit()
            await self.db_session.refresh(progress_entry)
            
            logger.info(f"Created new progress entry: {percentage_complete}% complete")

        # Update task's actual hours
        await self._update_task_actual_hours(task_id)
        
        # Update task status based on completion
        await self._update_task_status_by_progress(task_id, percentage_complete)

        return progress_entry

    async def get_task_progress_history(self, task_id: UUID) -> List[TaskProgress]:
        """
        Get complete progress history for a task.
        
        Args:
            task_id: ID of the task
            
        Returns:
            List[TaskProgress]: List of progress entries ordered by date
        """
        logger.info(f"Getting progress history for task {task_id}")

        result = await self.db_session.execute(
            select(TaskProgress)
            .filter(TaskProgress.task_id == task_id)
            .order_by(TaskProgress.progress_date.desc())
        )
        
        progress_entries = result.scalars().all()
        logger.info(f"Found {len(progress_entries)} progress entries for task {task_id}")
        return progress_entries

    async def calculate_task_completion(self, task_id: UUID) -> Dict[str, Any]:
        """
        Calculate overall task completion based on progress entries.
        
        Args:
            task_id: ID of the task
            
        Returns:
            Dict containing completion statistics
        """
        logger.info(f"Calculating completion for task {task_id}")

        # Get task and its progress
        task = await self._get_task_by_id(task_id)
        if not task:
            raise ValueError(f"Task with ID {task_id} not found")

        progress_entries = await self.get_task_progress_history(task_id)
        
        if not progress_entries:
            return {
                "task_id": str(task_id),
                "current_completion": 0.0,
                "total_hours_spent": 0.0,
                "estimated_hours": float(task.estimated_hours or 0),
                "hours_variance": float(task.estimated_hours or 0),
                "start_date": None,
                "last_updated": None,
                "average_daily_progress": 0.0,
                "projected_completion_date": None,
            }

        # Calculate statistics
        latest_progress = progress_entries[0]  # Most recent (ordered by date desc)
        total_hours = sum(p.hours_spent for p in progress_entries)
        start_date = progress_entries[-1].progress_date  # Earliest entry
        
        # Calculate average daily progress
        working_days = len(set(p.progress_date for p in progress_entries))
        avg_daily_progress = float(latest_progress.percentage_complete) / working_days if working_days > 0 else 0

        # Project completion date
        projected_completion_date = None
        if avg_daily_progress > 0 and latest_progress.percentage_complete < 100:
            remaining_percentage = 100 - float(latest_progress.percentage_complete)
            days_to_complete = remaining_percentage / avg_daily_progress
            projected_completion_date = latest_progress.progress_date + timedelta(days=int(days_to_complete))

        completion_stats = {
            "task_id": str(task_id),
            "current_completion": float(latest_progress.percentage_complete),
            "total_hours_spent": float(total_hours),
            "estimated_hours": float(task.estimated_hours or 0),
            "hours_variance": float(total_hours - (task.estimated_hours or 0)),
            "start_date": start_date.isoformat() if start_date else None,
            "last_updated": latest_progress.progress_date.isoformat(),
            "average_daily_progress": avg_daily_progress,
            "projected_completion_date": projected_completion_date.isoformat() if projected_completion_date else None,
            "working_days": working_days,
        }

        logger.info(f"Task {task_id} completion: {latest_progress.percentage_complete}%")
        return completion_stats

    async def calculate_project_completion(self, project_id: UUID) -> Dict[str, Any]:
        """
        Calculate overall project completion based on all task progress.
        
        Args:
            project_id: ID of the project
            
        Returns:
            Dict containing project completion statistics
        """
        logger.info(f"Calculating project completion for {project_id}")

        # Get all tasks for the project
        result = await self.db_session.execute(
            select(InternalTask)
            .filter(InternalTask.project_id == project_id)
        )
        
        tasks = result.scalars().all()
        
        if not tasks:
            return {
                "project_id": str(project_id),
                "overall_completion": 0.0,
                "total_tasks": 0,
                "completed_tasks": 0,
                "in_progress_tasks": 0,
                "not_started_tasks": 0,
                "total_estimated_hours": 0.0,
                "total_actual_hours": 0.0,
                "hours_variance": 0.0,
            }

        # Calculate task statistics
        total_tasks = len(tasks)
        completed_tasks = len([t for t in tasks if t.status == TaskStatus.COMPLETED])
        in_progress_tasks = len([t for t in tasks if t.status == TaskStatus.IN_PROGRESS])
        not_started_tasks = len([t for t in tasks if t.status == TaskStatus.NOT_STARTED])
        
        total_estimated_hours = sum(float(t.estimated_hours or 0) for t in tasks)
        total_actual_hours = sum(float(t.actual_hours or 0) for t in tasks)

        # Calculate weighted completion based on estimated hours
        if total_estimated_hours > 0:
            weighted_completion = 0.0
            for task in tasks:
                task_weight = float(task.estimated_hours or 0) / total_estimated_hours
                task_completion = await self._get_latest_task_completion(task.id)
                weighted_completion += task_completion * task_weight
        else:
            # Simple percentage if no estimated hours
            weighted_completion = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

        project_stats = {
            "project_id": str(project_id),
            "overall_completion": weighted_completion,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "in_progress_tasks": in_progress_tasks,
            "not_started_tasks": not_started_tasks,
            "total_estimated_hours": total_estimated_hours,
            "total_actual_hours": total_actual_hours,
            "hours_variance": total_actual_hours - total_estimated_hours,
            "completion_percentage_by_count": (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
        }

        logger.info(f"Project {project_id} overall completion: {weighted_completion:.1f}%")
        return project_stats

    async def create_project_milestones(
        self,
        project_id: UUID,
        milestone_config: Optional[Dict[str, Any]] = None,
    ) -> List[ProjectTimeline]:
        """
        Create standard project milestones.
        
        Args:
            project_id: ID of the project
            milestone_config: Optional custom milestone configuration
            
        Returns:
            List[ProjectTimeline]: Created milestone entries
        """
        logger.info(f"Creating milestones for project {project_id}")

        # Get project to determine dates
        project = await self._get_project_by_id(project_id)
        if not project:
            raise ValueError(f"Project with ID {project_id} not found")

        # Default milestone configuration
        default_milestones = [
            {"phase_name": "Project Initiation", "is_milestone": True, "phase_order": 1, "duration_percentage": 10},
            {"phase_name": "Requirements Gathering", "is_milestone": False, "phase_order": 2, "duration_percentage": 15},
            {"phase_name": "Design Phase", "is_milestone": False, "phase_order": 3, "duration_percentage": 25},
            {"phase_name": "Development Phase", "is_milestone": False, "phase_order": 4, "duration_percentage": 40},
            {"phase_name": "Testing & QA", "is_milestone": False, "phase_order": 5, "duration_percentage": 15},
            {"phase_name": "Project Delivery", "is_milestone": True, "phase_order": 6, "duration_percentage": 5},
        ]

        milestones = milestone_config.get("milestones", default_milestones) if milestone_config else default_milestones

        # Calculate phase dates based on project timeline
        start_date = project.start_date or datetime.now().date()
        end_date = project.end_date or (start_date + timedelta(days=90))  # Default 90 days
        total_days = (end_date - start_date).days

        created_milestones = []
        current_start = start_date

        for milestone in milestones:
            phase_days = int(total_days * milestone["duration_percentage"] / 100)
            phase_end = current_start + timedelta(days=phase_days)

            timeline_entry = ProjectTimeline(
                project_id=project_id,
                phase_name=milestone["phase_name"],
                planned_start_date=current_start,
                planned_end_date=phase_end,
                is_milestone=milestone["is_milestone"],
                phase_order=milestone["phase_order"],
                percentage_complete=Decimal('0.00'),
            )

            self.db_session.add(timeline_entry)
            created_milestones.append(timeline_entry)
            current_start = phase_end + timedelta(days=1)

        await self.db_session.commit()
        for milestone in created_milestones:
            await self.db_session.refresh(milestone)

        logger.info(f"Created {len(created_milestones)} milestones for project {project_id}")
        return created_milestones

    async def update_milestone_status(
        self,
        milestone_id: UUID,
        percentage_complete: Decimal,
        actual_start_date: Optional[date] = None,
        actual_end_date: Optional[date] = None,
        notes: Optional[str] = None,
    ) -> ProjectTimeline:
        """
        Update milestone completion status.
        
        Args:
            milestone_id: ID of the milestone
            percentage_complete: Completion percentage (0-100)
            actual_start_date: Actual start date
            actual_end_date: Actual end date
            notes: Update notes
            
        Returns:
            ProjectTimeline: Updated milestone
        """
        logger.info(f"Updating milestone {milestone_id} to {percentage_complete}% complete")

        milestone = await self._get_milestone_by_id(milestone_id)
        if not milestone:
            raise ValueError(f"Milestone with ID {milestone_id} not found")

        milestone.percentage_complete = percentage_complete
        if actual_start_date:
            milestone.actual_start_date = actual_start_date
        if actual_end_date:
            milestone.actual_end_date = actual_end_date
        
        milestone.updated_at = datetime.utcnow()

        await self.db_session.commit()
        await self.db_session.refresh(milestone)

        logger.info(f"Updated milestone: {percentage_complete}% complete")
        return milestone

    async def get_upcoming_milestones(
        self,
        project_id: UUID,
        days_ahead: int = 30,
    ) -> List[ProjectTimeline]:
        """
        Get milestones due within specified days.
        
        Args:
            project_id: ID of the project
            days_ahead: Number of days to look ahead
            
        Returns:
            List[ProjectTimeline]: Upcoming milestones
        """
        logger.info(f"Getting milestones due within {days_ahead} days for project {project_id}")

        cutoff_date = datetime.now().date() + timedelta(days=days_ahead)

        result = await self.db_session.execute(
            select(ProjectTimeline)
            .filter(
                and_(
                    ProjectTimeline.project_id == project_id,
                    ProjectTimeline.is_milestone == True,
                    ProjectTimeline.planned_end_date <= cutoff_date,
                    ProjectTimeline.percentage_complete < 100,
                )
            )
            .order_by(ProjectTimeline.planned_end_date)
        )
        
        milestones = result.scalars().all()
        logger.info(f"Found {len(milestones)} upcoming milestones")
        return milestones

    async def get_timeline_variance(self, project_id: UUID) -> Dict[str, Any]:
        """
        Compare actual vs planned timeline for a project.
        
        Args:
            project_id: ID of the project
            
        Returns:
            Dict containing timeline variance analysis
        """
        logger.info(f"Calculating timeline variance for project {project_id}")

        # Get all timeline entries
        result = await self.db_session.execute(
            select(ProjectTimeline)
            .filter(ProjectTimeline.project_id == project_id)
            .order_by(ProjectTimeline.phase_order)
        )
        
        timeline_entries = result.scalars().all()
        
        if not timeline_entries:
            return {"project_id": str(project_id), "phases": [], "overall_variance": 0}

        phase_analysis = []
        total_planned_days = 0
        total_actual_days = 0

        for entry in timeline_entries:
            planned_duration = (entry.planned_end_date - entry.planned_start_date).days
            total_planned_days += planned_duration

            actual_duration = None
            variance_days = None
            status = "not_started"

            if entry.actual_start_date and entry.actual_end_date:
                actual_duration = (entry.actual_end_date - entry.actual_start_date).days
                total_actual_days += actual_duration
                variance_days = actual_duration - planned_duration
                status = "completed"
            elif entry.actual_start_date:
                status = "in_progress"
                # Calculate current duration if in progress
                current_duration = (datetime.now().date() - entry.actual_start_date).days
                if current_duration > planned_duration:
                    variance_days = current_duration - planned_duration

            phase_info = {
                "phase_name": entry.phase_name,
                "is_milestone": entry.is_milestone,
                "planned_start": entry.planned_start_date.isoformat(),
                "planned_end": entry.planned_end_date.isoformat(),
                "planned_duration_days": planned_duration,
                "actual_start": entry.actual_start_date.isoformat() if entry.actual_start_date else None,
                "actual_end": entry.actual_end_date.isoformat() if entry.actual_end_date else None,
                "actual_duration_days": actual_duration,
                "variance_days": variance_days,
                "percentage_complete": float(entry.percentage_complete),
                "status": status,
                "is_delayed": variance_days > 0 if variance_days is not None else False,
            }
            phase_analysis.append(phase_info)

        overall_variance = total_actual_days - total_planned_days if total_actual_days > 0 else 0

        variance_analysis = {
            "project_id": str(project_id),
            "phases": phase_analysis,
            "overall_variance_days": overall_variance,
            "total_planned_days": total_planned_days,
            "total_actual_days": total_actual_days,
            "is_behind_schedule": overall_variance > 0,
            "completed_phases": len([p for p in phase_analysis if p["status"] == "completed"]),
            "delayed_phases": len([p for p in phase_analysis if p.get("is_delayed", False)]),
        }

        logger.info(f"Timeline variance: {overall_variance} days")
        return variance_analysis

    # Helper methods

    async def _get_task_by_id(self, task_id: UUID) -> Optional[InternalTask]:
        """Get task by ID."""
        result = await self.db_session.execute(
            select(InternalTask).filter(InternalTask.id == task_id)
        )
        return result.scalar_one_or_none()

    async def _get_project_by_id(self, project_id: UUID) -> Optional[Project]:
        """Get project by ID."""
        result = await self.db_session.execute(
            select(Project).filter(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def _get_milestone_by_id(self, milestone_id: UUID) -> Optional[ProjectTimeline]:
        """Get milestone by ID."""
        result = await self.db_session.execute(
            select(ProjectTimeline).filter(ProjectTimeline.id == milestone_id)
        )
        return result.scalar_one_or_none()

    async def _get_task_progress_by_date(
        self, task_id: UUID, progress_date: date
    ) -> Optional[TaskProgress]:
        """Get existing progress entry for specific date."""
        result = await self.db_session.execute(
            select(TaskProgress).filter(
                and_(
                    TaskProgress.task_id == task_id,
                    TaskProgress.progress_date == progress_date,
                )
            )
        )
        return result.scalar_one_or_none()

    async def _update_task_actual_hours(self, task_id: UUID) -> None:
        """Update task's actual hours from progress entries."""
        result = await self.db_session.execute(
            select(func.sum(TaskProgress.hours_spent))
            .filter(TaskProgress.task_id == task_id)
        )
        
        total_hours = result.scalar() or Decimal('0.00')
        
        await self.db_session.execute(
            update(InternalTask)
            .where(InternalTask.id == task_id)
            .values(actual_hours=total_hours)
        )
        
        await self.db_session.commit()

    async def _update_task_status_by_progress(
        self, task_id: UUID, percentage_complete: Decimal
    ) -> None:
        """Update task status based on completion percentage."""
        new_status = None
        
        if percentage_complete >= 100:
            new_status = TaskStatus.COMPLETED
        elif percentage_complete > 0:
            new_status = TaskStatus.IN_PROGRESS
        
        if new_status:
            await self.db_session.execute(
                update(InternalTask)
                .where(InternalTask.id == task_id)
                .values(status=new_status)
            )
            await self.db_session.commit()

    async def _get_latest_task_completion(self, task_id: UUID) -> float:
        """Get latest completion percentage for a task."""
        result = await self.db_session.execute(
            select(TaskProgress.percentage_complete)
            .filter(TaskProgress.task_id == task_id)
            .order_by(TaskProgress.progress_date.desc())
            .limit(1)
        )
        
        latest_completion = result.scalar()
        return float(latest_completion) if latest_completion is not None else 0.0 