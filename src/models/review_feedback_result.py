# src/models/review_feedback_result.py

from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ReviewFeedbackResult(BaseModel):
    """
    Pydantic model for the result of submitting review feedback.
    Used as a response model for feedback submission endpoints.
    """
    
    feedback_id: UUID = Field(..., description="ID of the created feedback")
    review_item_id: UUID = Field(..., description="ID of the review item")
    feedback_type: str = Field(..., description="Type of feedback submitted")
    review_status: str = Field(..., description="Updated status of the review item")
    submitted_at: datetime = Field(..., description="Timestamp when feedback was submitted")
    
    # Optional fields
    comment_text: Optional[str] = Field(None, description="Text comment if provided")
    timestamp_seconds: Optional[int] = Field(None, description="Timestamp for video/audio feedback")
    coordinates: Optional[Dict[str, Any]] = Field(None, description="Coordinates for image annotations")
    
    # Task generation result
    task_generated: bool = Field(False, description="Whether a rework task was generated")
    generated_task_id: Optional[UUID] = Field(None, description="ID of the generated rework task")
    
    class Config:
        orm_mode = True