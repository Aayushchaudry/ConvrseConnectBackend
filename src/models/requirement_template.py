# src/models/requirement_template.py

import uuid
from sqlalchemy import Column, DateTime, Boolean, String, Text, Enum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.config.database import Base
from src.models.requirement import RequirementType  # Import the enum from existing requirement model


class RequirementTemplate(Base):
    """
    SQLAlchemy model for the 'requirement_templates' table.
    Templates for auto-generating requirements based on deliverable types.
    """

    __tablename__ = "requirement_templates"
    __table_args__ = {"schema": "connect_backend"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Template identification
    deliverable_type = Column(String(100), nullable=False, index=True)
    requirement_name = Column(String(255), nullable=False)

    # Requirement specification
    requirement_type = Column(
        Enum(RequirementType, schema="connect_backend"), 
        nullable=False
    )

    # Template metadata
    is_mandatory = Column(Boolean, default=False, nullable=False)
    default_value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    def generate_requirement_instance(self, project_id, deliverable_id=None):
        """
        Generate a requirement instance from this template.
        Returns a dictionary that can be used to create a Requirement object.
        """
        from src.models.requirement import RequirementStatus
        
        return {
            "project_id": project_id,
            "deliverable_id": deliverable_id,
            "requirement_name": self.requirement_name,
            "requirement_type": self.requirement_type,
            "value": self.default_value,
            "status": RequirementStatus.PENDING,
            "is_mandatory": self.is_mandatory,
            "notes": self.description,
            "is_project_level": deliverable_id is None,
            "template_id": self.id
        }

    def __repr__(self):
        """String representation for debugging."""
        return (
            f"<RequirementTemplate(id='{self.id}', "
            f"deliverable_type='{self.deliverable_type}', "
            f"name='{self.requirement_name}', "
            f"type='{self.requirement_type.value}')>"
        ) 