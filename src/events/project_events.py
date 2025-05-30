# src/events/project_events.py (CORRECTED)

from dataclasses import dataclass
from datetime import datetime # <-- Ensure this is imported
from uuid import UUID
import uuid # <--- ADD THIS LINE! This imports the 'uuid' module needed for uuid.uuid4()
from typing import Optional, List, Dict, Any

# --- Base Event Definition (Optional but good practice) ---
@dataclass
class BaseEvent:
    event_id: UUID # Unique ID for this specific event instance
    timestamp: datetime # When the event occurred
    event_type: str # A string identifier for the type of event

    def __post_init__(self):
        if not hasattr(self, 'event_type') or self.event_type is None:
            self.event_type = self.__class__.__name__

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
    initial_status: str # e.g., "initiated" or "created"

    def __init__(self, project_id: UUID, project_name: str, initial_status: str):
        super().__init__(event_id=uuid.uuid4(), timestamp=datetime.utcnow(), event_type="ProjectCreatedEvent")
        self.project_id = project_id
        self.project_name = project_name
        self.initial_status = initial_status


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
    final_output_url: str

    def __init__(self, project_id: UUID, deliverable_id: UUID, deliverable_name: str, final_output_url: str):
        super().__init__(event_id=uuid.uuid4(), timestamp=datetime.utcnow(), event_type="DeliverableDeliveredEvent")
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.deliverable_name = deliverable_name
        self.final_output_url = final_output_url


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

    def __init__(self, project_id: UUID, deliverable_id: UUID, deliverable_name: str, reason: str, error_details: Optional[Dict[str, Any]] = None):
        super().__init__(event_id=uuid.uuid4(), timestamp=datetime.utcnow(), event_type="DeliverableFailedEvent")
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

    def __init__(self, project_id: UUID, project_name: str, completion_date: datetime):
        super().__init__(event_id=uuid.uuid4(), timestamp=datetime.utcnow(), event_type="ProjectCompletedEvent")
        self.project_id = project_id
        self.project_name = project_name
        self.completion_date = completion_date


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

    def __init__(self, project_id: UUID, project_name: str, reason: str, error_details: Optional[Dict[str, Any]] = None):
        super().__init__(event_id=uuid.uuid4(), timestamp=datetime.utcnow(), event_type="ProjectFailedEvent")
        self.project_id = project_id
        self.project_name = project_name
        self.reason = reason
        self.error_details = error_details