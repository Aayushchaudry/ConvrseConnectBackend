# src/models/review_feedback.py

import enum
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Text, JSON, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.config.database import Base
from src.models.client_feedback import FeedbackType
from src.models.review_item import ReviewItem


class ReviewFeedback(Base):
    """
    SQLAlchemy model for the 'review_feedback' table.
    Enhanced feedback model with coordinate and timestamp support for detailed annotations.
    """

    __tablename__ = "review_feedback"
    __table_args__ = {"schema": "connect_backend"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign Key linking to the ReviewItem
    review_item_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("connect_backend.review_items.id"), 
        nullable=False
    )
    
    # Feedback type and content
    feedback_type = Column(
        Enum(FeedbackType, schema="connect_backend"), 
        nullable=False
    )
    comment_text = Column(Text, nullable=True)
    
    # Media-specific feedback data
    timestamp_seconds = Column(Integer, nullable=True)  # For video/audio feedback
    coordinates = Column(JSON, nullable=True)  # For image annotation (x, y, width, height)
    
    # User who submitted the feedback
    submitted_by = Column(UUID(as_uuid=True), nullable=True)
    submitted_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Relationship to generated tasks for rework
    generated_task_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("connect_backend.internal_tasks.id"), 
        nullable=True
    )
    
    # --- Relationships ---
    # Relationship to the ReviewItem model
    review_item_ref = relationship(
        "ReviewItem", 
        backref="review_feedback", 
        lazy="joined"
    )
    
    # Relationship to the generated task
    generated_task_ref = relationship(
        "InternalTask",
        backref="source_feedback",
        lazy="joined"
    )

    def __repr__(self):
        """String representation for debugging."""
        return (
            f"<ReviewFeedback(id='{self.id}', review_item_id='{self.review_item_id}', "
            f"feedback_type='{self.feedback_type.value}', submitted_at='{self.submitted_at}')>"
        )