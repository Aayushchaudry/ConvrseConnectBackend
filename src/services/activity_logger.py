"""
Activity Logger Service for ConvrseConnectBackend
Handles activity logging for audit trails
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import Request

from src.config.database import get_db_session
from src.integrations.auth_service_client import get_auth_client
from src.middleware.auth_middleware import AuthContext
from src.models.activity_logs import ActivityLog

logger = logging.getLogger(__name__)


class ActivityLoggerService:
    """Service for logging user activities and system events"""

    @staticmethod
    async def log_activity(
        auth_context: AuthContext,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        request: Optional[Request] = None,
    ):
        """
        Log a user activity for audit trail

        Args:
            auth_context: Authentication context with user and business info
            action: Action performed (e.g., "project_created", "deliverable_updated")
            resource_type: Type of resource (e.g., "project", "deliverable")
            resource_id: ID of the affected resource (optional)
            details: Additional context as dictionary (optional)
            request: FastAPI request object for IP/user agent (optional)
        """
        try:
            # Only log if user is authenticated
            if not auth_context.is_authenticated:
                return

            # Extract request information if available
            ip_address = None
            user_agent = None
            if request:
                ip_address = request.client.host if request.client else None
                user_agent = request.headers.get("user-agent")

            # Determine business_id
            business_id = auth_context.business_id
            if not business_id and auth_context.user.businesses:
                # Use first business if no specific business context
                business_id = auth_context.user.businesses[0].get("business_id")

            if not business_id:
                logger.warning(
                    f"No business context for activity logging: user {auth_context.user_id}"
                )
                return

            # Create activity log entry
            activity_log = ActivityLog(
                user_id=auth_context.user_id,
                business_id=business_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details or {},
                ip_address=ip_address,
                user_agent=user_agent,
                correlation_id=auth_context.correlation_id,
            )

            # Save to database
            async for session in get_db_session():
                session.add(activity_log)
                await session.commit()
                break

            logger.debug(f"Activity logged: {action} by user {auth_context.user_id}")

            # Also log to auth-service for centralized audit
            try:
                auth_client = await get_auth_client()
                await auth_client.log_activity(
                    user_id=auth_context.user_id,
                    business_id=business_id,
                    action=action,
                    details={
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "service": "convrse-connect-backend",
                        "correlation_id": auth_context.correlation_id,
                        **(details or {}),
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to log activity to auth-service: {e}")
                # Don't fail the main operation

        except Exception as e:
            logger.error(f"Failed to log activity: {e}")
            # Don't fail the main operation


# Convenience functions for common activities


async def log_project_activity(
    auth_context: AuthContext,
    action: str,
    project_id: str,
    details: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
):
    """Log project-related activity"""
    await ActivityLoggerService.log_activity(
        auth_context=auth_context,
        action=action,
        resource_type="project",
        resource_id=project_id,
        details=details,
        request=request,
    )


async def log_deliverable_activity(
    auth_context: AuthContext,
    action: str,
    deliverable_id: str,
    details: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
):
    """Log deliverable-related activity"""
    await ActivityLoggerService.log_activity(
        auth_context=auth_context,
        action=action,
        resource_type="deliverable",
        resource_id=deliverable_id,
        details=details,
        request=request,
    )


async def log_system_activity(
    auth_context: AuthContext,
    action: str,
    details: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
):
    """Log system-level activity"""
    await ActivityLoggerService.log_activity(
        auth_context=auth_context,
        action=action,
        resource_type="system",
        details=details,
        request=request,
    )
