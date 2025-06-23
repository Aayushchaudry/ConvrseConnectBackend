# src/commands/production_commands.py

import uuid  # For uuid.uuid4()
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID


# --- Production-Specific Commands (sent by Deliverable SAGA Orchestrator to Production Management Service) ---


@dataclass
class CreateInternalTaskCommand:
    """
    Command to instruct the Production Management Service to create a new internal task.
    Published by: Deliverable SAGA Orchestrator
    Consumed by: Production Management Service
    """

    project_id: UUID
    deliverable_id: UUID
    task_name: str
    task_type: str  # e.g., 'modeling', 'texturing'
    parent_task_id: Optional[UUID] = None  # For sub-tasks/rework tasks
    source_review_item_id: Optional[UUID] = None  # If task created due to client feedback on a review item
    command_id: UUID = None
    timestamp: datetime = None
    command_type: str = None

    def __post_init__(self):
        if self.command_id is None:
            self.command_id = uuid.uuid4()
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.command_type is None:
            self.command_type = "CreateInternalTaskCommand"


@dataclass
class UpdateInternalTaskStatusCommand:
    """
    Command to instruct the Production Management Service to update the status of an internal task.
    Published by: Deliverable SAGA Orchestrator (e.g., after client feedback)
    Consumed by: Production Management Service
    """

    project_id: UUID
    deliverable_id: UUID
    task_id: UUID
    new_status: str  # e.g., 'done', 'awaiting_review', 'rejected_terminated'
    command_id: UUID = None
    timestamp: datetime = None
    command_type: str = None

    def __post_init__(self):
        if self.command_id is None:
            self.command_id = uuid.uuid4()
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.command_type is None:
            self.command_type = "UpdateInternalTaskStatusCommand"


@dataclass
class CreateReworkTaskCommand:
    """
    Specific command for creating a rework task, often in response to client comments.
    (This can be a specialized form of CreateInternalTaskCommand).
    Published by: Deliverable SAGA Orchestrator (after client comments)
    Consumed by: Production Management Service
    """

    project_id: UUID
    deliverable_id: UUID
    original_task_id: UUID  # The task that needs rework
    review_item_id: UUID  # The review item that received feedback
    comment_id: UUID  # The specific client feedback/comment that triggered the rework
    rework_description: str
    command_id: UUID = None
    timestamp: datetime = None
    command_type: str = None

    def __post_init__(self):
        if self.command_id is None:
            self.command_id = uuid.uuid4()
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.command_type is None:
            self.command_type = "CreateReworkTaskCommand"
