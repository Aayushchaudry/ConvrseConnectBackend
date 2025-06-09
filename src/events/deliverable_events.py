# src/events/deliverable_events.py

import uuid  # For uuid.uuid4()
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID


# --- Base Event Definition ---
# All your events inherit from this to ensure common fields.
@dataclass
class BaseEvent:
    event_id: UUID
    timestamp: datetime
    event_type: str

    def __post_init__(self):
        if not hasattr(self, "event_type") or self.event_type is None:
            self.event_type = self.__class__.__name__


# --- Deliverable-Specific Events ---


@dataclass
class DeliverableInfoGatheredEvent(BaseEvent):
    """
    Event published by the Information Gathering Service when all (or critical)
    requirements for a deliverable have been successfully gathered.
    Published by: Information Gathering Service
    Consumed by: Deliverable SAGA Orchestrator (to initiate production)
    """

    project_id: UUID
    deliverable_id: UUID
    # You might include a summary of gathered info, e.g.,
    # gathered_requirements_count: int
    # critical_requirements_met: bool

    def __init__(
        self,
        project_id: UUID,
        deliverable_id: UUID,
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
            event_type = "DeliverableInfoGatheredEvent"

        # Convert project_id to UUID if it's a string
        if isinstance(project_id, str):
            project_id = UUID(project_id)

        # Convert deliverable_id to UUID if it's a string
        if isinstance(deliverable_id, str):
            deliverable_id = UUID(deliverable_id)

        super().__init__(event_id=event_id, timestamp=timestamp, event_type=event_type)
        self.project_id = project_id
        self.deliverable_id = deliverable_id


@dataclass
class DeliverableInfoGatheringFailedEvent(BaseEvent):
    """
    Event published by the Information Gathering Service if it encounters a failure
    during requirement collection for a deliverable.
    Published by: Information Gathering Service
    Consumed by: Deliverable SAGA Orchestrator (to handle compensation/retry)
    """

    project_id: UUID
    deliverable_id: UUID
    reason: str
    error_details: Optional[Dict[str, Any]] = None

    def __init__(
        self,
        project_id: UUID,
        deliverable_id: UUID,
        reason: str,
        error_details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            event_id=uuid.uuid4(),
            timestamp=datetime.utcnow(),
            event_type="DeliverableInfoGatheringFailedEvent",
        )
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.reason = reason
        self.error_details = error_details


@dataclass
class RequirementUpdatedEvent(BaseEvent):
    """
    Event published when a specific requirement's status (e.g., from PENDING to RECEIVED)
    or value is updated. This can be used for granular tracking or UI updates.
    Published by: Information Gathering Service (via API endpoint/internal trigger)
    Consumed by: Deliverable SAGA Orchestrator (potentially) or UI/Analytics
    """

    project_id: UUID
    deliverable_id: UUID
    requirement_id: UUID
    new_status: str  # e.g., 'received', 'approved'
    # Optional: old_status: str, requirement_name: str, new_value: Optional[Any]

    def __init__(
        self,
        project_id: UUID,
        deliverable_id: UUID,
        requirement_id: UUID,
        new_status: str,
    ):
        super().__init__(
            event_id=uuid.uuid4(),
            timestamp=datetime.utcnow(),
            event_type="RequirementUpdatedEvent",
        )
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.requirement_id = requirement_id
        self.new_status = new_status


# ... (Other deliverable-specific events will be defined here later)
# e.g., ProductionCompletedEvent, ReviewItemGeneratedEvent, ClientFeedbackSubmittedEvent, etc.
