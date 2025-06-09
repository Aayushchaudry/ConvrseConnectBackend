# src/commands/project_commands.py

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID


# --- Base Command Definition (Optional but good practice) ---
# All your commands can inherit from this to ensure common fields like command_id, timestamp.
@dataclass
class BaseCommand:
    command_id: UUID  # Unique ID for this specific command instance
    timestamp: datetime  # When the command was issued
    command_type: str  # A string identifier for the type of command

    def __post_init__(self):
        # Automatically set command_type based on class name if not provided
        if not hasattr(self, "command_type") or self.command_type is None:
            self.command_type = self.__class__.__name__


# --- Project-Level Commands ---


@dataclass
class StartInformationGatheringCommand(BaseCommand):
    """
    Command to instruct the Information Gathering Service to start collecting
    requirements for a project.
    Published by: Project Lifecycle Orchestrator
    Consumed by: Information Gathering Service
    """

    project_id: UUID
    deliverable_ids: List[UUID]  # List of deliverables to gather info for

    def __init__(
        self,
        project_id: UUID,
        deliverable_ids: List[UUID],
        command_id: UUID = None,
        timestamp: datetime = None,
        command_type: str = None,
    ):
        # Handle both creation and deserialization scenarios
        if command_id is None:
            command_id = uuid.uuid4()
        elif isinstance(command_id, str):
            command_id = UUID(command_id)

        if timestamp is None:
            timestamp = datetime.utcnow()
        elif isinstance(timestamp, str):
            # Parse ISO format timestamp from Kafka
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        if command_type is None:
            command_type = "StartInformationGatheringCommand"

        # Convert project_id to UUID if it's a string
        if isinstance(project_id, str):
            project_id = UUID(project_id)

        # Convert deliverable_ids to UUIDs if they're strings
        if deliverable_ids and isinstance(deliverable_ids[0], str):
            deliverable_ids = [UUID(did) for did in deliverable_ids]

        super().__init__(
            command_id=command_id, timestamp=timestamp, command_type=command_type
        )
        self.project_id = project_id
        self.deliverable_ids = deliverable_ids


@dataclass
class StartDeliverableSagaCommand(BaseCommand):
    """
    Command to instruct a specific Deliverable SAGA Orchestrator instance
    to begin its lifecycle for a given deliverable.
    Published by: Project Lifecycle Orchestrator
    Consumed by: Deliverable SAGA Orchestrator (your colleague's responsibility)
    """

    project_id: UUID
    deliverable_id: UUID
    deliverable_name: str
    # Add any other initial data needed by the Deliverable SAGA Orchestrator

    def __init__(self, project_id: UUID, deliverable_id: UUID, deliverable_name: str):
        super().__init__(
            command_id=uuid.uuid4(),
            timestamp=datetime.utcnow(),
            command_type="StartDeliverableSagaCommand",
        )
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.deliverable_name = deliverable_name


# Add more project-level commands as needed for compensation or specific high-level actions
# Example:
# @dataclass
# class NotifyProjectManagerCommand(BaseCommand):
#     project_id: UUID
#     message: str
#     notification_type: str # e.g., 'email', 'slack'
#     # ... (other fields)
