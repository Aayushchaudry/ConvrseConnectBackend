# src/services/timeline_notification_service.py

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from uuid import UUID
from enum import Enum

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.review_item import ReviewItem, ReviewStatus
from src.models.project_timeline import ProjectTimeline
from src.models.project import Project
from src.models.deliverable import Deliverable
from src.models.internal_task import InternalTask
from src.services.notification_service import NotificationService, NotificationType
from src.services.review_timeline_service import ReviewTimelineService

logger = logging.getLogger(__name__)


class NotificationFrequency(Enum):
    """Frequency for automated notifications."""
    IMMEDIATE = "immediate"
    DAILY = "daily"
    WEEKLY = "weekly"
    CUSTOM = "custom"


class TimelineNotificationService:
    """
    Service for managing automated timeline notifications and stakeholder communications.
    Handles overdue review reminders, timeline change notifications, and early completion updates.
    """

    def __init__(
        self, 
        db_session: AsyncSession, 
        notification_service: NotificationService = None,
        review_timeline_service: ReviewTimelineService = None
    ):
        """
        Initialize the TimelineNotificationService.
        
        Args:
            db_session: An asynchronous SQLAlchemy database session
            notification_service: Service for sending notifications
            review_timeline_service: Service for review timeline management
        """
        self.db_session = db_session
        self.notification_service = notification_service or NotificationService()
        self.review_timeline_service = review_timeline_service or ReviewTimelineService(db_session, notification_service)
        logger.info("TimelineNotificationService initialized")

    async def send_automated_overdue_reminders(
        self,
        project_id: Optional[UUID] = None,
        reminder_intervals: List[int] = None,
        max_reminders: int = 3
    ) -> Dict[str, Any]:
        """
        Send automated reminders for overdue reviews at specified intervals.
        
        Args:
            project_id: Optional project ID to filter by
            reminder_intervals: Hours after deadline to send reminders [24, 48, 72]
            max_reminders: Maximum number of reminders to send per review
            
        Returns:
            Dict containing reminder statistics
        """
        logger.info(f"Sending automated overdue reminders for project {project_id}")
        
        try:
            reminder_intervals = reminder_intervals or [24, 48, 72]  # Default intervals
            
            # Get overdue reviews
            overdue_reviews = await self.review_timeline_service.detect_overdue_reviews(
                project_id=project_id,
                hours_overdue_threshold=min(reminder_intervals)
            )
            
            reminders_sent = 0
            reminder_details = []
            
            for overdue_review in overdue_reviews:
                hours_overdue = overdue_review["hours_overdue"]
                review_item_id = overdue_review["review_item_id"]
                
                # Determine which reminder level this is
                reminder_level = 0
                for i, interval in enumerate(sorted(reminder_intervals)):
                    if hours_overdue >= interval:
                        reminder_level = i + 1
                
                if reminder_level > 0 and reminder_level <= max_reminders:
                    # Send escalated reminder based on level
                    urgency = "HIGH" if reminder_level >= 3 else "MEDIUM" if reminder_level >= 2 else "LOW"
                    
                    notification_type = (
                        NotificationType.ERROR if reminder_level >= 3 
                        else NotificationType.WARNING
                    )
                    
                    title = f"URGENT: Review Overdue ({reminder_level}/{max_reminders})" if reminder_level >= 3 else f"Review Reminder ({reminder_level}/{max_reminders})"
                    
                    message = (
                        f"Review item '{overdue_review['description']}' is {hours_overdue:.1f} hours overdue. "
                        f"This is reminder {reminder_level} of {max_reminders}. "
                        f"Immediate attention required to avoid project delays."
                    )
                    
                    await self.notification_service.send_notification(
                        project_id=overdue_review["project_id"],
                        notification_type=notification_type,
                        title=title,
                        message=message,
                        data={
                            "review_item_id": review_item_id,
                            "deliverable_id": overdue_review["deliverable_id"],
                            "hours_overdue": hours_overdue,
                            "reminder_level": reminder_level,
                            "urgency": urgency,
                            "item_type": overdue_review["item_type"]
                        }
                    )
                    
                    reminders_sent += 1
                    reminder_details.append({
                        "review_item_id": review_item_id,
                        "hours_overdue": hours_overdue,
                        "reminder_level": reminder_level,
                        "urgency": urgency
                    })
            
            reminder_stats = {
                "total_overdue_reviews": len(overdue_reviews),
                "reminders_sent": reminders_sent,
                "reminder_details": reminder_details,
                "project_id": str(project_id) if project_id else None,
                "reminder_intervals": reminder_intervals,
                "max_reminders": max_reminders,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            logger.info(f"Sent {reminders_sent} automated overdue reminders")
            return reminder_stats
            
        except Exception as e:
            logger.error(f"Error sending automated overdue reminders: {e}", exc_info=True)
            raise

    async def notify_stakeholders_of_timeline_changes(
        self,
        project_id: UUID,
        change_type: str,  # "delay", "acceleration", "milestone_update"
        change_details: Dict[str, Any],
        stakeholder_roles: List[str] = None
    ) -> Dict[str, Any]:
        """
        Notify project stakeholders of timeline changes.
        
        Args:
            project_id: ID of the project
            change_type: Type of timeline change
            change_details: Details about the change
            stakeholder_roles: Roles to notify (defaults to all)
            
        Returns:
            Dict containing notification results
        """
        logger.info(f"Notifying stakeholders of timeline change: {change_type} for project {project_id}")
        
        try:
            stakeholder_roles = stakeholder_roles or ["client", "project_manager", "team_lead", "designer"]
            
            # Get project information
            project_result = await self.db_session.execute(
                select(Project).filter(Project.id == project_id)
            )
            project = project_result.scalar_one_or_none()
            
            if not project:
                raise ValueError(f"Project {project_id} not found")
            
            # Prepare notification content based on change type
            notification_content = await self._prepare_timeline_change_notification(
                change_type, change_details, project
            )
            
            # Send notifications to stakeholders
            notifications_sent = []
            
            for role in stakeholder_roles:
                try:
                    # Customize message for different stakeholder roles
                    customized_content = await self._customize_notification_for_role(
                        notification_content, role, change_type
                    )
                    
                    await self.notification_service.send_notification(
                        project_id=str(project_id),
                        notification_type=customized_content["notification_type"],
                        title=customized_content["title"],
                        message=customized_content["message"],
                        data={
                            **change_details,
                            "stakeholder_role": role,
                            "change_type": change_type,
                            "project_name": project.name if hasattr(project, 'name') else f"Project {project_id}"
                        }
                    )
                    
                    notifications_sent.append({
                        "stakeholder_role": role,
                        "notification_type": customized_content["notification_type"].value,
                        "title": customized_content["title"]
                    })
                    
                except Exception as e:
                    logger.error(f"Error sending notification to {role}: {e}")
            
            notification_results = {
                "project_id": str(project_id),
                "change_type": change_type,
                "change_details": change_details,
                "stakeholder_roles_targeted": stakeholder_roles,
                "notifications_sent": notifications_sent,
                "total_notifications": len(notifications_sent),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            logger.info(f"Sent {len(notifications_sent)} stakeholder notifications for timeline change")
            return notification_results
            
        except Exception as e:
            logger.error(f"Error notifying stakeholders of timeline changes: {e}", exc_info=True)
            raise

    async def send_early_completion_notifications(
        self,
        project_id: UUID,
        completed_items: List[Dict[str, Any]],
        time_saved: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send notifications when reviews are completed ahead of schedule.
        
        Args:
            project_id: ID of the project
            completed_items: List of completed review items
            time_saved: Information about time saved
            
        Returns:
            Dict containing notification results
        """
        logger.info(f"Sending early completion notifications for project {project_id}")
        
        try:
            # Get project information
            project_result = await self.db_session.execute(
                select(Project).filter(Project.id == project_id)
            )
            project = project_result.scalar_one_or_none()
            
            if not project:
                raise ValueError(f"Project {project_id} not found")
            
            # Prepare celebration message
            items_count = len(completed_items)
            days_saved = time_saved.get("days_saved", 0)
            
            title = f"🎉 Early Completion: {items_count} Review{'s' if items_count != 1 else ''} Approved Ahead of Schedule!"
            
            message = (
                f"Great news! {items_count} review item{'s' if items_count != 1 else ''} "
                f"{'have' if items_count != 1 else 'has'} been approved ahead of schedule, "
                f"saving {days_saved} day{'s' if days_saved != 1 else ''} on the project timeline. "
                f"The project is now ahead of schedule!"
            )
            
            # Send success notification
            await self.notification_service.send_notification(
                project_id=str(project_id),
                notification_type=NotificationType.SUCCESS,
                title=title,
                message=message,
                data={
                    "completed_items": completed_items,
                    "time_saved": time_saved,
                    "project_status": "ahead_of_schedule",
                    "celebration": True
                }
            )
            
            # Send additional notification to project managers with detailed timeline impact
            if days_saved > 0:
                pm_title = f"Timeline Update: Project Accelerated by {days_saved} Days"
                pm_message = (
                    f"Project timeline has been accelerated due to early review completions. "
                    f"Consider reallocating resources or advancing subsequent phases. "
                    f"Updated timeline available in project dashboard."
                )
                
                await self.notification_service.send_notification(
                    project_id=str(project_id),
                    notification_type=NotificationType.INFO,
                    title=pm_title,
                    message=pm_message,
                    data={
                        "target_role": "project_manager",
                        "timeline_acceleration": time_saved,
                        "action_required": "timeline_review"
                    }
                )
            
            completion_results = {
                "project_id": str(project_id),
                "completed_items_count": items_count,
                "days_saved": days_saved,
                "notifications_sent": 2 if days_saved > 0 else 1,
                "celebration_sent": True,
                "manager_notification_sent": days_saved > 0,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            logger.info(f"Sent early completion notifications for {items_count} items")
            return completion_results
            
        except Exception as e:
            logger.error(f"Error sending early completion notifications: {e}", exc_info=True)
            raise

    async def schedule_recurring_timeline_reports(
        self,
        project_id: UUID,
        frequency: NotificationFrequency = NotificationFrequency.WEEKLY,
        recipients: List[str] = None
    ) -> Dict[str, Any]:
        """
        Schedule recurring timeline status reports for stakeholders.
        
        Args:
            project_id: ID of the project
            frequency: How often to send reports
            recipients: List of recipient roles
            
        Returns:
            Dict containing scheduling results
        """
        logger.info(f"Scheduling recurring timeline reports for project {project_id}")
        
        try:
            recipients = recipients or ["project_manager", "client"]
            
            # Get current timeline status
            timeline_status = await self.review_timeline_service.get_review_timeline_status(project_id)
            
            # Prepare report content
            report_title = f"Weekly Timeline Report - Project {project_id}"
            
            review_stats = timeline_status["review_statistics"]
            timeline_health = timeline_status["timeline_health"]
            
            report_message = (
                f"Timeline Status Summary:\n"
                f"• Reviews: {review_stats['approved_reviews']}/{review_stats['total_reviews']} approved "
                f"({review_stats['approval_rate']:.1f}% approval rate)\n"
                f"• Overdue Reviews: {timeline_status['overdue_reviews']['count']}\n"
                f"• Timeline Health: {timeline_health['on_track_phases']}/{timeline_health['total_phases']} phases on track\n"
                f"• Delayed Phases: {timeline_health['delayed_phases']}"
            )
            
            if timeline_health['delayed_phases'] > 0:
                report_message += f"\n\n⚠️ Action Required: {timeline_health['delayed_phases']} phase(s) are behind schedule."
            
            # Send report to recipients
            reports_sent = []
            
            for recipient in recipients:
                try:
                    # Customize report for recipient role
                    customized_title, customized_message = await self._customize_report_for_recipient(
                        report_title, report_message, recipient, timeline_status
                    )
                    
                    await self.notification_service.send_notification(
                        project_id=str(project_id),
                        notification_type=NotificationType.INFO,
                        title=customized_title,
                        message=customized_message,
                        data={
                            "report_type": "timeline_status",
                            "frequency": frequency.value,
                            "recipient_role": recipient,
                            "timeline_status": timeline_status,
                            "report_date": datetime.utcnow().isoformat()
                        }
                    )
                    
                    reports_sent.append({
                        "recipient": recipient,
                        "report_sent": True,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
                except Exception as e:
                    logger.error(f"Error sending report to {recipient}: {e}")
                    reports_sent.append({
                        "recipient": recipient,
                        "report_sent": False,
                        "error": str(e)
                    })
            
            scheduling_results = {
                "project_id": str(project_id),
                "frequency": frequency.value,
                "recipients": recipients,
                "reports_sent": reports_sent,
                "successful_reports": len([r for r in reports_sent if r["report_sent"]]),
                "failed_reports": len([r for r in reports_sent if not r["report_sent"]]),
                "next_report_due": self._calculate_next_report_date(frequency),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            logger.info(f"Scheduled timeline reports for {len(recipients)} recipients")
            return scheduling_results
            
        except Exception as e:
            logger.error(f"Error scheduling recurring timeline reports: {e}", exc_info=True)
            raise

    async def send_milestone_achievement_notifications(
        self,
        project_id: UUID,
        milestone_id: UUID,
        achievement_details: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send notifications when project milestones are achieved.
        
        Args:
            project_id: ID of the project
            milestone_id: ID of the achieved milestone
            achievement_details: Details about the milestone achievement
            
        Returns:
            Dict containing notification results
        """
        logger.info(f"Sending milestone achievement notifications for project {project_id}")
        
        try:
            # Get milestone information
            milestone_result = await self.db_session.execute(
                select(ProjectTimeline).filter(ProjectTimeline.id == milestone_id)
            )
            milestone = milestone_result.scalar_one_or_none()
            
            if not milestone:
                raise ValueError(f"Milestone {milestone_id} not found")
            
            # Prepare celebration notification
            title = f"🎯 Milestone Achieved: {milestone.phase_name}"
            
            on_time_status = ""
            if milestone.planned_end_date:
                if achievement_details.get("completed_early", False):
                    days_early = achievement_details.get("days_early", 0)
                    on_time_status = f" ({days_early} day{'s' if days_early != 1 else ''} early!)"
                elif achievement_details.get("completed_late", False):
                    days_late = achievement_details.get("days_late", 0)
                    on_time_status = f" ({days_late} day{'s' if days_late != 1 else ''} late)"
                else:
                    on_time_status = " (on schedule)"
            
            message = (
                f"Milestone '{milestone.phase_name}' has been successfully completed{on_time_status}. "
                f"The project is progressing well and moving to the next phase."
            )
            
            # Send achievement notification
            await self.notification_service.send_notification(
                project_id=str(project_id),
                notification_type=NotificationType.SUCCESS,
                title=title,
                message=message,
                data={
                    "milestone_id": str(milestone_id),
                    "milestone_name": milestone.phase_name,
                    "phase_order": milestone.phase_order,
                    "achievement_details": achievement_details,
                    "celebration": True
                }
            )
            
            achievement_results = {
                "project_id": str(project_id),
                "milestone_id": str(milestone_id),
                "milestone_name": milestone.phase_name,
                "phase_order": milestone.phase_order,
                "achievement_details": achievement_details,
                "notification_sent": True,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            logger.info(f"Sent milestone achievement notification for '{milestone.phase_name}'")
            return achievement_results
            
        except Exception as e:
            logger.error(f"Error sending milestone achievement notifications: {e}", exc_info=True)
            raise

    # Helper methods

    async def _prepare_timeline_change_notification(
        self,
        change_type: str,
        change_details: Dict[str, Any],
        project: Project
    ) -> Dict[str, Any]:
        """Prepare notification content based on timeline change type."""
        
        if change_type == "delay":
            return {
                "notification_type": NotificationType.WARNING,
                "title": "Project Timeline Delayed",
                "message": (
                    f"Project timeline has been extended by {change_details.get('delay_days', 0)} days "
                    f"due to {change_details.get('reason', 'review feedback')}. "
                    f"Updated timeline available in project dashboard."
                )
            }
        elif change_type == "acceleration":
            return {
                "notification_type": NotificationType.SUCCESS,
                "title": "Project Timeline Accelerated",
                "message": (
                    f"Great news! Project timeline has been accelerated by {change_details.get('days_saved', 0)} days "
                    f"due to early completions. The project is now ahead of schedule."
                )
            }
        elif change_type == "milestone_update":
            return {
                "notification_type": NotificationType.INFO,
                "title": "Milestone Timeline Updated",
                "message": (
                    f"Milestone '{change_details.get('milestone_name', 'Unknown')}' timeline has been updated. "
                    f"Please review the updated schedule in the project dashboard."
                )
            }
        else:
            return {
                "notification_type": NotificationType.INFO,
                "title": "Timeline Update",
                "message": f"Project timeline has been updated. Details: {change_details}"
            }

    async def _customize_notification_for_role(
        self,
        base_content: Dict[str, Any],
        role: str,
        change_type: str
    ) -> Dict[str, Any]:
        """Customize notification content for specific stakeholder roles."""
        
        customized = base_content.copy()
        
        if role == "client":
            if change_type == "delay":
                customized["message"] += " We apologize for any inconvenience and will keep you updated on progress."
            elif change_type == "acceleration":
                customized["message"] += " Thank you for your prompt feedback that made this possible!"
        
        elif role == "project_manager":
            if change_type == "delay":
                customized["message"] += " Please review resource allocation and consider mitigation strategies."
            elif change_type == "acceleration":
                customized["message"] += " Consider reallocating resources or advancing subsequent phases."
        
        elif role == "team_lead":
            if change_type == "delay":
                customized["message"] += " Team capacity and task priorities may need adjustment."
            elif change_type == "acceleration":
                customized["message"] += " Excellent work! Team performance is exceeding expectations."
        
        return customized

    async def _customize_report_for_recipient(
        self,
        title: str,
        message: str,
        recipient: str,
        timeline_status: Dict[str, Any]
    ) -> tuple[str, str]:
        """Customize timeline report for specific recipients."""
        
        if recipient == "client":
            client_title = title.replace("Timeline Report", "Project Progress Update")
            client_message = message.replace("Timeline Health:", "Project Progress:")
            client_message += "\n\nThank you for your continued collaboration on this project."
            return client_title, client_message
        
        elif recipient == "project_manager":
            pm_message = message
            if timeline_status["timeline_health"]["delayed_phases"] > 0:
                pm_message += "\n\n📋 Management Actions Recommended:\n"
                pm_message += "• Review resource allocation\n"
                pm_message += "• Consider timeline mitigation strategies\n"
                pm_message += "• Schedule stakeholder communication"
            return title, pm_message
        
        return title, message

    def _calculate_next_report_date(self, frequency: NotificationFrequency) -> str:
        """Calculate when the next report should be sent."""
        
        now = datetime.utcnow()
        
        if frequency == NotificationFrequency.DAILY:
            next_date = now + timedelta(days=1)
        elif frequency == NotificationFrequency.WEEKLY:
            next_date = now + timedelta(weeks=1)
        else:
            next_date = now + timedelta(days=7)  # Default to weekly
        
        return next_date.isoformat()