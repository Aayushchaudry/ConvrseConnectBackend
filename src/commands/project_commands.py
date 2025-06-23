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
    command_id: UUID = None  # Default to None, will be set in __post_init__
    timestamp: datetime = None  # Default to None, will be set in __post_init__
    command_type: str = None  # Default to None, will be set in __post_init__

    def __post_init__(self):
        # Automatically set command_type based on class name if not provided
        if self.command_id is None:
            self.command_id = uuid.uuid4()
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if not hasattr(self, "command_type") or self.command_type is None:
            self.command_type = self.__class__.__name__


# --- Project-Level Commands ---


@dataclass
class StartInformationGatheringCommand:
    """
    Command to instruct the Information Gathering Service to start collecting
    requirements for a project.
    Published by: Project Lifecycle Orchestrator
    Consumed by: Information Gathering Service
    """

    project_id: UUID
    deliverable_ids: List[UUID]  # List of deliverables to gather info for
    command_id: UUID = None
    timestamp: datetime = None
    command_type: str = None

    def __post_init__(self):
        # Handle both creation and deserialization scenarios
        if self.command_id is None:
            self.command_id = uuid.uuid4()
        elif isinstance(self.command_id, str):
            self.command_id = UUID(self.command_id)

        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        elif isinstance(self.timestamp, str):
            # Parse ISO format timestamp from Kafka
            self.timestamp = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))

        if self.command_type is None:
            self.command_type = "StartInformationGatheringCommand"

        # Convert project_id to UUID if it's a string
        if isinstance(self.project_id, str):
            self.project_id = UUID(self.project_id)

        # Convert deliverable_ids to UUIDs if they're strings
        if self.deliverable_ids and isinstance(self.deliverable_ids[0], str):
            self.deliverable_ids = [UUID(did) for did in self.deliverable_ids]


@dataclass
class StartDeliverableSagaCommand:
    """
    Command to instruct a specific Deliverable SAGA Orchestrator instance
    to begin its lifecycle for a given deliverable.
    Published by: Project Lifecycle Orchestrator
    Consumed by: Deliverable SAGA Orchestrator (your colleague's responsibility)
    """

    project_id: UUID
    deliverable_id: UUID
    deliverable_name: str
    command_id: UUID = None
    timestamp: datetime = None
    command_type: str = None

    def __post_init__(self):
        if self.command_id is None:
            self.command_id = uuid.uuid4()
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.command_type is None:
            self.command_type = "StartDeliverableSagaCommand"


# Add more project-level commands as needed for compensation or specific high-level actions
# Example:
# @dataclass
# class NotifyProjectManagerCommand:
#     project_id: UUID
#     message: str
#     notification_type: str # e.g., 'email', 'slack'
#     command_id: UUID = None
#     timestamp: datetime = None
#     command_type: str = None
#     # ... (other fields)
