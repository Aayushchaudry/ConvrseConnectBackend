"""
Auth integration endpoints for ConvrseConnectBackend
Provides endpoints for token validation, user profile, and business context
"""
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel

from src.middleware.auth_middleware import (
    get_current_auth, 
    require_auth, 
    AuthContext
)
from src.integrations.auth_service_client import get_auth_client, AuthServiceError
from src.services.activity_logger import log_system_activity


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integration", tags=["Auth Integration"])


# Response models
class TokenValidationResponse(BaseModel):
    """Response model for token validation"""
    valid: bool
    user_id: int = None
    username: str = None
    email: str = None
    role_name: str = None
    businesses: List[Dict[str, Any]] = []
    permissions: List[str] = []


class UserProfileResponse(BaseModel):
    """Response model for user profile"""
    user_id: int
    username: str
    email: str
    role_name: str
    is_active: bool
    businesses: List[Dict[str, Any]]
    permissions: List[str]


class BusinessListResponse(BaseModel):
    """Response model for user businesses"""
    businesses: List[Dict[str, Any]]


class HealthCheckResponse(BaseModel):
    """Response model for health check"""
    status: str
    service: str
    auth_service_healthy: bool
    timestamp: str


@router.post("/auth/validate", response_model=TokenValidationResponse)
async def validate_token(
    request: Request,
    auth: AuthContext = Depends(get_current_auth)
):
    """
    Validate the current token and return user information
    This endpoint can be used by other services to validate tokens
    """
    try:
        if not auth.is_authenticated:
            return TokenValidationResponse(valid=False)
        
        # Log the validation request
        await log_system_activity(
            auth_context=auth,
            action="token_validated",
            details={"endpoint": "/integration/auth/validate"},
            request=request
        )
        
        return TokenValidationResponse(
            valid=True,
            user_id=auth.user.user_id,
            username=auth.user.username,
            email=auth.user.email,
            role_name=auth.user.role_name,
            businesses=auth.user.businesses,
            permissions=auth.user.permissions
        )
        
    except Exception as e:
        logger.error(f"Token validation endpoint error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token validation failed"
        )


@router.get("/user/profile", response_model=UserProfileResponse)
async def get_user_profile(
    request: Request,
    auth: AuthContext = Depends(require_auth)
):
    """
    Get the current user's profile information
    Requires authentication
    """
    try:
        # Log the profile access
        await log_system_activity(
            auth_context=auth,
            action="profile_accessed",
            details={"endpoint": "/integration/user/profile"},
            request=request
        )
        
        return UserProfileResponse(
            user_id=auth.user.user_id,
            username=auth.user.username,
            email=auth.user.email,
            role_name=auth.user.role_name,
            is_active=auth.user.is_active,
            businesses=auth.user.businesses,
            permissions=auth.user.permissions
        )
        
    except Exception as e:
        logger.error(f"User profile endpoint error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user profile"
        )


@router.get("/user/businesses", response_model=BusinessListResponse)
async def get_user_businesses(
    request: Request,
    auth: AuthContext = Depends(require_auth)
):
    """
    Get businesses accessible to the current user
    Requires authentication
    """
    try:
        # Fetch fresh business data from auth service
        auth_client = await get_auth_client()
        businesses = await auth_client.get_user_businesses(auth.user.user_id)
        
        # Convert to dict format
        business_data = [
            {
                "business_id": b.business_id,
                "business_name": b.business_name,
                "is_active": b.is_active,
                "settings": b.settings
            }
            for b in businesses
        ]
        
        # Log the business access
        await log_system_activity(
            auth_context=auth,
            action="businesses_accessed",
            details={
                "endpoint": "/integration/user/businesses",
                "business_count": len(business_data)
            },
            request=request
        )
        
        return BusinessListResponse(businesses=business_data)
        
    except AuthServiceError as e:
        logger.error(f"Auth service error in businesses endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service temporarily unavailable"
        )
    except Exception as e:
        logger.error(f"User businesses endpoint error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user businesses"
        )


@router.get("/health", response_model=HealthCheckResponse)
async def auth_integration_health():
    """
    Health check for auth integration
    Tests connectivity to auth-service
    """
    try:
        # Check auth service health
        auth_client = await get_auth_client()
        auth_service_healthy = await auth_client.health_check()
        
        from datetime import datetime
        
        return HealthCheckResponse(
            status="ok",
            service="convrse-connect-backend-auth-integration",
            auth_service_healthy=auth_service_healthy,
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Auth integration health check failed: {e}")
        return HealthCheckResponse(
            status="error",
            service="convrse-connect-backend-auth-integration",
            auth_service_healthy=False,
            timestamp=datetime.now().isoformat()
        ) 