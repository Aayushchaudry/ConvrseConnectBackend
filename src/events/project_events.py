# src/events/project_events.py (CORRECTED)

import uuid  # <--- ADD THIS LINE! This imports the 'uuid' module needed for uuid.uuid4()
from dataclasses import dataclass
from datetime import datetime  # <-- Ensure this is imported
from typing import Any, Dict, List, Optional
from uuid import UUID

from src.events.base_event import BaseEvent


# --- Project-Level Events ---


@dataclass
class ProjectCreatedEvent(BaseEvent):
    """
    Event published when a new project has been successfully created.
    Published by: Project Service (after saving to DB)
    Consumed by: Project Lifecycle Orchestrator (to start the SAGA)
    """

    project_id: UUID
    project_name: str
    initial_status: str  # e.g., "initiated" or "created"
    deliverable_types: List[str]  # List of deliverable types for orchestrator to auto-create
    deliverable_sub_types: Dict[str, str]  # Dictionary of deliverable subtypes for each deliverable type
    deliverable_timeline_days: Dict[str, int]  # Dictionary of deliverable timeline days for each deliverable type

    def __init__(
        self,
        project_id: UUID,
        project_name: str,
        initial_status: str,
        deliverable_types: List[str] = None,
        deliverable_sub_types: Dict[str, str] = None,
        deliverable_timeline_days: Dict[str, int] = None,
        event_id: UUID = None,
        timestamp: datetime = None,
        event_type: str = None,
    ):
        # Allow event_id and timestamp to be passed for deserialization
        if event_id is None:
            event_id = uuid.uuid4()
        elif isinstance(event_id, str):
            event_id = UUID(event_id)

        if timestamp is None:
            timestamp = datetime.utcnow()
        elif isinstance(timestamp, str):
            # Parse ISO format timestamp from Kafka
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        if event_type is None:
            event_type = "ProjectCreatedEvent"

        # Convert project_id to UUID if it's a string
        if isinstance(project_id, str):
            project_id = UUID(project_id)

        super().__init__(event_id=event_id, timestamp=timestamp, event_type=event_type)
        self.project_id = project_id
        self.project_name = project_name
        self.initial_status = initial_status
        self.deliverable_types = deliverable_types or []
        self.deliverable_sub_types = deliverable_sub_types or {}
        self.deliverable_timeline_days = deliverable_timeline_days or {}


@dataclass
class DeliverableDeliveredEvent(BaseEvent):
    """
    Event published by a Deliverable SAGA Orchestrator when a deliverable
    has been successfully completed and delivered.
    Published by: Deliverable SAGA Orchestrator
    Consumed by: Project Lifecycle Orchestrator (to track overall project progress)
    """

    project_id: UUID
    deliverable_id: UUID
    deliverable_name: str
    output_id: UUID

    def __init__(
        self,
        project_id: UUID,
        deliverable_id: UUID,
        deliverable_name: str,
        output_id: UUID,
    ):
        super().__init__(
            event_id=uuid.uuid4(),
            timestamp=datetime.utcnow(),
            event_type="DeliverableDeliveredEvent",
        )
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.deliverable_name = deliverable_name
        self.output_id = output_id


@dataclass
class DeliverableFailedEvent(BaseEvent):
    """
    Event published by a Deliverable SAGA Orchestrator when a deliverable's
    production/approval SAGA has failed or been canceled.
    Published by: Deliverable SAGA Orchestrator
    Consumed by: Project Lifecycle Orchestrator (to handle project-level compensation)
    """

    project_id: UUID
    deliverable_id: UUID
    deliverable_name: str
    reason: str
    error_details: Optional[Dict[str, Any]] = None

    def __init__(
        self,
        project_id: UUID,
        deliverable_id: UUID,
        deliverable_name: str,
        reason: str,
        error_details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            event_id=uuid.uuid4(),
            timestamp=datetime.utcnow(),
            event_type="DeliverableFailedEvent",
        )
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.deliverable_name = deliverable_name
        self.reason = reason
        self.error_details = error_details


@dataclass
class ProjectCompletedEvent(BaseEvent):
    """
    Event published by the Project Lifecycle Orchestrator when the entire project
    has been successfully completed (all deliverables delivered).
    Published by: Project Lifecycle Orchestrator
    Consumed by: Analytics, Reporting, external systems (e.g., CRM)
    """

    project_id: UUID
    project_name: str
    completion_date: datetime
    compilation_url: Optional[str] = None

    def __init__(self, project_id: UUID, project_name: str, completion_date: datetime, compilation_url: Optional[str] = None):
        super().__init__(
            event_id=uuid.uuid4(),
            timestamp=datetime.utcnow(),
            event_type="ProjectCompletedEvent",
        )
        self.project_id = project_id
        self.project_name = project_name
        self.completion_date = completion_date
        self.compilation_url = compilation_url


@dataclass
class ProjectFailedEvent(BaseEvent):
    """
    Event published by the Project Lifecycle Orchestrator if the entire project
    fails or is canceled at a high level.
    Published by: Project Lifecycle Orchestrator
    Consumed by: Analytics, Reporting, external systems.
    """

    project_id: UUID
    project_name: str
    reason: str
    error_details: Optional[Dict[str, Any]] = None

    def __init__(
        self,
        project_id: UUID,
        project_name: str,
        reason: str,
        error_details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            event_id=uuid.uuid4(),
            timestamp=datetime.utcnow(),
            event_type="ProjectFailedEvent",
        )
        self.project_id = project_id
        self.project_name = project_name
        self.reason = reason
        self.error_details = error_details
