# src/commands/production_commands.py

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


# --- Production-Specific Commands (sent by Deliverable SAGA Orchestrator to Production Management Service) ---


@dataclass
class CreateInternalTaskCommand(BaseCommand):
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
    source_review_item_id: Optional[UUID] = (
        None  # If task created due to client feedback on a review item
    )
    # Add other task details like assigned_to_user_id, priority, description

    def __init__(
        self,
        project_id: UUID,
        deliverable_id: UUID,
        task_name: str,
        task_type: str,
        parent_task_id: Optional[UUID] = None,
        source_review_item_id: Optional[UUID] = None,
    ):
        super().__init__(
            command_id=uuid.uuid4(),
            timestamp=datetime.utcnow(),
            command_type="CreateInternalTaskCommand",
        )
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.task_name = task_name
        self.task_type = task_type
        self.parent_task_id = parent_task_id
        self.source_review_item_id = source_review_item_id


@dataclass
class UpdateInternalTaskStatusCommand(BaseCommand):
    """
    Command to instruct the Production Management Service to update the status of an internal task.
    Published by: Deliverable SAGA Orchestrator (e.g., after client feedback)
    Consumed by: Production Management Service
    """

    project_id: UUID
    deliverable_id: UUID
    task_id: UUID
    new_status: str  # e.g., 'done', 'awaiting_review', 'rejected_terminated'
    # Optional: actual_end_date: Optional[datetime] = None

    def __init__(
        self,
        project_id: UUID,
        deliverable_id: UUID,
        task_id: UUID,
        new_status: str,
        command_id: UUID = None,
        timestamp: datetime = None,
        command_type: str = None,
    ):
        super().__init__(
            command_id=command_id or uuid.uuid4(),
            timestamp=timestamp or datetime.utcnow(),
            command_type=command_type or "UpdateInternalTaskStatusCommand",
        )
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.task_id = task_id
        self.new_status = new_status


@dataclass
class CreateReworkTaskCommand(BaseCommand):
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
    # Add task_name, task_type for the rework task itself if needed

    def __init__(
        self,
        project_id: UUID,
        deliverable_id: UUID,
        original_task_id: UUID,
        review_item_id: UUID,
        comment_id: UUID,
        rework_description: str,
        command_id: UUID = None,
        timestamp: datetime = None,
        command_type: str = None,
    ):
        super().__init__(
            command_id=command_id or uuid.uuid4(),
            timestamp=timestamp or datetime.utcnow(),
            command_type=command_type or "CreateReworkTaskCommand",
        )
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.original_task_id = original_task_id
        self.review_item_id = review_item_id
        self.comment_id = comment_id
        self.rework_description = rework_description
