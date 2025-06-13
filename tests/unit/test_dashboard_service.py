# tests/unit/test_dashboard_service.py

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from uuid import uuid4

from src.services.dashboard_service import DashboardService
from src.models.project import Project, ProjectStatus
from src.models.deliverable import Deliverable
from src.models.client_feedback import ClientFeedback
from src.models.review_item import ReviewItem
from src.models.internal_task import InternalTask


class TestDashboardService:
    """Unit tests for DashboardService"""

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session"""
        return AsyncMock()

    @pytest.fixture
    def dashboard_service(self, mock_db_session):
        """Dashboard service with mocked database session"""
        return DashboardService(db_session=mock_db_session)

    @pytest.fixture
    def sample_project(self):
        """Sample project for testing"""
        project = Project()
        project.id = uuid4()
        project.name = "Test Project"
        project.status = ProjectStatus.IN_PROGRESS
        project.business_id = 1
        project.budget = 10000.00
        project.start_date = datetime(2024, 1, 1)
        project.end_date = datetime(2024, 6, 1)
        project.created_at = datetime(2024, 1, 1)
        project.updated_at = datetime(2024, 1, 1)
        return project

    @pytest.fixture
    def sample_deliverable(self, sample_project):
        """Sample deliverable for testing"""
        deliverable = Deliverable()
        deliverable.id = uuid4()
        deliverable.project_id = sample_project.id
        deliverable.deliverable_type = "design"
        deliverable.deliverable_sub_type = "mockup"
        deliverable.current_status = "pending"
        deliverable.tentative_timeline_days = 30
        deliverable.created_at = datetime(2024, 1, 1)
        deliverable.updated_at = datetime(2024, 1, 1)
        return deliverable

    @pytest.mark.asyncio
    async def test_calculate_dashboard_kpis(self, dashboard_service, mock_db_session):
        """Test KPI calculation for dashboard"""
        # Mock database query results
        mock_db_session.execute.return_value.scalar.side_effect = [
            2,  # active projects
            5,  # pending reviews
            10, # completed tasks
            8   # total deliverables
        ]

        business_id = 1
        kpis = await dashboard_service.calculate_dashboard_kpis(business_id)

        assert len(kpis) == 4
        assert kpis[0].title == "Active Projects"
        assert kpis[0].value == 2
        assert kpis[1].title == "Pending Reviews"
        assert kpis[1].value == 5
        assert kpis[2].title == "Completed Tasks"
        assert kpis[2].value == 10
        assert kpis[3].title == "Total Deliverables"
        assert kpis[3].value == 8

    @pytest.mark.asyncio
    async def test_calculate_project_kpis(self, dashboard_service, mock_db_session):
        """Test KPI calculation for specific project"""
        project_id = uuid4()
        
        # Mock database query results
        mock_db_session.execute.return_value.scalar.side_effect = [
            5,  # total deliverables
            3,  # completed deliverables
            1,  # pending deliverables
            15  # project tasks
        ]

        kpis = await dashboard_service.calculate_project_kpis(project_id)

        assert len(kpis) == 4
        assert kpis[0].title == "Total Deliverables"
        assert kpis[0].value == 5
        assert kpis[1].title == "Completed Deliverables"
        assert kpis[1].value == 3
        assert kpis[2].title == "Pending Deliverables"
        assert kpis[2].value == 1
        assert kpis[3].title == "Project Tasks"
        assert kpis[3].value == 15

    @pytest.mark.asyncio
    async def test_get_projects_for_business(self, dashboard_service, mock_db_session, sample_project):
        """Test getting projects for a business"""
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = [sample_project]

        business_id = 1
        projects = await dashboard_service.get_projects_for_business(business_id)

        assert len(projects) == 1
        assert projects[0].id == sample_project.id
        assert projects[0].name == sample_project.name

    @pytest.mark.asyncio
    async def test_get_project_by_id(self, dashboard_service, mock_db_session, sample_project):
        """Test getting a specific project by ID"""
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = sample_project

        project_id = sample_project.id
        business_id = 1
        project = await dashboard_service.get_project_by_id(project_id, business_id)

        assert project is not None
        assert project.id == sample_project.id
        assert project.name == sample_project.name

    @pytest.mark.asyncio
    async def test_get_project_by_id_not_found(self, dashboard_service, mock_db_session):
        """Test getting a project that doesn't exist"""
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = None

        project_id = uuid4()
        business_id = 1
        project = await dashboard_service.get_project_by_id(project_id, business_id)

        assert project is None

    @pytest.mark.asyncio
    async def test_get_recent_comments_across_projects(self, dashboard_service, mock_db_session):
        """Test getting recent comments across all projects"""
        # Mock comment data
        mock_feedback = MagicMock()
        mock_feedback.id = uuid4()
        mock_feedback.comment_text = "Test comment"
        mock_feedback.created_at = datetime(2024, 1, 1)
        mock_feedback.context_coordinates = None
        mock_feedback.timestamp_seconds = None

        mock_review_item = MagicMock()
        mock_review_item.id = uuid4()

        mock_deliverable = MagicMock()
        mock_deliverable.id = uuid4()
        mock_deliverable.deliverable_type = "design"
        mock_deliverable.deliverable_sub_type = "mockup"

        mock_project = MagicMock()
        mock_project.id = uuid4()
        mock_project.name = "Test Project"

        mock_db_session.execute.return_value.fetchall.return_value = [
            (mock_feedback, mock_review_item, mock_deliverable, mock_project)
        ]

        business_id = 1
        comments = await dashboard_service.get_recent_comments_across_projects(business_id)

        assert len(comments) == 1
        assert comments[0].comment_text == "Test comment"
        assert comments[0].project_name == "Test Project"
        assert comments[0].deliverable_name == "design - mockup"

    @pytest.mark.asyncio
    async def test_get_dashboard_timeline(self, dashboard_service, mock_db_session, sample_project):
        """Test getting dashboard timeline events"""
        sample_project.end_date = datetime(2024, 12, 31)
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = [sample_project]

        business_id = 1
        timeline = await dashboard_service.get_dashboard_timeline(business_id)

        assert len(timeline) == 1
        assert timeline[0].project_name == sample_project.name
        assert timeline[0].event_type == "project_end"

    @pytest.mark.asyncio
    async def test_project_to_summary_conversion(self, dashboard_service, sample_project):
        """Test converting project ORM to summary Pydantic model"""
        summary = dashboard_service._project_to_summary(sample_project)

        assert summary.id == str(sample_project.id)
        assert summary.name == sample_project.name
        assert summary.status == sample_project.status.value
        assert summary.budget == float(sample_project.budget)
        assert summary.start_date == sample_project.start_date
        assert summary.end_date == sample_project.end_date
        assert summary.created_at == sample_project.created_at

    @pytest.mark.asyncio
    async def test_get_dashboard_data_integration(self, dashboard_service, mock_db_session, sample_project):
        """Test complete dashboard data retrieval"""
        # Mock all the individual method calls
        dashboard_service.get_projects_for_business = AsyncMock(return_value=[sample_project])
        dashboard_service.calculate_dashboard_kpis = AsyncMock(return_value=[])
        dashboard_service.get_recent_comments_across_projects = AsyncMock(return_value=[])
        dashboard_service.get_dashboard_timeline = AsyncMock(return_value=[])

        business_id = 1
        dashboard_data = await dashboard_service.get_dashboard_data(business_id)

        assert dashboard_data.projects is not None
        assert dashboard_data.kpis is not None
        assert dashboard_data.recent_comments is not None
        assert dashboard_data.timeline is not None

    @pytest.mark.asyncio
    async def test_get_project_dashboard_data_integration(self, dashboard_service, mock_db_session, sample_project):
        """Test complete project dashboard data retrieval"""
        project_id = sample_project.id
        business_id = 1

        # Mock all the individual method calls
        dashboard_service.get_project_by_id = AsyncMock(return_value=sample_project)
        dashboard_service.calculate_project_kpis = AsyncMock(return_value=[])
        dashboard_service.get_recent_comments_for_project = AsyncMock(return_value=[])
        dashboard_service.get_project_timeline = AsyncMock(return_value=[])

        project_data = await dashboard_service.get_project_dashboard_data(project_id, business_id)

        assert project_data.project is not None
        assert project_data.kpis is not None
        assert project_data.recent_comments is not None
        assert project_data.timeline is not None

    @pytest.mark.asyncio
    async def test_get_project_dashboard_data_not_found(self, dashboard_service, mock_db_session):
        """Test project dashboard data when project doesn't exist"""
        project_id = uuid4()
        business_id = 1

        dashboard_service.get_project_by_id = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Project .* not found or not accessible"):
            await dashboard_service.get_project_dashboard_data(project_id, business_id) 