"""
End-to-end tests for project output generation.
Tests the automatic generation of project outputs when all review items are approved,
and project completion detection when all deliverables are delivered.
"""

import asyncio
from datetime import date, datetime
import os
import pytest
import tempfile
import json
from uuid import UUID

from fastapi import status
from httpx import AsyncClient

from src.models.deliverable import DeliverableStatus, DeliverableType
from src.models.internal_task import TaskStatus
from src.models.project import ProjectStatus
from src.models.review_item import ReviewStatus, ReviewItemType


@pytest.mark.e2e
class TestProjectOutputGeneration:
    """End-to-end tests for project output generation."""

    @pytest.mark.asyncio
    async def test_automatic_output_generation(self, test_client, auth_headers):
        """Test automatic project output generation when all review items are approved."""

        # 1. Create Project
        project_data = {
            "name": "Output Generation Test Project",
            "budget": 150000.00,
            "start_date": date.today().isoformat(),
            "end_date": date.today().replace(year=date.today().year + 1).isoformat(),
        }

        project_response = await test_client.post(
            "/api/v1/projects/", json=project_data, headers=auth_headers
        )

        assert project_response.status_code == status.HTTP_201_CREATED
        project = project_response.json()
        project_id = project["id"]

        # 2. Create Multiple Deliverables
        deliverable_types = [
            (DeliverableType.RENDERED_IMAGES.value, "3D Renders"),
            (DeliverableType.TECHNICAL_RENDERS.value, "Technical Diagrams"),
            (DeliverableType.DOCUMENTATION.value, "User Documentation")
        ]
        
        deliverable_ids = []
        
        for d_type, d_subtype in deliverable_types:
            deliverable_data = {
                "deliverable_type": d_type,
                "deliverable_sub_type": d_subtype,
                "tentative_timeline_days": 15,
                "project_id": project_id,
            }

            deliverable_response = await test_client.post(
                "/api/v1/deliverables/", json=deliverable_data, headers=auth_headers
            )

            assert deliverable_response.status_code == status.HTTP_201_CREATED
            deliverable_ids.append(deliverable_response.json()["id"])

        # 3. Create Tasks for Each Deliverable
        task_ids = []
        
        for i, deliverable_id in enumerate(deliverable_ids):
            task_data = {
                "title": f"Create {deliverable_types[i][1]} files",
                "description": f"Create files for {deliverable_types[i][1]}",
                "deliverable_id": deliverable_id,
                "estimated_hours": 10.0,
                "priority": "high",
            }

            task_response = await test_client.post(
                "/api/v1/internal-tasks/", json=task_data, headers=auth_headers
            )

            assert task_response.status_code == status.HTTP_201_CREATED
            task_ids.append(task_response.json()["id"])

        # 4. Complete Tasks with Different File Types
        file_types = [
            ("image/jpeg", ".jpg", "FINAL_RENDER"),
            ("image/png", ".png", "TECHNICAL_DIAGRAM"),
            ("application/pdf", ".pdf", "DOCUMENTATION")
        ]
        
        for i, task_id in enumerate(task_ids):
            # Assign and start task
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
                "notes": f"Working on {deliverable_types[i][1]}",
            }

            await test_client.patch(
                f"/api/v1/internal-tasks/{task_id}/progress",
                json=progress_data,
                headers=auth_headers,
            )
            
            # Create multiple files for each task
            file_count = 3
            file_paths = []
            
            for j in range(file_count):
                suffix = file_types[i][1]
                content = f"Test content for {deliverable_types[i][1]} file {j}".encode()
                
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
                    temp_file.write(content)
                    file_paths.append(temp_file.name)
            
            try:
                # Complete task with files
                for file_path in file_paths:
                    with open(file_path, "rb") as file:
                        files = {"files": (os.path.basename(file_path), file, file_types[i][0])}
                        
                        # Add review item type metadata
                        metadata = {
                            "review_item_type": file_types[i][2]
                        }
                        
                        complete_response = await test_client.post(
                            f"/api/v1/internal-tasks/{task_id}/complete-with-files",
                            files=files,
                            data={"metadata": json.dumps(metadata)},
                            headers=auth_headers,
                        )
                        assert complete_response.status_code == status.HTTP_200_OK
            finally:
                for file_path in file_paths:
                    if os.path.exists(file_path):
                        os.unlink(file_path)

        # 5. Wait for Review Items to be Created
        await asyncio.sleep(2)

        # 6. Get and Approve Review Items for Each Deliverable
        for deliverable_id in deliverable_ids:
            review_items_response = await test_client.get(
                f"/api/v1/deliverables/{deliverable_id}/review-items", headers=auth_headers
            )
            assert review_items_response.status_code == status.HTTP_200_OK
            review_items = review_items_response.json()
            assert len(review_items) > 0
            
            # Approve all review items
            for review_item in review_items:
                feedback_data = {
                    "status": ReviewStatus.APPROVED.value,
                    "comments": "Approved for final delivery",
                    "rating": 5,
                }

                feedback_response = await test_client.post(
                    f"/api/v1/review-items/{review_item['id']}/feedback",
                    json=feedback_data,
                    headers=auth_headers,
                )
                assert feedback_response.status_code == status.HTTP_201_CREATED

        # 7. Wait for Automatic Project Output Generation
        await asyncio.sleep(3)

        # 8. Verify Project Outputs were Created for Each Deliverable
        for deliverable_id in deliverable_ids:
            outputs_response = await test_client.get(
                f"/api/v1/deliverables/{deliverable_id}/outputs", headers=auth_headers
            )
            assert outputs_response.status_code == status.HTTP_200_OK
            outputs = outputs_response.json()
            assert len(outputs) > 0
            
            # Verify output has a valid URL
            assert outputs[0]["output_url"] is not None
            assert "https://" in outputs[0]["output_url"]
            
            # Verify deliverable status is updated to DELIVERED
            deliverable_response = await test_client.get(
                f"/api/v1/deliverables/{deliverable_id}", headers=auth_headers
            )
            assert deliverable_response.status_code == status.HTTP_200_OK
            updated_deliverable = deliverable_response.json()
            assert updated_deliverable["current_status"] == DeliverableStatus.DELIVERED.value

        # 9. Verify Project Status is Updated to COMPLETED
        await asyncio.sleep(2)  # Wait for project completion detection
        
        project_response = await test_client.get(
            f"/api/v1/projects/{project_id}", headers=auth_headers
        )
        assert project_response.status_code == status.HTTP_200_OK
        updated_project = project_response.json()
        assert updated_project["status"] == ProjectStatus.COMPLETED.value

        # 10. Request Project Compilation and Verify
        compilation_response = await test_client.post(
            f"/api/v1/projects/{project_id}/compile",
            headers=auth_headers,
        )
        assert compilation_response.status_code == status.HTTP_200_OK
        compilation = compilation_response.json()
        assert "compilation_url" in compilation
        assert compilation["compilation_started"] is True

    @pytest.mark.asyncio
    async def test_project_output_with_file_versioning(self, test_client, auth_headers):
        """Test project output generation with file versioning through review cycles."""

        # 1. Create Project and Deliverable
        project_data = {
            "name": "File Version Test Project",
            "budget": 100000.00,
            "start_date": date.today().isoformat(),
            "end_date": date.today().replace(year=date.today().year + 1).isoformat(),
        }

        project_response = await test_client.post(
            "/api/v1/projects/", json=project_data, headers=auth_headers
        )
        project_id = project_response.json()["id"]

        deliverable_data = {
            "deliverable_type": DeliverableType.RENDERED_IMAGES.value,
            "deliverable_sub_type": "Version Test Deliverable",
            "tentative_timeline_days": 10,
            "project_id": project_id,
        }

        deliverable_response = await test_client.post(
            "/api/v1/deliverables/", json=deliverable_data, headers=auth_headers
        )
        deliverable_id = deliverable_response.json()["id"]

        # 2. Create Task
        task_data = {
            "title": "Create design files",
            "description": "Create design files for version testing",
            "deliverable_id": deliverable_id,
            "estimated_hours": 8.0,
            "priority": "high",
        }

        task_response = await test_client.post(
            "/api/v1/internal-tasks/", json=task_data, headers=auth_headers
        )
        task_id = task_response.json()["id"]

        # 3. Complete Task with Initial Files
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            temp_file.write(b"Initial version content")
            file_path = temp_file.name

        try:
            with open(file_path, "rb") as file:
                files = {"files": (os.path.basename(file_path), file, "image/jpeg")}
                metadata = {"review_item_type": "FINAL_RENDER"}
                
                complete_response = await test_client.post(
                    f"/api/v1/internal-tasks/{task_id}/complete-with-files",
                    files=files,
                    data={"metadata": json.dumps(metadata)},
                    headers=auth_headers,
                )
                assert complete_response.status_code == status.HTTP_200_OK
        finally:
            os.unlink(file_path)

        # 4. Wait for Review Items and Reject Initial Version
        await asyncio.sleep(1)
        
        review_items_response = await test_client.get(
            f"/api/v1/deliverables/{deliverable_id}/review-items", headers=auth_headers
        )
        review_items = review_items_response.json()
        assert len(review_items) > 0
        
        review_item_id = review_items[0]["id"]
        
        # Reject the initial version
        feedback_data = {
            "status": ReviewStatus.REJECTED.value,
            "comments": "Needs revision - please improve quality",
            "rating": 2,
        }

        feedback_response = await test_client.post(
            f"/api/v1/review-items/{review_item_id}/feedback",
            json=feedback_data,
            headers=auth_headers,
        )
        assert feedback_response.status_code == status.HTTP_201_CREATED

        # 5. Wait for Rework Task Creation
        await asyncio.sleep(2)
        
        # Get rework tasks
        tasks_response = await test_client.get(
            f"/api/v1/deliverables/{deliverable_id}/tasks", headers=auth_headers
        )
        tasks = tasks_response.json()
        
        # Find the rework task (should be the most recent one)
        rework_task = None
        for task in tasks:
            if "rework" in task["title"].lower():
                rework_task = task
                break
                
        assert rework_task is not None
        rework_task_id = rework_task["id"]

        # 6. Complete Rework Task with Improved File
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            temp_file.write(b"Improved version content after feedback")
            file_path = temp_file.name

        try:
            with open(file_path, "rb") as file:
                files = {"files": (os.path.basename(file_path), file, "image/jpeg")}
                metadata = {"review_item_type": "FINAL_RENDER"}
                
                complete_response = await test_client.post(
                    f"/api/v1/internal-tasks/{rework_task_id}/complete-with-files",
                    files=files,
                    data={"metadata": json.dumps(metadata)},
                    headers=auth_headers,
                )
                assert complete_response.status_code == status.HTTP_200_OK
        finally:
            os.unlink(file_path)

        # 7. Wait for New Review Items and Approve
        await asyncio.sleep(1)
        
        review_items_response = await test_client.get(
            f"/api/v1/deliverables/{deliverable_id}/review-items", headers=auth_headers
        )
        review_items = review_items_response.json()
        
        # Find the latest review item (should be from the rework task)
        latest_review_item = None
        for item in review_items:
            if latest_review_item is None or item["created_at"] > latest_review_item["created_at"]:
                latest_review_item = item
                
        assert latest_review_item is not None
        
        # Approve the revised version
        feedback_data = {
            "status": ReviewStatus.APPROVED.value,
            "comments": "Much better, approved!",
            "rating": 5,
        }

        feedback_response = await test_client.post(
            f"/api/v1/review-items/{latest_review_item['id']}/feedback",
            json=feedback_data,
            headers=auth_headers,
        )
        assert feedback_response.status_code == status.HTTP_201_CREATED

        # 8. Wait for Project Output Generation
        await asyncio.sleep(2)
        
        # 9. Verify Project Output was Created with Final Version
        outputs_response = await test_client.get(
            f"/api/v1/deliverables/{deliverable_id}/outputs", headers=auth_headers
        )
        assert outputs_response.status_code == status.HTTP_200_OK
        outputs = outputs_response.json()
        assert len(outputs) > 0
        
        # 10. Verify Deliverable Status is DELIVERED
        deliverable_response = await test_client.get(
            f"/api/v1/deliverables/{deliverable_id}", headers=auth_headers
        )
        updated_deliverable = deliverable_response.json()
        assert updated_deliverable["current_status"] == DeliverableStatus.DELIVERED.value