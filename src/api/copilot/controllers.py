"""
CopilotKit API Controllers for ConvrseConnect
Handles chat requests and provides AI assistance for the ConvrseConnect platform
"""

import logging
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from google import genai
from google.genai import types

from src.middleware.auth_middleware import get_current_auth, AuthContext
from src.integrations.auth_service_client import UserData
from src.services.dashboard_service import DashboardService
from src.services.project_service import ProjectService

logger = logging.getLogger(__name__)

# Global client variable - initialized lazily
_genai_client = None

def get_genai_client():
    """Get or initialize the Google GenAI client"""
    global _genai_client
    if _genai_client is None:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=503, 
                detail="Google API key not configured. CopilotKit AI features are unavailable."
            )
        try:
            _genai_client = genai.Client(api_key=api_key)
        except Exception as e:
            logger.error(f"Failed to initialize Google GenAI client: {e}")
            raise HTTPException(
                status_code=503,
                detail="Failed to initialize AI service. Please check configuration."
            )
    return _genai_client

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])

# CopilotKit Models
class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: Optional[datetime] = None

class TextMessage(BaseModel):
    content: str
    role: str

class CopilotMessage(BaseModel):
    id: str
    createdAt: str
    textMessage: TextMessage

class CopilotData(BaseModel):
    messages: List[CopilotMessage]
    threadId: Optional[str] = None
    runId: Optional[str] = None
    frontend: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

class CopilotKitRequest(BaseModel):
    data: CopilotData
    properties: Optional[Dict[str, Any]] = None

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    context: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    message: ChatMessage
    context: Optional[Dict[str, Any]] = None

class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    copilot_enabled: bool

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for CopilotKit"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(),
        copilot_enabled=bool(os.getenv("GOOGLE_API_KEY"))
    )

@router.post("")
async def copilot_chat(
    http_request: Request
):
    """
    Main CopilotKit endpoint - handles the standard CopilotKit protocol
    """
    try:
        # Parse the request body manually
        body = await http_request.json()
        logger.info(f"Received CopilotKit request: {body}")
        
        # Handle different request formats
        messages = []
        
        # Check if it's a simple messages format
        if "messages" in body:
            for msg in body["messages"]:
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    messages.append(ChatMessage(
                        role=msg["role"],
                        content=msg["content"],
                        timestamp=datetime.now()
                    ))
        
        # Check if it's a CopilotKit GraphQL format with variables
        elif "variables" in body and "data" in body["variables"] and "messages" in body["variables"]["data"]:
            for msg in body["variables"]["data"]["messages"]:
                if "textMessage" in msg and msg["textMessage"]["content"].strip():
                    messages.append(ChatMessage(
                        role=msg["textMessage"]["role"],
                        content=msg["textMessage"]["content"],
                        timestamp=datetime.now()
                    ))
        
        # Check if it's a direct CopilotKit format
        elif "data" in body and "messages" in body["data"]:
            for msg in body["data"]["messages"]:
                if "textMessage" in msg and msg["textMessage"]["content"].strip():
                    messages.append(ChatMessage(
                        role=msg["textMessage"]["role"],
                        content=msg["textMessage"]["content"],
                        timestamp=datetime.now()
                    ))
        
        if not messages:
            raise HTTPException(status_code=400, detail="No valid messages found in request")
        
        # Extract context from the request
        context = {}
        if "variables" in body and "data" in body["variables"]:
            context = {
                "threadId": body["variables"]["data"].get("threadId"),
                "runId": body["variables"]["data"].get("runId"),
                "metadata": body["variables"]["data"].get("metadata", {}),
                "frontend": body["variables"]["data"].get("frontend", {}),
                "properties": body["variables"].get("properties", {})
            }
        elif "data" in body:
            context = {
                "threadId": body["data"].get("threadId"),
                "runId": body["data"].get("runId"),
                "metadata": body["data"].get("metadata", {}),
                "frontend": body["data"].get("frontend", {}),
                "properties": body.get("properties", {})
            }
        else:
            context = body.get("context", {})
        
        # Create a ChatRequest object for our handler
        chat_request = ChatRequest(
            messages=messages,
            context=context
        )
        
        # Handle the chat request
        response = await chat_handler(chat_request, http_request)
        
        # Return CopilotKit-compatible GraphQL response format
        thread_id = chat_request.context.get("threadId", "default-thread")
        run_id = chat_request.context.get("runId", f"run-{datetime.now().timestamp()}")
        
        return {
            "data": {
                "generateCopilotResponse": {
                    "threadId": thread_id,
                    "runId": run_id,
                    "extensions": {},
                    "status": {
                        "code": "SUCCESS",
                        "__typename": "BaseResponseStatus"
                    },
                    "messages": [
                        {
                            "__typename": "TextMessageOutput",
                            "id": f"msg-{datetime.now().timestamp()}",
                            "createdAt": datetime.now().isoformat(),
                            "content": [response.message.content],
                            "role": "assistant",
                            "parentMessageId": None,
                            "status": {
                                "code": "SUCCESS",
                                "__typename": "SuccessMessageStatus"
                            }
                        }
                    ],
                    "metaEvents": [],
                    "__typename": "CopilotResponse"
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error in CopilotKit endpoint: {e}")
        # Return a fallback response in CopilotKit format
        return {
            "data": {
                "generateCopilotResponse": {
                    "threadId": "error-thread",
                    "runId": f"error-run-{datetime.now().timestamp()}",
                    "extensions": {},
                    "status": {
                        "code": "SUCCESS",
                        "__typename": "BaseResponseStatus"
                    },
                    "messages": [
                        {
                            "__typename": "TextMessageOutput",
                            "id": f"error-msg-{datetime.now().timestamp()}",
                            "createdAt": datetime.now().isoformat(),
                            "content": ["I'm here to help with ConvrseConnect! How can I assist you today?"],
                            "role": "assistant",
                            "parentMessageId": None,
                            "status": {
                                "code": "SUCCESS",
                                "__typename": "SuccessMessageStatus"
                            }
                        }
                    ],
                    "metaEvents": [],
                    "__typename": "CopilotResponse"
                }
            }
        }

@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    http_request: Request
):
    """
    Handle chat requests from CopilotKit frontend
    """
    return await chat_handler(request, http_request)

async def chat_handler(
    request: ChatRequest,
    http_request: Request
):
    """
    Handle chat requests from CopilotKit frontend
    """
    try:
        # Get current user context (optional - CopilotKit endpoints may not require auth)
        auth_context = get_current_auth(http_request)
        current_user = auth_context.user if auth_context.is_authenticated else None
        
        # Extract the latest message from the conversation
        if not request.messages:
            raise HTTPException(status_code=400, detail="No messages provided")
        
        latest_message = request.messages[-1].content
        
        # Build context for the AI
        full_context = {
            "conversation_history": [
                {"role": msg.role, "content": msg.content} 
                for msg in request.messages[:-1]  # Exclude the latest message
            ],
            "user_context": {
                "authenticated": auth_context.is_authenticated,
                "user_id": current_user.user_id if current_user else None,
                "username": current_user.username if current_user else None,
                "business_id": current_user.business_id if current_user else None,
            } if current_user else {"authenticated": False},
            "request_context": request.context or {}
        }
        
        # Generate response using Gemini AI
        response_content = await generate_gemini_response(latest_message, full_context, current_user)
        
        # Create response message
        response_message = ChatMessage(
            role="assistant",
            content=response_content,
            timestamp=datetime.now()
        )
        
        return ChatResponse(
            message=response_message,
            context={"processed_at": datetime.now().isoformat()}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

async def generate_gemini_response(
    user_message: str, 
    context: Dict[str, Any], 
    current_user: Optional[UserData]
) -> str:
    """
    Generate an AI response using Google Gemini
    """
    try:
        # Build context-aware prompt
        system_context = """You are a helpful assistant for ConvrseConnect, a project management and collaboration platform. 
        You can help users navigate the application, understand features, get project analytics, and perform various tasks. 
        Be friendly, helpful, and provide clear step-by-step guidance when needed.

        Available features in ConvrseConnect:
        - Project management and tracking
        - Deliverable creation and management  
        - Review workflows and feedback
        - File uploads and media management
        - Team collaboration tools
        - Dashboard analytics
        
        Keep responses concise but informative. If you need to perform actions, explain what you're doing."""
        
        # Add user context if available
        user_context = ""
        if current_user:
            user_context = f"\nCurrent user: {current_user.username} (ID: {current_user.user_id})"
            if hasattr(current_user, 'business_id') and current_user.business_id:
                user_context += f"\nBusiness context: {current_user.business_id}"
        
        # Build conversation history
        conversation_history = ""
        if context.get("conversation_history"):
            conversation_history = "\nConversation history:\n"
            for msg in context["conversation_history"][-5:]:  # Last 5 messages for context
                conversation_history += f"{msg['role']}: {msg['content']}\n"
        
        # Combine everything into a prompt
        full_prompt = f"{system_context}{user_context}{conversation_history}\n\nUser question: {user_message}\n\nAssistant:"
        
        # Generate response using Google GenAI
        client = get_genai_client()
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=[full_prompt],
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=1000,
            )
        )
        
        if response and response.text:
            return response.text.strip()
        else:
            return "I'm here to help with ConvrseConnect! I can assist with navigation, projects, file uploads, reviews, and analytics. What would you like help with?"
            
    except Exception as e:
        logger.error(f"Error generating Gemini response: {e}")
        return "I'm here to help with ConvrseConnect! I can assist with navigation, projects, file uploads, reviews, and analytics. What would you like help with?" 