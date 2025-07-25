# src/models/file_version.py

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, Boolean, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.config.database import Base


class VersionType(str, Enum):
    """Enum for file version types"""
    INITIAL = "initial"
    REVISION = "revision"
    FINAL = "final"


class FileVersion(Base):
    """
    SQLAlchemy model for the 'file_versions' table.
    Tracks version history and relationships between file versions.
    """

    __tablename__ = "file_versions"
    __table_args__ = {"schema": "connect_backend"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Reference to original platform file ID
    original_file_id = Column(UUID(as_uuid=True), nullable=False)
    
    # Reference to current version platform file ID
    current_file_id = Column(UUID(as_uuid=True), nullable=False)
    
    # Version information
    version_number = Column(Integer, nullable=False, default=1)
    version_type = Column(String(20), nullable=False, default=VersionType.INITIAL.value)
    
    # Version metadata
    version_notes = Column(String(500), nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=True)  # User ID who created this version
    is_final = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        """String representation for debugging."""
        return (
            f"<FileVersion(id='{self.id}', original_file_id='{self.original_file_id}', "
            f"version_number={self.version_number}, version_type='{self.version_type}')>"
        )