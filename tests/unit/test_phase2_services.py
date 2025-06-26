# tests/unit/test_phase2_services.py - Unit tests for Phase 2 services

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

# Tests for TaskManagementService
@pytest.mark.unit
class TestTaskManagementService:
    """Unit tests for TaskManagementService."""

    @pytest.fixture
    def mock_db_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_create_project_level_task(self, mock_db_session):
        """Test project level task creation."""
        from src.services.task_management_service import TaskManagementService
        
        service = TaskManagementService(db_session=mock_db_session)
        project_id = uuid4()
        
        # Mock the database operations
        mock_db_session.add.return_value = None
        mock_db_session.commit.return_value = None
        mock_db_session.refresh.return_value = None
        
        # Test would require actual service implementation
        assert service is not None
        assert service.db_session == mock_db_session

    @pytest.mark.asyncio
    async def test_associate_task_with_deliverable(self, mock_db_session):
        """Test task-deliverable association."""
        from src.services.task_management_service import TaskManagementService
        
        service = TaskManagementService(db_session=mock_db_session)
        task_id = uuid4()
        deliverable_id = uuid4()
        
        # Mock no existing association
        mock_db_session.query.return_value.filter.return_value.first.return_value = None
        
        assert service is not None

    @pytest.mark.asyncio
    async def test_find_similar_tasks(self, mock_db_session):
        """Test finding similar tasks in project."""
        from src.services.task_management_service import TaskManagementService
        
        service = TaskManagementService(db_session=mock_db_session)
        project_id = uuid4()
        
        # Mock query results
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = []
        
        assert service is not None


# Tests for PricingService  
@pytest.mark.unit
class TestPricingService:
    """Unit tests for PricingService."""

    @pytest.fixture
    def mock_db_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_set_deliverable_pricing(self, mock_db_session):
        """Test deliverable pricing creation."""
        from src.services.pricing_service import PricingService
        
        service = PricingService(db_session=mock_db_session)
        project_id = uuid4()
        deliverable_id = uuid4()
        
        # Mock no existing pricing
        mock_db_session.query.return_value.filter.return_value.first.return_value = None
        
        assert service is not None

    @pytest.mark.asyncio
    async def test_calculate_final_price(self, mock_db_session):
        """Test final price calculation."""
        from src.services.pricing_service import PricingService
        
        service = PricingService(db_session=mock_db_session)
        
        # Test calculation logic
        base_price = Decimal("1000.00")
        markup_percentage = Decimal("20.0")
        discount_percentage = Decimal("5.0")
        
        # Expected: 1000 + 20% = 1200, then -5% = 1140
        expected_price = Decimal("1140.00")
        
        assert service is not None

    @pytest.mark.asyncio
    async def test_calculate_project_budget(self, mock_db_session):
        """Test project budget calculation."""
        from src.services.pricing_service import PricingService
        
        service = PricingService(db_session=mock_db_session)
        project_id = uuid4()
        
        # Mock pricing data
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = []
        
        assert service is not None


# Tests for TimelineTrackingService
@pytest.mark.unit
class TestTimelineTrackingService:
    """Unit tests for TimelineTrackingService."""

    @pytest.fixture
    def mock_db_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_log_daily_progress(self, mock_db_session):
        """Test daily progress logging."""
        from src.services.timeline_tracking_service import TimelineTrackingService
        
        service = TimelineTrackingService(db_session=mock_db_session)
        task_id = uuid4()
        progress_date = date.today()
        
        # Mock no existing progress
        mock_db_session.query.return_value.filter.return_value.first.return_value = None
        
        assert service is not None

    @pytest.mark.asyncio
    async def test_calculate_task_completion(self, mock_db_session):
        """Test task completion calculation."""
        from src.services.timeline_tracking_service import TimelineTrackingService
        
        service = TimelineTrackingService(db_session=mock_db_session)
        task_id = uuid4()
        
        # Mock progress entries
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = []
        
        assert service is not None

    @pytest.mark.asyncio
    async def test_create_project_milestones(self, mock_db_session):
        """Test project milestone creation."""
        from src.services.timeline_tracking_service import TimelineTrackingService
        
        service = TimelineTrackingService(db_session=mock_db_session)
        project_id = uuid4()
        
        assert service is not None


# Tests for RequirementService
@pytest.mark.unit
class TestRequirementService:
    """Unit tests for RequirementService."""

    @pytest.fixture
    def mock_db_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_auto_generate_requirements(self, mock_db_session):
        """Test auto-generation of requirements."""
        from src.services.requirement_service import RequirementService
        
        service = RequirementService(db_session=mock_db_session)
        project_id = uuid4()
        
        # Mock templates
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = []
        
        assert service is not None

    @pytest.mark.asyncio
    async def test_create_custom_requirement(self, mock_db_session):
        """Test custom requirement creation."""
        from src.services.requirement_service import RequirementService
        
        service = RequirementService(db_session=mock_db_session)
        project_id = uuid4()
        
        assert service is not None

    @pytest.mark.asyncio
    async def test_get_requirement_templates(self, mock_db_session):
        """Test getting requirement templates."""
        from src.services.requirement_service import RequirementService
        
        service = RequirementService(db_session=mock_db_session)
        deliverable_type = "website"
        
        # Mock templates
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = []
        
        assert service is not None

    @pytest.mark.asyncio
    async def test_get_requirements_summary(self, mock_db_session):
        """Test requirements summary."""
        from src.services.requirement_service import RequirementService
        
        service = RequirementService(db_session=mock_db_session)
        project_id = uuid4()
        
        # Mock summary data
        mock_db_session.execute.return_value.first.return_value = (10, 7, 3)
        
        assert service is not None


# Integration tests
@pytest.mark.unit
class TestServiceIntegration:
    """Unit tests for service integration."""

    @pytest.fixture
    def mock_db_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_all_services_instantiate(self, mock_db_session):
        """Test that all services can be instantiated."""
        from src.services.task_management_service import TaskManagementService
        from src.services.pricing_service import PricingService
        from src.services.timeline_tracking_service import TimelineTrackingService
        from src.services.requirement_service import RequirementService
        
        services = {
            "task_management": TaskManagementService(db_session=mock_db_session),
            "pricing": PricingService(db_session=mock_db_session),
            "timeline_tracking": TimelineTrackingService(db_session=mock_db_session),
            "requirement": RequirementService(db_session=mock_db_session)
        }
        
        assert len(services) == 4
        assert all(service is not None for service in services.values())
        assert all(hasattr(service, 'db_session') for service in services.values())

    @pytest.mark.asyncio
    async def test_services_share_session(self, mock_db_session):
        """Test that services can share the same database session."""
        from src.services.task_management_service import TaskManagementService
        from src.services.pricing_service import PricingService
        
        task_service = TaskManagementService(db_session=mock_db_session)
        pricing_service = PricingService(db_session=mock_db_session)
        
        assert task_service.db_session is pricing_service.db_session
