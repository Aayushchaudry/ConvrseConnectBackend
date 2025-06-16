"""
Notification Service for ConvrseConnectBackend
Handles notification management and inter-service communication with platform-service
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum

import httpx
from fastapi import HTTPException

from ..config.settings import settings
from ..integrations.auth_service_client import AuthServiceClient
from ..api.websocket_controller import broadcast_to_project

logger = logging.getLogger(__name__)


class NotificationType(Enum):
    """Notification types for different events"""
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    COMMENT = "COMMENT"
    TASK_UPDATE = "TASK_UPDATE"
    SYSTEM = "SYSTEM"
    MENTION = "MENTION"


class NotificationService:
    """
    Service for managing notifications and inter-service communication
    """
    
    def __init__(self):
        self.platform_service_url = getattr(settings, 'PLATFORM_SERVICE_URL', 'http://platform-service:8000')
        self.auth_service_url = getattr(settings, 'AUTH_SERVICE_URL', 'http://auth-service:8000')
        self.service_client_id = getattr(settings, 'SERVICE_CLIENT_ID', None)
        self.service_client_secret = getattr(settings, 'SERVICE_CLIENT_SECRET', None)
        self.auth_client = AuthServiceClient()
        self._access_token = None
        self._token_expires_at = None
        
    async def _get_service_token(self) -> str:
        """
        Get or refresh service client access token for inter-service communication
        """
        try:
            # Check if we have a valid token
            if (self._access_token and self._token_expires_at and 
                datetime.utcnow() < self._token_expires_at):
                return self._access_token
            
            if not self.service_client_id or not self.service_client_secret:
                raise ValueError("Service client credentials not configured")
            
            # Request new token from auth-service
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.auth_service_url}/service-clients/token",
                    json={
                        "client_id": self.service_client_id,
                        "client_secret": self.service_client_secret
                    },
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to get service token: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to authenticate with auth service"
                    )
                
                token_data = response.json()
                self._access_token = token_data["access_token"]
                
                # Calculate expiration (subtract 5 minutes for safety)
                expires_in = token_data.get("expires_in", 3600)
                self._token_expires_at = datetime.utcnow().replace(
                    second=0, microsecond=0
                ) + timedelta(seconds=expires_in - 300)
                
                logger.info("Successfully obtained service client token")
                return self._access_token
                
        except Exception as e:
            logger.error(f"Error getting service token: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Failed to authenticate for inter-service communication"
            )

    async def _make_platform_service_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Dict[str, Any] = None,
        params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Make authenticated request to platform-service
        """
        try:
            token = await self._get_service_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient() as client:
                url = f"{self.platform_service_url}{endpoint}"
                
                if method.upper() == "GET":
                    response = await client.get(url, headers=headers, params=params, timeout=30.0)
                elif method.upper() == "POST":
                    response = await client.post(url, headers=headers, json=data, timeout=30.0)
                elif method.upper() == "PATCH":
                    response = await client.patch(url, headers=headers, json=data, timeout=30.0)
                elif method.upper() == "DELETE":
                    response = await client.delete(url, headers=headers, timeout=30.0)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                if response.status_code >= 400:
                    logger.error(f"Platform service request failed: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Platform service error: {response.text}"
                    )
                
                return response.json() if response.content else {}
                
        except httpx.TimeoutException:
            logger.error(f"Timeout calling platform service: {endpoint}")
            raise HTTPException(
                status_code=504,
                detail="Platform service request timeout"
            )
        except Exception as e:
            logger.error(f"Error calling platform service: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Failed to communicate with platform service"
            )

    async def send_notification(
        self,
        project_id: str,
        notification_type: NotificationType,
        title: str,
        message: str,
        user_id: str = None,
        data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Send a notification to all users in a project
        """
        try:
            # Send to platform-service for persistence
            notification_data = {
                "project_id": project_id,
                "title": title,
                "message": message,
                "notification_type": notification_type.value,
                "data": data or {}
            }
            
            result = await self._make_platform_service_request(
                "POST",
                "/notifications/send",
                data=notification_data
            )
            
            # Also broadcast via WebSocket for real-time updates
            await self._broadcast_notification_websocket(
                project_id=project_id,
                notification_type=notification_type,
                title=title,
                message=message,
                data=data
            )
            
            logger.info(f"Notification sent for project {project_id}: {title}")
            return result
            
        except Exception as e:
            logger.error(f"Error sending notification: {str(e)}")
            raise

    async def send_comment_notification(
        self,
        project_id: str,
        comment_data: Dict[str, Any],
        user_name: str = "Unknown User"
    ) -> Dict[str, Any]:
        """
        Send a comment notification
        """
        try:
            # Send to platform-service
            request_data = {
                "project_id": project_id,
                "comment_data": comment_data
            }
            
            result = await self._make_platform_service_request(
                "POST",
                "/notifications/comment",
                data=request_data
            )
            
            # Broadcast via WebSocket
            await broadcast_to_project(
                project_id=project_id,
                message_type="NEW_COMMENT",
                data={
                    "comment": comment_data,
                    "user_name": user_name,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            
            logger.info(f"Comment notification sent for project {project_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error sending comment notification: {str(e)}")
            raise

    async def send_task_update_notification(
        self,
        project_id: str,
        task_data: Dict[str, Any],
        action: str = "updated",
        user_name: str = "Unknown User"
    ) -> Dict[str, Any]:
        """
        Send a task update notification
        """
        try:
            # Send to platform-service
            request_data = {
                "project_id": project_id,
                "task_data": task_data,
                "action": action
            }
            
            result = await self._make_platform_service_request(
                "POST",
                "/notifications/task-update",
                data=request_data
            )
            
            # Broadcast via WebSocket
            await broadcast_to_project(
                project_id=project_id,
                message_type="TASK_UPDATE",
                data={
                    "task": task_data,
                    "action": action,
                    "user_name": user_name,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            
            logger.info(f"Task update notification sent for project {project_id}: {action}")
            return result
            
        except Exception as e:
            logger.error(f"Error sending task update notification: {str(e)}")
            raise

    async def send_system_notification(
        self,
        project_id: str,
        title: str,
        message: str,
        data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Send a system notification
        """
        try:
            result = await self._make_platform_service_request(
                "POST",
                f"/notifications/system/{project_id}",
                params={
                    "title": title,
                    "message": message,
                    "data": json.dumps(data) if data else None
                }
            )
            
            # Broadcast via WebSocket
            await self._broadcast_notification_websocket(
                project_id=project_id,
                notification_type=NotificationType.SYSTEM,
                title=title,
                message=message,
                data=data
            )
            
            logger.info(f"System notification sent for project {project_id}: {title}")
            return result
            
        except Exception as e:
            logger.error(f"Error sending system notification: {str(e)}")
            raise

    async def send_success_notification(
        self,
        project_id: str,
        title: str,
        message: str,
        data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Send a success notification
        """
        try:
            result = await self._make_platform_service_request(
                "POST",
                f"/notifications/success/{project_id}",
                params={
                    "title": title,
                    "message": message,
                    "data": json.dumps(data) if data else None
                }
            )
            
            # Broadcast via WebSocket
            await self._broadcast_notification_websocket(
                project_id=project_id,
                notification_type=NotificationType.SUCCESS,
                title=title,
                message=message,
                data=data
            )
            
            logger.info(f"Success notification sent for project {project_id}: {title}")
            return result
            
        except Exception as e:
            logger.error(f"Error sending success notification: {str(e)}")
            raise

    async def send_error_notification(
        self,
        project_id: str,
        title: str,
        message: str,
        error_data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Send an error notification
        """
        try:
            result = await self._make_platform_service_request(
                "POST",
                f"/notifications/error/{project_id}",
                params={
                    "title": title,
                    "message": message,
                    "error_data": json.dumps(error_data) if error_data else None
                }
            )
            
            # Broadcast via WebSocket
            await self._broadcast_notification_websocket(
                project_id=project_id,
                notification_type=NotificationType.ERROR,
                title=title,
                message=message,
                data=error_data
            )
            
            logger.info(f"Error notification sent for project {project_id}: {title}")
            return result
            
        except Exception as e:
            logger.error(f"Error sending error notification: {str(e)}")
            raise

    async def get_user_notifications(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        unread_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get notifications for a user from platform-service
        """
        try:
            params = {
                "limit": limit,
                "offset": offset,
                "unread_only": unread_only
            }
            
            result = await self._make_platform_service_request(
                "GET",
                "/notifications/user",
                params=params
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting user notifications: {str(e)}")
            raise

    async def get_project_notifications(
        self,
        project_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get notifications for a project from platform-service
        """
        try:
            params = {
                "limit": limit,
                "offset": offset
            }
            
            result = await self._make_platform_service_request(
                "GET",
                f"/notifications/project/{project_id}",
                params=params
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting project notifications: {str(e)}")
            raise

    async def get_unread_count(self, user_id: str) -> int:
        """
        Get unread notification count for a user
        """
        try:
            result = await self._make_platform_service_request(
                "GET",
                "/notifications/unread-count"
            )
            
            return result.get("unread_count", 0)
            
        except Exception as e:
            logger.error(f"Error getting unread count: {str(e)}")
            raise

    async def mark_notification_read(
        self,
        notification_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Mark a notification as read
        """
        try:
            result = await self._make_platform_service_request(
                "PATCH",
                f"/notifications/{notification_id}/read"
            )
            
            logger.info(f"Notification {notification_id} marked as read")
            return result
            
        except Exception as e:
            logger.error(f"Error marking notification as read: {str(e)}")
            raise

    async def mark_all_notifications_read(self, user_id: str) -> Dict[str, Any]:
        """
        Mark all notifications as read for a user
        """
        try:
            result = await self._make_platform_service_request(
                "PATCH",
                "/notifications/mark-all-read"
            )
            
            logger.info(f"All notifications marked as read for user {user_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error marking all notifications as read: {str(e)}")
            raise

    async def delete_notification(
        self,
        notification_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Delete a notification
        """
        try:
            result = await self._make_platform_service_request(
                "DELETE",
                f"/notifications/{notification_id}"
            )
            
            logger.info(f"Notification {notification_id} deleted")
            return result
            
        except Exception as e:
            logger.error(f"Error deleting notification: {str(e)}")
            raise

    async def get_connected_users(self, project_id: str) -> List[Dict[str, Any]]:
        """
        Get list of users connected to a project via WebSocket
        """
        try:
            result = await self._make_platform_service_request(
                "GET",
                f"/notifications/connected-users/{project_id}"
            )
            
            return result.get("users", [])
            
        except Exception as e:
            logger.error(f"Error getting connected users: {str(e)}")
            raise

    async def _broadcast_notification_websocket(
        self,
        project_id: str,
        notification_type: NotificationType,
        title: str,
        message: str,
        data: Dict[str, Any] = None
    ):
        """
        Broadcast notification via WebSocket for real-time updates
        """
        try:
            await broadcast_to_project(
                project_id=project_id,
                message_type="NOTIFICATION",
                data={
                    "type": notification_type.value.lower(),
                    "title": title,
                    "message": message,
                    "data": data or {},
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
        except Exception as e:
            logger.error(f"Error broadcasting notification via WebSocket: {str(e)}")
            # Don't raise here as this is supplementary to the main notification


# Global notification service instance
_notification_service = None

def get_notification_service() -> NotificationService:
    """Get or create the global notification service instance"""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service 