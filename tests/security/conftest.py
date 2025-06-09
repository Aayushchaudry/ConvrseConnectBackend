# tests/security/conftest.py - Security test configuration

import os
from typing import AsyncGenerator
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Force test environment variables for security tests BEFORE any other imports
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
os.environ["AUTH_CIRCUIT_BREAKER_FAILURE_THRESHOLD"] = "100"
os.environ["AUTH_CIRCUIT_BREAKER_RECOVERY_TIMEOUT"] = "1"


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create test database engine for security tests."""
    from src.config.database import Base

    # Use SQLite explicitly for security tests
    engine = create_async_engine(
        "sqlite+aiosqlite:///./test.db", echo=False, pool_pre_ping=True
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each security test."""
    engine = test_engine
    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session


@pytest.fixture
def mock_event_bus():
    """Mock event bus for security testing."""
    mock_bus = AsyncMock()
    mock_bus.publish = AsyncMock()
    mock_bus.subscribe = AsyncMock()
    mock_bus.close = AsyncMock()
    return mock_bus


def create_mock_auth_client(should_authenticate=True, user_data=None):
    """Helper to create a properly mocked auth client"""
    from src.integrations.auth_service_client import AuthServiceClient, UserData

    mock_auth_client = AsyncMock(spec=AuthServiceClient)
    mock_auth_client.health_check = AsyncMock(return_value=True)

    # Reset circuit breaker to closed state for testing
    mock_circuit_breaker = Mock()
    mock_circuit_breaker.can_attempt_call = Mock(return_value=True)
    mock_circuit_breaker.call_succeeded = Mock()
    mock_circuit_breaker.call_failed = Mock()
    mock_circuit_breaker.state = "closed"  # Ensure circuit breaker is closed
    mock_auth_client.circuit_breaker = mock_circuit_breaker

    if should_authenticate and user_data:
        mock_auth_client.validate_token = AsyncMock(return_value=user_data)
    elif should_authenticate:
        default_user_data = UserData(
            user_id=1,
            username="test@example.com",
            email="test@example.com",
            role_name="admin",
            is_active=True,
            businesses=[{"business_id": 1, "role": "admin"}],
            permissions=["read", "write", "admin"],
        )
        mock_auth_client.validate_token = AsyncMock(return_value=default_user_data)
    else:
        from src.integrations.auth_service_client import TokenValidationError

        mock_auth_client.validate_token = AsyncMock(
            side_effect=TokenValidationError(
                "Authentication required for security testing"
            )
        )

    return mock_auth_client


@pytest_asyncio.fixture
async def security_test_client(db_session, mock_event_bus):
    """Create FastAPI test client for security testing with controlled auth behavior."""
    from src.config.database import get_db_session
    from src.config.event_bus import get_event_bus
    from src.main import app

    def override_get_db_session():
        return db_session

    def override_get_event_bus():
        return mock_event_bus

    # Override dependencies
    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_event_bus] = override_get_event_bus

    # Create a properly mocked auth client for security testing (default to failed auth)
    mock_auth_client = create_mock_auth_client(should_authenticate=False)

    # Patch the get_auth_client function at the module level
    with patch(
        "src.integrations.auth_service_client.get_auth_client",
        return_value=mock_auth_client,
    ) as mock_get_auth:
        # Also patch the import in auth middleware
        with patch(
            "src.middleware.auth_middleware.get_auth_client",
            return_value=mock_auth_client,
        ):
            from httpx import ASGITransport

            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                yield client

    # Clear overrides
    app.dependency_overrides.clear()
