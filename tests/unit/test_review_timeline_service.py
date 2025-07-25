# tests/unit/test_review_timeline_service.py

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.services.review_timeline_service import ReviewTimelineService
from src.models.review_item import ReviewItem, ReviewStatus, ReviewItemType
from src.models.project_timeline import ProjectTimeline
from src.models.internal_task import InternalTask, TaskStatus
from src.services.notification_service import NotificationService, NotificationType


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    session = AsyncMock()
    return session


@pytest.fixture
def mock_notification_service():
    """Mock notification service."""
    return AsyncMock(spec=NotificationService)


@pytest.fixture
def review_timeline_service(mock_db_session, mock_notification_service):
    """Create ReviewTimelineService instance with mocked dependencies."""
    return ReviewTimelineService(
        db_session=mock_db_session,
        notification_service=mock_notification_service
    )


@pytest.fixture
def sample_review_item():
    """Sample review item for testing."""
    return ReviewItem(
        id=uuid4(),
        project_id=uuid4(),
        deliverable_id=uuid4(),
        source_internal_task_id=uuid4(),
        item_type=ReviewItemType.STATIC_RENDER,
        description="Test review item",
        review_status=ReviewStatus.PENDING_REVIEW,
        sequence_number=1,
        review_round=1,
        presented_at=datetime.utcnow() - timedelta(hours=1)
    )


@pytest.fixture
def sample_timeline_phase():
    """Sample timeline phase for testing."""
    return ProjectTimeline(
        id=uuid4(),
        project_id=uuid4(),
        phase_name="Modeling",
        phase_order=2,
        planned_start_date=(datetime.utcnow() + timedelta(days=1)).date(),
        planned_end_date=(datetime.utcnow() + timedelta(days=5)).date(),
        percentage_complete=0
    )


class TestReviewTimelineService:
    """Test cases for ReviewTimelineService."""

    @pytest.mark.asyncio
    async def test_set_review_deadline_with_custom_deadline(
        self, review_timeline_service, mock_db_session, sample_review_item
    ):
        """Test setting custom review deadline."""
        # Arrange
        custom_deadline = datetime.utcnow() + timedelta(days=2)
        
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = sample_review_item
        mock_db_session.execute.return_value = mock_result
        
        # Act
        result = await review_timeline_service.set_review_deadline(
            review_item_id=sample_review_item.id,
            custom_deadline=custom_deadline
        )
        
        # Assert
        assert result["review_item_id"] == str(sample_review_item.id)
        assert result["deadline"] == custom_deadline.isoformat()
        assert result["deadline_source"] == "custom"
        assert result["project_id"] == str(sample_review_item.project_id)

    @pytest.mark.asyncio
    async def test_set_review_deadline_with_timeline_phase(
        self, review_timeline_service, mock_db_session, sample_review_item, sample_timeline_phase
    ):
        """Test setting review deadline based on timeline phase."""
        # Arrange
        buffer_hours = 12
        
        # Mock review item query
        review_result = AsyncMock()
        review_result.scalar_one_or_none.return_value = sample_review_item
        
        # Mock timeline phase query
        timeline_result = AsyncMock()
        timeline_result.scalar_one_or_none.return_value = sample_timeline_phase
        
        mock_db_session.execute.side_effect = [review_result, timeline_result]
        
        # Act
        result = await review_timeline_service.set_review_deadline(
            review_item_id=sample_review_item.id,
            project_timeline_phase="Modeling",
            buffer_hours=buffer_hours
        )
        
        # Assert
        assert result["review_item_id"] == str(sample_review_item.id)
        assert result["deadline_source"] == "timeline_phase:Modeling"
        assert result["buffer_hours"] == buffer_hours
        
        # Verify deadline is buffer_hours before phase end
        expected_deadline = datetime.combine(sample_timeline_phase.planned_end_date, datetime.min.time()) - timedelta(hours=buffer_hours)
        assert result["deadline"] == expected_deadline.isoformat()

    @pytest.mark.asyncio
    async def test_set_review_deadline_default_fallback(
        self, review_timeline_service, mock_db_session, sample_review_item
    ):
        """Test setting review deadline with default fallback."""
        # Arrange
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = sample_review_item
        mock_db_session.execute.return_value = mock_result
        
        # Act
        with patch('src.services.review_timeline_service.datetime') as mock_datetime:
            mock_now = datetime(2024, 1, 15, 10, 0, 0)
            mock_datetime.utcnow.return_value = mock_now
            mock_datetime.combine = datetime.combine
            mock_datetime.min = datetime.min
            
            result = await review_timeline_service.set_review_deadline(
                review_item_id=sample_review_item.id
            )
        
        # Assert
        assert result["deadline_source"] == "default"
        expected_deadline = mock_now + timedelta(hours=48)
        assert result["deadline"] == expected_deadline.isoformat()

    @pytest.mark.asyncio
    async def test_detect_overdue_reviews(
        self, review_timeline_service, mock_db_session
    ):
        """Test detecting overdue review items."""
        # Arrange
        project_id = uuid4()
        
        # Create overdue review item
        overdue_review = ReviewItem(
            id=uuid4(),
            project_id=project_id,
            deliverable_id=uuid4(),
            source_internal_task_id=uuid4(),
            item_type=ReviewItemType.STATIC_RENDER,
            description="Overdue review",
            review_status=ReviewStatus.PENDING_REVIEW,
            sequence_number=1,
            review_round=1,
            presented_at=datetime.utcnow() - timedelta(hours=72)  # 72 hours ago
        )
        
        # Create recent review item (not overdue)
        recent_review = ReviewItem(
            id=uuid4(),
            project_id=project_id,
            deliverable_id=uuid4(),
            source_internal_task_id=uuid4(),
            item_type=ReviewItemType.TEXTURE_REVIEW,
            description="Recent review",
            review_status=ReviewStatus.PENDING_REVIEW,
            sequence_number=2,
            review_round=1,
            presented_at=datetime.utcnow() - timedelta(hours=12)  # 12 hours ago
        )
        
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = [overdue_review, recent_review]
        mock_db_session.execute.return_value = mock_result
        
        # Act
        overdue_reviews = await review_timeline_service.detect_overdue_reviews(
            project_id=project_id,
            hours_overdue_threshold=24
        )
        
        # Assert
        assert len(overdue_reviews) == 1
        assert overdue_reviews[0]["review_item_id"] == str(overdue_review.id)
        assert overdue_reviews[0]["hours_overdue"] >= 24
        assert overdue_reviews[0]["description"] == "Overdue review"

    @pytest.mark.asyncio
    async def test_send_overdue_reminders(
        self, review_timeline_service, mock_db_session, mock_notification_service
    ):
        """Test sending overdue reminder notifications."""
        # Arrange
        project_id = uuid4()
        
        # Mock overdue reviews detection
        overdue_reviews = [
            {
                "review_item_id": str(uuid4()),
                "project_id": str(project_id),
                "deliverable_id": str(uuid4()),
                "item_type": "STATIC_RENDER",
                "description": "Overdue review 1",
                "hours_overdue": 36.5
            },
            {
                "review_item_id": str(uuid4()),
                "project_id": str(project_id),
                "deliverable_id": str(uuid4()),
                "item_type": "TEXTURE_REVIEW",
                "description": "Overdue review 2",
                "hours_overdue": 48.2
            }
        ]
        
        with patch.object(review_timeline_service, 'detect_overdue_reviews', return_value=overdue_reviews):
            # Act
            result = await review_timeline_service.send_overdue_reminders(
                project_id=project_id,
                reminder_threshold_hours=24
            )
        
        # Assert
        assert result["total_overdue"] == 2
        assert result["reminders_sent"] == 2
        assert result["project_id"] == str(project_id)
        
        # Verify notifications were sent
        assert mock_notification_service.send_notification.call_count == 2
        
        # Check first notification call
        first_call = mock_notification_service.send_notification.call_args_list[0]
        assert first_call[1]["project_id"] == str(project_id)
        assert first_call[1]["notification_type"] == NotificationType.WARNING
        assert "overdue" in first_call[1]["message"].lower()

    @pytest.mark.asyncio
    async def test_adjust_timeline_for_rework(
        self, review_timeline_service, mock_db_session, mock_notification_service, sample_review_item
    ):
        """Test adjusting timeline when rework is required."""
        # Arrange
        rework_task_id = uuid4()
        rework_task = InternalTask(
            id=rework_task_id,
            project_id=sample_review_item.project_id,
            deliverable_id=sample_review_item.deliverable_id,
            title="Rework task",
            estimated_hours=16,
            status=TaskStatus.TODO
        )
        
        # Create future timeline phases
        future_phase1 = ProjectTimeline(
            id=uuid4(),
            project_id=sample_review_item.project_id,
            phase_name="Texturing",
            phase_order=3,
            planned_start_date=(datetime.utcnow() + timedelta(days=2)).date(),
            planned_end_date=(datetime.utcnow() + timedelta(days=5)).date(),
            actual_start_date=None,  # Not started yet
            percentage_complete=0
        )
        
        future_phase2 = ProjectTimeline(
            id=uuid4(),
            project_id=sample_review_item.project_id,
            phase_name="Lighting",
            phase_order=4,
            planned_start_date=(datetime.utcnow() + timedelta(days=6)).date(),
            planned_end_date=(datetime.utcnow() + timedelta(days=8)).date(),
            actual_start_date=None,  # Not started yet
            percentage_complete=0
        )
        
        # Mock database queries
        review_result = AsyncMock()
        review_result.scalar_one_or_none.return_value = sample_review_item
        
        task_result = AsyncMock()
        task_result.scalar_one_or_none.return_value = rework_task
        
        timeline_result = AsyncMock()
        timeline_result.scalars.return_value.all.return_value = [future_phase1, future_phase2]
        
        mock_db_session.execute.side_effect = [review_result, task_result, timeline_result]
        
        # Act
        result = await review_timeline_service.adjust_timeline_for_rework(
            review_item_id=sample_review_item.id,
            rework_task_id=rework_task_id,
            estimated_rework_hours=16
        )
        
        # Assert
        assert result["review_item_id"] == str(sample_review_item.id)
        assert result["rework_task_id"] == str(rework_task_id)
        assert result["rework_hours"] == 16
        assert result["rework_days"] == 2  # 16 hours / 8 hours per day
        assert result["total_phases_adjusted"] == 2
        
        # Verify notification was sent
        mock_notification_service.send_notification.assert_called_once()
        notification_call = mock_notification_service.send_notification.call_args
        assert notification_call[1]["notification_type"] == NotificationType.WARNING
        assert "Timeline Adjusted" in notification_call[1]["title"]

    @pytest.mark.asyncio
    async def test_update_timeline_for_early_completion(
        self, review_timeline_service, mock_db_session, mock_notification_service, sample_review_item
    ):
        """Test updating timeline for early review completion."""
        # Arrange
        early_completion_time = sample_review_item.presented_at + timedelta(hours=12)  # Completed early
        
        # Create future timeline phases
        future_phase = ProjectTimeline(
            id=uuid4(),
            project_id=sample_review_item.project_id,
            phase_name="Texturing",
            phase_order=3,
            planned_start_date=(datetime.utcnow() + timedelta(days=3)).date(),
            planned_end_date=(datetime.utcnow() + timedelta(days=6)).date(),
            percentage_complete=0
        )
        
        # Mock database queries
        review_result = AsyncMock()
        review_result.scalar_one_or_none.return_value = sample_review_item
        
        timeline_result = AsyncMock()
        timeline_result.scalars.return_value.all.return_value = [future_phase]
        
        mock_db_session.execute.side_effect = [review_result, timeline_result]
        
        # Act
        result = await review_timeline_service.update_timeline_for_early_completion(
            review_item_id=sample_review_item.id,
            completion_time=early_completion_time
        )
        
        # Assert
        assert result["review_item_id"] == str(sample_review_item.id)
        assert result["days_saved"] >= 1  # Should save at least 1 day
        assert result["total_phases_accelerated"] == 1
        
        # Verify notification was sent if phases were accelerated
        if result["days_saved"] > 0:
            mock_notification_service.send_notification.assert_called_once()
            notification_call = mock_notification_service.send_notification.call_args
            assert notification_call[1]["notification_type"] == NotificationType.SUCCESS
            assert "Timeline Accelerated" in notification_call[1]["title"]

    @pytest.mark.asyncio
    async def test_get_review_timeline_status(
        self, review_timeline_service, mock_db_session, sample_review_item
    ):
        """Test getting comprehensive review timeline status."""
        # Arrange
        project_id = sample_review_item.project_id
        
        # Create multiple review items with different statuses
        approved_review = ReviewItem(
            id=uuid4(),
            project_id=project_id,
            deliverable_id=uuid4(),
            source_internal_task_id=uuid4(),
            item_type=ReviewItemType.STATIC_RENDER,
            description="Approved review",
            review_status=ReviewStatus.APPROVED,
            sequence_number=1,
            review_round=1,
            presented_at=datetime.utcnow() - timedelta(hours=24)
        )
        
        rejected_review = ReviewItem(
            id=uuid4(),
            project_id=project_id,
            deliverable_id=uuid4(),
            source_internal_task_id=uuid4(),
            item_type=ReviewItemType.TEXTURE_REVIEW,
            description="Rejected review",
            review_status=ReviewStatus.REJECTED,
            sequence_number=2,
            review_round=1,
            presented_at=datetime.utcnow() - timedelta(hours=48)
        )
        
        # Create timeline phases
        on_track_phase = ProjectTimeline(
            id=uuid4(),
            project_id=project_id,
            phase_name="Modeling",
            phase_order=1,
            planned_start_date=(datetime.utcnow() - timedelta(days=2)).date(),
            planned_end_date=(datetime.utcnow() + timedelta(days=2)).date(),
            percentage_complete=75
        )
        
        delayed_phase = ProjectTimeline(
            id=uuid4(),
            project_id=project_id,
            phase_name="Texturing",
            phase_order=2,
            planned_start_date=(datetime.utcnow() - timedelta(days=5)).date(),
            planned_end_date=(datetime.utcnow() - timedelta(days=1)).date(),  # Should be done yesterday
            percentage_complete=50
        )
        
        # Mock database queries
        review_result = AsyncMock()
        review_result.scalars.return_value.all.return_value = [sample_review_item, approved_review, rejected_review]
        
        timeline_result = AsyncMock()
        timeline_result.scalars.return_value.all.return_value = [on_track_phase, delayed_phase]
        
        mock_db_session.execute.side_effect = [review_result, timeline_result]
        
        # Mock overdue reviews detection
        with patch.object(review_timeline_service, 'detect_overdue_reviews', return_value=[]):
            # Act
            result = await review_timeline_service.get_review_timeline_status(project_id)
        
        # Assert
        assert result["project_id"] == str(project_id)
        
        # Check review statistics
        review_stats = result["review_statistics"]
        assert review_stats["total_reviews"] == 3
        assert review_stats["pending_reviews"] == 1
        assert review_stats["approved_reviews"] == 1
        assert review_stats["rejected_reviews"] == 1
        assert review_stats["approval_rate"] == pytest.approx(33.33, rel=1e-2)
        
        # Check timeline health
        timeline_health = result["timeline_health"]
        assert timeline_health["total_phases"] == 2
        assert timeline_health["delayed_phases"] == 1
        assert timeline_health["on_track_phases"] == 1
        
        # Check delayed phase details
        delayed_details = timeline_health["delayed_phase_details"]
        assert len(delayed_details) == 1
        assert delayed_details[0]["phase_name"] == "Texturing"
        assert delayed_details[0]["days_delayed"] >= 1

    @pytest.mark.asyncio
    async def test_set_review_deadline_review_item_not_found(
        self, review_timeline_service, mock_db_session
    ):
        """Test setting review deadline when review item is not found."""
        # Arrange
        non_existent_id = uuid4()
        
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result
        
        # Act & Assert
        with pytest.raises(ValueError, match=f"Review item {non_existent_id} not found"):
            await review_timeline_service.set_review_deadline(
                review_item_id=non_existent_id,
                custom_deadline=datetime.utcnow() + timedelta(days=1)
            )

    @pytest.mark.asyncio
    async def test_adjust_timeline_for_rework_missing_entities(
        self, review_timeline_service, mock_db_session
    ):
        """Test timeline adjustment when review item or rework task is missing."""
        # Arrange
        review_item_id = uuid4()
        rework_task_id = uuid4()
        
        # Mock missing entities
        review_result = AsyncMock()
        review_result.scalar_one_or_none.return_value = None
        
        task_result = AsyncMock()
        task_result.scalar_one_or_none.return_value = None
        
        mock_db_session.execute.side_effect = [review_result, task_result]
        
        # Act & Assert
        with pytest.raises(ValueError, match="Review item or rework task not found"):
            await review_timeline_service.adjust_timeline_for_rework(
                review_item_id=review_item_id,
                rework_task_id=rework_task_id
            )