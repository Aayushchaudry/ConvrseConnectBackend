# src/models/requirement_file.py

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.config.database import Base  # Import Base from your database config
from src.models.requirement import (
    Requirement,
)  # Import Requirement model for ForeignKey

# from src.models.user import User # Import User model if you implement it for uploaded_by_user_id


class RequirementFile(Base):
    """
    SQLAlchemy model for the 'requirement_files' table.
    Stores metadata about files uploaded to fulfill specific requirements.
    """

    __tablename__ = "requirement_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign Key linking to the Requirement it fulfills
    requirement_id = Column(
        UUID(as_uuid=True), ForeignKey("requirements.id"), nullable=False
    )

    # Metadata about the file
    file_name = Column(
        String(255), nullable=False
    )  # Original name of the uploaded file
    file_path = Column(
        Text, nullable=False
    )  # URL to the file in cloud storage (e.g., S3 URL)
    file_type = Column(String(50), nullable=True)  # e.g., 'CAD', 'JPEG', 'PDF', 'MAX'

    # Who uploaded the file (if you implement a User model)
    # uploaded_by_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)

    # Automatic timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    # --- Relationships ---
    # Relationship to the Requirement model (many-to-one)
    requirement_ref = relationship(
        "Requirement", backref="requirement_files", lazy="joined"
    )
    # Relationship to User model (if implemented)
    # uploader_user_ref = relationship("User", back_populates="uploaded_requirement_files")

    def __repr__(self):
        """String representation for debugging."""
        return (
            f"<RequirementFile(id='{self.id}', requirement_id='{self.requirement_id}', "
            f"file_name='{self.file_name}', file_type='{self.file_type}')>"
        )
