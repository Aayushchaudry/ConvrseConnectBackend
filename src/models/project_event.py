# src/models/project_event.py

import enum
import uuid
from sqlalchemy import Column, DateTime, ForeignKey, String, Text, Boolean, func
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.orm import relationship

from src.config.database import Base


class EventType(enum.Enum):
    """Defines the type of project event."""
    
    MILESTONE = "milestone"
    REVIEW = "review"
    DEADLINE = "deadline"
    MEETING = "meeting"
    DELIVERY = "delivery"
    CLIENT_FEEDBACK = "client_feedback"


class EventStatus(enum.Enum):
    """Defines the status of an event."""
    
    UPCOMING = "upcoming"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    OVERDUE = "overdue"


class ProjectEvent(Base):
    """
    SQLAlchemy model for the 'project_events' table.
    Stores events, milestones, and upcoming activities for projects and deliverables.
    """

    __tablename__ = "project_events"
    __table_args__ = {"schema": "connect_backend"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign Keys
    project_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("connect_backend.projects.id"), 
        nullable=False,
        index=True
    )
    
    deliverable_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("connect_backend.deliverables.id"), 
        nullable=True,  # Events can be project-level or deliverable-specific
        index=True
    )

    # Event details
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    event_type = Column(
        ENUM(EventType, schema="connect_backend"), 
        nullable=False
    )
    
    # Event scheduling
    scheduled_date = Column(DateTime, nullable=False, index=True)
    due_date = Column(DateTime, nullable=True)  # For events with deadlines
    
    # Event status and priority
    status = Column(
        ENUM(EventStatus, schema="connect_backend"), 
        default=EventStatus.UPCOMING,
        nullable=False
    )
    
    is_critical = Column(Boolean, default=False, nullable=False)
    is_automated = Column(Boolean, default=False, nullable=False)  # System-generated vs manual
    
    # Notification settings
    notify_days_before = Column(UUID(as_uuid=True), nullable=True)  # Days before to notify
    notification_sent = Column(Boolean, default=False, nullable=False)
    
    # User assignments
    assigned_to = Column(UUID(as_uuid=True), nullable=True, index=True)  # User responsible
    created_by = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    project_ref = relationship("Project", backref="events", lazy="joined")
    deliverable_ref = relationship("Deliverable", backref="events", lazy="joined")

    def is_overdue(self):
        """Check if the event is overdue."""
        from datetime import datetime
        if self.status in [EventStatus.COMPLETED, EventStatus.CANCELLED]:
            return False
        return datetime.utcnow() > self.scheduled_date

    def days_until_event(self):
        """Calculate days until the event."""
        from datetime import datetime
        if self.status == EventStatus.COMPLETED:
            return 0
        delta = self.scheduled_date - datetime.utcnow()
        return max(0, delta.days)

    def __repr__(self):
        """String representation for debugging."""
        return (
            f"<ProjectEvent(id='{self.id}', title='{self.title}', "
            f"type='{self.event_type.value}', status='{self.status.value}', "
            f"date='{self.scheduled_date}')>"
        ) 