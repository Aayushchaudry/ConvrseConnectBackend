"""
Notification API routes for ConvrseConnectBackend
Provides endpoints for notification management and real-time updates
"""

from fastapi import APIRouter, HTTPException, Depends, Query, status
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from ..auth.dependencies import get_current_user
from ..services.notification_service import get_notification_service, NotificationService, NotificationType

# Create router for notification endpoints
notification_router = APIRouter(prefix="/notifications", tags=["Notifications"])


class NotificationRequest(BaseModel):
    """Request model for sending notifications"""
    project_id: str = Field(..., description="Project ID to send notification to")
    title: str = Field(..., min_length=1, max_length=200, description="Notification title")
    message: str = Field(..., min_length=1, max_length=1000, description="Notification message")
    notification_type: str = Field(default="INFO", description="Notification type")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Additional notification data")


class CommentNotificationRequest(BaseModel):
    """Request model for comment notifications"""
    project_id: str = Field(..., description="Project ID")
    comment_data: Dict[str, Any] = Field(..., description="Comment data")
    user_name: Optional[str] = Field(default="Unknown User", description="User who made the comment")


class TaskUpdateNotificationRequest(BaseModel):
    """Request model for task update notifications"""
    project_id: str = Field(..., description="Project ID")
    task_data: Dict[str, Any] = Field(..., description="Task data")
    action: str = Field(default="updated", description="Action performed on task")
    user_name: Optional[str] = Field(default="Unknown User", description="User who updated the task")


class SystemNotificationRequest(BaseModel):
    """Request model for system notifications"""
    project_id: str = Field(..., description="Project ID")
    title: str = Field(..., min_length=1, max_length=200, description="Notification title")
    message: str = Field(..., min_length=1, max_length=1000, description="Notification message")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Additional notification data")


class NotificationResponse(BaseModel):
    """Response model for notifications"""
    success: bool
    message: str
    notification_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


@notification_router.post(
    "/send",
    response_model=NotificationResponse,
    summary="Send notification",
    description="Send a notification to all users in a project"
)
async def send_notification(
    request: NotificationRequest,
    current_user: dict = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Send a notification to project users"""
    try:
        # Validate notification type
        try:
            notification_type = NotificationType(request.notification_type.upper())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid notification type: {request.notification_type}"
            )
        
        result = await notification_service.send_notification(
            project_id=request.project_id,
            notification_type=notification_type,
            title=request.title,
            message=request.message,
            user_id=current_user.get("user_id"),
            data=request.data
        )
        
        return NotificationResponse(
            success=True,
            message="Notification sent successfully",
            data=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send notification: {str(e)}"
        )


@notification_router.post(
    "/comment",
    response_model=NotificationResponse,
    summary="Send comment notification",
    description="Send a notification when a comment is added"
)
async def send_comment_notification(
    request: CommentNotificationRequest,
    current_user: dict = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Send a comment notification"""
    try:
        result = await notification_service.send_comment_notification(
            project_id=request.project_id,
            comment_data=request.comment_data,
            user_name=request.user_name or current_user.get("full_name", "Unknown User")
        )
        
        return NotificationResponse(
            success=True,
            message="Comment notification sent successfully",
            data=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send comment notification: {str(e)}"
        )


@notification_router.post(
    "/task-update",
    response_model=NotificationResponse,
    summary="Send task update notification",
    description="Send a notification when a task is updated"
)
async def send_task_update_notification(
    request: TaskUpdateNotificationRequest,
    current_user: dict = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Send a task update notification"""
    try:
        result = await notification_service.send_task_update_notification(
            project_id=request.project_id,
            task_data=request.task_data,
            action=request.action,
            user_name=request.user_name or current_user.get("full_name", "Unknown User")
        )
        
        return NotificationResponse(
            success=True,
            message="Task update notification sent successfully",
            data=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send task update notification: {str(e)}"
        )


@notification_router.post(
    "/system",
    response_model=NotificationResponse,
    summary="Send system notification",
    description="Send a system notification to project users"
)
async def send_system_notification(
    request: SystemNotificationRequest,
    current_user: dict = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Send a system notification"""
    try:
        result = await notification_service.send_system_notification(
            project_id=request.project_id,
            title=request.title,
            message=request.message,
            data=request.data
        )
        
        return NotificationResponse(
            success=True,
            message="System notification sent successfully",
            data=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send system notification: {str(e)}"
        )


@notification_router.post(
    "/success",
    response_model=NotificationResponse,
    summary="Send success notification",
    description="Send a success notification to project users"
)
async def send_success_notification(
    request: SystemNotificationRequest,
    current_user: dict = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Send a success notification"""
    try:
        result = await notification_service.send_success_notification(
            project_id=request.project_id,
            title=request.title,
            message=request.message,
            data=request.data
        )
        
        return NotificationResponse(
            success=True,
            message="Success notification sent successfully",
            data=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send success notification: {str(e)}"
        )


@notification_router.post(
    "/error",
    response_model=NotificationResponse,
    summary="Send error notification",
    description="Send an error notification to project users"
)
async def send_error_notification(
    request: SystemNotificationRequest,
    current_user: dict = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Send an error notification"""
    try:
        result = await notification_service.send_error_notification(
            project_id=request.project_id,
            title=request.title,
            message=request.message,
            error_data=request.data
        )
        
        return NotificationResponse(
            success=True,
            message="Error notification sent successfully",
            data=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send error notification: {str(e)}"
        )


@notification_router.get(
    "/user",
    summary="Get user notifications",
    description="Get notifications for the current user"
)
async def get_user_notifications(
    limit: int = Query(50, ge=1, le=100, description="Number of notifications to retrieve"),
    offset: int = Query(0, ge=0, description="Number of notifications to skip"),
    unread_only: bool = Query(False, description="Only return unread notifications"),
    current_user: dict = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Get notifications for the current user"""
    try:
        notifications = await notification_service.get_user_notifications(
            user_id=current_user.get("user_id"),
            limit=limit,
            offset=offset,
            unread_only=unread_only
        )
        
        return {
            "success": True,
            "notifications": notifications,
            "limit": limit,
            "offset": offset,
            "unread_only": unread_only
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user notifications: {str(e)}"
        )


@notification_router.get(
    "/project/{project_id}",
    summary="Get project notifications",
    description="Get notifications for a specific project"
)
async def get_project_notifications(
    project_id: str,
    limit: int = Query(50, ge=1, le=100, description="Number of notifications to retrieve"),
    offset: int = Query(0, ge=0, description="Number of notifications to skip"),
    current_user: dict = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Get notifications for a specific project"""
    try:
        notifications = await notification_service.get_project_notifications(
            project_id=project_id,
            limit=limit,
            offset=offset
        )
        
        return {
            "success": True,
            "project_id": project_id,
            "notifications": notifications,
            "limit": limit,
            "offset": offset
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get project notifications: {str(e)}"
        )


@notification_router.get(
    "/unread-count",
    summary="Get unread notification count",
    description="Get the count of unread notifications for the current user"
)
async def get_unread_count(
    current_user: dict = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Get unread notification count for the current user"""
    try:
        count = await notification_service.get_unread_count(
            user_id=current_user.get("user_id")
        )
        
        return {
            "success": True,
            "unread_count": count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get unread count: {str(e)}"
        )


@notification_router.patch(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    summary="Mark notification as read",
    description="Mark a specific notification as read"
)
async def mark_notification_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Mark a notification as read"""
    try:
        result = await notification_service.mark_notification_read(
            notification_id=notification_id,
            user_id=current_user.get("user_id")
        )
        
        return NotificationResponse(
            success=True,
            message="Notification marked as read",
            data=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to mark notification as read: {str(e)}"
        )


@notification_router.patch(
    "/mark-all-read",
    response_model=NotificationResponse,
    summary="Mark all notifications as read",
    description="Mark all notifications as read for the current user"
)
async def mark_all_notifications_read(
    current_user: dict = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Mark all notifications as read for the current user"""
    try:
        result = await notification_service.mark_all_notifications_read(
            user_id=current_user.get("user_id")
        )
        
        return NotificationResponse(
            success=True,
            message="All notifications marked as read",
            data=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to mark all notifications as read: {str(e)}"
        )


@notification_router.delete(
    "/{notification_id}",
    response_model=NotificationResponse,
    summary="Delete notification",
    description="Delete a specific notification"
)
async def delete_notification(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Delete a notification"""
    try:
        result = await notification_service.delete_notification(
            notification_id=notification_id,
            user_id=current_user.get("user_id")
        )
        
        return NotificationResponse(
            success=True,
            message="Notification deleted successfully",
            data=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete notification: {str(e)}"
        )


@notification_router.get(
    "/connected-users/{project_id}",
    summary="Get connected users",
    description="Get list of users connected to a project via WebSocket"
)
async def get_connected_users(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Get list of users connected to a project"""
    try:
        users = await notification_service.get_connected_users(project_id=project_id)
        
        return {
            "success": True,
            "project_id": project_id,
            "connected_users": users
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get connected users: {str(e)}"
        ) 