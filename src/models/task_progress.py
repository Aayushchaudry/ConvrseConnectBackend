# src/models/task_progress.py

import uuid
from sqlalchemy import Column, DateTime, ForeignKey, DECIMAL, Text, Date, func, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.config.database import Base


class TaskProgress(Base):
    """
    SQLAlchemy model for the 'task_progress' table.
    Daily progress tracking for tasks with percentage completion and hours spent.
    """

    __tablename__ = "task_progress"
    __table_args__ = {"schema": "connect_backend"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign Keys
    task_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("connect_backend.internal_tasks.id"), 
        nullable=False,
        index=True
    )

    # Progress tracking fields
    progress_date = Column(Date, nullable=False, index=True)
    percentage_complete = Column(
        DECIMAL(5, 2), 
        default=0, 
        nullable=False,
        # Add check constraint for percentage range (0-100)
    )
    hours_spent = Column(DECIMAL(8, 2), default=0, nullable=False)
    notes = Column(Text, nullable=True)

    # User tracking
    created_by = Column(UUID(as_uuid=True), nullable=False, index=True)  # User ID from auth-service

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    task_ref = relationship(
        "InternalTask",
        backref="progress_entries",
        lazy="joined"
    )

    # Table arguments with schema
    __table_args__ = {"schema": "connect_backend"}

    def calculate_cumulative_progress(self):
        """Calculate cumulative progress for the task up to this date."""
        # This would typically be calculated at the service layer
        # using queries to get all progress entries for the task
        pass

    def __repr__(self):
        """String representation for debugging."""
        return (
            f"<TaskProgress(id='{self.id}', task_id='{self.task_id}', "
            f"date='{self.progress_date}', percentage='{self.percentage_complete}', "
            f"hours='{self.hours_spent}')>"
        ) 