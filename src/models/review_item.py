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

    RENDER_OPTION = "render_option"  # For multiple static images presented as options
    STATIC_RENDER = "static_render"  # A single, specific still render
    TECHNICAL_MODEL = "technical_model"
    THREE_SIXTY_VIEW = "360_view"
    VIDEO_SEGMENT = "video_segment"  # A short clip from a video walkthrough
    VIDEO_DRAFT = "video_draft"  # An entire draft video
    MAP_DRAFT = "map_draft"  # An initial design draft of a map
    UI_PROTOTYPE = "ui_prototype"  # For interactive apps like sales app or interplayer
    DRONE_FOOTAGE = "drone_footage"
    STORYBOARD = "storyboard"
    OTHER = "other"


class ReviewStatus(enum.Enum):
    """Defines the current status of a review item from client perspective."""

    PENDING = "pending"  # Waiting for client to review
    ACCEPTED = "accepted"  # Client has approved this item
    REJECTED = "rejected"  # Client has rejected this item
    COMMENTED = "commented"  # Client has left comments but not yet approved/rejected
    SELECTED = "selected"  # For options, client selected this one (implies acceptance of this option)
    REVISIONS_PENDING = (
        "revisions_pending"  # Revisions requested by client, awaiting new version
    )


# --- ReviewItem ORM Model ---


class ReviewItem(Base):
    """
    SQLAlchemy model for the 'review_items' table.
    Represents specific outputs or drafts sent to the client for review and feedback.
    """

    __tablename__ = "review_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign Keys linking to the Deliverable, Project, and the InternalTask that produced it
    deliverable_id = Column(
        UUID(as_uuid=True), ForeignKey("deliverables.id"), nullable=False
    )
    project_id = Column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )  # For convenience
    source_internal_task_id = Column(
        UUID(as_uuid=True), ForeignKey("internal_tasks.id"), nullable=False
    )  # The task that generated this output

    item_type = Column(
        Enum(ReviewItemType), nullable=False
    )  # Type of content being reviewed
    item_url = Column(
        Text, nullable=False
    )  # URL to the asset (e.g., image URL, video URL, prototype link)
    description = Column(
        Text, nullable=True
    )  # Description/context for this specific review item

    review_status = Column(
        Enum(ReviewStatus), default=ReviewStatus.PENDING, nullable=False
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
