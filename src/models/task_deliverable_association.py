# src/models/task_deliverable_association.py

import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Boolean, DECIMAL, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.config.database import Base


class TaskDeliverableAssociation(Base):
    """
    SQLAlchemy model for the 'task_deliverable_associations' table.
    Junction table for many-to-many relationship between tasks and deliverables.
    """

    __tablename__ = "task_deliverable_associations"
    __table_args__ = {"schema": "connect_backend"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign Keys
    task_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("connect_backend.internal_tasks.id"), 
        nullable=False,
        index=True
    )
    deliverable_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("connect_backend.deliverables.id"), 
        nullable=False,
        index=True
    )

    # Association metadata
    is_primary_deliverable = Column(Boolean, default=False, nullable=False)
    estimated_hours = Column(DECIMAL(8, 2), nullable=True)
    actual_hours = Column(DECIMAL(8, 2), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    task_ref = relationship(
        "InternalTask",
        backref="deliverable_associations",
        lazy="joined"
    )
    deliverable_ref = relationship(
        "Deliverable",
        backref="task_associations", 
        lazy="joined"
    )

    # Table arguments with schema
    __table_args__ = {"schema": "connect_backend"}

    def __repr__(self):
        """String representation for debugging."""
        return (
            f"<TaskDeliverableAssociation(id='{self.id}', "
            f"task_id='{self.task_id}', deliverable_id='{self.deliverable_id}', "
            f"is_primary='{self.is_primary_deliverable}')>"
        ) 