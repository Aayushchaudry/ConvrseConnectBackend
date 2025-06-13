"""
WebSocket controller for real-time project collaboration.
Handles real-time messaging for projects, comments, file uploads, and tasks.
"""

import asyncio
import json
import logging
from typing import Dict, List, Set
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from src.middleware.auth_middleware import get_websocket_user
from src.config.event_bus import get_event_bus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manages WebSocket connections for real-time project collaboration."""
    
    def __init__(self):
        # Store active connections by project ID
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # Store user information for each connection
        self.connection_users: Dict[WebSocket, dict] = {}
        
    async def connect(self, websocket: WebSocket, project_id: str, user_info: dict):
        """Accept a WebSocket connection and add it to the project room."""
        await websocket.accept()
        
        if project_id not in self.active_connections:
            self.active_connections[project_id] = set()
        
        self.active_connections[project_id].add(websocket)
        self.connection_users[websocket] = user_info
        
        logger.info(f"User {user_info.get('user_id')} connected to project {project_id}")
        
        # Broadcast user joined to other users in the project
        await self.broadcast_to_project(project_id, {
            "type": "USER_JOINED",
            "data": {
                "userId": user_info.get("user_id"),
                "userName": user_info.get("user_name", "Unknown"),
                "projectId": project_id
            },
            "timestamp": self._get_timestamp()
        }, exclude=websocket)
        
    def disconnect(self, websocket: WebSocket, project_id: str):
        """Remove a WebSocket connection from the project room."""
        if project_id in self.active_connections:
            self.active_connections[project_id].discard(websocket)
            
            # Clean up empty project rooms
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]
        
        user_info = self.connection_users.pop(websocket, {})
        
        logger.info(f"User {user_info.get('user_id')} disconnected from project {project_id}")
        
        # Broadcast user left to remaining users in the project (if any)
        if project_id in self.active_connections:
            asyncio.create_task(self.broadcast_to_project(project_id, {
                "type": "USER_LEFT",
                "data": {
                    "userId": user_info.get("user_id"),
                    "userName": user_info.get("user_name", "Unknown"),
                    "projectId": project_id
                },
                "timestamp": self._get_timestamp()
            }))
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send a message to a specific WebSocket connection."""
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Failed to send personal message: {e}")
    
    async def broadcast_to_project(self, project_id: str, message: dict, exclude: WebSocket = None):
        """Broadcast a message to all connections in a project room."""
        if project_id not in self.active_connections:
            return
        
        dead_connections = []
        
        for websocket in self.active_connections[project_id]:
            if exclude and websocket == exclude:
                continue
                
            if websocket.client_state == WebSocketState.CONNECTED:
                try:
                    await websocket.send_text(json.dumps(message))
                except Exception as e:
                    logger.error(f"Failed to broadcast to project {project_id}: {e}")
                    dead_connections.append(websocket)
            else:
                dead_connections.append(websocket)
        
        # Clean up dead connections
        for dead_ws in dead_connections:
            self.active_connections[project_id].discard(dead_ws)
            self.connection_users.pop(dead_ws, None)
    
    async def broadcast_comment_update(self, project_id: str, comment_data: dict):
        """Broadcast a new comment to all project participants."""
        await self.broadcast_to_project(project_id, {
            "type": "NEW_COMMENT",
            "data": comment_data,
            "timestamp": self._get_timestamp()
        })
    
    async def broadcast_upload_progress(self, project_id: str, progress_data: dict):
        """Broadcast file upload progress to all project participants."""
        await self.broadcast_to_project(project_id, {
            "type": "UPLOAD_PROGRESS",
            "data": progress_data,
            "timestamp": self._get_timestamp()
        })
    
    async def broadcast_task_update(self, project_id: str, task_data: dict):
        """Broadcast task status update to all project participants."""
        await self.broadcast_to_project(project_id, {
            "type": "TASK_UPDATE",
            "data": task_data,
            "timestamp": self._get_timestamp()
        })
    
    async def broadcast_annotation_added(self, project_id: str, annotation_data: dict):
        """Broadcast new annotation to all project participants."""
        await self.broadcast_to_project(project_id, {
            "type": "ANNOTATION_ADDED",
            "data": annotation_data,
            "timestamp": self._get_timestamp()
        })
    
    def get_project_participants(self, project_id: str) -> List[dict]:
        """Get list of users currently connected to a project."""
        if project_id not in self.active_connections:
            return []
        
        participants = []
        for websocket in self.active_connections[project_id]:
            user_info = self.connection_users.get(websocket, {})
            if user_info:
                participants.append({
                    "userId": user_info.get("user_id"),
                    "userName": user_info.get("user_name", "Unknown"),
                    "connectedAt": user_info.get("connected_at")
                })
        
        return participants
    
    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime
        return datetime.utcnow().isoformat()


# Global connection manager instance
manager = ConnectionManager()


@router.websocket("/ws/projects/{project_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    project_id: str,
    user_info: dict = Depends(get_websocket_user)
):
    """
    WebSocket endpoint for real-time project collaboration.
    
    Args:
        websocket: The WebSocket connection
        project_id: UUID of the project to connect to
        user_info: User information from auth middleware
    """
    # Validate project_id format
    try:
        UUID(project_id)
    except ValueError:
        await websocket.close(code=1008, reason="Invalid project ID format")
        return
    
    # Add connection timestamp to user info
    from datetime import datetime
    user_info["connected_at"] = datetime.utcnow().isoformat()
    
    await manager.connect(websocket, project_id, user_info)
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                await handle_websocket_message(websocket, project_id, message, user_info)
            except json.JSONDecodeError:
                await manager.send_personal_message({
                    "type": "ERROR",
                    "data": {"message": "Invalid JSON format"},
                    "timestamp": manager._get_timestamp()
                }, websocket)
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}")
                await manager.send_personal_message({
                    "type": "ERROR", 
                    "data": {"message": "Message processing failed"},
                    "timestamp": manager._get_timestamp()
                }, websocket)
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, project_id)
    except Exception as e:
        logger.error(f"WebSocket error for project {project_id}: {e}")
        manager.disconnect(websocket, project_id)


async def handle_websocket_message(
    websocket: WebSocket, 
    project_id: str, 
    message: dict, 
    user_info: dict
):
    """Handle incoming WebSocket messages from clients."""
    
    message_type = message.get("type")
    
    if message_type == "PING":
        # Respond to ping with pong
        await manager.send_personal_message({
            "type": "PONG",
            "timestamp": manager._get_timestamp()
        }, websocket)
        
    elif message_type == "GET_PARTICIPANTS":
        # Send current project participants
        participants = manager.get_project_participants(project_id)
        await manager.send_personal_message({
            "type": "PARTICIPANTS_LIST",
            "data": {"participants": participants},
            "timestamp": manager._get_timestamp()
        }, websocket)
        
    elif message_type == "TYPING_START":
        # Broadcast typing indicator
        await manager.broadcast_to_project(project_id, {
            "type": "USER_TYPING",
            "data": {
                "userId": user_info.get("user_id"),
                "userName": user_info.get("user_name", "Unknown"),
                "isTyping": True
            },
            "timestamp": manager._get_timestamp()
        }, exclude=websocket)
        
    elif message_type == "TYPING_STOP":
        # Broadcast stop typing indicator
        await manager.broadcast_to_project(project_id, {
            "type": "USER_TYPING",
            "data": {
                "userId": user_info.get("user_id"),
                "userName": user_info.get("user_name", "Unknown"),
                "isTyping": False
            },
            "timestamp": manager._get_timestamp()
        }, exclude=websocket)
        
    else:
        logger.warning(f"Unknown WebSocket message type: {message_type}")


# Function to broadcast events from other parts of the application
async def broadcast_to_project(project_id: str, message_type: str, data: dict):
    """
    Utility function to broadcast messages to a project from outside WebSocket handlers.
    
    Args:
        project_id: The project to broadcast to
        message_type: Type of message (NEW_COMMENT, TASK_UPDATE, etc.)
        data: Message data payload
    """
    message = {
        "type": message_type,
        "data": data,
        "timestamp": manager._get_timestamp()
    }
    
    await manager.broadcast_to_project(project_id, message)


# Export the manager for use in other modules
__all__ = ["router", "manager", "broadcast_to_project"] 