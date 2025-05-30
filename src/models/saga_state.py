# src/models/saga_state.py

import enum
import uuid
from sqlalchemy import Column, String, DateTime, func, Enum, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship # Used for defining relationships
from src.config.database import Base # Import Base from your database config

# --- Enums for SAGA Status and Type ---
# These enums provide controlled values for SAGA lifecycle and classification.

class SagaStatus(enum.Enum):
    """Overall status of a SAGA instance."""
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATING = "compensating" # When undoing previous steps due to failure
    CANCELED = "canceled"         # Manually canceled

class SagaType(enum.Enum):
    """Type of SAGA, distinguishing between Project and Deliverable level."""
    PROJECT_LIFECYCLE = "project_lifecycle"
    DELIVERABLE_PRODUCTION = "deliverable_production"

# --- SagaState ORM Model ---

class SagaState(Base):
    """
    SQLAlchemy model for the 'saga_state' table.
    Stores the current state and metadata for each SAGA instance.
    """
    __tablename__ = "saga_state" # This defines the table name in the database

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Unique identifier for this specific SAGA instance (e.g., one per project, one per deliverable)
    saga_id = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True) 
    
    # Classifies the type of SAGA instance
    saga_type = Column(Enum(SagaType), nullable=False)

    # Foreign Keys linking to the entities this SAGA is orchestrating
    # project_id is always present
    project_id = Column(UUID(as_uuid=True), ForeignKey('projects.id'), nullable=False)
    # deliverable_id is nullable because the Project SAGA doesn't have one
    # TODO: Uncomment when deliverables table is created
    # deliverable_id = Column(UUID(as_uuid=True), ForeignKey('deliverables.id'), nullable=True)
    deliverable_id = Column(UUID(as_uuid=True), nullable=True)  # Temporary until deliverables table exists

    # Current state in the SAGA's state machine
    current_state = Column(String(100), nullable=False) # e.g., 'INFO_GATHERING', 'AWAITING_CLIENT_REVIEW_RENDER'
    
    # Overall status of the SAGA instance
    status = Column(Enum(SagaStatus), default=SagaStatus.IN_PROGRESS, nullable=False)

    # Tracking for idempotency and recovery in event processing
    last_event_processed_id = Column(String(255), nullable=True) # ID of the last event processed
    last_event_processed_timestamp = Column(DateTime, nullable=True)
    last_command_sent_id = Column(String(255), nullable=True) # ID of the last command sent
    last_command_sent_timestamp = Column(DateTime, nullable=True)
    
    # Fields for retry mechanisms (useful for robustness)
    retry_attempts = Column(Integer, default=0, nullable=False)
    next_retry_at = Column(DateTime, nullable=True)

    # Automatic timestamps for auditing
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # --- Relationships (will be defined more fully as other models are created) ---
    # Defines the relationship with the Project model.
    # The 'back_populates' argument creates a bidirectional relationship.
    # project_ref = relationship("Project", back_populates="saga_states") # Requires a 'saga_states' relationship on Project model

    def __repr__(self):
        """String representation for debugging."""
        return (f"<SagaState(saga_id='{self.saga_id}', type='{self.saga_type.value}', "
                f"project_id='{self.project_id}', current_state='{self.current_state}', "
                f"status='{self.status.value}')>")