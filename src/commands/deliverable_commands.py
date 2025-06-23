# src/commands/deliverable_commands.py

import uuid  # For uuid.uuid4()
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID


# --- Deliverable-Specific Commands (sent by Deliverable SAGA Orchestrator) ---


@dataclass
class InitiateDeliverableProductionCommand:
    """
    Command to instruct the Production Management Service to begin initial
    production tasks (e.g., modeling, base environment setup) for a deliverable.
    Published by: Deliverable SAGA Orchestrator
    Consumed by: Production Management Service
    """

    project_id: UUID
    deliverable_id: UUID
    command_id: UUID = None
    timestamp: datetime = None
    command_type: str = None
    
    def __post_init__(self):
        if self.command_id is None:
            self.command_id = uuid.uuid4()
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.command_type is None:
            self.command_type = "InitiateDeliverableProductionCommand"


@dataclass
class GenerateReviewItemCommand:
    """
    Command to create a new review item for a deliverable.
    Enhanced to support file references and explicit sequence control.
    """
    project_id: UUID
    deliverable_id: UUID
    review_item_type: str = "WORK_REVIEW"  # Default to business-specific type
    platform_file_id: Optional[UUID] = None  # Reference to platform-service file (updated from int to UUID)
    sequence_number: Optional[int] = None  # Explicit sequence control for multiple files from same task
    item_url: Optional[str] = None  # Optional URL (deprecated in favor of file references)
    command_id: UUID = None
    timestamp: datetime = None
    command_type: str = None

    def __post_init__(self):
        if self.command_id is None:
            self.command_id = uuid.uuid4()
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.command_type is None:
            self.command_type = "GenerateReviewItemCommand"
        
        # Convert string UUIDs to UUID objects if necessary
        if isinstance(self.project_id, str):
            self.project_id = UUID(self.project_id)
        if isinstance(self.deliverable_id, str):
            self.deliverable_id = UUID(self.deliverable_id)
        if isinstance(self.platform_file_id, str):
            try:
                self.platform_file_id = UUID(self.platform_file_id)
            except ValueError:
                # Handle integer string during transition
                import uuid as uuid_lib
                namespace = uuid_lib.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
                self.platform_file_id = uuid_lib.uuid5(namespace, f"content_id_{self.platform_file_id}")
        elif isinstance(self.platform_file_id, int):
            # Convert integer ID to UUID using deterministic method (transition period)
            import uuid as uuid_lib
            namespace = uuid_lib.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
            self.platform_file_id = uuid_lib.uuid5(namespace, f"content_id_{self.platform_file_id}")


@dataclass
class UpdateDeliverableStatusCommand:
    """
    A command to update the overall status of a deliverable.
    Published by: Deliverable SAGA Orchestrator
    Consumed by: Deliverable Service (to update Deliverable model)
    """

    project_id: UUID
    deliverable_id: UUID
    new_status: str  # e.g., 'modeling_pending', 'revisions_in_progress', 'delivered'
    command_id: UUID = None
    timestamp: datetime = None
    command_type: str = None

    def __post_init__(self):
        if self.command_id is None:
            self.command_id = uuid.uuid4()
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.command_type is None:
            self.command_type = "UpdateDeliverableStatusCommand"


# ... (Other deliverable-specific commands will be defined here later)
# e.g., GenerateFinalOutputCommand (for Delivery Service)
