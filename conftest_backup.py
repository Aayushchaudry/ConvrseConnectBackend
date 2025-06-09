# conftest.py - Main pytest configuration and fixtures

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime, date
from typing import AsyncGenerator, Generator
from uuid import uuid4
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from unittest.mock import AsyncMock, Mock, patch
import redis
from fastapi.testclient import TestClient

# Add src to Python path
sys.path.append(str(Path(__file__).parent / "src"))

from src.main import app
from src.config.database import Base, get_db_session
from src.config.settings import settings
from src.config.event_bus import get_event_bus
from src.integrations.auth_service_client import get_auth_client
from src.models.project import Project, ProjectStatus
from src.models.deliverable import Deliverable
from src.models.internal_task import InternalTask
from src.models.review_item import ReviewItem
from src.models.client_feedback import ClientFeedback
from src.services.project_service import ProjectService
from src.services.deliverable_service import DeliverableService


# Test database URL - use environment variable or fallback to PostgreSQL
import os
TEST_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://test_user:test_pass@localhost:5433/test_project_db")


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_pre_ping=True
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup: Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
def mock_event_bus():
    """Mock event bus for testing."""
    mock_bus = AsyncMock()
    mock_bus.publish = AsyncMock()
    mock_bus.subscribe = AsyncMock()
    mock_bus.close = AsyncMock()
    return mock_bus


@pytest.fixture
def mock_auth_client():
    """Mock authentication client for testing."""
    mock_client = AsyncMock()
    mock_client.health_check = AsyncMock(return_value=True)
    mock_client.verify_token = AsyncMock(return_value={
        "user_id": 1,
        "business_id": 1,
        "role": "admin",
        "permissions": ["read", "write", "admin"]
    })
    mock_client.get_user_info = AsyncMock(return_value={
        "id": 1,
        "email": "test@example.com",
        "name": "Test User",
        "business_id": 1
    })
    return mock_client


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    mock_redis = Mock()
    mock_redis.get = Mock(return_value=None)
    mock_redis.set = Mock()
    mock_redis.delete = Mock()
    mock_redis.exists = Mock(return_value=False)
    return mock_redis


@pytest.fixture
async def test_client(db_session, mock_event_bus, mock_auth_client):
    """Create FastAPI test client with dependency overrides."""
    
    def override_get_db_session():
        return db_session
    
    def override_get_event_bus():
        return mock_event_bus
    
    def override_get_auth_client():
        return mock_auth_client
    
    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_event_bus] = override_get_event_bus
    app.dependency_overrides[get_auth_client] = override_get_auth_client
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    # Clear overrides
    app.dependency_overrides.clear()


@pytest.fixture
def sync_test_client():
    """Synchronous test client for simpler testing scenarios."""
    return TestClient(app)


@pytest.fixture
def sample_project_data():
    """Sample project data for testing."""
    return {
        "name": "Test Project",
        "budget": 50000.00,
        "start_date": date.today(),
        "end_date": date.today().replace(year=date.today().year + 1),
        "business_id": 1,
        "created_by": 1
    }


@pytest.fixture
async def test_project(db_session, sample_project_data):
    """Create a test project in the database."""
    project = Project(
        id=uuid4(),
        name=sample_project_data["name"],
        budget=sample_project_data["budget"],
        start_date=datetime.combine(sample_project_data["start_date"], datetime.min.time()),
        end_date=datetime.combine(sample_project_data["end_date"], datetime.min.time()),
        business_id=sample_project_data["business_id"],
        created_by=sample_project_data["created_by"],
        status=ProjectStatus.INITIATED
    )
    
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    
    yield project
    
    # Cleanup
    await db_session.delete(project)
    await db_session.commit()


@pytest.fixture
def sample_deliverable_data():
    """Sample deliverable data for testing."""
    return {
        "name": "Test Deliverable",
        "description": "A test deliverable",
        "type": "design",
        "due_date": datetime.now(),
        "project_id": None  # Will be set by test
    }


@pytest.fixture
async def test_deliverable(db_session, test_project, sample_deliverable_data):
    """Create a test deliverable in the database."""
    deliverable_data = sample_deliverable_data.copy()
    deliverable_data["project_id"] = test_project.id
    
    deliverable = Deliverable(**deliverable_data)
    db_session.add(deliverable)
    await db_session.commit()
    await db_session.refresh(deliverable)
    
    yield deliverable
    
    # Cleanup
    await db_session.delete(deliverable)
    await db_session.commit()


@pytest.fixture
def auth_headers():
    """Sample authentication headers for testing."""
    return {
        "Authorization": "Bearer test_token",
        "X-Business-ID": "1"
    }


@pytest.fixture
def invalid_auth_headers():
    """Invalid authentication headers for security testing."""
    return {
        "Authorization": "Bearer invalid_token",
        "X-Business-ID": "999"
    }


@pytest.fixture
async def project_service(db_session, mock_event_bus):
    """Create project service instance for testing."""
    return ProjectService(db_session=db_session, event_bus=mock_event_bus)


@pytest.fixture
async def deliverable_service(db_session, mock_event_bus):
    """Create deliverable service instance for testing."""
    return DeliverableService(db_session=db_session, event_bus=mock_event_bus)


@pytest.fixture(autouse=True)
def mock_external_services():
    """Automatically mock external services for all tests."""
    with patch('src.integrations.auth_service_client.AuthServiceClient') as mock_auth, \
         patch('redis.Redis') as mock_redis_client, \
         patch('aiokafka.AIOKafkaProducer') as mock_kafka:
        
        # Configure mocks
        mock_auth.return_value.health_check = AsyncMock(return_value=True)
        mock_redis_client.return_value.ping = Mock(return_value=True)
        mock_kafka.return_value.start = AsyncMock()
        mock_kafka.return_value.stop = AsyncMock()
        
        yield {
            'auth': mock_auth,
            'redis': mock_redis_client,
            'kafka': mock_kafka
        }


# Pytest configuration
pytest_plugins = ["pytest_asyncio"]


def pytest_configure(config):
    """Configure pytest settings."""
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "e2e: marks tests as end-to-end tests"
    )
    config.addinivalue_line(
        "markers", "security: marks tests as security tests"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow running"
    )


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment variables."""
    os.environ.update({
        "ENV": "test",
        "DEBUG": "true",
        "DATABASE_URL": TEST_DATABASE_URL,
        "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
        "ACTIVE_EVENT_BUS": "kafka"
    }) 