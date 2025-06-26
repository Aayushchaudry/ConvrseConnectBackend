# src/models/project.py

import enum
import uuid

from sqlalchemy import DECIMAL, Column, DateTime, Enum, Integer, String, func
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import (
    relationship,
)  # Used for defining relationships between models

from src.config.database import Base  # Import Base from your database config


# --- Enums for Project Status ---
# Using the exact status values provided by you.
class ProjectStatus(enum.Enum):
    """Defines the high-level status of a project."""

    INITIATED = "initiated"
    INFO_GATHERING = "info_gathering"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


# --- Project ORM Model ---


class Project(Base):
    """
    SQLAlchemy model for the 'projects' table.
    Represents a high-level project in the system.
    """

    __tablename__ = "projects"  # This defines the table name in the database
    __table_args__ = {"schema": "connect_backend"}

    # project_id as Primary Key (maps to 'id' in SQLAlchemy for consistency)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(
        String(255), nullable=False, index=True
    )  # Project name, indexed for faster lookup

    # Status of the project, using our new defined Enum
    status = Column(
        ENUM("initiated", "info_gathering", "in_progress", "completed", name="projectstatus", schema="connect_backend"), default="initiated", nullable=False
    )

    # Financial details - renamed from total_fee to budget
    budget = Column(
        DECIMAL(10, 2), nullable=True
    )  # Total budget for the project, e.g., 3422020.00

    # New fields for enhanced budget tracking
    calculated_budget = Column(DECIMAL(12, 2), nullable=True)  # Auto-calculated from deliverable pricing
    actual_cost = Column(DECIMAL(12, 2), default=0, nullable=False)  # Actual costs incurred
    budget_variance = Column(DECIMAL(12, 2), default=0, nullable=False)  # Difference between budget and actual
    budget_last_calculated = Column(DateTime, nullable=True)  # When budget was last recalculated

    # Timelines - end_date instead of due_date
    start_date = Column(DateTime, nullable=True)
    end_date = Column(
        DateTime, nullable=True
    )  # Overall project deadline (renamed from due_date)

    # --- AUTH INTEGRATION FIELDS ---
    # Business context - links project to a business from auth-service
    business_id = Column(
        String(255), nullable=False, index=True
    )  # Foreign key to businesses table in auth-service

    # User context - who created and is assigned to this project
    created_by = Column(
        UUID(as_uuid=True), nullable=False, index=True
    )  # Foreign key to users table in auth-service (proper UUID)
    assigned_to = Column(
        UUID(as_uuid=True), nullable=True, index=True
    )  # Foreign key to users table in auth-service (proper UUID, optional)

    # Automatic timestamps for auditing
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    # --- Relationships (will be defined as other models are created) ---
    # These define how this Project model relates to other models.
    # For example, a Project has many Deliverables and many SagaState entries.
    # You will uncomment or add similar lines here as you create related models.
    # deliverables = relationship("Deliverable", back_populates="project_ref") # Example
    # saga_states = relationship("SagaState", back_populates="project_ref") # Example

    def __repr__(self):
        """String representation for debugging."""
        return f"<Project(id='{self.id}', name='{self.name}', status='{self.status.value}', business_id='{self.business_id}')>"
