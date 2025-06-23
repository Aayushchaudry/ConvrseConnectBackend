# src/models/review_item.py

import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.config.database import Base  # Import Base from your database config
from src.models.deliverable import (
    Deliverable,
)  # Import Deliverable model for ForeignKey
from src.models.internal_task import (
    InternalTask,
)  # Import InternalTask model for ForeignKey
from src.models.project import Project  # Import Project model for ForeignKey

# --- Enums for Review Item Type and Status ---


class ReviewItemType(enum.Enum):
    """Defines the type of content being reviewed."""

    # Generic content types
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    INTERACTIVE_CONTENT = "interactive_content"
    OTHER = "other"
    
    # Business-specific review types for production workflow
    STATIC_RENDER = "STATIC_RENDER"      # For modeling/static image reviews
    TEXTURE_REVIEW = "TEXTURE_REVIEW"    # For texture and material reviews
    FINAL_RENDER = "FINAL_RENDER"        # For final rendering reviews
    WORK_REVIEW = "WORK_REVIEW"          # For general work completion reviews


class ReviewStatus(enum.Enum):
    """Defines the current status of a review item from client perspective."""

    PENDING_REVIEW = "PENDING_REVIEW"  # Waiting for client to review
    APPROVED = "APPROVED"  # Client has approved this item  
    REJECTED = "REJECTED"  # Client has rejected this item
    NEEDS_REVISION = "NEEDS_REVISION"  # Client has provided comments requiring revisions


# --- ReviewItem ORM Model ---


class ReviewItem(Base):
    """
    SQLAlchemy model for the 'review_items' table.
    Represents specific outputs or drafts sent to the client for review and feedback.
    """

    __tablename__ = "review_items"
    __table_args__ = {"schema": "connect_backend"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign Keys linking to the Deliverable, Project, and the InternalTask that produced it
    deliverable_id = Column(
        UUID(as_uuid=True), ForeignKey("connect_backend.deliverables.id"), nullable=False
    )
    project_id = Column(
        UUID(as_uuid=True), ForeignKey("connect_backend.projects.id"), nullable=False
    )  # For convenience
    source_internal_task_id = Column(
        UUID(as_uuid=True), ForeignKey("connect_backend.internal_tasks.id"), nullable=False
    )  # The task that generated this output

    item_type = Column(
        Enum(ReviewItemType, schema="connect_backend"), nullable=False
    )  # Type of content being reviewed
    
    # File reference options - either platform_file_id OR item_url can be used
    platform_file_id = Column(
        UUID(as_uuid=True), nullable=True
    )  # Reference to file ID in platform-service for review assets
    item_url = Column(
        Text, nullable=True
    )  # Optional URL to the asset - nullable for review items that do not require file attachments
    
    description = Column(
        Text, nullable=True
    )  # Description/context for this specific review item

    review_status = Column(
        Enum(ReviewStatus, schema="connect_backend"), default=ReviewStatus.PENDING_REVIEW, nullable=False
    )  # Current status from client's review perspective

    # For review batches or specific rounds
    sequence_number = Column(
        Integer, nullable=True
    )  # Order in a list of options (e.g., render option 1, 2)
    review_round = Column(
        Integer, nullable=True
    )  # Which revision round this item belongs to (e.g., 1st draft, 2nd revision)

    presented_at = Column(
        DateTime, default=func.now(), nullable=False
    )  # When this item was presented for review

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    # --- Relationships ---
    # Relationships back to Project, Deliverable, and InternalTask
    project_ref = relationship("Project", backref="review_items_project", lazy="joined")
    deliverable_ref = relationship(
        "Deliverable", backref="review_items_deliverable", lazy="joined"
    )
    source_internal_task_ref = relationship(
        "InternalTask",
        foreign_keys=[source_internal_task_id],
        backref="generated_review_items",
        lazy="joined",
    )

    # Relationship to ClientFeedback (one-to-many)
    # client_feedbacks = relationship("ClientFeedback", back_populates="review_item_ref")

    def __repr__(self):
        """String representation for debugging."""
        return (
            f"<ReviewItem(id='{self.id}', type='{self.item_type.value}', "
            f"deliverable_id='{self.deliverable_id}', status='{self.review_status.value}')>"
        )
