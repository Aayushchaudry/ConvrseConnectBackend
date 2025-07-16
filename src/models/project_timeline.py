# src/models/project_timeline.py

import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Boolean, DECIMAL, String, Date, Integer, func, CheckConstraint, Enum as PgEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from src.config.database import Base


class ProjectTimeline(Base):
    """
    SQLAlchemy model for the 'project_timeline' table.
    Planned and actual project timeline phases and milestones.
    """

    __tablename__ = "project_timeline"
    __table_args__ = {"schema": "connect_backend"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign Keys
    project_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("connect_backend.projects.id"), 
        nullable=False,
        index=True
    )

    # Timeline phase information
    phase_name = Column(String(255), nullable=False)
    phase_order = Column(Integer, nullable=False)

    # Planned timeline
    planned_start_date = Column(Date, nullable=True)
    planned_end_date = Column(Date, nullable=True)

    # Actual timeline
    actual_start_date = Column(Date, nullable=True)
    actual_end_date = Column(Date, nullable=True)

    # Phase metadata
    is_milestone = Column(Boolean, default=False, nullable=False)
    percentage_complete = Column(
        DECIMAL(5, 2), 
        default=0, 
        nullable=False
    )

    # Dependencies and relationships
    dependencies = Column(JSONB, nullable=True)  # Array of dependent phase IDs
    timeline_type = Column(
        PgEnum('interior', 'exterior', 'other', name='timelinetype', schema='connect_backend'),
        nullable=False,
        default='other'
    )

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    project_ref = relationship(
        "Project",
        backref="timeline_phases",
        lazy="joined"
    )

    # Table arguments with schema
    __table_args__ = {"schema": "connect_backend"}

    def calculate_phase_duration(self):
        """Calculate planned duration in days."""
        if self.planned_start_date and self.planned_end_date:
            return (self.planned_end_date - self.planned_start_date).days
        return None

    def calculate_actual_duration(self):
        """Calculate actual duration in days."""
        if self.actual_start_date and self.actual_end_date:
            return (self.actual_end_date - self.actual_start_date).days
        return None

    def is_delayed(self):
        """Check if the phase is delayed compared to planned timeline."""
        if self.planned_end_date and self.actual_end_date:
            return self.actual_end_date > self.planned_end_date
        elif self.planned_end_date and not self.actual_end_date:
            from datetime import date
            return date.today() > self.planned_end_date
        return False

    def __repr__(self):
        """String representation for debugging."""
        return (
            f"<ProjectTimeline(id='{self.id}', project_id='{self.project_id}', "
            f"phase='{self.phase_name}', order='{self.phase_order}', "
            f"completion='{self.percentage_complete}%')>"
        ) 