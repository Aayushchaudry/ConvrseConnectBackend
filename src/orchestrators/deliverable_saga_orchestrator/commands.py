# src/orchestrators/deliverable_saga_orchestrator/commands.py

import uuid  # For uuid.uuid4()
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID


# --- Commands sent by Deliverable SAGA Orchestrator ---


@dataclass
class StartDeliverableInfoGatheringCommand:
    """
    Command to instruct the Information Gathering Service to start or confirm
    gathering specific requirements for a deliverable.
    Published by: Deliverable SAGA Orchestrator (often initial step after SAGA start)
    Consumed by: Information Gathering Service
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
            self.command_type = "StartDeliverableInfoGatheringCommand"


@dataclass
class InitiateModelingCommand:
    """
    Command to instruct the Production Management Service to begin 3D modeling
    for a deliverable.
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
            self.command_type = "InitiateModelingCommand"


@dataclass
class InitiateTexturingCommand:
    """
    Command to instruct the Production Management Service to begin texturing
    for a deliverable.
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
            self.command_type = "InitiateTexturingCommand"


@dataclass
class InitiateRenderingCommand:
    """
    Command to instruct the Production Management Service to begin rendering
    for a deliverable.
    Published by: Deliverable SAGA Orchestrator
    Consumed by: Production Management Service
    """

    project_id: UUID
    deliverable_id: UUID
    render_type: str  # e.g., 'white_render', 'low_res_texture_render', 'final_render'
    command_id: UUID = None
    timestamp: datetime = None
    command_type: str = None

    def __post_init__(self):
        if self.command_id is None:
            self.command_id = uuid.uuid4()
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.command_type is None:
            self.command_type = "InitiateRenderingCommand"


@dataclass
class GenerateFinalOutputCommand:
    """
    Command to instruct the Delivery Service to generate and make available
    the final approved output for a deliverable.
    Published by: Deliverable SAGA Orchestrator
    Consumed by: Delivery Service
    """

    project_id: UUID
    deliverable_id: UUID
    output_name: str
    approved_review_item_id: Optional[UUID] = None  # ID of the approved review item to use as source
    command_id: UUID = None
    timestamp: datetime = None
    command_type: str = None

    def __post_init__(self):
        if self.command_id is None:
            self.command_id = uuid.uuid4()
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.command_type is None:
            self.command_type = "GenerateFinalOutputCommand"


@dataclass
class UpdateDeliverableStatusInDBCommand:
    """
    Command to update the deliverable's overall status in the database.
    (This is different from SAGA state; it's the Deliverable model's status)
    Published by: Deliverable SAGA Orchestrator
    Consumed by: Deliverable Service
    """

    project_id: UUID
    deliverable_id: UUID
    new_status: str  # String representation of DeliverableStatus enum
    command_id: UUID = None
    timestamp: datetime = None
    command_type: str = None

    def __post_init__(self):
        if self.command_id is None:
            self.command_id = uuid.uuid4()
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.command_type is None:
            self.command_type = "UpdateDeliverableStatusInDBCommand"


# Note: Commands like CreateReworkTaskCommand and UpdateInternalTaskStatusCommand
# are already defined in src/commands/production_commands.py.
# The Deliverable SAGA Orchestrator will use those too.
