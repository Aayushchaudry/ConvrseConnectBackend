# tests/unit/conftest.py

from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio

from src.models.deliverable import Deliverable, DeliverableStatus, DeliverableType

# Add necessary imports for models
from src.models.project import Project, ProjectStatus


@pytest_asyncio.fixture
async def db_session():
    """Override the db_session fixture for unit tests to return a mock session."""
    mock_session = AsyncMock()
    return mock_session


@pytest.fixture
def sample_project_data():
    """Provides sample data for creating a project."""
    return {
        "id": uuid4(),
        "name": "Test Project",
        "budget": 10000.00,
        "start_date": date(2023, 1, 1),
        "end_date": date(2023, 12, 31),
        "business_id": uuid4(),
        "created_by": uuid4(),
    }


@pytest.fixture
def test_project(sample_project_data):
    """Override test_project to return a mock project object without db interaction."""
    project = Project(**sample_project_data, status=ProjectStatus.INITIATED)
    return project


@pytest.fixture
def sample_deliverable_data():
    """Provides sample data for creating a deliverable."""
    return {
        "id": uuid4(),
        "deliverable_type": DeliverableType.RENDERED_IMAGES,
        "current_status": DeliverableStatus.INFO_GATHERING,
        "created_by": 1,  # Add required created_by field
    }


@pytest.fixture
def test_deliverable(test_project, sample_deliverable_data):
    """Override test_deliverable to return a mock deliverable object."""
    project = test_project
    deliverable_data = sample_deliverable_data.copy()
    deliverable_data["project_id"] = project.id
    deliverable = Deliverable(**deliverable_data)
    return deliverable
