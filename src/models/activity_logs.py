# src/models/activity_logs.py

import uuid

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from src.config.database import Base


class ActivityLog(Base):
    """
    SQLAlchemy model for the 'activity_logs' table.
    Tracks user activities for audit trails across the system.
    """

    __tablename__ = "activity_logs"
    __table_args__ = {"schema": "connect_backend"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # User and business context from auth-service
    user_id = Column(
        Integer, nullable=False, index=True
    )  # Foreign key to users table in auth-service
    business_id = Column(
        Integer, nullable=False, index=True
    )  # Foreign key to businesses table in auth-service

    # Action details
    action = Column(
        String(100), nullable=False, index=True
    )  # Action performed (e.g., "project_created", "deliverable_updated")
    resource_type = Column(
        String(50), nullable=False, index=True
    )  # Type of resource (e.g., "project", "deliverable")
    resource_id = Column(
        String(100), nullable=True, index=True
    )  # ID of the affected resource

    # Additional context and details
    details = Column(JSON, nullable=True)  # JSON object with additional context
    ip_address = Column(String(45), nullable=True)  # Client IP address
    user_agent = Column(Text, nullable=True)  # Client user agent

    # Service context
    service_name = Column(
        String(50), nullable=False, default="convrse-connect-backend"
    )  # Source service
    correlation_id = Column(
        String(36), nullable=True, index=True
    )  # Request correlation ID

    # Automatic timestamp
    created_at = Column(DateTime, default=func.now(), nullable=False, index=True)

    def __repr__(self):
        """String representation for debugging."""
        return (
            f"<ActivityLog(id='{self.id}', user_id='{self.user_id}', "
            f"action='{self.action}', resource_type='{self.resource_type}')>"
        )
