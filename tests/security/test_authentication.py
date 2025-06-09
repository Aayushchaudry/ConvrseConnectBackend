# tests/security/test_authentication.py - Security tests for authentication

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import jwt
import pytest
import pytest_asyncio
from fastapi import HTTPException, status
from httpx import AsyncClient

from src.integrations.auth_service_client import (
    AuthServiceClient,
    AuthServiceError,
    TokenValidationError,
    UserData,
)
from src.middleware.auth_middleware import AuthenticationMiddleware


# Helper function for creating auth client mocks
def create_mock_auth_client(should_authenticate=True, user_data=None):
    """Helper to create a properly mocked auth client"""
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
        mock_auth_client.validate_token = AsyncMock(
            side_effect=TokenValidationError(
                "Authentication required for security testing"
            )
        )

    return mock_auth_client


@pytest.fixture
def disable_auth_mocks():
    """Disable automatic auth service mocking for security tests."""
    # This will prevent the autouse mock_external_services fixture from affecting auth
    with patch("src.integrations.auth_service_client.get_auth_client") as mock_get_auth:
        yield mock_get_auth


@pytest.mark.security
class TestAuthenticationSecurity:
    """Security tests for authentication mechanisms."""

    @pytest.mark.asyncio
    async def test_missing_authorization_header(self, security_test_client):
        """Test that requests without authorization header are rejected."""
        # Use POST endpoint which requires authentication
        project_data = {
            "name": "Test Project",
            "budget": 50000.00,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        }

        response = await security_test_client.post(
            "/api/v1/projects/", json=project_data
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_invalid_token_format(self, security_test_client):
        """Test that malformed tokens are rejected."""
        invalid_headers = [
            {"Authorization": "Bearer"},  # Missing token
            {"Authorization": "Invalid token format"},  # Wrong format
            {"Authorization": "Bearer invalid.token.format"},  # Invalid JWT structure
            {"Authorization": "Basic dXNlcjpwYXNz"},  # Wrong auth type
        ]

        project_data = {
            "name": "Test Project",
            "budget": 50000.00,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        }

        for headers in invalid_headers:
            try:
                response = await security_test_client.post(
                    "/api/v1/projects/", json=project_data, headers=headers
                )
                # If we get here, check the status code
                assert response.status_code == status.HTTP_401_UNAUTHORIZED
            except HTTPException as exc:
                # If an HTTPException is raised, verify it's a 401
                assert exc.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_expired_token(self, security_test_client):
        """Test that expired tokens are rejected."""
        # Create an expired token
        expired_payload = {
            "user_id": 1,
            "business_id": 1,
            "exp": datetime.utcnow() - timedelta(hours=1),  # Expired 1 hour ago
        }
        expired_token = jwt.encode(expired_payload, "secret", algorithm="HS256")

        headers = {"Authorization": f"Bearer {expired_token}"}
        project_data = {
            "name": "Test Project",
            "budget": 50000.00,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        }

        try:
            response = await security_test_client.post(
                "/api/v1/projects/", json=project_data, headers=headers
            )
            # If we get here, check the status code
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
        except HTTPException as exc:
            # If an HTTPException is raised, verify it's a 401
            assert exc.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_tampered_token(self, security_test_client):
        """Test that tampered tokens are rejected."""
        valid_payload = {
            "user_id": 1,
            "business_id": 1,
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        valid_token = jwt.encode(valid_payload, "secret", algorithm="HS256")

        # Tamper with the token
        tampered_token = valid_token[:-10] + "tamperedXX"
        headers = {"Authorization": f"Bearer {tampered_token}"}
        project_data = {
            "name": "Test Project",
            "budget": 50000.00,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        }

        try:
            response = await security_test_client.post(
                "/api/v1/projects/", json=project_data, headers=headers
            )
            # If we get here, check the status code
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
        except HTTPException as exc:
            # If an HTTPException is raised, verify it's a 401
            assert exc.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_authentication_bypass_attempts(self, security_test_client):
        """Test various authentication bypass attempts."""
        # Test that requests without valid authentication are rejected
        project_data = {
            "name": "Test Project",
            "budget": 50000.00,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        }

        bypass_attempts = [
            {},  # No headers
            {"Authorization": ""},  # Empty authorization
            {"Authorization": "None"},  # Invalid format
            {"Authorization": "Bearer null"},  # Null token
            {"X-Auth-Token": "bypass"},  # Wrong header
            {"Authorization": "Basic YWRtaW46cGFzc3dvcmQ="},  # Basic auth
        ]

        for headers in bypass_attempts:
            try:
                response = await security_test_client.post(
                    "/api/v1/projects/", json=project_data, headers=headers
                )
                # If we get here, check the status code
                assert response.status_code == status.HTTP_401_UNAUTHORIZED
            except HTTPException as exc:
                # If an HTTPException is raised, verify it's a 401
                assert exc.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.security
class TestAuthorizationSecurity:
    """Security tests for authorization mechanisms."""

    @pytest.mark.asyncio
    async def test_unauthorized_resource_access(self, security_test_client):
        """Test access to resources without proper authorization."""
        # First create a project with admin user
        project_data = {
            "name": "Test Project",
            "budget": 50000.00,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        }

        # Create mock for admin user with proper permissions
        admin_user_data = UserData(
            user_id=1,
            username="admin@example.com",
            email="admin@example.com",
            role_name="admin",
            is_active=True,
            businesses=[{"business_id": 1, "role": "admin"}],
            permissions=["read", "write", "admin"],
        )
        admin_mock_client = create_mock_auth_client(
            should_authenticate=True, user_data=admin_user_data
        )
        admin_headers = {"Authorization": "Bearer valid-admin-token"}

        with patch(
            "src.integrations.auth_service_client.get_auth_client",
            return_value=admin_mock_client,
        ):
            with patch(
                "src.middleware.auth_middleware.get_auth_client",
                return_value=admin_mock_client,
            ):
                create_response = await security_test_client.post(
                    "/api/v1/projects/", json=project_data, headers=admin_headers
                )
                assert create_response.status_code == status.HTTP_201_CREATED
                project_id = create_response.json()["id"]

        # Now try to access with limited user
        limited_user_data = UserData(
            user_id=2,
            username="limited@example.com",
            email="limited@example.com",
            role_name="viewer",
            is_active=True,
            businesses=[{"business_id": 2, "role": "viewer"}],  # Different business
            permissions=["read"],
        )
        limited_mock_client = create_mock_auth_client(
            should_authenticate=True, user_data=limited_user_data
        )
        limited_headers = {"Authorization": "Bearer valid-limited-token"}

        with patch(
            "src.integrations.auth_service_client.get_auth_client",
            return_value=limited_mock_client,
        ):
            with patch(
                "src.middleware.auth_middleware.get_auth_client",
                return_value=limited_mock_client,
            ):
                response = await security_test_client.get(
                    f"/api/v1/projects/{project_id}", headers=limited_headers
                )
                # Should be forbidden due to different business access
                assert response.status_code in [
                    status.HTTP_403_FORBIDDEN,
                    status.HTTP_404_NOT_FOUND,
                ]

    @pytest.mark.asyncio
    async def test_cross_tenant_data_leakage(self, security_test_client):
        """Test prevention of cross-tenant data access."""
        # Create project for business 1
        project_data = {
            "name": "Business 1 Project",
            "budget": 50000.00,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        }

        # User from business 1
        business1_user_data = UserData(
            user_id=1,
            username="user1@business1.com",
            email="user1@business1.com",
            role_name="admin",
            is_active=True,
            businesses=[{"business_id": 1, "role": "admin"}],
            permissions=["read", "write", "admin"],
        )
        business1_mock_client = create_mock_auth_client(
            should_authenticate=True, user_data=business1_user_data
        )
        business1_headers = {"Authorization": "Bearer business1-token"}

        with patch(
            "src.integrations.auth_service_client.get_auth_client",
            return_value=business1_mock_client,
        ):
            with patch(
                "src.middleware.auth_middleware.get_auth_client",
                return_value=business1_mock_client,
            ):
                create_response = await security_test_client.post(
                    "/api/v1/projects/", json=project_data, headers=business1_headers
                )
                assert create_response.status_code == status.HTTP_201_CREATED
                project_id = create_response.json()["id"]

        # User from business 2 trying to access business 1's project
        business2_user_data = UserData(
            user_id=2,
            username="user2@business2.com",
            email="user2@business2.com",
            role_name="admin",
            is_active=True,
            businesses=[{"business_id": 2, "role": "admin"}],
            permissions=["read", "write", "admin"],
        )
        business2_mock_client = create_mock_auth_client(
            should_authenticate=True, user_data=business2_user_data
        )
        business2_headers = {"Authorization": "Bearer business2-token"}

        with patch(
            "src.integrations.auth_service_client.get_auth_client",
            return_value=business2_mock_client,
        ):
            with patch(
                "src.middleware.auth_middleware.get_auth_client",
                return_value=business2_mock_client,
            ):
                access_response = await security_test_client.get(
                    f"/api/v1/projects/{project_id}", headers=business2_headers
                )
                # Should not be able to access cross-tenant data
                assert access_response.status_code in [
                    status.HTTP_403_FORBIDDEN,
                    status.HTTP_404_NOT_FOUND,
                ]


@pytest.mark.security
class TestInputValidationSecurity:
    """Security tests for input validation."""

    @pytest.mark.asyncio
    async def test_sql_injection_prevention(self, security_test_client):
        """Test SQL injection prevention in search parameters."""
        # Create valid auth for this test
        admin_user_data = UserData(
            user_id=1,
            username="admin@example.com",
            email="admin@example.com",
            role_name="admin",
            is_active=True,
            businesses=[{"business_id": 1, "role": "admin"}],
            permissions=["read", "write", "admin"],
        )
        admin_mock_client = create_mock_auth_client(
            should_authenticate=True, user_data=admin_user_data
        )
        auth_headers = {"Authorization": "Bearer valid-admin-token"}

        sql_injection_attempts = [
            "'; DROP TABLE projects; --",
            "1' OR '1'='1",
            "'; UPDATE projects SET budget=0; --",
            "1; DELETE FROM projects; --",
        ]

        for injection_attempt in sql_injection_attempts:
            with patch(
                "src.integrations.auth_service_client.get_auth_client",
                return_value=admin_mock_client,
            ):
                with patch(
                    "src.middleware.auth_middleware.get_auth_client",
                    return_value=admin_mock_client,
                ):
                    response = await security_test_client.post(
                        "/api/v1/projects/",
                        json={
                            "name": injection_attempt,
                            "budget": 50000.00,
                            "start_date": "2024-01-01",
                            "end_date": "2024-12-31",
                        },
                        headers=auth_headers,
                    )
                    # Should either succeed (sanitized) or fail validation, but not cause SQL error
                    assert response.status_code in [
                        status.HTTP_201_CREATED,
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                        status.HTTP_400_BAD_REQUEST,
                    ]

    @pytest.mark.asyncio
    async def test_xss_prevention(self, security_test_client):
        """Test XSS prevention in input fields."""
        # Create valid auth for this test
        admin_user_data = UserData(
            user_id=1,
            username="admin@example.com",
            email="admin@example.com",
            role_name="admin",
            is_active=True,
            businesses=[{"business_id": 1, "role": "admin"}],
            permissions=["read", "write", "admin"],
        )
        admin_mock_client = create_mock_auth_client(
            should_authenticate=True, user_data=admin_user_data
        )
        auth_headers = {"Authorization": "Bearer valid-admin-token"}

        xss_attempts = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "'><script>alert(String.fromCharCode(88,83,83))</script>",
        ]

        for xss_attempt in xss_attempts:
            with patch(
                "src.integrations.auth_service_client.get_auth_client",
                return_value=admin_mock_client,
            ):
                with patch(
                    "src.middleware.auth_middleware.get_auth_client",
                    return_value=admin_mock_client,
                ):
                    response = await security_test_client.post(
                        "/api/v1/projects/",
                        json={
                            "name": xss_attempt,
                            "budget": 50000.00,
                            "start_date": "2024-01-01",
                            "end_date": "2024-12-31",
                        },
                        headers=auth_headers,
                    )
                    # Should either succeed (sanitized) or fail validation
                    assert response.status_code in [
                        status.HTTP_201_CREATED,
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                        status.HTTP_400_BAD_REQUEST,
                    ]

    @pytest.mark.asyncio
    async def test_large_payload_handling(self, security_test_client):
        """Test handling of large payloads."""
        # Create valid auth for this test
        admin_user_data = UserData(
            user_id=1,
            username="admin@example.com",
            email="admin@example.com",
            role_name="admin",
            is_active=True,
            businesses=[{"business_id": 1, "role": "admin"}],
            permissions=["read", "write", "admin"],
        )
        admin_mock_client = create_mock_auth_client(
            should_authenticate=True, user_data=admin_user_data
        )
        auth_headers = {"Authorization": "Bearer valid-admin-token"}

        # Create a large payload
        large_string = "A" * 10000  # 10KB string
        full_data = {
            "name": large_string,
            "budget": 50000.00,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        }

        with patch(
            "src.integrations.auth_service_client.get_auth_client",
            return_value=admin_mock_client,
        ):
            with patch(
                "src.middleware.auth_middleware.get_auth_client",
                return_value=admin_mock_client,
            ):
                response = await security_test_client.post(
                    "/api/v1/projects/", json=full_data, headers=auth_headers
                )
                # Should handle large payloads gracefully
                assert response.status_code in [
                    status.HTTP_201_CREATED,
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    status.HTTP_400_BAD_REQUEST,
                ]


@pytest.mark.security
class TestDataExposureSecurity:
    """Security tests for data exposure prevention."""

    @pytest.mark.asyncio
    async def test_sensitive_data_not_exposed(self, security_test_client):
        """Test that sensitive data is not exposed in responses."""
        # Create valid auth for this test
        admin_user_data = UserData(
            user_id=1,
            username="admin@example.com",
            email="admin@example.com",
            role_name="admin",
            is_active=True,
            businesses=[{"business_id": 1, "role": "admin"}],
            permissions=["read", "write", "admin"],
        )
        admin_mock_client = create_mock_auth_client(
            should_authenticate=True, user_data=admin_user_data
        )
        auth_headers = {"Authorization": "Bearer valid-admin-token"}

        project_data = {
            "name": "Test Project",
            "budget": 50000.00,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        }

        with patch(
            "src.integrations.auth_service_client.get_auth_client",
            return_value=admin_mock_client,
        ):
            with patch(
                "src.middleware.auth_middleware.get_auth_client",
                return_value=admin_mock_client,
            ):
                response = await security_test_client.post(
                    "/api/v1/projects/", json=project_data, headers=auth_headers
                )

                if response.status_code == status.HTTP_201_CREATED:
                    response_data = response.json()
                    # Check that sensitive fields are not exposed
                    sensitive_fields = ["password", "secret", "token", "key", "private"]
                    for field in sensitive_fields:
                        assert field not in str(response_data).lower()

    @pytest.mark.asyncio
    async def test_error_messages_dont_leak_info(self, security_test_client):
        """Test that error messages don't leak sensitive information."""
        # Create valid auth for this test
        admin_user_data = UserData(
            user_id=1,
            username="admin@example.com",
            email="admin@example.com",
            role_name="admin",
            is_active=True,
            businesses=[{"business_id": 1, "role": "admin"}],
            permissions=["read", "write", "admin"],
        )
        admin_mock_client = create_mock_auth_client(
            should_authenticate=True, user_data=admin_user_data
        )
        auth_headers = {"Authorization": "Bearer valid-admin-token"}

        # Test accessing non-existent resource
        non_existent_id = str(uuid4())
        url = f"/api/v1/projects/{non_existent_id}"

        with patch(
            "src.integrations.auth_service_client.get_auth_client",
            return_value=admin_mock_client,
        ):
            with patch(
                "src.middleware.auth_middleware.get_auth_client",
                return_value=admin_mock_client,
            ):
                response = await security_test_client.get(url, headers=auth_headers)

                if response.status_code == status.HTTP_404_NOT_FOUND:
                    error_message = response.json().get("detail", "")
                    # Check that error doesn't leak internal info
                    sensitive_info = [
                        "database",
                        "table",
                        "column",
                        "sql",
                        "internal",
                        "server",
                        "stack",
                        "trace",
                    ]
                    for info in sensitive_info:
                        assert info not in error_message.lower()

    @pytest.mark.asyncio
    async def test_debug_info_not_exposed(self, security_test_client):
        """Test that debug information is not exposed in production-like environment."""
        # Test that debug endpoints are not accessible
        debug_endpoints = [
            "/debug",
            "/api/debug",
            "/api/v1/debug",
            "/_debug",
            "/internal",
        ]

        for endpoint in debug_endpoints:
            response = await security_test_client.get(endpoint)
            # Debug endpoints should not be accessible
            assert response.status_code in [
                status.HTTP_404_NOT_FOUND,
                status.HTTP_405_METHOD_NOT_ALLOWED,
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
            ]
