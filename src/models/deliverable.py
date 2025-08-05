# src/models/deliverable.py

import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.orm import relationship  # To define relationships with other models

from src.config.database import Base  # Import Base from your database config
from src.models.project import Project  # Import Project model for ForeignKey

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

    @classmethod
    def _missing_(cls, value):
        """Handle dynamic rendered_images_* values for multiple renders."""
        if isinstance(value, str) and value.startswith("rendered_images_") and value != "rendered_images":
            try:
                render_number = int(value.split("_")[-1])
                if render_number >= 1:
                    # Create a new enum member dynamically
                    member_name = f"RENDERED_IMAGES_{render_number}"
                    member_value = value
                    
                    # Create the enum member
                    new_member = enum.Enum._member_type_.__new__(cls, member_name, member_value)
                    new_member._name_ = member_name
                    new_member._value_ = member_value
                    
                    # Add to the enum's member maps
                    cls._member_map_[member_name] = new_member
                    cls._value2member_map_[member_value] = new_member
                    
                    return new_member
            except ValueError:
                pass
        return None


# --- Deliverable ORM Model ---


class Deliverable(Base):
    """
    SQLAlchemy model for the 'deliverables' table.
    Represents a single deliverable associated with a project.
    """

    __tablename__ = "deliverables"
    __table_args__ = {"schema": "connect_backend"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign Key linking to the Project
    project_id = Column(UUID(as_uuid=True), ForeignKey("connect_backend.projects.id"), nullable=False)

    # Type of deliverable (e.g., Rendered Images, VR Tour)
    deliverable_type = Column(String(100), nullable=False)
    
    # Sub-type for interior/exterior specification
    deliverable_sub_type = Column(String(100), nullable=True)
    
    # Quantity for rendered images (e.g., 5 for rendered_images_1 through rendered_images_5)
    deliverable_quantity = Column(Integer, nullable=True)

    # Status of this specific deliverable within its lifecycle
    current_status = Column(
        ENUM("info_gathering", "modeling_pending", "texturing_pending", "rendering_pending", 
             "awaiting_client_review", "revisions_in_progress", "ready_for_delivery", 
             "delivered", "failed", "canceled", 
             name="deliverablestatus", schema="connect_backend"), 
        default="info_gathering",
        nullable=False,
    )

    # Tentative timeline in days for this deliverable
    tentative_timeline_days = Column(Integer, nullable=True)

    # --- AUTH INTEGRATION FIELDS ---
    # User context - who is assigned to and who created this deliverable
    assigned_to = Column(
        UUID(as_uuid=True), nullable=True, index=True
    )  # Foreign key to users table in auth-service (proper UUID)
    created_by = Column(
        UUID(as_uuid=True), nullable=False, index=True
    )  # Foreign key to users table in auth-service (proper UUID)

    # Automatic timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    # --- Relationships ---
    # Defines the many-to-one relationship with the Project model
    project_ref = relationship(
        "Project", backref="deliverables", lazy="joined"
    )  # Use backref for simpler back-populates on Project

    # Relationships with other deliverable-specific models (will be defined later)
    # requirements = relationship("Requirement", back_populates="deliverable_ref")
    # internal_tasks = relationship("InternalTask", back_populates="deliverable_ref")
    # review_items = relationship("ReviewItem", back_populates="deliverable_ref")
    # project_outputs = relationship("ProjectOutput", back_populates="deliverable_ref")
    # saga_states = relationship("SagaState", back_populates="deliverable_ref") # If SagaState tracks deliverable_id

    def __repr__(self):
        """String representation for debugging."""
        return (
            f"<Deliverable(id='{self.id}', project_id='{self.project_id}', "
            f"type='{self.deliverable_type.value}', status='{self.current_status.value}', assigned_to='{self.assigned_to}')>"
        )
