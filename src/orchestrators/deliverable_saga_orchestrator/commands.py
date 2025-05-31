# src/orchestrators/deliverable_saga_orchestrator/commands.py

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
import uuid # For uuid.uuid4()
from typing import Optional, List, Dict, Any

# --- Base Command Definition ---
# All your commands inherit from this to ensure common fields.
@dataclass
class BaseCommand:
    command_id: UUID
    timestamp: datetime
    command_type: str

    def __post_init__(self):
        if not hasattr(self, 'command_type') or self.command_type is None:
            self.command_type = self.__class__.__name__

# --- Commands sent by Deliverable SAGA Orchestrator ---

@dataclass
class StartDeliverableInfoGatheringCommand(BaseCommand):
    """
    Command to instruct the Information Gathering Service to start or confirm
    gathering specific requirements for a deliverable.
    Published by: Deliverable SAGA Orchestrator (often initial step after SAGA start)
    Consumed by: Information Gathering Service
    """
    project_id: UUID
    deliverable_id: UUID

    def __init__(self, project_id: UUID, deliverable_id: UUID, command_id: Optional[UUID] = None, timestamp: Optional[datetime] = None, command_type: Optional[str] = None):
        super().__init__(
            command_id=command_id or uuid.uuid4(), 
            timestamp=timestamp or datetime.utcnow(), 
            command_type=command_type or "StartDeliverableInfoGatheringCommand"
        )
        self.project_id = project_id
        self.deliverable_id = deliverable_id


@dataclass
class InitiateModelingCommand(BaseCommand):
    """
    Command to instruct the Production Management Service to begin 3D modeling
    for a deliverable.
    Published by: Deliverable SAGA Orchestrator
    Consumed by: Production Management Service
    """
    project_id: UUID
    deliverable_id: UUID
    # Optional: Initial modeling requirements (e.g., specific CAD files to use)
    # modeling_requirements: Optional[Dict[str, Any]] = None

    def __init__(self, project_id: UUID, deliverable_id: UUID, command_id: Optional[UUID] = None, timestamp: Optional[datetime] = None, command_type: Optional[str] = None):
        super().__init__(
            command_id=command_id or uuid.uuid4(), 
            timestamp=timestamp or datetime.utcnow(), 
            command_type=command_type or "InitiateModelingCommand"
        )
        self.project_id = project_id
        self.deliverable_id = deliverable_id


@dataclass
class InitiateTexturingCommand(BaseCommand):
    """
    Command to instruct the Production Management Service to begin texturing
    for a deliverable.
    Published by: Deliverable SAGA Orchestrator
    Consumed by: Production Management Service
    """
    project_id: UUID
    deliverable_id: UUID
    # Optional: Specific material/texture details

    def __init__(self, project_id: UUID, deliverable_id: UUID, command_id: Optional[UUID] = None, timestamp: Optional[datetime] = None, command_type: Optional[str] = None):
        super().__init__(
            command_id=command_id or uuid.uuid4(), 
            timestamp=timestamp or datetime.utcnow(), 
            command_type=command_type or "InitiateTexturingCommand"
        )
        self.project_id = project_id
        self.deliverable_id = deliverable_id


@dataclass
class InitiateRenderingCommand(BaseCommand):
    """
    Command to instruct the Production Management Service to begin rendering
    for a deliverable.
    Published by: Deliverable SAGA Orchestrator
    Consumed by: Production Management Service
    """
    project_id: UUID
    deliverable_id: UUID
    render_type: str # e.g., 'white_render', 'low_res_texture_render', 'final_render'
    # Optional: camera_angles: List[Dict[str, Any]] = None # For specific renders

    def __init__(self, project_id: UUID, deliverable_id: UUID, render_type: str, command_id: Optional[UUID] = None, timestamp: Optional[datetime] = None, command_type: Optional[str] = None):
        super().__init__(
            command_id=command_id or uuid.uuid4(), 
            timestamp=timestamp or datetime.utcnow(), 
            command_type=command_type or "InitiateRenderingCommand"
        )
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.render_type = render_type


@dataclass
class GenerateReviewItemCommand(BaseCommand):
    """
    Command to instruct the Review Service to generate a review item
    for client feedback on a deliverable.
    Published by: Deliverable SAGA Orchestrator
    Consumed by: Review Service
    """
    project_id: UUID
    deliverable_id: UUID
    review_item_type: str # e.g., 'white_render_review', 'texture_review', 'final_review'
    asset_urls: List[str] # URLs to the assets to be reviewed
    
    def __init__(self, project_id: UUID, deliverable_id: UUID, review_item_type: str, asset_urls: List[str] = None, command_id: Optional[UUID] = None, timestamp: Optional[datetime] = None, command_type: Optional[str] = None):
        super().__init__(
            command_id=command_id or uuid.uuid4(), 
            timestamp=timestamp or datetime.utcnow(), 
            command_type=command_type or "GenerateReviewItemCommand"
        )
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.review_item_type = review_item_type
        self.asset_urls = asset_urls or []


@dataclass
class GenerateFinalOutputCommand(BaseCommand):
    """
    Command to instruct the Delivery Service to generate and make available
    the final approved output for a deliverable.
    Published by: Deliverable SAGA Orchestrator
    Consumed by: Delivery Service
    """
    project_id: UUID
    deliverable_id: UUID
    output_name: str
    # Optional: final_asset_locations: List[str] # URLs to final files
    
    def __init__(self, project_id: UUID, deliverable_id: UUID, output_name: str, command_id: Optional[UUID] = None, timestamp: Optional[datetime] = None, command_type: Optional[str] = None):
        super().__init__(
            command_id=command_id or uuid.uuid4(), 
            timestamp=timestamp or datetime.utcnow(), 
            command_type=command_type or "GenerateFinalOutputCommand"
        )
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.output_name = output_name


@dataclass
class UpdateDeliverableStatusInDBCommand(BaseCommand):
    """
    Command to update the deliverable's overall status in the database.
    (This is different from SAGA state; it's the Deliverable model's status)
    Published by: Deliverable SAGA Orchestrator
    Consumed by: Deliverable Service
    """
    project_id: UUID
    deliverable_id: UUID
    new_status: str # String representation of DeliverableStatus enum

    def __init__(self, project_id: UUID, deliverable_id: UUID, new_status: str, command_id: Optional[UUID] = None, timestamp: Optional[datetime] = None, command_type: Optional[str] = None):
        super().__init__(
            command_id=command_id or uuid.uuid4(), 
            timestamp=timestamp or datetime.utcnow(), 
            command_type=command_type or "UpdateDeliverableStatusInDBCommand"
        )
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.new_status = new_status


# Note: Commands like CreateReworkTaskCommand and UpdateInternalTaskStatusCommand
# are already defined in src/commands/production_commands.py.
# The Deliverable SAGA Orchestrator will use those too.