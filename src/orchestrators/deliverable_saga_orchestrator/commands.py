"""
Commands for the DeliverableSagaOrchestrator.
"""

import uuid
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID


@dataclass
class StartDeliverableInfoGatheringCommand:
    """Command to start gathering information for a deliverable."""
    project_id: UUID
    deliverable_id: UUID
    command_id: UUID = field(default_factory=uuid.uuid4)


@dataclass
class InitiateModelingCommand:
    """Command to initiate modeling for a deliverable."""
    project_id: UUID
    deliverable_id: UUID
    command_id: UUID = field(default_factory=uuid.uuid4)


@dataclass
class InitiateTexturingCommand:
    """Command to initiate texturing for a deliverable."""
    project_id: UUID
    deliverable_id: UUID
    command_id: UUID = field(default_factory=uuid.uuid4)


@dataclass
class InitiateRenderingCommand:
    """Command to initiate rendering for a deliverable."""
    project_id: UUID
    deliverable_id: UUID
    command_id: UUID = field(default_factory=uuid.uuid4)


@dataclass
class UpdateDeliverableStatusInDBCommand:
    """Command to update deliverable status in the database."""
    project_id: UUID
    deliverable_id: UUID
    new_status: str
    command_id: UUID = field(default_factory=uuid.uuid4)


@dataclass
class GenerateFinalOutputCommand:
    """Command to generate final output for a deliverable."""
    project_id: UUID
    deliverable_id: UUID
    output_name: Optional[str] = None
    command_id: UUID = field(default_factory=uuid.uuid4)