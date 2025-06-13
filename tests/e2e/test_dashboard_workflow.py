# tests/e2e/test_dashboard_workflow.py

import pytest
from httpx import AsyncClient
from fastapi import status
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import patch

from src.main import app
from src.models.project import Project, ProjectStatus
from src.models.deliverable import Deliverable
from src.models.client_feedback import ClientFeedback
from src.models.review_item import ReviewItem
from src.models.internal_task import InternalTask, TaskStatus


class TestDashboardWorkflowE2E:
    """End-to-end tests for complete dashboard workflow"""

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
            "permissions": ["read", "write", "admin"]
        }

    @pytest.fixture
    def complete_business_data(self):
        """Complete business data for testing"""
        business_id = 1
        
        # Projects
        project1_id = uuid4()
        project2_id = uuid4()
        project3_id = uuid4()
        
        projects = [
            {
                "id": project1_id,
                "name": "E-commerce Website",
                "status": ProjectStatus.IN_PROGRESS,
                "business_id": business_id,
                "budget": 50000.0,
                "start_date": datetime.now() - timedelta(days=30),
                "end_date": datetime.now() + timedelta(days=60),
                "created_at": datetime.now() - timedelta(days=30)
            },
            {
                "id": project2_id,
                "name": "Mobile App",
                "status": ProjectStatus.COMPLETED,
                "business_id": business_id,
                "budget": 75000.0,
                "start_date": datetime.now() - timedelta(days=90),
                "end_date": datetime.now() - timedelta(days=10),
                "created_at": datetime.now() - timedelta(days=90)
            },
            {
                "id": project3_id,
                "name": "Brand Identity",
                "status": ProjectStatus.PLANNING,
                "business_id": business_id,
                "budget": 25000.0,
                "start_date": datetime.now() + timedelta(days=15),
                "end_date": datetime.now() + timedelta(days=75),
                "created_at": datetime.now() - timedelta(days=5)
            }
        ]
        
        # Deliverables
        deliverable1_id = uuid4()
        deliverable2_id = uuid4()
        deliverable3_id = uuid4()
        
        deliverables = [
            {
                "id": deliverable1_id,
                "project_id": project1_id,
                "deliverable_type": "design",
                "deliverable_sub_type": "wireframes",
                "current_status": "completed",
                "tentative_timeline_days": 14,
                "created_at": datetime.now() - timedelta(days=25)
            },
            {
                "id": deliverable2_id,
                "project_id": project1_id,
                "deliverable_type": "design",
                "deliverable_sub_type": "mockups",
                "current_status": "pending",
                "tentative_timeline_days": 21,
                "created_at": datetime.now() - timedelta(days=20)
            },
            {
                "id": deliverable3_id,
                "project_id": project2_id,
                "deliverable_type": "development",
                "deliverable_sub_type": "backend",
                "current_status": "completed",
                "tentative_timeline_days": 45,
                "created_at": datetime.now() - timedelta(days=60)
            }
        ]
        
        # Review Items
        review_item1_id = uuid4()
        review_item2_id = uuid4()
        
        review_items = [
            {
                "id": review_item1_id,
                "deliverable_id": deliverable1_id,
                "media_url": "https://example.com/wireframes.pdf",
                "media_type": "document",
                "created_at": datetime.now() - timedelta(days=20)
            },
            {
                "id": review_item2_id,
                "deliverable_id": deliverable2_id,
                "media_url": "https://example.com/mockups.png",
                "media_type": "image",
                "created_at": datetime.now() - timedelta(days=15)
            }
        ]
        
        # Client Feedback
        feedback_items = [
            {
                "id": uuid4(),
                "review_item_id": review_item1_id,
                "comment_text": "The wireframes look great! Love the user flow.",
                "context_coordinates": None,
                "timestamp_seconds": None,
                "created_at": datetime.now() - timedelta(days=18)
            },
            {
                "id": uuid4(),
                "review_item_id": review_item2_id,
                "comment_text": "Can we adjust the color scheme to be more vibrant?",
                "context_coordinates": {"x": 150, "y": 200},
                "timestamp_seconds": None,
                "created_at": datetime.now() - timedelta(days=12)
            },
            {
                "id": uuid4(),
                "review_item_id": review_item1_id,
                "comment_text": "The navigation structure needs some refinement.",
                "context_coordinates": None,
                "timestamp_seconds": None,
                "created_at": datetime.now() - timedelta(days=5)
            }
        ]
        
        # Internal Tasks
        tasks = [
            {
                "id": uuid4(),
                "project_id": project1_id,
                "title": "Complete wireframe revisions",
                "status": TaskStatus.COMPLETED,
                "assigned_to": "designer1",
                "created_at": datetime.now() - timedelta(days=20)
            },
            {
                "id": uuid4(),
                "project_id": project1_id,
                "title": "Design system documentation",
                "status": TaskStatus.IN_PROGRESS,
                "assigned_to": "designer2",
                "created_at": datetime.now() - timedelta(days=15)
            },
            {
                "id": uuid4(),
                "project_id": project2_id,
                "title": "API integration testing",
                "status": TaskStatus.COMPLETED,
                "assigned_to": "developer1",
                "created_at": datetime.now() - timedelta(days=30)
            },
            {
                "id": uuid4(),
                "project_id": project3_id,
                "title": "Brand research and analysis",
                "status": TaskStatus.TODO,
                "assigned_to": "strategist1",
                "created_at": datetime.now() - timedelta(days=3)
            }
        ]
        
        return {
            "projects": projects,
            "deliverables": deliverables,
            "review_items": review_items,
            "feedback_items": feedback_items,
            "tasks": tasks,
            "business_id": business_id
        }

    @pytest.mark.asyncio
    async def test_complete_dashboard_workflow(self, client, mock_auth_context):
        """Test complete dashboard workflow from main dashboard to project details"""
        
        project_id = uuid4()
        
        # Mock database responses for dashboard data
        with patch("src.api.dashboard.controllers.get_current_business", return_value=mock_auth_context):
            with patch("src.services.dashboard_service.DashboardService") as mock_service_class:
                
                # Mock service instance
                mock_service = mock_service_class.return_value
                
                # Mock main dashboard data
                mock_service.get_dashboard_data.return_value.kpis = [
                    {"title": "Active Projects", "value": 2, "icon": "📊", "color": "blue"},
                    {"title": "Pending Reviews", "value": 1, "icon": "⏳", "color": "orange"},
                    {"title": "Completed Tasks", "value": 2, "icon": "✅", "color": "green"},
                    {"title": "Total Deliverables", "value": 3, "icon": "📦", "color": "purple"}
                ]
                
                mock_service.get_dashboard_data.return_value.projects = [
                    {
                        "id": str(project_id),
                        "name": "E-commerce Website",
                        "status": "in_progress",
                        "budget": 50000.0,
                        "start_date": datetime.now() - timedelta(days=30),
                        "end_date": datetime.now() + timedelta(days=60),
                        "created_at": datetime.now() - timedelta(days=30)
                    }
                ]
                
                mock_service.get_dashboard_data.return_value.recent_comments = [
                    {
                        "id": str(uuid4()),
                        "comment_text": "The navigation structure needs some refinement.",
                        "created_at": (datetime.now() - timedelta(days=5)).isoformat(),
                        "project_name": "E-commerce Website",
                        "deliverable_name": "design - wireframes",
                        "project_id": str(project_id),
                        "deliverable_id": str(uuid4()),
                        "coordinates": None,
                        "timestamp": None
                    }
                ]
                
                mock_service.get_dashboard_data.return_value.timeline = [
                    {
                        "date": (datetime.now() + timedelta(days=60)).date().isoformat(),
                        "event_type": "project_end",
                        "project_name": "E-commerce Website",
                        "description": "Project completion deadline"
                    }
                ]
                
                # Step 1: Get main dashboard
                dashboard_response = await client.get("/api/v1/dashboard")
                
                assert dashboard_response.status_code == status.HTTP_200_OK
                dashboard_data = dashboard_response.json()
                
                # Verify dashboard structure
                assert "kpis" in dashboard_data
                assert "projects" in dashboard_data
                assert "recent_comments" in dashboard_data
                assert "timeline" in dashboard_data
                
                # Verify KPI data
                assert len(dashboard_data["kpis"]) == 4
                assert dashboard_data["kpis"][0]["title"] == "Active Projects"
                assert dashboard_data["kpis"][0]["value"] == 2
                
                # Verify project data
                assert len(dashboard_data["projects"]) == 1
                assert dashboard_data["projects"][0]["name"] == "E-commerce Website"
                assert dashboard_data["projects"][0]["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_dashboard_performance_with_large_dataset(self, client, mock_auth_context):
        """Test dashboard performance with large amounts of data"""
        
        # Mock large dataset
        large_kpis = [
            {"title": f"KPI {i}", "value": i * 100, "icon": "📊", "color": "blue"}
            for i in range(10)
        ]
        
        large_comments = [
            {
                "id": str(uuid4()),
                "comment_text": f"Comment {i} with some detailed feedback",
                "created_at": (datetime.now() - timedelta(days=i)).isoformat(),
                "project_name": f"Project {i}",
                "deliverable_name": f"deliverable-{i}",
                "project_id": str(uuid4()),
                "deliverable_id": str(uuid4()),
                "coordinates": None,
                "timestamp": None
            }
            for i in range(50)
        ]
        
        large_projects = [
            {
                "id": str(uuid4()),
                "name": f"Project {i}",
                "status": "in_progress",
                "budget": float(i * 10000),
                "start_date": (datetime.now() - timedelta(days=i*30)).isoformat(),
                "end_date": (datetime.now() + timedelta(days=i*30)).isoformat(),
                "created_at": (datetime.now() - timedelta(days=i*30)).isoformat()
            }
            for i in range(25)
        ]
        
        with patch("src.api.dashboard.controllers.get_current_business", return_value=mock_auth_context):
            with patch("src.services.dashboard_service.DashboardService") as mock_service_class:
                
                mock_service = mock_service_class.return_value
                mock_service.get_dashboard_data.return_value.kpis = large_kpis
                mock_service.get_dashboard_data.return_value.recent_comments = large_comments
                mock_service.get_dashboard_data.return_value.projects = large_projects
                mock_service.get_dashboard_data.return_value.timeline = []
                
                start_time = datetime.now()
                response = await client.get("/api/v1/dashboard")
                end_time = datetime.now()
                
                # Response should be successful
                assert response.status_code == status.HTTP_200_OK
                
                # Response time should be reasonable (less than 2 seconds)
                response_time = (end_time - start_time).total_seconds()
                assert response_time < 2.0, f"Dashboard response too slow: {response_time}s"
                
                # Data should be complete
                data = response.json()
                assert len(data["kpis"]) == 10
                assert len(data["recent_comments"]) == 50
                assert len(data["projects"]) == 25

    @pytest.mark.asyncio
    async def test_dashboard_error_recovery(self, client, mock_auth_context):
        """Test dashboard error handling and recovery"""
        
        with patch("src.api.dashboard.controllers.get_current_business", return_value=mock_auth_context):
            with patch("src.services.dashboard_service.DashboardService") as mock_service_class:
                
                # Test database connection error
                mock_service = mock_service_class.return_value
                mock_service.get_dashboard_data.side_effect = Exception("Database connection failed")
                
                response = await client.get("/api/v1/dashboard")
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
                
                # Test project not found error
                mock_service.get_project_dashboard_data.side_effect = ValueError("Project not found")
                
                response = await client.get(f"/api/v1/dashboard/projects/{uuid4()}")
                assert response.status_code == status.HTTP_404_NOT_FOUND
                
                # Test recent comments service error
                mock_service.get_recent_comments_across_projects.side_effect = Exception("Query timeout")
                
                response = await client.get("/api/v1/dashboard/recent-comments")
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_dashboard_data_consistency(self, client, mock_auth_context, complete_business_data):
        """Test that dashboard data is consistent across different endpoints"""
        
        with patch("src.api.dashboard.controllers.get_current_business", return_value=mock_auth_context):
            with patch("src.services.dashboard_service.DashboardService") as mock_service_class:
                
                mock_service = mock_service_class.return_value
                project_id = complete_business_data["projects"][0]["id"]
                
                # Set up consistent mock data
                main_dashboard_projects = [
                    {
                        "id": str(project_id),
                        "name": "E-commerce Website",
                        "status": "in_progress",
                        "budget": 50000.0,
                        "start_date": complete_business_data["projects"][0]["start_date"],
                        "end_date": complete_business_data["projects"][0]["end_date"],
                        "created_at": complete_business_data["projects"][0]["created_at"]
                    }
                ]
                
                # Mock main dashboard
                mock_service.get_dashboard_data.return_value.projects = main_dashboard_projects
                mock_service.get_dashboard_data.return_value.kpis = []
                mock_service.get_dashboard_data.return_value.recent_comments = []
                mock_service.get_dashboard_data.return_value.timeline = []
                
                # Mock project dashboard
                mock_service.get_project_dashboard_data.return_value.project = main_dashboard_projects[0]
                mock_service.get_project_dashboard_data.return_value.kpis = []
                mock_service.get_project_dashboard_data.return_value.recent_comments = []
                mock_service.get_project_dashboard_data.return_value.timeline = []
                
                # Get main dashboard
                main_response = await client.get("/api/v1/dashboard")
                main_data = main_response.json()
                
                # Get project dashboard
                project_response = await client.get(f"/api/v1/dashboard/projects/{project_id}")
                project_data = project_response.json()
                
                # Verify project data consistency
                main_project = main_data["projects"][0]
                project_detail = project_data["project"]
                
                assert main_project["id"] == project_detail["id"]
                assert main_project["name"] == project_detail["name"]
                assert main_project["status"] == project_detail["status"]
                assert main_project["budget"] == project_detail["budget"] 