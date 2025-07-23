"""
End-to-end tests for file-driven project lifecycle.
Tests the complete project lifecycle with file uploads, reviews, and automatic project output generation.
"""

import asyncio
from datetime import date, datetime
import os
import pytest
import tempfile
from uuid import UUID

from fastapi import status
from httpx import AsyncClient

from src.models.deliverable import DeliverableStatus, DeliverableType
from src.models.internal_task import TaskStatus
from src.models.project import ProjectStatus
from src.models.review_item import ReviewStatus


@pytest.mark.e2e
class TestFileBasedProjectLifecycle:
    """End-to-end tests for file-based project lifecycle."""

    @pytest.mark.asyncio
    async def test_file_driven_project_lifecycle(self, test_client, auth_headers):
        """Test complete project lifecycle with file uploads, reviews, and automatic output generation."""

        # 1. Create Project
        project_data = {
            "name": "File-Driven Test Project",
            "budget": 120000.00,
            "start_date": date.today().isoformat(),
            "end_date": date.today().replace(year=date.today().year + 1).isoformat(),
        }

        project_response = await test_client.post(
            "/api/v1/projects/", json=project_data, headers=auth_headers
        )

        assert project_response.status_code == status.HTTP_201_CREATED
        project = project_response.json()
        project_id = project["id"]

        # 2. Create Deliverable
        deliverable_data = {
            "deliverable_type": DeliverableType.RENDERED_IMAGES.value,
            "deliverable_sub_type": "File-Based Deliverable",
            "tentative_timeline_days": 15,
            "project_id": project_id,
        }

        deliverable_response = await test_client.post(
            "/api/v1/deliverables/", json=deliverable_data, headers=auth_headers
        )

        assert deliverable_response.status_code == status.HTTP_201_CREATED
        deliverable = deliverable_response.json()
        deliverable_id = deliverable["id"]

        # 3. Create Requirement
        requirement_data = {
            "title": "File Upload Requirement",
            "description": "Requirement with file attachments",
            "category": "functional",
            "priority": "high",
            "project_id": project_id,
        }

        requirement_response = await test_client.post(
            "/api/v1/requirements/", json=requirement_data, headers=auth_headers
        )

        assert requirement_response.status_code == status.HTTP_201_CREATED
        requirement = requirement_response.json()
        requirement_id = requirement["id"]

        # 4. Upload Requirement Files
        # Create a temporary test file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
            temp_file.write(b"Test requirement file content")
            temp_file_path = temp_file.name

        try:
            with open(temp_file_path, "rb") as file:
                files = {"files": (os.path.basename(temp_file_path), file, "application/pdf")}
                req_file_response = await test_client.post(
                    f"/api/v1/requirements/{requirement_id}/files",
                    files=files,
                    headers=auth_headers,
                )
                assert req_file_response.status_code == status.HTTP_201_CREATED
        finally:
            os.unlink(temp_file_path)

        # 5. Create Task for Deliverable
        task_data = {
            "title": "Create design files",
            "description": "Create design files for the deliverable",
            "deliverable_id": deliverable_id,
            "estimated_hours": 10.0,
            "priority": "high",
        }

        task_response = await test_client.post(
            "/api/v1/internal-tasks/", json=task_data, headers=auth_headers
        )

        assert task_response.status_code == status.HTTP_201_CREATED
        task = task_response.json()
        task_id = task["id"]

        # 6. Assign and Start Task
        assign_data = {"assigned_to": 1}
        await test_client.patch(
            f"/api/v1/internal-tasks/{task_id}/assign",
            json=assign_data,
            headers=auth_headers,
        )

        progress_data = {
            "status": TaskStatus.IN_PROGRESS.value,
            "progress_percentage": 50,
            "time_spent": 5.0,
            "notes": "Working on design files",
        }

        await test_client.patch(
            f"/api/v1/internal-tasks/{task_id}/progress",
            json=progress_data,
            headers=auth_headers,
        )

        # 7. Complete Task with Files
        # Create temporary test files for task completion
        temp_files = []
        file_paths = []
        for i in range(2):
            temp_file = tempfile.NamedTemporaryFile(suffix=f"_{i}.jpg", delete=False)
            temp_file.write(f"Test design file content {i}".encode())
            temp_file.close()
            temp_files.append(temp_file)
            file_paths.append(temp_file.name)

        try:
            # Complete task with files
            files_dict = {}
            for i, file_path in enumerate(file_paths):
                with open(file_path, "rb") as file:
                    files_dict[f"files"] = (
                        os.path.basename(file_path),
                        file,
                        "image/jpeg",
                    )
                    
                    complete_response = await test_client.post(
                        f"/api/v1/internal-tasks/{task_id}/complete-with-files",
                        files=files_dict,
                        headers=auth_headers,
                    )
                    assert complete_response.status_code == status.HTTP_200_OK
        finally:
            for file_path in file_paths:
                os.unlink(file_path)

        # 8. Wait for Review Items to be Created
        # In a real test, we might need to poll until review items appear
        await asyncio.sleep(1)

        # Get review items for the deliverable
        review_items_response = await test_client.get(
            f"/api/v1/deliverables/{deliverable_id}/review-items", headers=auth_headers
        )
        assert review_items_response.status_code == status.HTTP_200_OK
        review_items = review_items_response.json()
        assert len(review_items) > 0

        # 9. Submit Approval for Review Items
        for review_item in review_items:
            feedback_data = {
                "status": ReviewStatus.APPROVED.value,
                "comments": "Looks great, approved!",
                "rating": 5,
            }

            feedback_response = await test_client.post(
                f"/api/v1/review-items/{review_item['id']}/feedback",
                json=feedback_data,
                headers=auth_headers,
            )
            assert feedback_response.status_code == status.HTTP_201_CREATED

        # 10. Wait for Automatic Project Output Generation
        # In a real test, we might need to poll until project outputs appear
        await asyncio.sleep(2)

        # 11. Verify Project Output was Created
        outputs_response = await test_client.get(
            f"/api/v1/deliverables/{deliverable_id}/outputs", headers=auth_headers
        )
        assert outputs_response.status_code == status.HTTP_200_OK
        outputs = outputs_response.json()
        assert len(outputs) > 0

        # 12. Verify Deliverable Status Updated to DELIVERED
        deliverable_response = await test_client.get(
            f"/api/v1/deliverables/{deliverable_id}", headers=auth_headers
        )
        assert deliverable_response.status_code == status.HTTP_200_OK
        updated_deliverable = deliverable_response.json()
        assert updated_deliverable["current_status"] == DeliverableStatus.DELIVERED.value

        # 13. Create Second Deliverable and Complete It
        deliverable_data2 = {
            "deliverable_type": DeliverableType.TECHNICAL_RENDERS.value,
            "deliverable_sub_type": "Second File-Based Deliverable",
            "tentative_timeline_days": 10,
            "project_id": project_id,
        }

        deliverable_response2 = await test_client.post(
            "/api/v1/deliverables/", json=deliverable_data2, headers=auth_headers
        )
        assert deliverable_response2.status_code == status.HTTP_201_CREATED
        deliverable_id2 = deliverable_response2.json()["id"]

        # Repeat steps 5-11 for second deliverable (simplified)
        task_data2 = {
            "title": "Create technical renders",
            "description": "Create technical renders for the deliverable",
            "deliverable_id": deliverable_id2,
            "estimated_hours": 8.0,
            "priority": "medium",
        }

        task_response2 = await test_client.post(
            "/api/v1/internal-tasks/", json=task_data2, headers=auth_headers
        )
        task_id2 = task_response2.json()["id"]

        # Complete task with file
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            temp_file.write(b"Technical render content")
            temp_file_path = temp_file.name

        try:
            with open(temp_file_path, "rb") as file:
                files = {"files": (os.path.basename(temp_file_path), file, "image/jpeg")}
                await test_client.post(
                    f"/api/v1/internal-tasks/{task_id2}/complete-with-files",
                    files=files,
                    headers=auth_headers,
                )
        finally:
            os.unlink(temp_file_path)

        # Wait for review items
        await asyncio.sleep(1)

        # Get and approve review items
        review_items_response2 = await test_client.get(
            f"/api/v1/deliverables/{deliverable_id2}/review-items", headers=auth_headers
        )
        review_items2 = review_items_response2.json()

        for review_item in review_items2:
            feedback_data = {
                "status": ReviewStatus.APPROVED.value,
                "comments": "Technical renders approved",
                "rating": 4,
            }
            await test_client.post(
                f"/api/v1/review-items/{review_item['id']}/feedback",
                json=feedback_data,
                headers=auth_headers,
            )

        # 14. Wait for Project Completion Detection
        await asyncio.sleep(2)

        # 15. Verify Project Status Updated to COMPLETED
        project_response = await test_client.get(
            f"/api/v1/projects/{project_id}", headers=auth_headers
        )
        assert project_response.status_code == status.HTTP_200_OK
        updated_project = project_response.json()
        assert updated_project["status"] == ProjectStatus.COMPLETED.value

        # 16. Verify Project Compilation
        compilation_response = await test_client.post(
            f"/api/v1/projects/{project_id}/compile",
            headers=auth_headers,
        )
        assert compilation_response.status_code == status.HTTP_200_OK
        compilation = compilation_response.json()
        assert "compilation_url" in compilation