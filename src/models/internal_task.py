# src/models/internal_task.py

import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.config.database import Base  # Import Base from your database config
from src.models.deliverable import (
    Deliverable,
)  # Import Deliverable model for ForeignKey
from src.models.project import Project  # Import Project model for ForeignKey

# from src.models.user import User # Import User model if you implement it for assigned_to_user_id

# --- Enums for Task Type, Status, and Priority ---


class TaskType(enum.Enum):
    """Defines the type of internal production task."""

    MODELING = "MODELING"
    TEXTURING = "TEXTURING"
    LIGHTING = "LIGHTING"
    RENDERING = "RENDERING"
    COMPOSITING = "COMPOSITING"
    REWORK = "REWORK"  # For tasks generated due to client comments/rejection
    REVIEW_INTERNAL = "REVIEW_INTERNAL"  # For internal QA/review tasks
    FINAL_PREP = "FINAL_PREP"  # Final preparation before delivery
    OTHER = "OTHER"


class TaskStatus(enum.Enum):
    """Defines the current status of an internal task."""

    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_REVIEW = (
        "AWAITING_REVIEW"  # Awaiting internal review or client review prep
    )
    DONE = "DONE"
    BLOCKED = "BLOCKED"  # Task is blocked waiting for something else
    ON_HOLD = "ON_HOLD"
    REJECTED_TERMINATED = "REJECTED_TERMINATED"  # Task rejected, work stopped on it


class Priority(enum.Enum):
    """Defines the priority level of an internal task."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# --- InternalTask ORM Model ---


class InternalTask(Base):
    """
    SQLAlchemy model for the 'internal_tasks' table.
    Manages granular work tasks within a deliverable's production.
    """

    __tablename__ = "internal_tasks"
    __table_args__ = {"schema": "connect_backend"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign Keys linking to the Deliverable and Project
    deliverable_id = Column(
        UUID(as_uuid=True), ForeignKey("connect_backend.deliverables.id"), nullable=True  # Allow project-level tasks
    )
    project_id = Column(
        UUID(as_uuid=True), ForeignKey("connect_backend.projects.id"), nullable=False
    )  # For convenience

    # For parent-subtask relationship (e.g., rework tasks)
    parent_task_id = Column(
        UUID(as_uuid=True), ForeignKey("connect_backend.internal_tasks.id"), nullable=True
    )

    task_name = Column(String(255), nullable=False)  # Descriptive name for the task
    task_type = Column(
        Enum(TaskType, schema="connect_backend"), nullable=False
    )  # Type of work (e.g., modeling, rendering)

    # User assigned to this task (if User model is implemented)
    # assigned_to_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)

    status = Column(Enum(TaskStatus, schema="connect_backend"), nullable=False)
    priority = Column(Enum(Priority, schema="connect_backend"), default=Priority.NORMAL, nullable=False)

    start_date = Column(DateTime, nullable=True)
    tentative_end_date = Column(DateTime, nullable=True)  # Expected completion
    actual_end_date = Column(DateTime, nullable=True)  # Actual completion time

    description = Column(Text, nullable=True)  # Detailed description of the task

    # Source of the task, e.g., if it was created due to feedback on a specific ReviewItem
    source_review_item_id = Column(
        UUID(as_uuid=True), ForeignKey("connect_backend.review_items.id"), nullable=True
    )

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    # --- Relationships ---
    # Relationships back to Project and Deliverable
    project_ref = relationship(
        "Project", backref="internal_tasks_project", lazy="joined"
    )  # backref needed if 'internal_tasks' already used
    deliverable_ref = relationship(
        "Deliverable", backref="internal_tasks_deliverable", lazy="joined"
    )

    # Self-referencing relationship for parent/sub-tasks
    parent_task = relationship(
        "InternalTask",
        remote_side=[id],
        backref="sub_tasks",
        uselist=False,
        lazy="joined",
    )

    # Relationship to ReviewItem (many-to-one) - specify foreign_keys to resolve circular reference
    source_review_item_ref = relationship(
        "ReviewItem",
        foreign_keys=[source_review_item_id],
        backref="related_internal_tasks",
        lazy="joined",
    )

    def __repr__(self):
        """String representation for debugging."""
        return (
            f"<InternalTask(id='{self.id}', name='{self.task_name}', "
            f"deliverable_id='{self.deliverable_id}', status='{self.status.value}')>"
        )
