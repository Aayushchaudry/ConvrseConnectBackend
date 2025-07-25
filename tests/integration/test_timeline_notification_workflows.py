# tests/integration/test_timeline_notification_workflows.py

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.services.timeline_notification_service import TimelineNotificationService, NotificationFrequency
from src.services.review_timeline_service import ReviewTimelineService
from src.services.notification_service import NotificationService, NotificationType
from src.models.review_item import ReviewItem, ReviewStatus, ReviewItemType
from src.models.project_timeline import ProjectTimeline
from src.models.project import Project
from src.models.internal_task import InternalTask, TaskStatus


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    return AsyncMock()


@pytest.fixture
def mock_notification_service():
    """Mock notification service."""
    return AsyncMock(spec=NotificationService)


@pytest.fixture
def mock_review_timeline_service():
    """Mock review timeline service."""
    return AsyncMock(spec=ReviewTimelineService)


@pytest.fixture
def timeline_notification_service(mock_db_session, mock_notification_service, mock_review_timeline_service):
    """Create TimelineNotificationService instance with mocked dependencies."""
    return TimelineNotificationService(
        db_session=mock_db_session,
        notification_service=mock_notification_service,
        review_timeline_service=mock_review_timeline_service
    )


@pytest.fixture
def sample_project():
    """Sample project for testing."""
    return Project(
        id=uuid4(),
        name="Test Project",
        description="Test project description"
    )


@pytest.fixture
def sample_overdue_reviews():
    """Sample overdue reviews for testing."""
    return [
        {
            "review_item_id": str(uuid4()),
            "project_id": str(uuid4()),
            "deliverable_id": str(uuid4()),
            "item_type": "STATIC_RENDER",
            "description": "Overdue review 1",
            "hours_overdue": 36.5,
            "sequence_number": 1,
            "review_round": 1
        },
        {
            "review_item_id": str(uuid4()),
            "project_id": str(uuid4()),
            "deliverable_id": str(uuid4()),
            "item_type": "TEXTURE_REVIEW",
            "description": "Overdue review 2",
            "hours_overdue": 72.8,
            "sequence_number": 2,
            "review_round": 1
        }
    ]


class TestTimelineNotificationWorkflows:
    """Integration tests for timeline notification workflows."""

    @pytest.mark.asyncio
    async def test_automated_overdue_reminder_workflow(
        self, timeline_notification_service, mock_review_timeline_service, 
        mock_notification_service, sample_overdue_reviews
    ):
        """Test complete automated overdue reminder workflow."""
        # Arrange
        project_id = uuid4()
        reminder_intervals = [24, 48, 72]
        
        # Mock overdue reviews detection
        mock_review_timeline_service.detect_overdue_reviews.return_value = sample_overdue_reviews
        
        # Act
        result = await timeline_notification_service.send_automated_overdue_reminders(
            project_id=project_id,
            reminder_intervals=reminder_intervals,
            max_reminders=3
        )
        
        # Assert
        assert result["total_overdue_reviews"] == 2
        assert result["reminders_sent"] == 2
        assert result["project_id"] == str(project_id)
        
        # Verify overdue detection was called
        mock_review_timeline_service.detect_overdue_reviews.assert_called_once_with(
            project_id=project_id,
            hours_overdue_threshold=24
        )
        
        # Verify notifications were sent
        assert mock_notification_service.send_notification.call_count == 2
        
        # Check first notification (36.5 hours overdue - level 2)
        first_call = mock_notification_service.send_notification.call_args_list[0]
        assert first_call[1]["notification_type"] == NotificationType.WARNING
        assert "Review Reminder (2/3)" in first_call[1]["title"]
        assert "36.5 hours overdue" in first_call[1]["message"]
        
        # Check second notification (72.8 hours overdue - level 3)
        second_call = mock_notification_service.send_notification.call_args_list[1]
        assert second_call[1]["notification_type"] == NotificationType.ERROR
        assert "URGENT: Review Overdue (3/3)" in second_call[1]["title"]
        assert "72.8 hours overdue" in second_call[1]["message"]

    @pytest.mark.asyncio
    async def test_stakeholder_timeline_change_notification_workflow(
        self, timeline_notification_service, mock_db_session, 
        mock_notification_service, sample_project
    ):
        """Test stakeholder notification workflow for timeline changes."""
        # Arrange
        project_id = sample_project.id
        change_type = "delay"
        change_details = {
            "delay_days": 3,
            "reason": "review feedback requiring rework",
            "affected_phases": ["Texturing", "Lighting"]
        }
        stakeholder_roles = ["client", "project_manager", "team_lead"]
        
        # Mock project query
        project_result = AsyncMock()
        project_result.scalar_one_or_none.return_value = sample_project
        mock_db_session.execute.return_value = project_result
        
        # Act
        result = await timeline_notification_service.notify_stakeholders_of_timeline_changes(
            project_id=project_id,
            change_type=change_type,
            change_details=change_details,
            stakeholder_roles=stakeholder_roles
        )
        
        # Assert
        assert result["project_id"] == str(project_id)
        assert result["change_type"] == change_type
        assert result["total_notifications"] == 3
        
        # Verify notifications were sent to all stakeholders
        assert mock_notification_service.send_notification.call_count == 3
        
        # Check that different roles received customized messages
        notification_calls = mock_notification_service.send_notification.call_args_list
        
        # All should be WARNING type for delays
        for call in notification_calls:
            assert call[1]["notification_type"] == NotificationType.WARNING
            assert "Project Timeline Delayed" in call[1]["title"]
            assert "3 days" in call[1]["message"]
        
        # Check role-specific customizations in data
        sent_roles = [call[1]["data"]["stakeholder_role"] for call in notification_calls]
        assert set(sent_roles) == set(stakeholder_roles)

    @pytest.mark.asyncio
    async def test_early_completion_notification_workflow(
        self, timeline_notification_service, mock_db_session, 
        mock_notification_service, sample_project
    ):
        """Test early completion notification workflow."""
        # Arrange
        project_id = sample_project.id
        completed_items = [
            {
                "review_item_id": str(uuid4()),
                "description": "Static render review",
                "completed_at": datetime.utcnow().isoformat()
            },
            {
                "review_item_id": str(uuid4()),
                "description": "Texture review",
                "completed_at": datetime.utcnow().isoformat()
            }
        ]
        time_saved = {
            "days_saved": 2,
            "hours_saved": 48,
            "accelerated_phases": ["Lighting", "Final Review"]
        }
        
        # Mock project query
        project_result = AsyncMock()
        project_result.scalar_one_or_none.return_value = sample_project
        mock_db_session.execute.return_value = project_result
        
        # Act
        result = await timeline_notification_service.send_early_completion_notifications(
            project_id=project_id,
            completed_items=completed_items,
            time_saved=time_saved
        )
        
        # Assert
        assert result["project_id"] == str(project_id)
        assert result["completed_items_count"] == 2
        assert result["days_saved"] == 2
        assert result["celebration_sent"] is True
        assert result["manager_notification_sent"] is True
        assert result["notifications_sent"] == 2
        
        # Verify notifications were sent
        assert mock_notification_service.send_notification.call_count == 2
        
        # Check celebration notification
        first_call = mock_notification_service.send_notification.call_args_list[0]
        assert first_call[1]["notification_type"] == NotificationType.SUCCESS
        assert "🎉 Early Completion" in first_call[1]["title"]
        assert "2 reviews" in first_call[1]["message"]
        assert "2 days" in first_call[1]["message"]
        
        # Check project manager notification
        second_call = mock_notification_service.send_notification.call_args_list[1]
        assert second_call[1]["notification_type"] == NotificationType.INFO
        assert "Timeline Update" in second_call[1]["title"]
        assert "project_manager" in second_call[1]["data"]["target_role"]

    @pytest.mark.asyncio
    async def test_recurring_timeline_reports_workflow(
        self, timeline_notification_service, mock_review_timeline_service, 
        mock_notification_service
    ):
        """Test recurring timeline reports workflow."""
        # Arrange
        project_id = uuid4()
        frequency = NotificationFrequency.WEEKLY
        recipients = ["project_manager", "client"]
        
        # Mock timeline status
        timeline_status = {
            "project_id": str(project_id),
            "review_statistics": {
                "total_reviews": 10,
                "pending_reviews": 2,
                "approved_reviews": 7,
                "rejected_reviews": 1,
                "approval_rate": 70.0
            },
            "overdue_reviews": {
                "count": 1,
                "items": []
            },
            "timeline_health": {
                "total_phases": 5,
                "delayed_phases": 1,
                "on_track_phases": 4,
                "delayed_phase_details": [
                    {
                        "phase_name": "Texturing",
                        "days_delayed": 2,
                        "percentage_complete": 75
                    }
                ]
            }
        }
        
        mock_review_timeline_service.get_review_timeline_status.return_value = timeline_status
        
        # Act
        result = await timeline_notification_service.schedule_recurring_timeline_reports(
            project_id=project_id,
            frequency=frequency,
            recipients=recipients
        )
        
        # Assert
        assert result["project_id"] == str(project_id)
        assert result["frequency"] == frequency.value
        assert result["successful_reports"] == 2
        assert result["failed_reports"] == 0
        
        # Verify timeline status was retrieved
        mock_review_timeline_service.get_review_timeline_status.assert_called_once_with(project_id)
        
        # Verify reports were sent to recipients
        assert mock_notification_service.send_notification.call_count == 2
        
        # Check report content
        notification_calls = mock_notification_service.send_notification.call_args_list
        
        for call in notification_calls:
            assert call[1]["notification_type"] == NotificationType.INFO
            assert "Timeline Report" in call[1]["title"] or "Progress Update" in call[1]["title"]
            assert "7/10 approved" in call[1]["message"]
            assert "70.0% approval rate" in call[1]["message"]
            assert "1 phase(s) are behind schedule" in call[1]["message"]

    @pytest.mark.asyncio
    async def test_milestone_achievement_notification_workflow(
        self, timeline_notification_service, mock_db_session, mock_notification_service
    ):
        """Test milestone achievement notification workflow."""
        # Arrange
        project_id = uuid4()
        milestone_id = uuid4()
        
        milestone = ProjectTimeline(
            id=milestone_id,
            project_id=project_id,
            phase_name="Modeling Complete",
            phase_order=2,
            planned_start_date=(datetime.utcnow() - timedelta(days=5)).date(),
            planned_end_date=(datetime.utcnow() - timedelta(days=1)).date(),
            percentage_complete=100,
            is_milestone=True
        )
        
        achievement_details = {
            "completed_early": True,
            "days_early": 1,
            "completion_percentage": 100,
            "next_phase": "Texturing"
        }
        
        # Mock milestone query
        milestone_result = AsyncMock()
        milestone_result.scalar_one_or_none.return_value = milestone
        mock_db_session.execute.return_value = milestone_result
        
        # Act
        result = await timeline_notification_service.send_milestone_achievement_notifications(
            project_id=project_id,
            milestone_id=milestone_id,
            achievement_details=achievement_details
        )
        
        # Assert
        assert result["project_id"] == str(project_id)
        assert result["milestone_id"] == str(milestone_id)
        assert result["milestone_name"] == "Modeling Complete"
        assert result["notification_sent"] is True
        
        # Verify notification was sent
        mock_notification_service.send_notification.assert_called_once()
        
        # Check notification content
        call = mock_notification_service.send_notification.call_args
        assert call[1]["notification_type"] == NotificationType.SUCCESS
        assert "🎯 Milestone Achieved: Modeling Complete" in call[1]["title"]
        assert "1 day early" in call[1]["message"]
        assert call[1]["data"]["celebration"] is True

    @pytest.mark.asyncio
    async def test_end_to_end_timeline_notification_workflow(
        self, timeline_notification_service, mock_review_timeline_service,
        mock_notification_service, sample_overdue_reviews
    ):
        """Test end-to-end timeline notification workflow with multiple notification types."""
        # Arrange
        project_id = uuid4()
        
        # Mock overdue reviews for automated reminders
        mock_review_timeline_service.detect_overdue_reviews.return_value = sample_overdue_reviews
        
        # Act 1: Send automated overdue reminders
        reminder_result = await timeline_notification_service.send_automated_overdue_reminders(
            project_id=project_id,
            reminder_intervals=[24, 48, 72],
            max_reminders=3
        )
        
        # Act 2: Notify stakeholders of timeline changes due to overdue reviews
        change_details = {
            "delay_days": 2,
            "reason": "overdue reviews requiring additional time",
            "affected_phases": ["Final Review"]
        }
        
        with patch.object(timeline_notification_service.db_session, 'execute') as mock_execute:
            project_result = AsyncMock()
            project_result.scalar_one_or_none.return_value = Project(id=project_id, name="Test Project")
            mock_execute.return_value = project_result
            
            stakeholder_result = await timeline_notification_service.notify_stakeholders_of_timeline_changes(
                project_id=project_id,
                change_type="delay",
                change_details=change_details,
                stakeholder_roles=["client", "project_manager"]
            )
        
        # Assert
        # Check reminder results
        assert reminder_result["total_overdue_reviews"] == 2
        assert reminder_result["reminders_sent"] == 2
        
        # Check stakeholder notification results
        assert stakeholder_result["change_type"] == "delay"
        assert stakeholder_result["total_notifications"] == 2
        
        # Verify total notifications sent (2 reminders + 2 stakeholder notifications)
        assert mock_notification_service.send_notification.call_count == 4
        
        # Verify different notification types were used
        notification_calls = mock_notification_service.send_notification.call_args_list
        notification_types = [call[1]["notification_type"] for call in notification_calls]
        
        # Should have WARNING and ERROR from reminders, WARNING from stakeholder notifications
        assert NotificationType.WARNING in notification_types
        assert NotificationType.ERROR in notification_types

    @pytest.mark.asyncio
    async def test_notification_failure_handling(
        self, timeline_notification_service, mock_review_timeline_service,
        mock_notification_service, sample_overdue_reviews
    ):
        """Test handling of notification failures in workflows."""
        # Arrange
        project_id = uuid4()
        
        # Mock overdue reviews
        mock_review_timeline_service.detect_overdue_reviews.return_value = sample_overdue_reviews
        
        # Mock notification service to fail on second call
        mock_notification_service.send_notification.side_effect = [
            None,  # First call succeeds
            Exception("Notification service unavailable")  # Second call fails
        ]
        
        # Act
        result = await timeline_notification_service.send_automated_overdue_reminders(
            project_id=project_id,
            reminder_intervals=[24, 48, 72],
            max_reminders=3
        )
        
        # Assert
        # Should still return results even with partial failures
        assert result["total_overdue_reviews"] == 2
        assert result["reminders_sent"] == 1  # Only one succeeded
        
        # Verify both calls were attempted
        assert mock_notification_service.send_notification.call_count == 2

    @pytest.mark.asyncio
    async def test_customized_notifications_for_different_roles(
        self, timeline_notification_service, mock_db_session, mock_notification_service
    ):
        """Test that notifications are properly customized for different stakeholder roles."""
        # Arrange
        project_id = uuid4()
        project = Project(id=project_id, name="Test Project")
        
        change_details = {
            "delay_days": 1,
            "reason": "client feedback",
            "affected_phases": ["Final Review"]
        }
        
        # Mock project query
        project_result = AsyncMock()
        project_result.scalar_one_or_none.return_value = project
        mock_db_session.execute.return_value = project_result
        
        # Act
        result = await timeline_notification_service.notify_stakeholders_of_timeline_changes(
            project_id=project_id,
            change_type="delay",
            change_details=change_details,
            stakeholder_roles=["client", "project_manager", "team_lead"]
        )
        
        # Assert
        assert result["total_notifications"] == 3
        
        # Verify role-specific customizations
        notification_calls = mock_notification_service.send_notification.call_args_list
        
        # Check that each role received appropriate messaging
        for call in notification_calls:
            role = call[1]["data"]["stakeholder_role"]
            message = call[1]["message"]
            
            if role == "client":
                assert "apologize for any inconvenience" in message
            elif role == "project_manager":
                assert "review resource allocation" in message
            elif role == "team_lead":
                assert "Team capacity" in message