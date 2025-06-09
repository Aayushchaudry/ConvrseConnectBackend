# tests/e2e/test_complete_workflows.py - End-to-end tests for complete workflows

import asyncio
from datetime import date, datetime
from uuid import UUID

import pytest
from fastapi import status
from httpx import AsyncClient

from src.models.deliverable import DeliverableStatus, DeliverableType
from src.models.internal_task import TaskStatus
from src.models.project import ProjectStatus
from src.models.review_item import ReviewStatus


@pytest.mark.e2e
class TestCompleteProjectLifecycle:
    """End-to-end tests for complete project lifecycle."""

    @pytest.mark.asyncio
    async def test_full_project_lifecycle(self, test_client, auth_headers):
        """Test complete project lifecycle from creation to delivery."""

        # 1. Create Project
        project_data = {
            "name": "E2E Test Project",
            "budget": 100000.00,
            "start_date": date.today().isoformat(),
            "end_date": date.today().replace(year=date.today().year + 1).isoformat(),
        }

        project_response = await test_client.post(
            "/api/v1/projects/", json=project_data, headers=auth_headers
        )

        assert project_response.status_code == status.HTTP_201_CREATED
        project = project_response.json()
        project_id = project["id"]

        # Verify project is in INITIATED status
        assert project["status"] == ProjectStatus.INITIATED.value

        # 2. Update Project to INFO_GATHERING
        status_update = {"status": ProjectStatus.INFO_GATHERING.value}

        status_response = await test_client.patch(
            f"/api/v1/projects/{project_id}/status",
            json=status_update,
            headers=auth_headers,
        )

        assert status_response.status_code == status.HTTP_200_OK
        assert status_response.json()["status"] == ProjectStatus.INFO_GATHERING.value

        # 3. Create Requirements
        requirements_data = [
            {
                "title": "User Authentication System",
                "description": "Secure user login and registration",
                "category": "functional",
                "priority": "high",
                "project_id": project_id,
            },
            {
                "title": "Dashboard Interface",
                "description": "Main user dashboard with analytics",
                "category": "functional",
                "priority": "medium",
                "project_id": project_id,
            },
        ]

        created_requirements = []
        for req_data in requirements_data:
            req_response = await test_client.post(
                "/api/v1/requirements/", json=req_data, headers=auth_headers
            )
            assert req_response.status_code == status.HTTP_201_CREATED
            created_requirements.append(req_response.json())

        # 4. Create Deliverables
        deliverables_data = [
            {
                "deliverable_type": DeliverableType.RENDERED_IMAGES.value,
                "deliverable_sub_type": "Interior Design",
                "tentative_timeline_days": 15,
                "project_id": project_id,
            },
            {
                "deliverable_type": DeliverableType.TECHNICAL_RENDERS.value,
                "deliverable_sub_type": "Technical Documentation",
                "tentative_timeline_days": 20,
                "project_id": project_id,
            },
            {
                "deliverable_type": DeliverableType.EXTERIOR_VR_TOUR.value,
                "deliverable_sub_type": "Virtual Reality Experience",
                "tentative_timeline_days": 30,
                "project_id": project_id,
            },
        ]

        created_deliverables = []
        for del_data in deliverables_data:
            del_response = await test_client.post(
                "/api/v1/deliverables/", json=del_data, headers=auth_headers
            )
            assert del_response.status_code == status.HTTP_201_CREATED
            created_deliverables.append(del_response.json())

        # 5. Update Project to IN_PROGRESS
        progress_update = {"status": ProjectStatus.IN_PROGRESS.value}

        progress_response = await test_client.patch(
            f"/api/v1/projects/{project_id}/status",
            json=progress_update,
            headers=auth_headers,
        )

        assert progress_response.status_code == status.HTTP_200_OK
        assert progress_response.json()["status"] == ProjectStatus.IN_PROGRESS.value

        # 6. Create Tasks for each Deliverable
        all_tasks = []
        for deliverable in created_deliverables:
            tasks_data = [
                {
                    "title": f"Task 1 for deliverable {deliverable['id']}",
                    "description": f"First task for deliverable {deliverable['deliverable_sub_type']}",
                    "deliverable_id": deliverable["id"],
                    "estimated_hours": 8.0,
                    "priority": "medium",
                },
                {
                    "title": f"Task 2 for deliverable {deliverable['id']}",
                    "description": f"Second task for deliverable {deliverable['deliverable_sub_type']}",
                    "deliverable_id": deliverable["id"],
                    "estimated_hours": 12.0,
                    "priority": "high",
                },
            ]

            for task_data in tasks_data:
                task_response = await test_client.post(
                    "/api/v1/internal-tasks/", json=task_data, headers=auth_headers
                )
                assert task_response.status_code == status.HTTP_201_CREATED
                all_tasks.append(task_response.json())

        # 7. Assign and Progress Tasks
        for i, task in enumerate(all_tasks[:3]):  # Work on first 3 tasks
            # Assign task
            assign_data = {"assigned_to": 1}
            assign_response = await test_client.patch(
                f"/api/v1/internal-tasks/{task['id']}/assign",
                json=assign_data,
                headers=auth_headers,
            )
            assert assign_response.status_code == status.HTTP_200_OK

            # Update progress
            progress_data = {
                "status": TaskStatus.IN_PROGRESS.value,
                "progress_percentage": 50,
                "time_spent": 4.0,
                "notes": f"Working on task {i+1}",
            }

            progress_response = await test_client.patch(
                f"/api/v1/internal-tasks/{task['id']}/progress",
                json=progress_data,
                headers=auth_headers,
            )
            assert progress_response.status_code == status.HTTP_200_OK

        # 8. Complete some tasks
        for task in all_tasks[:2]:  # Complete first 2 tasks
            complete_data = {
                "status": TaskStatus.COMPLETED.value,
                "progress_percentage": 100,
                "time_spent": 8.0,
                "notes": "Task completed successfully",
            }

            complete_response = await test_client.patch(
                f"/api/v1/internal-tasks/{task['id']}/progress",
                json=complete_data,
                headers=auth_headers,
            )
            assert complete_response.status_code == status.HTTP_200_OK

        # 9. Update Deliverable Status
        for deliverable in created_deliverables[:1]:  # Update first deliverable
            del_status_update = {
                "current_status": DeliverableStatus.MODELING_PENDING.value
            }

            del_status_response = await test_client.patch(
                f"/api/v1/deliverables/{deliverable['id']}/status",
                json=del_status_update,
                headers=auth_headers,
            )
            assert del_status_response.status_code == status.HTTP_200_OK

        # 10. Create Review Items
        review_items = []
        for deliverable in created_deliverables[
            :2
        ]:  # Create reviews for first 2 deliverables
            review_data = {
                "title": f"Review for deliverable {deliverable['id']}",
                "description": f"Quality review for {deliverable['deliverable_sub_type']}",
                "type": "internal",
                "deliverable_id": deliverable["id"],
                "priority": "high",
            }

            review_response = await test_client.post(
                "/api/v1/review-items/", json=review_data, headers=auth_headers
            )
            assert review_response.status_code == status.HTTP_201_CREATED
            review_items.append(review_response.json())

        # 11. Assign Reviewers and Submit Reviews
        for review in review_items:
            # Assign reviewer
            assign_reviewer_data = {"reviewer_id": 2}
            assign_reviewer_response = await test_client.patch(
                f"/api/v1/review-items/{review['id']}/assign",
                json=assign_reviewer_data,
                headers=auth_headers,
            )
            assert assign_reviewer_response.status_code == status.HTTP_200_OK

            # Submit review feedback
            feedback_data = {
                "status": ReviewStatus.APPROVED.value,
                "comments": "Excellent work, approved for next phase",
                "rating": 4,
            }

            feedback_response = await test_client.patch(
                f"/api/v1/review-items/{review['id']}/feedback",
                json=feedback_data,
                headers=auth_headers,
            )
            assert feedback_response.status_code == status.HTTP_200_OK

        # 12. Complete Deliverables
        for deliverable in created_deliverables:
            complete_del_data = {"current_status": DeliverableStatus.DELIVERED.value}

            complete_del_response = await test_client.patch(
                f"/api/v1/deliverables/{deliverable['id']}/status",
                json=complete_del_data,
                headers=auth_headers,
            )
            assert complete_del_response.status_code == status.HTTP_200_OK

        # 13. Create Project Outputs
        outputs_data = [
            {
                "name": "Final Design Package",
                "description": "Complete UI/UX design files",
                "type": "design_file",
                "file_path": "/outputs/design_package.zip",
                "project_id": project_id,
            },
            {
                "name": "Source Code",
                "description": "Complete application source code",
                "type": "source_code",
                "file_path": "/outputs/source_code.zip",
                "project_id": project_id,
            },
            {
                "name": "Documentation",
                "description": "Technical and user documentation",
                "type": "documentation",
                "file_path": "/outputs/documentation.pdf",
                "project_id": project_id,
            },
        ]

        created_outputs = []
        for output_data in outputs_data:
            output_response = await test_client.post(
                "/api/v1/project-outputs/", json=output_data, headers=auth_headers
            )
            assert output_response.status_code == status.HTTP_201_CREATED
            created_outputs.append(output_response.json())

        # 14. Complete Project
        final_status_update = {"status": ProjectStatus.COMPLETED.value}

        final_response = await test_client.patch(
            f"/api/v1/projects/{project_id}/status",
            json=final_status_update,
            headers=auth_headers,
        )

        assert final_response.status_code == status.HTTP_200_OK
        final_project = final_response.json()
        assert final_project["status"] == ProjectStatus.COMPLETED.value

        # 15. Verify Final State
        # Get project details
        final_project_response = await test_client.get(
            f"/api/v1/projects/{project_id}", headers=auth_headers
        )
        assert final_project_response.status_code == status.HTTP_200_OK

        # Get all deliverables
        deliverables_response = await test_client.get(
            f"/api/v1/projects/{project_id}/deliverables/", headers=auth_headers
        )
        assert deliverables_response.status_code == status.HTTP_200_OK
        final_deliverables = deliverables_response.json()
        assert len(final_deliverables) >= 3

        # Get all outputs
        outputs_response = await test_client.get(
            f"/api/v1/projects/{project_id}/outputs", headers=auth_headers
        )
        assert outputs_response.status_code == status.HTTP_200_OK
        final_outputs = outputs_response.json()
        assert len(final_outputs) >= 3

        # Verify project completion
        assert final_project_response.json()["status"] == ProjectStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_project_with_client_feedback_workflow(
        self, test_client, auth_headers
    ):
        """Test project workflow with client feedback integration."""

        # 1. Create Project
        project_data = {
            "name": "Client Feedback Test Project",
            "budget": 75000.00,
            "start_date": date.today().isoformat(),
            "end_date": date.today().replace(year=date.today().year + 1).isoformat(),
        }

        project_response = await test_client.post(
            "/api/v1/projects/", json=project_data, headers=auth_headers
        )

        assert project_response.status_code == status.HTTP_201_CREATED
        project_id = project_response.json()["id"]

        # 2. Create Deliverable
        deliverable_data = {
            "deliverable_type": DeliverableType.RENDERED_IMAGES.value,
            "deliverable_sub_type": "Client Review Design",
            "tentative_timeline_days": 10,
            "project_id": project_id,
        }

        deliverable_response = await test_client.post(
            "/api/v1/deliverables/", json=deliverable_data, headers=auth_headers
        )

        assert deliverable_response.status_code == status.HTTP_201_CREATED
        deliverable_id = deliverable_response.json()["id"]

        # 3. Create Client Review
        client_review_data = {
            "title": "Client Design Review",
            "description": "Client review of initial design concepts",
            "type": "client",
            "deliverable_id": deliverable_id,
            "priority": "high",
        }

        client_review_response = await test_client.post(
            "/api/v1/review-items/", json=client_review_data, headers=auth_headers
        )

        assert client_review_response.status_code == status.HTTP_201_CREATED
        review_id = client_review_response.json()["id"]

        # 4. Submit Client Feedback (Revision Request)
        revision_feedback = {
            "status": "rejected",
            "comments": "Please adjust the color scheme and add more interactive elements",
            "rating": 2,
        }

        revision_response = await test_client.patch(
            f"/api/v1/review-items/{review_id}/feedback",
            json=revision_feedback,
            headers=auth_headers,
        )

        assert revision_response.status_code == status.HTTP_200_OK

        # 5. Create Revision Tasks
        revision_task_data = {
            "title": "Implement Client Revisions",
            "description": "Update design based on client feedback",
            "deliverable_id": deliverable_id,
            "estimated_hours": 16.0,
            "priority": "high",
        }

        revision_task_response = await test_client.post(
            "/api/v1/internal-tasks/", json=revision_task_data, headers=auth_headers
        )

        assert revision_task_response.status_code == status.HTTP_201_CREATED
        task_id = revision_task_response.json()["id"]

        # 6. Complete Revision Task
        complete_revision_data = {
            "status": TaskStatus.COMPLETED.value,
            "progress_percentage": 100,
            "time_spent": 16.0,
            "notes": "Revisions completed based on client feedback",
        }

        complete_revision_response = await test_client.patch(
            f"/api/v1/internal-tasks/{task_id}/progress",
            json=complete_revision_data,
            headers=auth_headers,
        )

        assert complete_revision_response.status_code == status.HTTP_200_OK

        # 7. Create Second Client Review
        second_review_data = {
            "title": "Client Final Review",
            "description": "Final client review after revisions",
            "type": "client",
            "deliverable_id": deliverable_id,
            "priority": "high",
        }

        second_review_response = await test_client.post(
            "/api/v1/review-items/", json=second_review_data, headers=auth_headers
        )

        assert second_review_response.status_code == status.HTTP_201_CREATED
        second_review_id = second_review_response.json()["id"]

        # 8. Submit Final Approval
        approval_feedback = {
            "status": ReviewStatus.APPROVED.value,
            "comments": "Perfect! The revisions look great. Approved for final delivery.",
            "rating": 5,
        }

        approval_response = await test_client.patch(
            f"/api/v1/review-items/{second_review_id}/feedback",
            json=approval_feedback,
            headers=auth_headers,
        )

        assert approval_response.status_code == status.HTTP_200_OK

        # 9. Complete Deliverable
        complete_deliverable_data = {
            "current_status": DeliverableStatus.DELIVERED.value
        }

        complete_deliverable_response = await test_client.patch(
            f"/api/v1/deliverables/{deliverable_id}/status",
            json=complete_deliverable_data,
            headers=auth_headers,
        )

        assert complete_deliverable_response.status_code == status.HTTP_200_OK

        # 10. Verify Final State
        final_deliverable_response = await test_client.get(
            f"/api/v1/deliverables/{deliverable_id}", headers=auth_headers
        )

        assert final_deliverable_response.status_code == status.HTTP_200_OK
        assert (
            final_deliverable_response.json()["current_status"]
            == DeliverableStatus.DELIVERED.value
        )


@pytest.mark.e2e
class TestMultiUserCollaboration:
    """End-to-end tests for multi-user collaboration scenarios."""

    @pytest.mark.asyncio
    async def test_team_collaboration_workflow(self, test_client):
        """Test collaboration between multiple team members."""

        # Different user contexts
        admin_headers = {"Authorization": "Bearer admin_token", "X-Business-ID": "1"}
        manager_headers = {
            "Authorization": "Bearer manager_token",
            "X-Business-ID": "1",
        }
        developer_headers = {
            "Authorization": "Bearer developer_token",
            "X-Business-ID": "1",
        }

        # 1. Admin creates project
        project_data = {
            "name": "Team Collaboration Project",
            "budget": 120000.00,
            "start_date": date.today().isoformat(),
            "end_date": date.today().replace(year=date.today().year + 1).isoformat(),
        }

        project_response = await test_client.post(
            "/api/v1/projects/", json=project_data, headers=admin_headers
        )

        assert project_response.status_code == status.HTTP_201_CREATED
        project_id = project_response.json()["id"]

        # 2. Manager creates deliverables
        deliverable_data = {
            "deliverable_type": DeliverableType.ANIMATED_VR_TOUR.value,
            "deliverable_sub_type": "Team Development Project",
            "tentative_timeline_days": 25,
            "project_id": project_id,
        }

        deliverable_response = await test_client.post(
            "/api/v1/deliverables/", json=deliverable_data, headers=manager_headers
        )

        assert deliverable_response.status_code == status.HTTP_201_CREATED
        deliverable_id = deliverable_response.json()["id"]

        # 3. Manager creates and assigns tasks to developers
        tasks_data = [
            {
                "title": "Frontend Development",
                "description": "Develop user interface components",
                "deliverable_id": deliverable_id,
                "estimated_hours": 40.0,
                "priority": "high",
            },
            {
                "title": "Backend API Development",
                "description": "Develop REST API endpoints",
                "deliverable_id": deliverable_id,
                "estimated_hours": 32.0,
                "priority": "high",
            },
        ]

        created_tasks = []
        for task_data in tasks_data:
            task_response = await test_client.post(
                "/api/v1/internal-tasks/", json=task_data, headers=manager_headers
            )
            assert task_response.status_code == status.HTTP_201_CREATED
            created_tasks.append(task_response.json())

        # 4. Assign tasks to developers
        for i, task in enumerate(created_tasks):
            assign_data = {"assigned_to": i + 2}  # Developer IDs 2, 3

            assign_response = await test_client.patch(
                f"/api/v1/internal-tasks/{task['id']}/assign",
                json=assign_data,
                headers=manager_headers,
            )
            assert assign_response.status_code == status.HTTP_200_OK

        # 5. Developers work on tasks
        for task in created_tasks:
            # Start working
            start_work_data = {
                "status": TaskStatus.IN_PROGRESS.value,
                "progress_percentage": 25,
                "time_spent": 8.0,
                "notes": "Started working on the task",
            }

            start_response = await test_client.patch(
                f"/api/v1/internal-tasks/{task['id']}/progress",
                json=start_work_data,
                headers=developer_headers,
            )
            assert start_response.status_code == status.HTTP_200_OK

            # Continue progress
            continue_work_data = {
                "status": TaskStatus.IN_PROGRESS.value,
                "progress_percentage": 75,
                "time_spent": 24.0,
                "notes": "Making good progress",
            }

            continue_response = await test_client.patch(
                f"/api/v1/internal-tasks/{task['id']}/progress",
                json=continue_work_data,
                headers=developer_headers,
            )
            assert continue_response.status_code == status.HTTP_200_OK

        # 6. Manager reviews progress
        for task in created_tasks:
            task_details_response = await test_client.get(
                f"/api/v1/internal-tasks/{task['id']}", headers=manager_headers
            )
            assert task_details_response.status_code == status.HTTP_200_OK

            task_details = task_details_response.json()
            assert task_details["status"] == TaskStatus.IN_PROGRESS.value
            assert task_details["progress_percentage"] == 75

        # 7. Complete tasks
        for task in created_tasks:
            complete_data = {
                "status": TaskStatus.COMPLETED.value,
                "progress_percentage": 100,
                "time_spent": 32.0,
                "notes": "Task completed successfully",
            }

            complete_response = await test_client.patch(
                f"/api/v1/internal-tasks/{task['id']}/progress",
                json=complete_data,
                headers=developer_headers,
            )
            assert complete_response.status_code == status.HTTP_200_OK

        # 8. Manager creates review
        review_data = {
            "title": "Team Development Review",
            "description": "Review of collaborative development work",
            "type": "internal",
            "deliverable_id": deliverable_id,
            "priority": "high",
        }

        review_response = await test_client.post(
            "/api/v1/review-items/", json=review_data, headers=manager_headers
        )

        assert review_response.status_code == status.HTTP_201_CREATED
        review_id = review_response.json()["id"]

        # 9. Admin conducts final review
        admin_review_data = {
            "status": ReviewStatus.APPROVED.value,
            "comments": "Excellent collaborative work from the team",
            "rating": 5,
        }

        admin_review_response = await test_client.patch(
            f"/api/v1/review-items/{review_id}/feedback",
            json=admin_review_data,
            headers=admin_headers,
        )

        assert admin_review_response.status_code == status.HTTP_200_OK

        # 10. Complete deliverable
        complete_deliverable_data = {
            "current_status": DeliverableStatus.DELIVERED.value
        }

        complete_deliverable_response = await test_client.patch(
            f"/api/v1/deliverables/{deliverable_id}/status",
            json=complete_deliverable_data,
            headers=manager_headers,
        )

        assert complete_deliverable_response.status_code == status.HTTP_200_OK


@pytest.mark.e2e
@pytest.mark.slow
class TestScalabilityWorkflows:
    """End-to-end tests for scalability scenarios."""

    @pytest.mark.asyncio
    async def test_large_project_workflow(self, test_client, auth_headers):
        """Test workflow with large number of deliverables and tasks."""

        # 1. Create large project
        project_data = {
            "name": "Large Scale E2E Project",
            "budget": 500000.00,
            "start_date": date.today().isoformat(),
            "end_date": date.today().replace(year=date.today().year + 2).isoformat(),
        }

        project_response = await test_client.post(
            "/api/v1/projects/", json=project_data, headers=auth_headers
        )

        assert project_response.status_code == status.HTTP_201_CREATED
        project_id = project_response.json()["id"]

        # 2. Create multiple deliverables
        deliverable_types = [
            DeliverableType.RENDERED_IMAGES,
            DeliverableType.TECHNICAL_RENDERS,
            DeliverableType.EXTERIOR_VR_TOUR,
            DeliverableType.ANIMATED_VR_TOUR,
        ]

        created_deliverables = []
        for i in range(10):  # Create 10 deliverables
            deliverable_data = {
                "deliverable_type": deliverable_types[i % len(deliverable_types)].value,
                "deliverable_sub_type": f"Large Project Sub Type {i+1}",
                "tentative_timeline_days": 15 + (i * 2),
                "project_id": project_id,
            }

            deliverable_response = await test_client.post(
                "/api/v1/deliverables/", json=deliverable_data, headers=auth_headers
            )

            assert deliverable_response.status_code == status.HTTP_201_CREATED
            created_deliverables.append(deliverable_response.json())

        # 3. Create multiple tasks for each deliverable
        all_tasks = []
        for deliverable in created_deliverables:
            for j in range(5):  # 5 tasks per deliverable = 50 total tasks
                task_data = {
                    "title": f"Task {j+1} for deliverable {deliverable['id']}",
                    "description": f"Task {j+1} description",
                    "deliverable_id": deliverable["id"],
                    "estimated_hours": 8.0,
                    "priority": "medium",
                }

                task_response = await test_client.post(
                    "/api/v1/internal-tasks/", json=task_data, headers=auth_headers
                )

                assert task_response.status_code == status.HTTP_201_CREATED
                all_tasks.append(task_response.json())

        # 4. Batch process tasks (simulate parallel work)
        batch_size = 10
        for i in range(0, len(all_tasks), batch_size):
            batch = all_tasks[i : i + batch_size]

            # Process batch concurrently
            async def process_task(task):
                # Assign task
                assign_response = await test_client.patch(
                    f"/api/v1/internal-tasks/{task['id']}/assign",
                    json={"assigned_to": 1},
                    headers=auth_headers,
                )

                # Update progress
                progress_response = await test_client.patch(
                    f"/api/v1/internal-tasks/{task['id']}/progress",
                    json={
                        "status": TaskStatus.COMPLETED.value,
                        "progress_percentage": 100,
                        "time_spent": 8.0,
                        "notes": "Batch processed task",
                    },
                    headers=auth_headers,
                )

                return (
                    assign_response.status_code == status.HTTP_200_OK
                    and progress_response.status_code == status.HTTP_200_OK
                )

            # Process batch
            batch_results = await asyncio.gather(
                *[process_task(task) for task in batch], return_exceptions=True
            )

            # Verify batch processing
            successful_tasks = sum(1 for result in batch_results if result is True)
            assert successful_tasks >= len(batch) * 0.8  # At least 80% success rate

        # 5. Complete deliverables in batches
        for deliverable in created_deliverables:
            complete_response = await test_client.patch(
                f"/api/v1/deliverables/{deliverable['id']}/status",
                json={"current_status": DeliverableStatus.DELIVERED.value},
                headers=auth_headers,
            )
            assert complete_response.status_code == status.HTTP_200_OK

        # 6. Verify final project state
        final_project_response = await test_client.get(
            f"/api/v1/projects/{project_id}", headers=auth_headers
        )

        assert final_project_response.status_code == status.HTTP_200_OK

        # Get project statistics
        deliverables_response = await test_client.get(
            f"/api/v1/projects/{project_id}/deliverables/", headers=auth_headers
        )

        assert deliverables_response.status_code == status.HTTP_200_OK
        final_deliverables = deliverables_response.json()
        assert len(final_deliverables) == 10

        # Verify all deliverables are completed
        completed_deliverables = [
            d
            for d in final_deliverables
            if d["current_status"] == DeliverableStatus.DELIVERED.value
        ]
        assert len(completed_deliverables) == 10


@pytest.mark.e2e
class TestErrorRecoveryWorkflows:
    """End-to-end tests for error recovery scenarios."""

    @pytest.mark.asyncio
    async def test_failed_task_recovery_workflow(self, test_client, auth_headers):
        """Test recovery from failed tasks in project workflow."""

        # 1. Create project and deliverable
        project_data = {
            "name": "Error Recovery Test Project",
            "budget": 60000.00,
            "start_date": date.today().isoformat(),
            "end_date": date.today().replace(year=date.today().year + 1).isoformat(),
        }

        project_response = await test_client.post(
            "/api/v1/projects/", json=project_data, headers=auth_headers
        )

        assert project_response.status_code == status.HTTP_201_CREATED
        project_id = project_response.json()["id"]

        deliverable_data = {
            "deliverable_type": DeliverableType.VIDEO_WALKTHROUGH.value,
            "deliverable_sub_type": "Recovery Test Deliverable",
            "tentative_timeline_days": 12,
            "project_id": project_id,
        }

        deliverable_response = await test_client.post(
            "/api/v1/deliverables/", json=deliverable_data, headers=auth_headers
        )

        assert deliverable_response.status_code == status.HTTP_201_CREATED
        deliverable_id = deliverable_response.json()["id"]

        # 2. Create task that will "fail"
        task_data = {
            "title": "Task That Will Fail",
            "description": "This task will encounter issues",
            "deliverable_id": deliverable_id,
            "estimated_hours": 16.0,
            "priority": "high",
        }

        task_response = await test_client.post(
            "/api/v1/internal-tasks/", json=task_data, headers=auth_headers
        )

        assert task_response.status_code == status.HTTP_201_CREATED
        task_id = task_response.json()["id"]

        # 3. Start task
        start_task_data = {
            "status": TaskStatus.IN_PROGRESS.value,
            "progress_percentage": 30,
            "time_spent": 8.0,
            "notes": "Started working on the task",
        }

        start_response = await test_client.patch(
            f"/api/v1/internal-tasks/{task_id}/progress",
            json=start_task_data,
            headers=auth_headers,
        )

        assert start_response.status_code == status.HTTP_200_OK

        # 4. Mark task as blocked/failed
        block_task_data = {
            "status": "blocked",
            "progress_percentage": 30,
            "time_spent": 12.0,
            "notes": "Task blocked due to technical issues - need to reassess approach",
        }

        block_response = await test_client.patch(
            f"/api/v1/internal-tasks/{task_id}/progress",
            json=block_task_data,
            headers=auth_headers,
        )

        assert block_response.status_code == status.HTTP_200_OK

        # 5. Create recovery task
        recovery_task_data = {
            "title": "Recovery Task - Alternative Approach",
            "description": "Alternative approach to complete the blocked task",
            "deliverable_id": deliverable_id,
            "estimated_hours": 20.0,
            "priority": "urgent",
        }

        recovery_response = await test_client.post(
            "/api/v1/internal-tasks/", json=recovery_task_data, headers=auth_headers
        )

        assert recovery_response.status_code == status.HTTP_201_CREATED
        recovery_task_id = recovery_response.json()["id"]

        # 6. Complete recovery task successfully
        complete_recovery_data = {
            "status": TaskStatus.COMPLETED.value,
            "progress_percentage": 100,
            "time_spent": 20.0,
            "notes": "Successfully completed using alternative approach",
        }

        complete_recovery_response = await test_client.patch(
            f"/api/v1/internal-tasks/{recovery_task_id}/progress",
            json=complete_recovery_data,
            headers=auth_headers,
        )

        assert complete_recovery_response.status_code == status.HTTP_200_OK

        # 7. Complete deliverable despite initial failure
        complete_deliverable_data = {
            "current_status": DeliverableStatus.DELIVERED.value
        }

        complete_deliverable_response = await test_client.patch(
            f"/api/v1/deliverables/{deliverable_id}/status",
            json=complete_deliverable_data,
            headers=auth_headers,
        )

        assert complete_deliverable_response.status_code == status.HTTP_200_OK

        # 8. Verify recovery was successful
        final_deliverable_response = await test_client.get(
            f"/api/v1/deliverables/{deliverable_id}", headers=auth_headers
        )

        assert final_deliverable_response.status_code == status.HTTP_200_OK
        assert (
            final_deliverable_response.json()["current_status"]
            == DeliverableStatus.DELIVERED.value
        )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_project_creation_workflow(test_client, auth_headers):
    """Complete end-to-end test of project creation workflow."""

    # 1. Create a project
    project_data = {
        "name": "Full E2E Test Project",
        "budget": 75000.00,
        "start_date": date.today().isoformat(),
        "end_date": date.today().replace(year=date.today().year + 1).isoformat(),
    }

    project_response = await test_client.post(
        "/api/v1/projects/", json=project_data, headers=auth_headers
    )

    assert project_response.status_code == status.HTTP_201_CREATED
    project_id = project_response.json()["id"]
    assert project_id is not None

    # 2. Add deliverables
    deliverable_data = {
        "deliverable_type": DeliverableType.RENDERED_IMAGES.value,
        "deliverable_sub_type": "Full E2E Test Deliverable",
        "tentative_timeline_days": 14,
        "project_id": project_id,
    }

    deliverable_response = await test_client.post(
        "/api/v1/deliverables/", json=deliverable_data, headers=auth_headers
    )

    assert deliverable_response.status_code == status.HTTP_201_CREATED
    deliverable_id = deliverable_response.json()["id"]

    # 3. Verify project was created successfully
    final_project_response = await test_client.get(
        f"/api/v1/projects/{project_id}", headers=auth_headers
    )

    assert final_project_response.status_code == status.HTTP_200_OK
    assert final_project_response.json()["name"] == "Full E2E Test Project"
