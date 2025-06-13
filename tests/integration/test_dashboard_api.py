# tests/integration/test_dashboard_api.py

import pytest
from httpx import AsyncClient
from fastapi import status
from datetime import datetime
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from src.main import app
from src.models.project import Project, ProjectStatus
from src.models.deliverable import Deliverable
from src.models.client_feedback import ClientFeedback
from src.models.review_item import ReviewItem
from src.models.internal_task import InternalTask
from src.middleware.auth_middleware import get_current_business


class TestDashboardAPI:
    """Integration tests for Dashboard API endpoints"""

    @pytest.fixture
    async def client(self):
        """HTTP client for testing"""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac

    @pytest.fixture
    def mock_auth_context(self):
        """Mock authentication context"""
        return {
            "business_id": 1,
            "user_id": "test-user-id",
            "permissions": ["read", "write"]
        }

    @pytest.fixture
    def sample_dashboard_response(self):
        """Sample dashboard response data"""
        return {
            "kpis": [
                {"title": "Active Projects", "value": 3, "icon": "📊", "color": "blue"},
                {"title": "Pending Reviews", "value": 5, "icon": "⏳", "color": "orange"},
                {"title": "Completed Tasks", "value": 12, "icon": "✅", "color": "green"},
                {"title": "Total Deliverables", "value": 8, "icon": "📦", "color": "purple"}
            ],
            "timeline": [
                {
                    "date": "2024-01-15",
                    "event_type": "project_end",
                    "project_name": "Website Redesign",
                    "description": "Project completion deadline"
                }
            ],
            "recent_comments": [
                {
                    "id": str(uuid4()),
                    "comment_text": "Looks great! Minor feedback on the color scheme.",
                    "created_at": "2024-01-10T10:30:00",
                    "project_name": "Mobile App Design",
                    "deliverable_name": "design - mockup",
                    "project_id": str(uuid4()),
                    "deliverable_id": str(uuid4()),
                    "coordinates": None,
                    "timestamp": None
                }
            ],
            "projects": [
                {
                    "id": str(uuid4()),
                    "name": "Website Redesign",
                    "status": "in_progress",
                    "budget": 25000.0,
                    "start_date": "2024-01-01T00:00:00",
                    "end_date": "2024-03-31T00:00:00",
                    "created_at": "2024-01-01T00:00:00"
                }
            ]
        }

    @pytest.fixture
    def sample_project_dashboard_response(self):
        """Sample project dashboard response data"""
        project_id = uuid4()
        return {
            "project": {
                "id": str(project_id),
                "name": "Mobile App Design",
                "status": "in_progress",
                "budget": 35000.0,
                "start_date": "2024-02-01T00:00:00",
                "end_date": "2024-05-31T00:00:00",
                "created_at": "2024-02-01T00:00:00"
            },
            "kpis": [
                {"title": "Total Deliverables", "value": 4, "icon": "📦", "color": "blue"},
                {"title": "Completed Deliverables", "value": 2, "icon": "✅", "color": "green"},
                {"title": "Pending Deliverables", "value": 2, "icon": "⏳", "color": "orange"},
                {"title": "Project Tasks", "value": 15, "icon": "📋", "color": "purple"}
            ],
            "timeline": [
                {
                    "date": "2024-03-15",
                    "event_type": "deliverable_due",
                    "project_name": "Mobile App Design",
                    "description": "Wireframes due"
                }
            ],
            "recent_comments": [
                {
                    "id": str(uuid4()),
                    "comment_text": "The wireframes look excellent!",
                    "created_at": "2024-01-12T14:20:00",
                    "project_name": "Mobile App Design",
                    "deliverable_name": "wireframes",
                    "project_id": str(project_id),
                    "deliverable_id": str(uuid4()),
                    "coordinates": None,
                    "timestamp": None
                }
            ]
        }

    @pytest.mark.asyncio
    async def test_get_dashboard_success(self, client, mock_auth_context, sample_dashboard_response):
        """Test successful dashboard data retrieval"""
        with patch("src.api.dashboard.controllers.get_current_business", return_value=mock_auth_context):
            with patch("src.api.dashboard.controllers.DashboardService") as mock_service:
                mock_service_instance = AsyncMock()
                mock_service.return_value = mock_service_instance
                mock_service_instance.get_dashboard_data.return_value = AsyncMock()
                mock_service_instance.get_dashboard_data.return_value.__dict__.update(sample_dashboard_response)

                response = await client.get("/api/v1/dashboard")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert "kpis" in data
                assert "timeline" in data
                assert "recent_comments" in data
                assert "projects" in data
                assert len(data["kpis"]) == 4
                assert data["kpis"][0]["title"] == "Active Projects"

    @pytest.mark.asyncio
    async def test_get_dashboard_unauthorized(self, client):
        """Test dashboard access without authentication"""
        response = await client.get("/api/v1/dashboard")
        
        # Should return 401 or redirect to authentication
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    @pytest.mark.asyncio
    async def test_get_project_dashboard_success(self, client, mock_auth_context, sample_project_dashboard_response):
        """Test successful project dashboard data retrieval"""
        project_id = str(uuid4())
        
        with patch("src.api.dashboard.controllers.get_current_business", return_value=mock_auth_context):
            with patch("src.api.dashboard.controllers.DashboardService") as mock_service:
                mock_service_instance = AsyncMock()
                mock_service.return_value = mock_service_instance
                mock_service_instance.get_project_dashboard_data.return_value = AsyncMock()
                mock_service_instance.get_project_dashboard_data.return_value.__dict__.update(sample_project_dashboard_response)

                response = await client.get(f"/api/v1/dashboard/projects/{project_id}")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert "project" in data
                assert "kpis" in data
                assert "timeline" in data
                assert "recent_comments" in data
                assert len(data["kpis"]) == 4

    @pytest.mark.asyncio
    async def test_get_project_dashboard_not_found(self, client, mock_auth_context):
        """Test project dashboard when project doesn't exist"""
        project_id = str(uuid4())
        
        with patch("src.api.dashboard.controllers.get_current_business", return_value=mock_auth_context):
            with patch("src.api.dashboard.controllers.DashboardService") as mock_service:
                mock_service_instance = AsyncMock()
                mock_service.return_value = mock_service_instance
                mock_service_instance.get_project_dashboard_data.side_effect = ValueError(f"Project {project_id} not found or not accessible")

                response = await client.get(f"/api/v1/dashboard/projects/{project_id}")

                assert response.status_code == status.HTTP_404_NOT_FOUND
                data = response.json()
                assert "detail" in data
                assert "not found" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_project_dashboard_invalid_uuid(self, client, mock_auth_context):
        """Test project dashboard with invalid UUID"""
        invalid_project_id = "invalid-uuid"
        
        with patch("src.api.dashboard.controllers.get_current_business", return_value=mock_auth_context):
            response = await client.get(f"/api/v1/dashboard/projects/{invalid_project_id}")

            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_get_recent_comments_success(self, client, mock_auth_context):
        """Test successful recent comments retrieval"""
        sample_comments = [
            {
                "id": str(uuid4()),
                "comment_text": "Great work on the design!",
                "created_at": "2024-01-10T10:30:00",
                "project_name": "Website Redesign",
                "deliverable_name": "design - homepage",
                "project_id": str(uuid4()),
                "deliverable_id": str(uuid4()),
                "coordinates": None,
                "timestamp": None
            },
            {
                "id": str(uuid4()),
                "comment_text": "Can we adjust the color palette?",
                "created_at": "2024-01-09T15:45:00",
                "project_name": "Mobile App",
                "deliverable_name": "design - mockup",
                "project_id": str(uuid4()),
                "deliverable_id": str(uuid4()),
                "coordinates": None,
                "timestamp": None
            }
        ]
        
        with patch("src.api.dashboard.controllers.get_current_business", return_value=mock_auth_context):
            with patch("src.api.dashboard.controllers.DashboardService") as mock_service:
                mock_service_instance = AsyncMock()
                mock_service.return_value = mock_service_instance
                mock_service_instance.get_recent_comments_across_projects.return_value = [
                    AsyncMock(**comment) for comment in sample_comments
                ]

                response = await client.get("/api/v1/dashboard/recent-comments")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert len(data) == 2
                assert data[0]["comment_text"] == "Great work on the design!"
                assert data[1]["comment_text"] == "Can we adjust the color palette?"

    @pytest.mark.asyncio
    async def test_get_recent_comments_with_limit(self, client, mock_auth_context):
        """Test recent comments with limit parameter"""
        sample_comments = [
            {
                "id": str(uuid4()),
                "comment_text": f"Comment {i}",
                "created_at": f"2024-01-{10+i:02d}T10:30:00",
                "project_name": "Test Project",
                "deliverable_name": "test deliverable",
                "project_id": str(uuid4()),
                "deliverable_id": str(uuid4()),
                "coordinates": None,
                "timestamp": None
            }
            for i in range(10)
        ]
        
        with patch("src.api.dashboard.controllers.get_current_business", return_value=mock_auth_context):
            with patch("src.api.dashboard.controllers.DashboardService") as mock_service:
                mock_service_instance = AsyncMock()
                mock_service.return_value = mock_service_instance
                # Return only the first 5 comments when limit=5
                mock_service_instance.get_recent_comments_across_projects.return_value = [
                    AsyncMock(**comment) for comment in sample_comments[:5]
                ]

                response = await client.get("/api/v1/dashboard/recent-comments?limit=5")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert len(data) == 5

    @pytest.mark.asyncio
    async def test_dashboard_service_error_handling(self, client, mock_auth_context):
        """Test dashboard API error handling"""
        with patch("src.api.dashboard.controllers.get_current_business", return_value=mock_auth_context):
            with patch("src.api.dashboard.controllers.DashboardService") as mock_service:
                mock_service_instance = AsyncMock()
                mock_service.return_value = mock_service_instance
                mock_service_instance.get_dashboard_data.side_effect = Exception("Database connection error")

                response = await client.get("/api/v1/dashboard")

                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
                data = response.json()
                assert "detail" in data

    @pytest.mark.asyncio
    async def test_recent_comments_service_error_handling(self, client, mock_auth_context):
        """Test recent comments API error handling"""
        with patch("src.api.dashboard.controllers.get_current_business", return_value=mock_auth_context):
            with patch("src.api.dashboard.controllers.DashboardService") as mock_service:
                mock_service_instance = AsyncMock()
                mock_service.return_value = mock_service_instance
                mock_service_instance.get_recent_comments_across_projects.side_effect = Exception("Query failed")

                response = await client.get("/api/v1/dashboard/recent-comments")

                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
                data = response.json()
                assert "detail" in data

    @pytest.mark.asyncio
    async def test_dashboard_endpoints_security(self, client):
        """Test that all dashboard endpoints require authentication"""
        endpoints = [
            "/api/v1/dashboard",
            f"/api/v1/dashboard/projects/{uuid4()}",
            "/api/v1/dashboard/recent-comments"
        ]
        
        for endpoint in endpoints:
            response = await client.get(endpoint)
            # Should require authentication
            assert response.status_code in [
                status.HTTP_401_UNAUTHORIZED, 
                status.HTTP_403_FORBIDDEN
            ], f"Endpoint {endpoint} should require authentication"

    @pytest.mark.asyncio
    async def test_dashboard_data_structure_validation(self, client, mock_auth_context, sample_dashboard_response):
        """Test that dashboard API returns correctly structured data"""
        with patch("src.api.dashboard.controllers.get_current_business", return_value=mock_auth_context):
            with patch("src.api.dashboard.controllers.DashboardService") as mock_service:
                mock_service_instance = AsyncMock()
                mock_service.return_value = mock_service_instance
                mock_service_instance.get_dashboard_data.return_value = AsyncMock()
                mock_service_instance.get_dashboard_data.return_value.__dict__.update(sample_dashboard_response)

                response = await client.get("/api/v1/dashboard")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                
                # Validate KPI structure
                for kpi in data["kpis"]:
                    assert "title" in kpi
                    assert "value" in kpi
                    assert "icon" in kpi
                    assert "color" in kpi
                    assert isinstance(kpi["value"], (int, float))
                
                # Validate timeline structure
                for timeline_item in data["timeline"]:
                    assert "date" in timeline_item
                    assert "event_type" in timeline_item
                    assert "project_name" in timeline_item
                    assert "description" in timeline_item
                
                # Validate recent comments structure
                for comment in data["recent_comments"]:
                    assert "id" in comment
                    assert "comment_text" in comment
                    assert "created_at" in comment
                    assert "project_name" in comment
                    assert "deliverable_name" in comment
                    assert "project_id" in comment
                    assert "deliverable_id" in comment
                
                # Validate projects structure
                for project in data["projects"]:
                    assert "id" in project
                    assert "name" in project
                    assert "status" in project
                    assert "budget" in project
                    assert isinstance(project["budget"], (int, float)) 