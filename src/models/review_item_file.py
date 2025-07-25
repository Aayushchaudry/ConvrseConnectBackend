# src/models/review_item_file.py

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.config.database import Base
from src.models.review_item import ReviewItem


class ReviewItemFile(Base):
    """
    SQLAlchemy model for the 'review_item_files' table.
    Stores metadata about files associated with review items.
    Supports multiple files per review item with sequence ordering.
    """

    __tablename__ = "review_item_files"
    __table_args__ = {"schema": "connect_backend"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign Key linking to the ReviewItem
    review_item_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("connect_backend.review_items.id"), 
        nullable=False
    )

    # Platform-service file reference (primary file identifier)
    platform_file_id = Column(UUID(as_uuid=True), nullable=False)

    # File metadata
    file_name = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=True)  # e.g., 'png', 'mp4', 'pdf'
    file_size = Column(Integer, nullable=True)  # File size in bytes
    
    # Ordering and organization
    sequence_order = Column(Integer, nullable=False, default=1)  # Order within review item
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # --- Relationships ---
    # Relationship to the ReviewItem model (many-to-one)
    review_item_ref = relationship(
        "ReviewItem", 
        backref="review_item_files", 
        lazy="joined"
    )

    def __repr__(self):
        """String representation for debugging."""
        return (
            f"<ReviewItemFile(id='{self.id}', review_item_id='{self.review_item_id}', "
            f"platform_file_id='{self.platform_file_id}', file_name='{self.file_name}', "
            f"sequence_order={self.sequence_order})>"
        )