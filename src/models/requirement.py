# src/models/requirement.py

import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.config.database import Base  # Import Base from your database config
from src.models.deliverable import (
    Deliverable,
)  # Import Deliverable model for ForeignKey
from src.models.project import (
    Project,
)  # Import Project model for ForeignKey (for convenience/denormalization)

# --- Enums for Requirement Type and Status ---


class RequirementType(enum.Enum):
    """Defines the type of data expected for a requirement."""

    FILE_UPLOAD = "file_upload"
    TEXT_INPUT = "text_input"
    BOOLEAN_INPUT = "boolean_input"
    JSON_INPUT = "json_input"  # For complex structured data like highlights list


class RequirementStatus(enum.Enum):
    """Defines the status of a specific requirement."""

    PENDING = "pending"  # Waiting for client/internal team to provide
    RECEIVED = "received"  # Data/file has been provided
    APPROVED = "approved"  # Client has approved this specific requirement (e.g., a specific material choice)
    NOT_APPLICABLE = (
        "not_applicable"  # This requirement does not apply to this deliverable instance
    )


# --- Requirement ORM Model ---


class Requirement(Base):
    """
    SQLAlchemy model for the 'requirements' table.
    Stores specific requirements for a deliverable.
    """

    __tablename__ = "requirements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign Keys linking to the Deliverable and Project
    deliverable_id = Column(
        UUID(as_uuid=True), ForeignKey("deliverables.id"), nullable=False
    )
    project_id = Column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )  # For convenience in queries

    # Name of the requirement (e.g., 'Floor Plan Cad File', 'Theme/Mood Board')
    requirement_name = Column(String(255), nullable=False)

    # Type of data expected for this requirement
    requirement_type = Column(Enum(RequirementType), nullable=False)

    # Value for non-file requirements (e.g., 'Yes' for boolean, JSON string for structured data)
    value = Column(
        Text, nullable=True
    )  # Use Text for JSON_INPUT if you store stringified JSON

    # Status of this specific requirement
    status = Column(
        Enum(RequirementStatus), default=RequirementStatus.PENDING, nullable=False
    )

    # Indicates if this requirement is critical for the deliverable
    is_mandatory = Column(Boolean, default=False, nullable=False)

    # Additional notes or context for the requirement
    notes = Column(Text, nullable=True)

    # Automatic timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    # --- Relationships ---
    # Relationship to the Deliverable model (many-to-one)
    deliverable_ref = relationship("Deliverable", backref="requirements", lazy="joined")
    # Relationship to the Project model (many-to-one)
    project_ref = relationship("Project", backref="requirements", lazy="joined")

    # Relationships with RequirementFiles (if requirement_type is FILE_UPLOAD)
    # requirement_files = relationship("RequirementFile", back_populates="requirement_ref")

    def __repr__(self):
        """String representation for debugging."""
        return (
            f"<Requirement(id='{self.id}', name='{self.requirement_name}', "
            f"deliverable_id='{self.deliverable_id}', status='{self.status.value}')>"
        )
