# src/models/project_output.py

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.config.database import Base  # Import Base from your database config
from src.models.deliverable import (
    Deliverable,
)  # Import Deliverable model for ForeignKey
from src.models.project import (
    Project,
)  # Import Project model for ForeignKey (for convenience)


class ProjectOutput(Base):
    """
    SQLAlchemy model for the 'project_outputs' table.
    Stores metadata and access links for final, approved deliverables.
    """

    __tablename__ = "project_outputs"
    __table_args__ = {"schema": "connect_backend"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign Keys linking to the Deliverable and Project
    deliverable_id = Column(
        UUID(as_uuid=True), ForeignKey("connect_backend.deliverables.id"), nullable=False
    )
    project_id = Column(
        UUID(as_uuid=True), ForeignKey("connect_backend.projects.id"), nullable=False
    )  # For convenience

    # Descriptive name for the final output (e.g., "Final High-Res Renders Pack")
    output_name = Column(String(255), nullable=False)

    # URL to the final asset (e.g., S3 URL to a zip file, or link to a live app)
    output_url = Column(Text, nullable=False)

    # Date/time when the final output was officially delivered
    delivery_date = Column(DateTime, default=func.now(), nullable=False)

    # Boolean to indicate if clients can still leave comments on this final output
    comments_allowed_on_output = Column(Boolean, default=False, nullable=False)

    # Automatic timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    # --- Relationships ---
    # Relationships back to Project and Deliverable
    project_ref = relationship(
        "Project", backref="project_outputs_project", lazy="joined"
    )
    deliverable_ref = relationship(
        "Deliverable", backref="project_outputs_deliverable", lazy="joined"
    )

    # Relationship to ClientFeedback (one-to-many, specific to this output)
    # client_feedbacks_output = relationship("ClientFeedback", back_populates="project_output_ref") # Requires back_populates on ClientFeedback model

    def __repr__(self):
        """String representation for debugging."""
        return (
            f"<ProjectOutput(id='{self.id}', name='{self.output_name}', "
            f"deliverable_id='{self.deliverable_id}', url='{self.output_url[:30]}...')>"
        )
