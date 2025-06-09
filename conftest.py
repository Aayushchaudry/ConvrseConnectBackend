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


# Test database URL - use environment variable or fallback to SQLite
import os


async def get_test_database_url():
    """Get the test database URL, falling back to SQLite if PostgreSQL is not available."""
    postgres_url = os.getenv("DATABASE_URL")
    
    if postgres_url and postgres_url.startswith("postgresql"):
        # Try to connect to PostgreSQL first
        try:
            test_engine = create_async_engine(postgres_url, echo=False, pool_pre_ping=True)
            async with test_engine.begin() as conn:
                await conn.execute("SELECT 1")
            await test_engine.dispose()
            print(f"✅ Using PostgreSQL for tests: {postgres_url}")
            return postgres_url
        except Exception as e:
            print(f"⚠️  PostgreSQL not available ({e}), falling back to SQLite")
    
    # Fall back to SQLite
    sqlite_url = "sqlite+aiosqlite:///./test_e2e.db"
    print(f"✅ Using SQLite for tests: {sqlite_url}")
    return sqlite_url


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create test database engine with automatic fallback."""
    test_db_url = await get_test_database_url()
    
    engine = create_async_engine(
        test_db_url,
        echo=False,
        pool_pre_ping=True
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    engine = test_engine
    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session


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
    from src.integrations.auth_service_client import UserData
    mock_user_data = UserData(
        user_id=1,
        username="test@example.com",
        email="test@example.com",
        role_name="admin", 
        is_active=True,
        businesses=[{"business_id": 1, "role": "admin"}],
        permissions=["read", "write", "admin"]
    )
    mock_client.validate_token = AsyncMock(return_value=mock_user_data)
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


@pytest_asyncio.fixture
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
    
    from httpx import ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
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


@pytest_asyncio.fixture
async def test_project(db_session, sample_project_data):
    """Create a test project in the database."""
    session = db_session
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
    
    session.add(project)
    await session.commit()
    await session.refresh(project)
    
    return project


@pytest.fixture
def sample_deliverable_data():
    """Sample deliverable data for testing."""
    return {
        "deliverable_type": "RENDERED_IMAGES",
        "deliverable_sub_type": "Interior Requirement",
        "tentative_timeline_days": 10,
        "project_id": None,  # Will be set by test
        "created_by": 1,
        "assigned_to": 1
    }


@pytest_asyncio.fixture
async def test_deliverable(db_session, test_project, sample_deliverable_data):
    """Create a test deliverable in the database."""
    from src.models.deliverable import DeliverableType
    
    session = db_session
    project = test_project
    deliverable_data = sample_deliverable_data.copy()
    deliverable_data["project_id"] = project.id
    
    # Convert string enum to proper enum value
    deliverable_data["deliverable_type"] = DeliverableType.RENDERED_IMAGES
    
    deliverable = Deliverable(**deliverable_data)
    session.add(deliverable)
    await session.commit()
    await session.refresh(deliverable)
    
    return deliverable


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


@pytest_asyncio.fixture
async def project_service(db_session, mock_event_bus):
    """Create project service instance for testing."""
    session = db_session
    return ProjectService(db_session=session, event_bus=mock_event_bus)


@pytest_asyncio.fixture
async def deliverable_service(db_session, mock_event_bus):
    """Create deliverable service instance for testing."""
    session = db_session
    return DeliverableService(db_session=session, event_bus=mock_event_bus)


@pytest.fixture(autouse=True)
def mock_external_services(request):
    """Automatically mock external services for all tests except security tests."""
    # Skip auto-mocking for security tests
    if hasattr(request, 'node') and request.node.get_closest_marker("security"):
        yield None
        return
    
    with patch('src.integrations.auth_service_client.AuthServiceClient') as mock_auth, \
         patch('src.integrations.auth_service_client.get_auth_client') as mock_get_auth_client, \
         patch('redis.Redis') as mock_redis_client, \
         patch('aiokafka.AIOKafkaProducer') as mock_kafka:
        
        # Create a proper auth client mock with UserData structure
        from src.integrations.auth_service_client import UserData
        
        mock_auth_client_instance = AsyncMock()
        
        # Mock validate_token to return UserData object
        mock_user_data = UserData(
            user_id=1,
            username="test@example.com",
            email="test@example.com", 
            role_name="admin",
            is_active=True,
            businesses=[{"business_id": 1, "role": "admin"}],
            permissions=["read", "write", "admin"]
        )
        mock_auth_client_instance.validate_token = AsyncMock(return_value=mock_user_data)
        mock_auth_client_instance.health_check = AsyncMock(return_value=True)
        
        # Configure mocks
        mock_auth.return_value = mock_auth_client_instance
        mock_get_auth_client.return_value = mock_auth_client_instance
        mock_redis_client.return_value.ping = Mock(return_value=True)
        mock_kafka.return_value.start = AsyncMock()
        mock_kafka.return_value.stop = AsyncMock()
        
        yield {
            'auth': mock_auth,
            'auth_client': mock_auth_client_instance,
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
    # Force test environment variables - these will override any existing values
    os.environ["ENV"] = "test"
    os.environ["ENVIRONMENT"] = "test" 
    os.environ["DEBUG"] = "true"
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
    os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-testing-only-at-least-32-chars"
    os.environ["AUTH_SERVICE_TOKEN"] = "test-auth-service-token"
    os.environ["AUTH_SERVICE_URL"] = "http://localhost:8001"
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
    os.environ["KAFKA_BOOTSTRAP_SERVERS"] = "localhost:9092"
    os.environ["ACTIVE_EVENT_BUS"] = "kafka" 