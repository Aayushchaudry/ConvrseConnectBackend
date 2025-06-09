# src/commands/deliverable_commands.py

import uuid  # For uuid.uuid4()
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID


# --- Base Command Definition ---
# All your commands inherit from this to ensure common fields.
@dataclass
class BaseCommand:
    command_id: UUID
    timestamp: datetime
    command_type: str

    def __post_init__(self):
        if not hasattr(self, "command_type") or self.command_type is None:
            self.command_type = self.__class__.__name__


# --- Deliverable-Specific Commands (sent by Deliverable SAGA Orchestrator) ---


@dataclass
class InitiateDeliverableProductionCommand(BaseCommand):
    """
    Command to instruct the Production Management Service to begin initial
    production tasks (e.g., modeling, base environment setup) for a deliverable.
    Published by: Deliverable SAGA Orchestrator
    Consumed by: Production Management Service
    """

    project_id: UUID
    deliverable_id: UUID
    # You might include specific initial production requirements, e.g.,
    # initial_production_tasks: List[str] # Or a list of specific task definitions

    def __init__(self, project_id: UUID, deliverable_id: UUID):
        super().__init__(
            command_id=uuid.uuid4(),
            timestamp=datetime.utcnow(),
            command_type="InitiateDeliverableProductionCommand",
        )
        self.project_id = project_id
        self.deliverable_id = deliverable_id


@dataclass
class GenerateReviewItemCommand(BaseCommand):
    """
    Command to instruct the Review Management Service to generate and present
    a new review item (e.g., render, 360 view draft) to the client.
    Published by: Deliverable SAGA Orchestrator (after production tasks are ready)
    Consumed by: Review Management Service
    """

    project_id: UUID
    deliverable_id: UUID
    source_internal_task_id: UUID  # Link to the task that produced this output
    item_type: str  # e.g., 'render_option', 'video_draft'
    item_url: str  # URL to the asset in cloud storage
    review_round: int  # e.g., 1st draft, 2nd revision

    def __init__(
        self,
        project_id: UUID,
        deliverable_id: UUID,
        source_internal_task_id: UUID,
        item_type: str,
        item_url: str,
        review_round: int,
    ):
        super().__init__(
            command_id=uuid.uuid4(),
            timestamp=datetime.utcnow(),
            command_type="GenerateReviewItemCommand",
        )
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.source_internal_task_id = source_internal_task_id
        self.item_type = item_type
        self.item_url = item_url
        self.review_round = review_round


@dataclass
class UpdateDeliverableStatusCommand(BaseCommand):
    """
    A command to update the overall status of a deliverable.
    Published by: Deliverable SAGA Orchestrator
    Consumed by: Deliverable Service (to update Deliverable model)
    """

    project_id: UUID
    deliverable_id: UUID
    new_status: str  # e.g., 'modeling_pending', 'revisions_in_progress', 'delivered'

    def __init__(self, project_id: UUID, deliverable_id: UUID, new_status: str):
        super().__init__(
            command_id=uuid.uuid4(),
            timestamp=datetime.utcnow(),
            command_type="UpdateDeliverableStatusCommand",
        )
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.new_status = new_status


# ... (Other deliverable-specific commands will be defined here later)
# e.g., GenerateFinalOutputCommand (for Delivery Service)
