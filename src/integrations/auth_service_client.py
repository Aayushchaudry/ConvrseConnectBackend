"""
Auth Service Client for ConvrseConnectBackend
Handles communication with the centralized auth-service
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx
import redis.asyncio as aioredis
from fastapi import HTTPException
from jose import JWTError, jwt

from src.config.auth_config import get_auth_config, get_auth_endpoints

logger = logging.getLogger(__name__)


class AuthServiceError(Exception):
    """Base exception for auth service errors"""

    pass


class TokenValidationError(AuthServiceError):
    """Token validation specific errors"""

    pass


class BusinessAccessError(AuthServiceError):
    """Business access specific errors"""

    pass


class PermissionError(AuthServiceError):
    """Permission checking specific errors"""

    pass


@dataclass
class UserData:
    """User data from auth service"""

    user_id: int
    username: str
    email: str
    role_name: str
    is_active: bool
    businesses: List[Dict[str, Any]]
    permissions: List[str]
    business_id: Optional[str] = None  # Direct business ID for single-business users

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserData":
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            email=data["email"],
            role_name=data["role_name"],
            is_active=data.get("is_active", True),
            businesses=data.get("businesses", []),
            permissions=data.get("permissions", []),
            business_id=data.get("business_id"),  # Include direct business_id
        )


@dataclass
class BusinessData:
    """Business data from auth service"""

    business_id: int
    business_name: str
    is_active: bool
    settings: Dict[str, Any]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BusinessData":
        return cls(
            business_id=data["business_id"],
            business_name=data["business_name"],
            is_active=data.get("is_active", True),
            settings=data.get("settings", {}),
        )


class CircuitBreakerState(Enum):
    """Circuit breaker states"""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker for auth service calls"""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED

    def call_succeeded(self):
        """Record successful call"""
        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED

    def call_failed(self):
        """Record failed call"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN

    def can_attempt_call(self) -> bool:
        """Check if call can be attempted"""
        if self.state == CircuitBreakerState.CLOSED:
            return True

        if self.state == CircuitBreakerState.OPEN:
            if (
                datetime.now() - self.last_failure_time
            ).seconds >= self.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                return True
            return False

        # HALF_OPEN state
        return True


class AuthServiceClient:
    """Client for communicating with the auth service"""

    def __init__(self):
        self.config = get_auth_config()
        self.endpoints = get_auth_endpoints()
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=self.config.circuit_breaker_failure_threshold,
            recovery_timeout=self.config.circuit_breaker_recovery_timeout,
        )
        self._http_client: Optional[httpx.AsyncClient] = None
        self._redis_client: Optional[aioredis.Redis] = None

    async def __aenter__(self):
        await self._init_clients()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._close_clients()

    async def _init_clients(self):
        """Initialize HTTP and Redis clients"""
        if self._http_client is None:
            timeout = httpx.Timeout(self.config.auth_service_timeout)
            self._http_client = httpx.AsyncClient(
                timeout=timeout,
                headers={
                    "Authorization": f"Bearer {self.config.auth_service_token}",
                    "Content-Type": "application/json",
                    "X-Service-Name": "convrse-connect-backend",
                },
            )

        if self._redis_client is None:
            try:
                self._redis_client = aioredis.from_url(
                    self.config.redis_url, encoding="utf-8", decode_responses=True
                )
                # Test connection
                await self._redis_client.ping()
                logger.info("Redis connection established for auth caching")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}. Caching disabled.")
                self._redis_client = None

    async def _close_clients(self):
        """Close HTTP and Redis clients"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        if self._redis_client:
            await self._redis_client.aclose()
            self._redis_client = None

    async def _make_request(
        self,
        method: str,
        url: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request with circuit breaker and retry logic"""
        if not self.circuit_breaker.can_attempt_call():
            raise AuthServiceError("Auth service circuit breaker is open")

        await self._init_clients()

        for attempt in range(self.config.auth_service_max_retries):
            try:
                response = await self._http_client.request(
                    method=method, url=url, json=data, params=params
                )

                if response.status_code == 200:
                    self.circuit_breaker.call_succeeded()
                    return response.json()
                elif response.status_code == 401:
                    raise TokenValidationError("Invalid or expired token")
                elif response.status_code == 403:
                    raise PermissionError("Insufficient permissions")
                elif response.status_code == 404:
                    raise AuthServiceError("Resource not found")
                else:
                    raise AuthServiceError(
                        f"Auth service error: {response.status_code}"
                    )

            except httpx.RequestError as e:
                logger.warning(
                    f"Auth service request failed (attempt {attempt + 1}): {e}"
                )
                if attempt == self.config.auth_service_max_retries - 1:
                    self.circuit_breaker.call_failed()
                    raise AuthServiceError(
                        f"Auth service unreachable after {self.config.auth_service_max_retries} attempts"
                    )

                # Exponential backoff
                await asyncio.sleep(2**attempt)

            except Exception as e:
                self.circuit_breaker.call_failed()
                raise AuthServiceError(f"Auth service error: {str(e)}")

    async def _get_from_cache(self, key: str) -> Optional[Dict]:
        """Get data from Redis cache"""
        if not self._redis_client:
            return None

        try:
            cached_data = await self._redis_client.get(key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Cache get error: {e}")

        return None

    async def _set_cache(self, key: str, data: Dict, ttl: int = None):
        """Set data in Redis cache"""
        if not self._redis_client:
            return

        try:
            ttl = ttl or self.config.token_cache_ttl
            await self._redis_client.setex(key, ttl, json.dumps(data, default=str))
        except Exception as e:
            logger.warning(f"Cache set error: {e}")

    async def validate_token(self, token: str) -> UserData:
        """Validate JWT token and return user data"""
        # Check cache first
        cache_key = f"token_validation:{token[:20]}..."
        cached_data = await self._get_from_cache(cache_key)
        if cached_data:
            logger.debug("Token validation served from cache")
            return UserData.from_dict(cached_data)

        try:
            # Validate with auth service
            response = await self._make_request(
                "POST", self.endpoints.validate_token, data={"token": token}
            )

            # If we get here, the token is valid (200 OK)
            user_data = UserData.from_dict(response["user"])

            # Cache the result
            await self._set_cache(cache_key, response["user"])

            logger.info(f"Token validated for user {user_data.user_id}")
            return user_data

        except Exception as e:
            # Check if this is an HTTP error with specific status codes
            if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
                if e.response.status_code == 401:
                    logger.warning(f"Token validation failed - invalid or expired token")
                    raise TokenValidationError("Invalid or expired token")
                elif e.response.status_code == 404:
                    logger.warning(f"Token validation failed - user not found")
                    raise AuthServiceError("User not found")
                elif e.response.status_code >= 500:
                    logger.error(f"Auth service error during token validation: {e}")
                    raise AuthServiceError("Authentication service error")
            
            logger.error(f"Token validation failed: {e}")
            raise TokenValidationError("Token validation failed")

    async def get_user_data(self, user_id: int) -> UserData:
        """Get user data by user ID"""
        cache_key = f"user_data:{user_id}"
        cached_data = await self._get_from_cache(cache_key)
        if cached_data:
            return UserData.from_dict(cached_data)

        try:
            response = await self._make_request(
                "GET", f"{self.endpoints.get_user}?user_id={user_id}"
            )

            user_data = UserData.from_dict(response["user"])
            await self._set_cache(cache_key, response["user"])

            return user_data

        except Exception as e:
            logger.error(f"Failed to get user data for {user_id}: {e}")
            raise

    async def get_user_businesses(self, user_id: int) -> List[BusinessData]:
        """Get businesses accessible to user"""
        cache_key = f"user_businesses:{user_id}"
        cached_data = await self._get_from_cache(cache_key)
        if cached_data:
            return [BusinessData.from_dict(b) for b in cached_data]

        try:
            response = await self._make_request(
                "GET", f"{self.endpoints.get_user_businesses}?user_id={user_id}"
            )

            businesses = [BusinessData.from_dict(b) for b in response["businesses"]]
            await self._set_cache(cache_key, response["businesses"])

            return businesses

        except Exception as e:
            logger.error(f"Failed to get user businesses for {user_id}: {e}")
            raise

    async def check_permissions(
        self, user_id: int, business_id: int, permissions: List[str]
    ) -> bool:
        """Check if user has required permissions for business"""
        cache_key = f"permissions:{user_id}:{business_id}:{':'.join(permissions)}"
        cached_result = await self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result.get("has_permission", False)

        try:
            response = await self._make_request(
                "POST",
                self.endpoints.check_permissions,
                data={
                    "user_id": user_id,
                    "business_id": business_id,
                    "permissions": permissions,
                },
            )

            has_permission = response.get("has_permission", False)

            # Cache for shorter time due to permission sensitivity
            await self._set_cache(
                cache_key,
                {"has_permission": has_permission},
                ttl=60,  # 1 minute cache for permissions
            )

            return has_permission

        except Exception as e:
            logger.error(f"Permission check failed for user {user_id}: {e}")
            raise

    async def validate_business_access(self, user_id: int, business_id: int) -> bool:
        """Validate if user has access to business"""
        try:
            businesses = await self.get_user_businesses(user_id)
            business_ids = [b.business_id for b in businesses if b.is_active]
            return business_id in business_ids
        except Exception as e:
            logger.error(f"Business access validation failed: {e}")
            return False

    async def log_activity(
        self, user_id: int, business_id: int, action: str, details: Dict[str, Any]
    ):
        """Log user activity for audit trail"""
        if not self.config.audit_logging_enabled:
            return

        try:
            await self._make_request(
                "POST",
                self.endpoints.log_activity,
                data={
                    "user_id": user_id,
                    "business_id": business_id,
                    "action": action,
                    "details": details,
                    "timestamp": datetime.now().isoformat(),
                    "service": "convrse-connect-backend",
                },
            )

            logger.debug(f"Activity logged: {action} for user {user_id}")

        except Exception as e:
            # Don't fail the main operation if activity logging fails
            logger.error(f"Activity logging failed: {e}")

    async def check_user_permission(self, user_id: str, permission: str, auth_token: str = None) -> bool:
        """
        Check if user has specific permission using user's token.
        
        Args:
            user_id: User ID to check
            permission: Permission string to check
            auth_token: User's JWT token for authentication
            
        Returns:
            True if user has permission, False otherwise
        """
        try:
            # Prepare headers with user's token
            headers = {
                "Content-Type": "application/json",
                "X-Service-Name": "convrse-connect-backend",
            }
            
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"
            else:
                # Fallback to service token
                headers["Authorization"] = f"Bearer {self.config.auth_service_token}"
            
            # Make request with user's token
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.config.auth_service_timeout)) as client:
                response = await client.post(
                    f"{self.config.auth_service_url}/integration/check-permission",
                    json={"user_id": user_id, "permission": permission},
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get("has_permission", False)
                elif response.status_code == 401:
                    raise TokenValidationError("Invalid or expired token")
                elif response.status_code == 403:
                    return False  # No permission
                else:
                    logger.warning(f"Unexpected response from permission check: {response.status_code}")
                    return False
                    
        except TokenValidationError:
            raise
        except Exception as e:
            logger.error(f"Permission check failed for user {user_id}, permission {permission}: {e}")
            return False

    async def health_check(self) -> bool:
        """Check auth service health"""
        try:
            response = await self._make_request("GET", self.endpoints.health)
            return response.get("status") in ["ok", "healthy"]
        except Exception as e:
            logger.error(f"Auth service health check failed: {e}")
            return False


# Global auth service client instance
_auth_client: Optional[AuthServiceClient] = None


async def get_auth_client() -> AuthServiceClient:
    """Get the global auth service client instance"""
    global _auth_client

    if _auth_client is None:
        _auth_client = AuthServiceClient()
        await _auth_client._init_clients()

    return _auth_client


async def close_auth_client():
    """Close the global auth service client"""
    global _auth_client

    if _auth_client:
        await _auth_client._close_clients()
        _auth_client = None
