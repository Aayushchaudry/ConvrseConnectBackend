"""
Integration tests for project output API endpoints.
"""

import pytest
from fastapi import status
from httpx import AsyncClient
from uuid import UUID

from src.models.deliverable import DeliverableStatus
from src.models.project import ProjectStatus
from src.models.review_item import ReviewStatus


@pytest.mark.asyncio
async def test_create_project_output(
    test_client, test_project, test_deliverable, auth_headers
):
    """Test creating a project output."""
    # Create project output
    output_data = {
        "name": "Test Project Output",
        "deliverable_id": str(test_deliverable.id),
        "description": "Test description",
        "type": "test_type",
        "project_id": str(test_project.id)
    }
    
    response = await test_client.post(
        "/api/v1/project-outputs",
        json=output_data,
        headers=auth_headers
    )
    
    assert response.status_code == status.HTTP_201_CREATED
    output = response.json()
    assert output["output_name"] == "Test Project Output"
    assert output["deliverable_id"] == str(test_deliverable.id)
    assert output["project_id"] == str(test_project.id)


@pytest.mark.asyncio
async def test_list_project_outputs(
    test_client, test_project, test_deliverable, auth_headers
):
    """Test listing project outputs for a project."""
    # Create project output first
    output_data = {
        "name": "Test Project Output",
        "deliverable_id": str(test_deliverable.id),
        "project_id": str(test_project.id)
    }
    
    await test_client.post(
        "/api/v1/project-outputs",
        json=output_data,
        headers=auth_headers
    )
    
    # List project outputs
    response = await test_client.get(
        f"/api/v1/projects/{test_project.id}/outputs",
        headers=auth_headers
    )
    
    assert response.status_code == status.HTTP_200_OK
    outputs = response.json()
    assert len(outputs) >= 1
    assert outputs[0]["project_id"] == str(test_project.id)


@pytest.mark.asyncio
async def test_list_deliverable_outputs(
    test_client, test_project, test_deliverable, auth_headers
):
    """Test listing project outputs for a deliverable."""
    # Create project output first
    output_data = {
        "name": "Test Deliverable Output",
        "deliverable_id": str(test_deliverable.id),
        "project_id": str(test_project.id)
    }
    
    await test_client.post(
        "/api/v1/project-outputs",
        json=output_data,
        headers=auth_headers
    )
    
    # List deliverable outputs
    response = await test_client.get(
        f"/api/v1/deliverables/{test_deliverable.id}/outputs",
        headers=auth_headers
    )
    
    assert response.status_code == status.HTTP_200_OK
    outputs = response.json()
    assert len(outputs) >= 1
    assert outputs[0]["deliverable_id"] == str(test_deliverable.id)


@pytest.mark.asyncio
async def test_generate_deliverable_output(
    test_client, test_project, test_deliverable, test_review_item, auth_headers
):
    """Test generating a project output for a deliverable."""
    # First, approve the review item
    feedback_data = {
        "status": ReviewStatus.APPROVED.value,
        "comments": "Approved for output generation",
        "rating": 5
    }
    
    await test_client.post(
        f"/api/v1/review-items/{test_review_item.id}/feedback",
        json=feedback_data,
        headers=auth_headers
    )
    
    # Generate output
    response = await test_client.post(
        f"/api/v1/deliverables/{test_deliverable.id}/generate-output",
        headers=auth_headers
    )
    
    assert response.status_code == status.HTTP_200_OK
    output = response.json()
    assert output["deliverable_id"] == str(test_deliverable.id)
    assert output["project_id"] == str(test_project.id)
    
    # Verify deliverable status is updated
    deliverable_response = await test_client.get(
        f"/api/v1/deliverables/{test_deliverable.id}",
        headers=auth_headers
    )
    
    assert deliverable_response.status_code == status.HTTP_200_OK
    deliverable = deliverable_response.json()
    assert deliverable["current_status"] == DeliverableStatus.DELIVERED.value


@pytest.mark.asyncio
async def test_compile_project(
    test_client, test_project, test_deliverable, auth_headers
):
    """Test compiling a project."""
    # First, mark the deliverable as delivered
    status_update = {
        "current_status": DeliverableStatus.DELIVERED.value
    }
    
    await test_client.patch(
        f"/api/v1/deliverables/{test_deliverable.id}/status",
        json=status_update,
        headers=auth_headers
    )
    
    # Compile project
    response = await test_client.post(
        f"/api/v1/projects/{test_project.id}/compile",
        headers=auth_headers
    )
    
    assert response.status_code == status.HTTP_200_OK
    compilation = response.json()
    assert compilation["project_id"] == str(test_project.id)
    assert compilation["compilation_started"] is True
    assert "compilation_url" in compilation


@pytest.mark.asyncio
async def test_check_pending_outputs(
    test_client, test_project, test_deliverable, test_review_item, auth_headers
):
    """Test checking for pending outputs."""
    # First, approve the review item
    feedback_data = {
        "status": ReviewStatus.APPROVED.value,
        "comments": "Approved for automatic output generation",
        "rating": 5
    }
    
    await test_client.post(
        f"/api/v1/review-items/{test_review_item.id}/feedback",
        json=feedback_data,
        headers=auth_headers
    )
    
    # Check pending outputs
    response = await test_client.post(
        "/api/v1/check-pending-outputs",
        headers=auth_headers
    )
    
    assert response.status_code == status.HTTP_200_OK
    result = response.json()
    assert "outputs_created" in result
    assert "deliverable_ids" in result