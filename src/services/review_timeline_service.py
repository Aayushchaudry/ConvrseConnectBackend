# src/services/review_timeline_service.py

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from uuid import UUID

from sqlalchemy import select, and_, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.review_item import ReviewItem, ReviewStatus
from src.models.project_timeline import ProjectTimeline
from src.models.deliverable import Deliverable
from src.models.project import Project
from src.models.internal_task import InternalTask, TaskStatus
from src.services.notification_service import NotificationService, NotificationType

logger = logging.getLogger(__name__)


class ReviewTimelineService:
    """
    Service for managing review deadlines and timeline integration with review processes.
    Handles automatic deadline setting, overdue detection, and timeline adjustments.
    """

    def __init__(self, db_session: AsyncSession, notification_service: NotificationService = None):
        """
        Initialize the ReviewTimelineService.
        
        Args:
            db_session: An asynchronous SQLAlchemy database session
            notification_service: Service for sending notifications
        """
        self.db_session = db_session
        self.notification_service = notification_service or NotificationService()
        logger.info("ReviewTimelineService initialized")

    async def set_review_deadline(
        self,
        review_item_id: UUID,
        project_timeline_phase: Optional[str] = None,
        custom_deadline: Optional[datetime] = None,
        buffer_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Set review deadline based on project timeline or custom deadline.
        
        Args:
            review_item_id: ID of the review item
            project_timeline_phase: Phase name to base deadline on
            custom_deadline: Custom deadline to set
            buffer_hours: Buffer hours before phase deadline
            
        Returns:
            Dict containing deadline information
        """
        logger.info(f"Setting review deadline for review item {review_item_id}")
        
        try:
            # Get the review item
            review_item_result = await self.db_session.execute(
                select(ReviewItem).filter(ReviewItem.id == review_item_id)
            )
            review_item = review_item_result.scalar_one_or_none()
            
            if not review_item:
                raise ValueError(f"Review item {review_item_id} not found")
            
            deadline = None
            deadline_source = "custom"
            
            if custom_deadline:
                deadline = custom_deadline
                deadline_source = "custom"
            elif project_timeline_phase:
                # Find the timeline phase
                timeline_result = await self.db_session.execute(
                    select(ProjectTimeline).filter(
                        and_(
                            ProjectTimeline.project_id == review_item.project_id,
                            ProjectTimeline.phase_name == project_timeline_phase
                        )
                    )
                )
                timeline_phase = timeline_result.scalar_one_or_none()
                
                if timeline_phase and timeline_phase.planned_end_date:
                    # Set deadline with buffer before phase end
                    phase_end = datetime.combine(timeline_phase.planned_end_date, datetime.min.time())
                    deadline = phase_end - timedelta(hours=buffer_hours)
                    deadline_source = f"timeline_phase:{project_timeline_phase}"
                else:
                    logger.warning(f"Timeline phase {project_timeline_phase} not found or has no end date")
            
            if not deadline:
                # Default to 48 hours from now if no other deadline can be determined
                deadline = datetime.utcnow() + timedelta(hours=48)
                deadline_source = "default"
            
            # Store deadline information in review item (assuming we add a deadline field)
            # For now, we'll track this in a separate way or extend the model
            
            deadline_info = {
                "review_item_id": str(review_item_id),
                "deadline": deadline.isoformat(),
                "deadline_source": deadline_source,
                "buffer_hours": buffer_hours,
                "project_id": str(review_item.project_id),
                "deliverable_id": str(review_item.deliverable_id)
            }
            
            logger.info(f"Set review deadline for {review_item_id}: {deadline} (source: {deadline_source})")
            return deadline_info
            
        except Exception as e:
            logger.error(f"Error setting review deadline: {e}", exc_info=True)
            raise

    async def detect_overdue_reviews(
        self,
        project_id: Optional[UUID] = None,
        hours_overdue_threshold: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Detect overdue review items based on deadlines.
        
        Args:
            project_id: Optional project ID to filter by
            hours_overdue_threshold: Minimum hours overdue to include
            
        Returns:
            List of overdue review items with deadline information
        """
        logger.info(f"Detecting overdue reviews for project {project_id}")
        
        try:
            # Build query for pending reviews
            query = select(ReviewItem).filter(
                ReviewItem.review_status == ReviewStatus.PENDING_REVIEW.value
            )
            
            if project_id:
                query = query.filter(ReviewItem.project_id == project_id)
            
            result = await self.db_session.execute(query)
            pending_reviews = result.scalars().all()
            
            overdue_reviews = []
            current_time = datetime.utcnow()
            
            for review_item in pending_reviews:
                # Calculate expected deadline based on presentation time
                # Default to 48 hours from presentation if no specific deadline
                expected_deadline = review_item.presented_at + timedelta(hours=48)
                
                # Check if overdue
                hours_overdue = (current_time - expected_deadline).total_seconds() / 3600
                
                if hours_overdue >= hours_overdue_threshold:
                    overdue_info = {
                        "review_item_id": str(review_item.id),
                        "project_id": str(review_item.project_id),
                        "deliverable_id": str(review_item.deliverable_id),
                        "item_type": review_item.item_type.value,
                        "presented_at": review_item.presented_at.isoformat(),
                        "expected_deadline": expected_deadline.isoformat(),
                        "hours_overdue": round(hours_overdue, 2),
                        "description": review_item.description,
                        "sequence_number": review_item.sequence_number,
                        "review_round": review_item.review_round
                    }
                    overdue_reviews.append(overdue_info)
            
            logger.info(f"Found {len(overdue_reviews)} overdue reviews")
            return overdue_reviews
            
        except Exception as e:
            logger.error(f"Error detecting overdue reviews: {e}", exc_info=True)
            raise

    async def send_overdue_reminders(
        self,
        project_id: Optional[UUID] = None,
        reminder_threshold_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Send reminder notifications for overdue reviews.
        
        Args:
            project_id: Optional project ID to filter by
            reminder_threshold_hours: Hours overdue before sending reminder
            
        Returns:
            Dict containing reminder statistics
        """
        logger.info(f"Sending overdue reminders for project {project_id}")
        
        try:
            overdue_reviews = await self.detect_overdue_reviews(
                project_id=project_id,
                hours_overdue_threshold=reminder_threshold_hours
            )
            
            reminders_sent = 0
            
            for overdue_review in overdue_reviews:
                try:
                    # Send notification for overdue review
                    await self.notification_service.send_notification(
                        project_id=overdue_review["project_id"],
                        notification_type=NotificationType.WARNING,
                        title="Review Overdue",
                        message=f"Review item '{overdue_review['description']}' is {overdue_review['hours_overdue']:.1f} hours overdue",
                        data={
                            "review_item_id": overdue_review["review_item_id"],
                            "deliverable_id": overdue_review["deliverable_id"],
                            "hours_overdue": overdue_review["hours_overdue"],
                            "item_type": overdue_review["item_type"]
                        }
                    )
                    reminders_sent += 1
                    
                except Exception as e:
                    logger.error(f"Error sending reminder for review {overdue_review['review_item_id']}: {e}")
            
            reminder_stats = {
                "total_overdue": len(overdue_reviews),
                "reminders_sent": reminders_sent,
                "project_id": str(project_id) if project_id else None,
                "reminder_threshold_hours": reminder_threshold_hours,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            logger.info(f"Sent {reminders_sent} overdue reminders out of {len(overdue_reviews)} overdue reviews")
            return reminder_stats
            
        except Exception as e:
            logger.error(f"Error sending overdue reminders: {e}", exc_info=True)
            raise

    async def adjust_timeline_for_rework(
        self,
        review_item_id: UUID,
        rework_task_id: UUID,
        estimated_rework_hours: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Adjust project timeline when rework is required based on review feedback.
        
        Args:
            review_item_id: ID of the review item that was rejected
            rework_task_id: ID of the created rework task
            estimated_rework_hours: Estimated hours for rework
            
        Returns:
            Dict containing timeline adjustment information
        """
        logger.info(f"Adjusting timeline for rework - review item {review_item_id}, task {rework_task_id}")
        
        try:
            # Get review item and rework task
            review_item_result = await self.db_session.execute(
                select(ReviewItem).filter(ReviewItem.id == review_item_id)
            )
            review_item = review_item_result.scalar_one_or_none()
            
            rework_task_result = await self.db_session.execute(
                select(InternalTask).filter(InternalTask.id == rework_task_id)
            )
            rework_task = rework_task_result.scalar_one_or_none()
            
            if not review_item or not rework_task:
                raise ValueError("Review item or rework task not found")
            
            # Calculate rework impact
            rework_hours = estimated_rework_hours or float(rework_task.estimated_hours or 8)
            rework_days = max(1, int(rework_hours / 8))  # Convert to working days
            
            # Find affected timeline phases
            timeline_phases_result = await self.db_session.execute(
                select(ProjectTimeline)
                .filter(ProjectTimeline.project_id == review_item.project_id)
                .filter(ProjectTimeline.planned_end_date >= datetime.utcnow().date())
                .order_by(ProjectTimeline.phase_order)
            )
            timeline_phases = timeline_phases_result.scalars().all()
            
            adjusted_phases = []
            
            # Adjust timeline phases that haven't started yet
            for phase in timeline_phases:
                if phase.actual_start_date is None:  # Phase hasn't started
                    # Extend the phase end date
                    original_end = phase.planned_end_date
                    new_end = original_end + timedelta(days=rework_days)
                    
                    phase.planned_end_date = new_end
                    self.db_session.add(phase)
                    
                    adjusted_phases.append({
                        "phase_name": phase.phase_name,
                        "phase_order": phase.phase_order,
                        "original_end_date": original_end.isoformat(),
                        "new_end_date": new_end.isoformat(),
                        "delay_days": rework_days
                    })
            
            await self.db_session.commit()
            
            # Send notification about timeline adjustment
            if adjusted_phases:
                await self.notification_service.send_notification(
                    project_id=str(review_item.project_id),
                    notification_type=NotificationType.WARNING,
                    title="Timeline Adjusted Due to Rework",
                    message=f"Project timeline has been extended by {rework_days} days due to required rework",
                    data={
                        "review_item_id": str(review_item_id),
                        "rework_task_id": str(rework_task_id),
                        "rework_days": rework_days,
                        "adjusted_phases": adjusted_phases
                    }
                )
            
            adjustment_info = {
                "review_item_id": str(review_item_id),
                "rework_task_id": str(rework_task_id),
                "project_id": str(review_item.project_id),
                "rework_hours": rework_hours,
                "rework_days": rework_days,
                "adjusted_phases": adjusted_phases,
                "total_phases_adjusted": len(adjusted_phases),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            logger.info(f"Adjusted {len(adjusted_phases)} timeline phases for rework")
            return adjustment_info
            
        except Exception as e:
            logger.error(f"Error adjusting timeline for rework: {e}", exc_info=True)
            raise

    async def update_timeline_for_early_completion(
        self,
        review_item_id: UUID,
        completion_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Update timeline when reviews are completed ahead of schedule.
        
        Args:
            review_item_id: ID of the completed review item
            completion_time: Time when review was completed (defaults to now)
            
        Returns:
            Dict containing timeline update information
        """
        logger.info(f"Updating timeline for early completion - review item {review_item_id}")
        
        try:
            completion_time = completion_time or datetime.utcnow()
            
            # Get review item
            review_item_result = await self.db_session.execute(
                select(ReviewItem).filter(ReviewItem.id == review_item_id)
            )
            review_item = review_item_result.scalar_one_or_none()
            
            if not review_item:
                raise ValueError(f"Review item {review_item_id} not found")
            
            # Calculate time saved
            expected_completion = review_item.presented_at + timedelta(hours=48)  # Default review time
            time_saved = expected_completion - completion_time
            
            if time_saved.total_seconds() > 0:
                days_saved = max(0, int(time_saved.total_seconds() / (24 * 3600)))
                
                if days_saved > 0:
                    # Find future timeline phases that can be accelerated
                    timeline_phases_result = await self.db_session.execute(
                        select(ProjectTimeline)
                        .filter(ProjectTimeline.project_id == review_item.project_id)
                        .filter(ProjectTimeline.planned_start_date > datetime.utcnow().date())
                        .order_by(ProjectTimeline.phase_order)
                    )
                    timeline_phases = timeline_phases_result.scalars().all()
                    
                    accelerated_phases = []
                    
                    # Accelerate future phases
                    for phase in timeline_phases:
                        original_start = phase.planned_start_date
                        original_end = phase.planned_end_date
                        
                        new_start = original_start - timedelta(days=days_saved)
                        new_end = original_end - timedelta(days=days_saved)
                        
                        phase.planned_start_date = new_start
                        phase.planned_end_date = new_end
                        self.db_session.add(phase)
                        
                        accelerated_phases.append({
                            "phase_name": phase.phase_name,
                            "phase_order": phase.phase_order,
                            "original_start_date": original_start.isoformat(),
                            "new_start_date": new_start.isoformat(),
                            "original_end_date": original_end.isoformat(),
                            "new_end_date": new_end.isoformat(),
                            "days_accelerated": days_saved
                        })
                    
                    await self.db_session.commit()
                    
                    # Send notification about timeline acceleration
                    if accelerated_phases:
                        await self.notification_service.send_notification(
                            project_id=str(review_item.project_id),
                            notification_type=NotificationType.SUCCESS,
                            title="Timeline Accelerated",
                            message=f"Project timeline has been accelerated by {days_saved} days due to early review completion",
                            data={
                                "review_item_id": str(review_item_id),
                                "days_saved": days_saved,
                                "accelerated_phases": accelerated_phases
                            }
                        )
                    
                    update_info = {
                        "review_item_id": str(review_item_id),
                        "project_id": str(review_item.project_id),
                        "completion_time": completion_time.isoformat(),
                        "expected_completion": expected_completion.isoformat(),
                        "days_saved": days_saved,
                        "accelerated_phases": accelerated_phases,
                        "total_phases_accelerated": len(accelerated_phases),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    
                    logger.info(f"Accelerated {len(accelerated_phases)} timeline phases by {days_saved} days")
                    return update_info
            
            # No significant time saved
            return {
                "review_item_id": str(review_item_id),
                "project_id": str(review_item.project_id),
                "completion_time": completion_time.isoformat(),
                "days_saved": 0,
                "accelerated_phases": [],
                "message": "No significant timeline acceleration possible"
            }
            
        except Exception as e:
            logger.error(f"Error updating timeline for early completion: {e}", exc_info=True)
            raise

    async def get_review_timeline_status(
        self,
        project_id: UUID
    ) -> Dict[str, Any]:
        """
        Get comprehensive review timeline status for a project.
        
        Args:
            project_id: ID of the project
            
        Returns:
            Dict containing timeline status information
        """
        logger.info(f"Getting review timeline status for project {project_id}")
        
        try:
            # Get all review items for the project
            review_items_result = await self.db_session.execute(
                select(ReviewItem)
                .filter(ReviewItem.project_id == project_id)
                .order_by(ReviewItem.presented_at.desc())
            )
            review_items = review_items_result.scalars().all()
            
            # Get project timeline phases
            timeline_phases_result = await self.db_session.execute(
                select(ProjectTimeline)
                .filter(ProjectTimeline.project_id == project_id)
                .order_by(ProjectTimeline.phase_order)
            )
            timeline_phases = timeline_phases_result.scalars().all()
            
            # Calculate statistics
            total_reviews = len(review_items)
            pending_reviews = len([r for r in review_items if r.review_status == ReviewStatus.PENDING_REVIEW.value])
            approved_reviews = len([r for r in review_items if r.review_status == ReviewStatus.APPROVED.value])
            rejected_reviews = len([r for r in review_items if r.review_status == ReviewStatus.REJECTED.value])
            
            # Detect overdue reviews
            overdue_reviews = await self.detect_overdue_reviews(project_id=project_id)
            
            # Calculate timeline health
            current_time = datetime.utcnow()
            delayed_phases = []
            on_track_phases = []
            
            for phase in timeline_phases:
                if phase.planned_end_date:
                    phase_end = datetime.combine(phase.planned_end_date, datetime.min.time())
                    if current_time > phase_end and phase.percentage_complete < 100:
                        delayed_phases.append({
                            "phase_name": phase.phase_name,
                            "planned_end_date": phase.planned_end_date.isoformat(),
                            "days_delayed": (current_time.date() - phase.planned_end_date).days,
                            "percentage_complete": float(phase.percentage_complete)
                        })
                    else:
                        on_track_phases.append({
                            "phase_name": phase.phase_name,
                            "planned_end_date": phase.planned_end_date.isoformat(),
                            "percentage_complete": float(phase.percentage_complete)
                        })
            
            timeline_status = {
                "project_id": str(project_id),
                "review_statistics": {
                    "total_reviews": total_reviews,
                    "pending_reviews": pending_reviews,
                    "approved_reviews": approved_reviews,
                    "rejected_reviews": rejected_reviews,
                    "approval_rate": (approved_reviews / total_reviews * 100) if total_reviews > 0 else 0
                },
                "overdue_reviews": {
                    "count": len(overdue_reviews),
                    "items": overdue_reviews
                },
                "timeline_health": {
                    "total_phases": len(timeline_phases),
                    "delayed_phases": len(delayed_phases),
                    "on_track_phases": len(on_track_phases),
                    "delayed_phase_details": delayed_phases,
                    "on_track_phase_details": on_track_phases
                },
                "timestamp": current_time.isoformat()
            }
            
            logger.info(f"Generated timeline status for project {project_id}")
            return timeline_status
            
        except Exception as e:
            logger.error(f"Error getting review timeline status: {e}", exc_info=True)
            raise