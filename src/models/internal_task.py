# src/models/internal_task.py

import enum
import uuid
from sqlalchemy import Column, String, DateTime, func, Integer, Text, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.config.database import Base # Import Base from your database config
from src.models.project import Project # Import Project model for ForeignKey
from src.models.deliverable import Deliverable # Import Deliverable model for ForeignKey
# from src.models.user import User # Import User model if you implement it for assigned_to_user_id

# --- Enums for Task Type, Status, and Priority ---

class TaskType(enum.Enum):
    """Defines the type of internal production task."""
    MODELING = "modeling"
    TEXTURING = "texturing"
    LIGHTING = "lighting"
    RENDERING = "rendering"
    COMPOSITING = "compositing"
    REWORK = "rework" # For tasks generated due to client comments/rejection
    REVIEW_INTERNAL = "review_internal" # For internal QA/review tasks
    FINAL_PREP = "final_prep" # Final preparation before delivery
    OTHER = "other"

class TaskStatus(enum.Enum):
    """Defines the current status of an internal task."""
    TODO = "to_do"
    IN_PROGRESS = "in_progress"
    AWAITING_REVIEW = "awaiting_review" # Awaiting internal review or client review prep
    DONE = "done"
    BLOCKED = "blocked" # Task is blocked waiting for something else
    ON_HOLD = "on_hold"
    REJECTED_TERMINATED = "rejected_terminated" # Task rejected, work stopped on it

class Priority(enum.Enum):
    """Defines the priority level of an internal task."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"

# --- InternalTask ORM Model ---

class InternalTask(Base):
    """
    SQLAlchemy model for the 'internal_tasks' table.
    Manages granular work tasks within a deliverable's production.
    """
    __tablename__ = "internal_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign Keys linking to the Deliverable and Project
    deliverable_id = Column(UUID(as_uuid=True), ForeignKey('deliverables.id'), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey('projects.id'), nullable=False) # For convenience

    # For parent-subtask relationship (e.g., rework tasks)
    parent_task_id = Column(UUID(as_uuid=True), ForeignKey('internal_tasks.id'), nullable=True)
    
    task_name = Column(String(255), nullable=False) # Descriptive name for the task
    task_type = Column(Enum(TaskType), nullable=False) # Type of work (e.g., modeling, rendering)
    
    # User assigned to this task (if User model is implemented)
    # assigned_to_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)

    status = Column(Enum(TaskStatus), default=TaskStatus.TODO, nullable=False)
    priority = Column(Enum(Priority), default=Priority.NORMAL, nullable=False)

    start_date = Column(DateTime, nullable=True)
    tentative_end_date = Column(DateTime, nullable=True) # Expected completion
    actual_end_date = Column(DateTime, nullable=True) # Actual completion time

    description = Column(Text, nullable=True) # Detailed description of the task
    
    # Source of the task, e.g., if it was created due to feedback on a specific ReviewItem
    source_review_item_id = Column(UUID(as_uuid=True), ForeignKey('review_items.id'), nullable=True) 

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # --- Relationships ---
    # Relationships back to Project and Deliverable
    project_ref = relationship("Project", backref="internal_tasks_project", lazy="joined") # backref needed if 'internal_tasks' already used
    deliverable_ref = relationship("Deliverable", backref="internal_tasks_deliverable", lazy="joined")

    # Self-referencing relationship for parent/sub-tasks
    parent_task = relationship("InternalTask", remote_side=[id], backref="sub_tasks", uselist=False, lazy="joined")

    # Relationship to ReviewItem (many-to-one) - specify foreign_keys to resolve circular reference
    source_review_item_ref = relationship("ReviewItem", foreign_keys=[source_review_item_id], backref="related_internal_tasks", lazy="joined")

    def __repr__(self):
        """String representation for debugging."""
        return (f"<InternalTask(id='{self.id}', name='{self.task_name}', "
                f"deliverable_id='{self.deliverable_id}', status='{self.status.value}')>")