"""
Authentication middleware for ConvrseConnectBackend
Handles JWT token validation and user context injection
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Callable, List, Optional

from fastapi import HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware

from src.config.auth_config import get_auth_config
from src.integrations.auth_service_client import (
    AuthServiceError,
    TokenValidationError,
    UserData,
    get_auth_client,
)

logger = logging.getLogger(__name__)
security = HTTPBearer()


class AuthContext:
    """Authentication context for request processing"""

    def __init__(
        self,
        user: Optional[UserData] = None,
        token: Optional[str] = None,
        correlation_id: Optional[str] = None,
        business_id: Optional[int] = None,
    ):
        self.user = user
        self.token = token
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.business_id = business_id
        self.request_time = datetime.now()

    @property
    def is_authenticated(self) -> bool:
        """Check if user is authenticated"""
        return self.user is not None and self.user.is_active

    @property
    def is_super_admin(self) -> bool:
        """Check if user is super admin"""
        return self.user and self.user.role_name == "super_admin"

    @property
    def user_id(self) -> Optional[int]:
        """Get user ID"""
        return self.user.user_id if self.user else None

    @property
    def username(self) -> Optional[str]:
        """Get username"""
        return self.user.username if self.user else None

    def has_business_access(self, business_id: int) -> bool:
        """Check if user has access to specific business"""
        if self.is_super_admin:
            return True

        if not self.user or not self.user.businesses:
            return False

        business_ids = [b.get("business_id") for b in self.user.businesses]
        return business_id in business_ids

    def get_accessible_business_ids(self) -> List[int]:
        """Get list of accessible business IDs"""
        if not self.user or not self.user.businesses:
            return []

        return [
            b.get("business_id")
            for b in self.user.businesses
            if b.get("is_active", True)
        ]


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Middleware for JWT token validation and user context injection"""

    def __init__(self, app, exclude_paths: Optional[List[str]] = None):
        super().__init__(app)
        self.config = get_auth_config()
        self.exclude_paths = exclude_paths or [
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/api/v1/health",
        ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with authentication"""
        # Generate correlation ID for request tracking
        correlation_id = str(uuid.uuid4())

        # Add correlation ID to request headers for logging
        request.state.correlation_id = correlation_id

        # Check if path should be excluded from authentication
        if self._should_exclude_path(request.url.path):
            logger.debug(f"Skipping auth for excluded path: {request.url.path}")
            request.state.auth = AuthContext(correlation_id=correlation_id)
            return await call_next(request)

        try:
            # Extract and validate token
            auth_context = await self._authenticate_request(request, correlation_id)
            request.state.auth = auth_context

            # Log successful authentication
            if auth_context.is_authenticated:
                logger.info(
                    f"User {auth_context.user_id} authenticated for {request.method} {request.url.path}",
                    extra={
                        "correlation_id": correlation_id,
                        "user_id": auth_context.user_id,
                        "username": auth_context.username,
                        "endpoint": f"{request.method} {request.url.path}",
                    },
                )

            response = await call_next(request)

            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = correlation_id

            return response

        except TokenValidationError as e:
            logger.warning(
                f"Token validation failed: {e}",
                extra={"correlation_id": correlation_id, "path": request.url.path},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"X-Correlation-ID": correlation_id},
            )

        except AuthServiceError as e:
            logger.error(
                f"Auth service error: {e}",
                extra={"correlation_id": correlation_id, "path": request.url.path},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable",
                headers={"X-Correlation-ID": correlation_id},
            )

        except Exception as e:
            logger.error(
                f"Authentication middleware error: {e}",
                extra={"correlation_id": correlation_id, "path": request.url.path},
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal authentication error",
                headers={"X-Correlation-ID": correlation_id},
            )

    def _should_exclude_path(self, path: str) -> bool:
        """Check if path should be excluded from authentication"""
        for exclude_path in self.exclude_paths:
            if path.startswith(exclude_path):
                return True
        return False

    async def _authenticate_request(
        self, request: Request, correlation_id: str
    ) -> AuthContext:
        """Authenticate request and return auth context"""
        # Extract token from header
        token = self._extract_token(request)

        if not token:
            logger.debug("No token provided in request")
            return AuthContext(correlation_id=correlation_id)

        # Validate token with auth service
        try:
            auth_client = await get_auth_client()
            user_data = await auth_client.validate_token(token)

            # Extract business ID from query params or headers if present
            business_id = self._extract_business_id(request)

            return AuthContext(
                user=user_data,
                token=token,
                correlation_id=correlation_id,
                business_id=business_id,
            )

        except (TokenValidationError, AuthServiceError):
            # Re-raise these as they should be handled by the outer exception handler
            raise
        except Exception as e:
            # Convert other exceptions (like JWT exceptions) to TokenValidationError
            import jwt

            if isinstance(
                e, (jwt.ExpiredSignatureError, jwt.InvalidTokenError, jwt.DecodeError)
            ):
                logger.error(f"Token validation failed: {e}")
                raise TokenValidationError(str(e))
            else:
                logger.error(f"Token validation failed: {e}")
                raise TokenValidationError(str(e))

    def _extract_token(self, request: Request) -> Optional[str]:
        """Extract JWT token from request headers"""
        auth_header = request.headers.get(self.config.auth_header_name)

        if not auth_header:
            return None

        try:
            scheme, token = auth_header.split(" ", 1)
            if scheme.lower() != self.config.auth_header_prefix.lower():
                return None
            return token
        except ValueError:
            return None

    def _extract_business_id(self, request: Request) -> Optional[int]:
        """Extract business ID from request"""
        # Try query parameter first
        business_id = request.query_params.get("business_id")
        if business_id:
            try:
                return int(business_id)
            except ValueError:
                pass

        # Try header
        business_id = request.headers.get("X-Business-ID")
        if business_id:
            try:
                return int(business_id)
            except ValueError:
                pass

        return None


def get_current_auth(request: Request) -> AuthContext:
    """Get authentication context from request"""
    return getattr(request.state, "auth", AuthContext())


def require_auth(request: Request) -> AuthContext:
    """Require authentication and return auth context"""
    auth = get_current_auth(request)

    if not auth.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )

    return auth


def require_business_access(request: Request, business_id: int) -> AuthContext:
    """Require business access and return auth context"""
    auth = require_auth(request)

    if not auth.has_business_access(business_id):
        logger.warning(
            f"User {auth.user_id} denied access to business {business_id}",
            extra={
                "correlation_id": auth.correlation_id,
                "user_id": auth.user_id,
                "requested_business_id": business_id,
                "user_businesses": auth.get_accessible_business_ids(),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to requested business",
        )

    return auth


def require_super_admin(request: Request) -> AuthContext:
    """Require super admin role and return auth context"""
    auth = require_auth(request)

    if not auth.is_super_admin:
        logger.warning(
            f"User {auth.user_id} denied super admin access",
            extra={
                "correlation_id": auth.correlation_id,
                "user_id": auth.user_id,
                "user_role": auth.user.role_name if auth.user else None,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required"
        )

    return auth


# Dependency for FastAPI endpoints
def get_auth_dependency():
    """FastAPI dependency for authentication"""

    def auth_dependency(request: Request) -> AuthContext:
        return get_current_auth(request)

    return auth_dependency


def get_required_auth_dependency():
    """FastAPI dependency for required authentication"""

    def required_auth_dependency(request: Request) -> AuthContext:
        return require_auth(request)

    return required_auth_dependency


def get_business_auth_dependency(business_id: int):
    """FastAPI dependency for business-specific authentication"""

    def business_auth_dependency(request: Request) -> AuthContext:
        return require_business_access(request, business_id)

    return business_auth_dependency


def get_super_admin_dependency():
    """FastAPI dependency for super admin authentication"""

    def super_admin_dependency(request: Request) -> AuthContext:
        return require_super_admin(request)

    return super_admin_dependency


# WebSocket Authentication Functions
async def get_websocket_user(websocket, token: Optional[str] = None, user_id: Optional[str] = None) -> dict:
    """
    Authenticate WebSocket connection using token from query parameters.
    
    Args:
        websocket: The WebSocket connection
        token: JWT token from query parameters
        user_id: User ID from query parameters (optional)
    
    Returns:
        dict: User information for WebSocket connection
    
    Raises:
        WebSocketException: If authentication fails
    """
    from fastapi import WebSocketException, status
    
    # Extract token from query parameters if not provided
    if not token:
        query_params = dict(websocket.query_params)
        token = query_params.get("token")
    
    if not token:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Authentication token required"
        )
    
    try:
        # Validate token with auth service
        auth_client = await get_auth_client()
        user_data = await auth_client.validate_token(token)
        
        if not user_data or not user_data.is_active:
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Invalid or inactive user"
            )
        
        return {
            "user_id": user_data.user_id,
            "user_name": user_data.username,
            "business_ids": [b.get("business_id") for b in user_data.businesses] if user_data.businesses else [],
            "is_super_admin": user_data.role_name == "super_admin",
            "token": token
        }
        
    except TokenValidationError as e:
        logger.warning(f"WebSocket token validation failed: {e}")
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid or expired token"
        )
    except AuthServiceError as e:
        logger.error(f"WebSocket auth service error: {e}")
        raise WebSocketException(
            code=status.WS_1011_INTERNAL_ERROR,
            reason="Authentication service error"
        )
    except Exception as e:
        logger.error(f"WebSocket authentication error: {e}")
        raise WebSocketException(
            code=status.WS_1011_INTERNAL_ERROR,
            reason="Authentication failed"
        )
