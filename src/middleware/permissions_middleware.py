"""
Permission enforcement middleware for ConvrseConnectBackend
Validates permissions against auth-service database - NO HARDCODED LOGIC
"""

import logging
from typing import List, Optional

from fastapi import HTTPException, Request, status, Depends
from src.middleware.auth_middleware import AuthContext, require_auth
from src.integrations.auth_service_client import get_auth_client, AuthServiceError

logger = logging.getLogger(__name__)


async def check_user_permission(user_id: str, permission: str, auth_token: str = None) -> bool:
    """
    Check if user has specific permission via auth-service client.
    Pure database-driven - no hardcoded logic.
    
    Args:
        user_id: User ID (UUID string) to check
        permission: Permission string (e.g., "connect.projects.read")
        auth_token: JWT token for authentication
    
    Returns:
        True if user has permission, False otherwise
    """
    try:
        auth_client = await get_auth_client()
        
        # Use the new check_user_permission method
        has_permission = await auth_client.check_user_permission(
            user_id=user_id,
            permission=permission,
            auth_token=auth_token
        )
        
        if has_permission:
            logger.info(f"User {user_id} granted permission: {permission}")
        else:
            logger.warning(f"User {user_id} denied permission: {permission}")
            
        return has_permission
        
    except Exception as e:
        logger.error(f"Permission check failed for user {user_id}, permission {permission}: {e}")
        return False


async def check_user_permissions(user_id: str, permissions: List[str], auth_token: str = None) -> bool:
    """
    Check if user has all specified permissions via auth-service client.
    Pure database-driven - no hardcoded logic.
    
    Args:
        user_id: User ID (UUID string) to check
        permissions: List of permission strings
        auth_token: JWT token for authentication
    
    Returns:
        True if user has all permissions, False otherwise
    """
    if not permissions:
        return True
        
    try:
        # Check each permission individually for better error reporting
        for permission in permissions:
            has_permission = await check_user_permission(user_id, permission, auth_token)
            if not has_permission:
                logger.warning(f"User {user_id} denied permission: {permission}")
                return False
        
        logger.info(f"User {user_id} granted all permissions: {permissions}")
        return True
        
    except Exception as e:
        logger.error(f"Permissions check failed for user {user_id}, permissions {permissions}: {e}")
        return False


def require_permission(permission: str):
    """
    FastAPI dependency factory for permission checking.
    Pure database-driven - no hardcoded logic.
    
    Args:
        permission: Required permission string
        
    Returns:
        FastAPI dependency function
    """
    async def permission_dependency(auth_context: AuthContext = Depends(require_auth)):
        """Check if current user has required permission"""
        
        has_permission = await check_user_permission(
            user_id=str(auth_context.user_id),
            permission=permission,
            auth_token=auth_context.token  # Pass the auth token
        )
        
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission}"
            )
        
        return auth_context
    
    return permission_dependency


def require_permissions(permissions: List[str]):
    """
    FastAPI dependency factory for multiple permission checking.
    Pure database-driven - no hardcoded logic.
    
    Args:
        permissions: List of required permission strings
        
    Returns:
        FastAPI dependency function
    """
    async def permissions_dependency(auth_context: AuthContext = Depends(require_auth)):
        """Check if current user has all required permissions"""
        
        has_permissions = await check_user_permissions(
            user_id=str(auth_context.user_id),
            permissions=permissions,
            auth_token=auth_context.token  # Pass the auth token
        )
        
        if not has_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permissions required: {', '.join(permissions)}"
            )
        
        return auth_context
    
    return permissions_dependency


def require_resource_permission(resource_type: str, action: str):
    """
    FastAPI dependency factory for resource-action based permissions.
    Pure database-driven - no hardcoded logic.
    
    Args:
        resource_type: Resource type (e.g., "projects", "deliverables", "requirements")
        action: Action (e.g., "read", "create", "update", "delete")
        
    Returns:
        FastAPI dependency function
    """
    permission = f"connect.{resource_type}.{action}"
    return require_permission(permission)


def require_resource_business_permission(resource_type_or_permission: str, action: str = None):
    """
    FastAPI dependency factory for resource-business permission checking.
    Ensures user has permission and proper business context.
    Pure database-driven - no hardcoded logic.
    
    Args:
        resource_type_or_permission: Either a full permission string (e.g., "connect.projects.read") 
                                   OR resource type (e.g., "projects", "requirements")
        action: Action (e.g., "read", "create") - only used when first arg is resource_type
        
    Returns:
        FastAPI dependency function
    """
    # Determine the permission string based on arguments
    if action is None:
        # Single permission string provided
        permission = resource_type_or_permission
    else:
        # Resource type and action provided
        permission = f"connect.{resource_type_or_permission}.{action}"
    
    async def business_permission_dependency(
        request: Request,
        auth_context: AuthContext = Depends(require_auth)
    ):
        """Check if current user has required permission for business resource"""
        
        # Extract business identifier from request headers or domain
        business_id = request.headers.get("X-Business-Identifier")
        
        # Check basic permission first
        has_permission = await check_user_permission(
            user_id=str(auth_context.user_id),
            permission=permission,
            auth_token=auth_context.token
        )
        
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission}"
            )
        
        # Add business context to auth_context if needed
        auth_context.business_id = business_id
        return auth_context
    
    return business_permission_dependency


# Convenience functions for common ConvrseConnect permissions
def require_projects_read():
    """Require connect.projects.read permission"""
    return require_permission("connect.projects.read")


def require_projects_write():
    """Require connect.projects.create/update permissions"""
    return require_any_permission(["connect.projects.create", "connect.projects.update"])


def require_deliverables_read():
    """Require connect.deliverables.read permission"""
    return require_permission("connect.deliverables.read")


def require_deliverables_write():
    """Require connect.deliverables.create/update permissions"""
    return require_any_permission(["connect.deliverables.create", "connect.deliverables.update"])


def require_comments_access():
    """Require connect.comments read/write permissions"""
    return require_any_permission(["connect.comments.read", "connect.comments.create"])


def require_tasks_access():
    """Require connect.tasks read/write permissions"""
    return require_any_permission(["connect.tasks.read", "connect.tasks.create"])


def require_reviews_access():
    """Require connect.reviews permissions"""
    return require_any_permission([
        "connect.reviews.approve", 
        "connect.reviews.comment", 
        "connect.reviews.reject"
    ])


def require_outputs_access():
    """Require connect.outputs read/write permissions"""
    return require_any_permission(["connect.outputs.read", "connect.outputs.create"]) 