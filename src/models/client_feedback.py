# src/models/client_feedback.py

import enum
import uuid

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.config.database import Base  # Import Base from your database config
from src.models.deliverable import (
    Deliverable,
)  # Import Deliverable model for ForeignKey (for convenience)
from src.models.project import (
    Project,
)  # Import Project model for ForeignKey (for convenience)
from src.models.review_item import ReviewItem  # Import ReviewItem model for ForeignKey

# from src.models.project_output import ProjectOutput # Import ProjectOutput for ForeignKey (will be defined next)
# from src.models.user import User # Import User model if you implement it for client_user_id

# --- Enums for Feedback Type ---


class FeedbackType(enum.Enum):
    """Defines the type of feedback provided by the client."""

    ACCEPT = "ACCEPT"  # Client fully approves
    REJECT = "REJECT"  # Client fully rejects
    COMMENT = "COMMENT"  # Client provides text comments (requires rework)
    LIKE = "LIKE"  # Client likes a specific option (e.g., a render option)
    FINAL_APPROVAL = "FINAL_APPROVAL"  # Specific approval for a final deliverable


# --- ClientFeedback ORM Model ---


class ClientFeedback(Base):
    """
    SQLAlchemy model for the 'client_feedbacks' table.
    Captures detailed feedback from clients on review items or final outputs.
    """

    __tablename__ = "client_feedbacks"
    __table_args__ = {"schema": "connect_backend"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign Keys linking to the entities this feedback is related to
    # A feedback must be related to either a ReviewItem OR a ProjectOutput
    review_item_id = Column(
        UUID(as_uuid=True), ForeignKey("connect_backend.review_items.id"), nullable=True
    )
    project_output_id = Column(
        UUID(as_uuid=True), ForeignKey("connect_backend.project_outputs.id"), nullable=True
    )  # Will be defined next

    # Link to the Project, Deliverable for convenience in queries
    project_id = Column(UUID(as_uuid=True), ForeignKey("connect_backend.projects.id"), nullable=False)
    deliverable_id = Column(
        UUID(as_uuid=True), ForeignKey("connect_backend.deliverables.id"), nullable=False
    )

    # Who provided the feedback (if User model is implemented and linked to clients)
    # client_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False) # Or nullable if anonymous feedback allowed

    feedback_type = Column(Enum(FeedbackType, schema="connect_backend"), nullable=False)  # Type of feedback

    comment_text = Column(Text, nullable=True)  # The actual text comment

    # For video/drone video comments
    timestamp_seconds = Column(
        Integer, nullable=True
    )  # Time in seconds into the video/audio

    # For image/3D view comments - using JSON instead of JSONB for database compatibility
    context_coordinates = Column(
        JSON, nullable=True
    )  # e.g., {"x": 100, "y": 200, "width": 50, "height": 50} for bounding box

    # Automatic timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    # --- Relationships ---
    # Relationships back to core entities
    review_item_ref = relationship(
        "ReviewItem", backref="client_feedbacks", lazy="joined"
    )
    project_ref = relationship(
        "Project", backref="client_feedbacks_project", lazy="joined"
    )
    deliverable_ref = relationship(
        "Deliverable", backref="client_feedbacks_deliverable", lazy="joined"
    )
    # project_output_ref = relationship("ProjectOutput", back_populates="client_feedbacks_output") # Will define on ProjectOutput model

    # Relationship to User (if implemented)
    # client_user_ref = relationship("User", back_populates="client_feedbacks_provided")

    def __repr__(self):
        """String representation for debugging."""
        return (
            f"<ClientFeedback(id='{self.id}', type='{self.feedback_type.value}', "
            f"review_item_id='{self.review_item_id}', project_output_id='{self.project_output_id}')>"
        )
