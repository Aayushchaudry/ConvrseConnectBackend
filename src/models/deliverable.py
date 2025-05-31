# src/models/deliverable.py

import enum
import uuid
from sqlalchemy import Column, String, DateTime, func, Integer, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship # To define relationships with other models
from src.config.database import Base # Import Base from your database config
from src.models.project import Project # Import Project model for ForeignKey

# --- Enums for Deliverable Status and Type ---
# These enums provide a controlled set of values for certain columns,
# ensuring data consistency.

class DeliverableStatus(enum.Enum):
    """Defines the high-level status of a Deliverable."""
    INFO_GATHERING = "info_gathering"
    MODELING_PENDING = "modeling_pending"
    TEXTURING_PENDING = "texturing_pending"
    RENDERING_PENDING = "rendering_pending"
    AWAITING_CLIENT_REVIEW = "awaiting_client_review"
    REVISIONS_IN_PROGRESS = "revisions_in_progress"
    READY_FOR_DELIVERY = "ready_for_delivery"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELED = "canceled"

class DeliverableType(enum.Enum):
    """Defines the type of deliverable."""
    RENDERED_IMAGES = "rendered_images"
    TECHNICAL_RENDERS = "technical_renders"
    EXTERIOR_VR_TOUR = "exterior_vr_tour"
    ANIMATED_VR_TOUR = "animated_vr_tour"
    VIDEO_WALKTHROUGH = "video_walkthrough"
    INVENTORY_MODULE = "inventory_module"
    LOCATION_MAP = "location_map"
    INTERACTIVE_SALES_APP = "interactive_sales_app"
    INTERACTIVE_DRONE_SHOOT = "interactive_drone_shoot"
    INTERPLAYER_SOFTWARE = "interplayer_software_av_room"

# --- Deliverable ORM Model ---

class Deliverable(Base):
    """
    SQLAlchemy model for the 'deliverables' table.
    Represents a single deliverable associated with a project.
    """
    __tablename__ = "deliverables"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign Key linking to the Project
    project_id = Column(UUID(as_uuid=True), ForeignKey('projects.id'), nullable=False)
    
    # Type of deliverable (e.g., Rendered Images, VR Tour)
    deliverable_type = Column(Enum(DeliverableType), nullable=False)
    
    # Sub-type if applicable (e.g., 'Interior Requirement', 'Exterior Requirement')
    deliverable_sub_type = Column(String(100), nullable=True)
    
    # Status of this specific deliverable within its lifecycle
    current_status = Column(Enum(DeliverableStatus), default=DeliverableStatus.INFO_GATHERING, nullable=False)
    
    # Tentative timeline in days for this deliverable
    tentative_timeline_days = Column(Integer, nullable=True)

    # Automatic timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # --- Relationships ---
    # Defines the many-to-one relationship with the Project model
    project_ref = relationship("Project", backref="deliverables", lazy="joined") # Use backref for simpler back-populates on Project
    
    # Relationships with other deliverable-specific models (will be defined later)
    # requirements = relationship("Requirement", back_populates="deliverable_ref")
    # internal_tasks = relationship("InternalTask", back_populates="deliverable_ref")
    # review_items = relationship("ReviewItem", back_populates="deliverable_ref")
    # project_outputs = relationship("ProjectOutput", back_populates="deliverable_ref")
    # saga_states = relationship("SagaState", back_populates="deliverable_ref") # If SagaState tracks deliverable_id

    def __repr__(self):
        """String representation for debugging."""
        return (f"<Deliverable(id='{self.id}', project_id='{self.project_id}', "
                f"type='{self.deliverable_type.value}', status='{self.current_status.value}')>")