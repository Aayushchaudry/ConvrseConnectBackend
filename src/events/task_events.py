# src/events/task_events.py

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
import uuid # For uuid.uuid4()
from typing import Optional, List, Dict, Any

# --- Base Event Definition ---
@dataclass
class BaseEvent:
    event_id: UUID
    timestamp: datetime
    event_type: str

    def __post_init__(self):
        if not hasattr(self, 'event_type') or self.event_type is None:
            self.event_type = self.__class__.__name__

# --- Task-Specific Events ---

@dataclass
class InternalTaskCreatedEvent(BaseEvent):
    """
    Event published when a new internal production task has been created.
    Published by: Production Management Service
    Consumed by: Deliverable SAGA Orchestrator (to track task initiation)
    """
    project_id: UUID
    deliverable_id: UUID
    task_id: UUID
    task_name: str
    task_type: str
    assigned_to_user_id: Optional[UUID] = None

    def __init__(self, project_id: UUID, deliverable_id: UUID, task_id: UUID, task_name: str, task_type: str, assigned_to_user_id: Optional[UUID] = None):
        super().__init__(event_id=uuid.uuid4(), timestamp=datetime.utcnow(), event_type="InternalTaskCreatedEvent")
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.task_id = task_id
        self.task_name = task_name
        self.task_type = task_type
        self.assigned_to_user_id = assigned_to_user_id


@dataclass
class InternalTaskCompletedEvent(BaseEvent):
    """
    Event published when an internal production task has been successfully completed.
    Published by: Production Management Service
    Consumed by: Deliverable SAGA Orchestrator (to move to next stage, e.g., review prep)
    """
    project_id: UUID
    deliverable_id: UUID
    task_id: UUID
    task_name: str
    task_type: str
    # Optional: output_url: Optional[str] = None # If task produces a direct output (e.g., render)

    def __init__(self, project_id: UUID, deliverable_id: UUID, task_id: UUID, task_name: str, task_type: str):
        super().__init__(event_id=uuid.uuid4(), timestamp=datetime.utcnow(), event_type="InternalTaskCompletedEvent")
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.task_id = task_id
        self.task_name = task_name
        self.task_type = task_type


@dataclass
class InternalTaskFailedEvent(BaseEvent):
    """
    Event published when an internal production task has failed (e.g., render job failed).
    Published by: Production Management Service
    Consumed by: Deliverable SAGA Orchestrator (to trigger rework or mark deliverable failed)
    """
    project_id: UUID
    deliverable_id: UUID
    task_id: UUID
    task_name: str
    task_type: str
    reason: str
    error_details: Optional[Dict[str, Any]] = None

    def __init__(self, project_id: UUID, deliverable_id: UUID, task_id: UUID, task_name: str, task_type: str, reason: str, error_details: Optional[Dict[str, Any]] = None):
        super().__init__(event_id=uuid.uuid4(), timestamp=datetime.utcnow(), event_type="InternalTaskFailedEvent")
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.task_id = task_id
        self.task_name = task_name
        self.task_type = task_type
        self.reason = reason
        self.error_details = error_details


@dataclass
class InternalTaskStatusUpdatedEvent(BaseEvent):
    """
    Generic event for any status update on an internal task,
    useful for dashboards and tracking.
    Published by: Production Management Service
    Consumed by: Deliverable SAGA Orchestrator (potentially) or UI/Analytics
    """
    project_id: UUID
    deliverable_id: UUID
    task_id: UUID
    old_status: str
    new_status: str
    
    def __init__(self, project_id: UUID, deliverable_id: UUID, task_id: UUID, old_status: str, new_status: str):
        super().__init__(event_id=uuid.uuid4(), timestamp=datetime.utcnow(), event_type="InternalTaskStatusUpdatedEvent")
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.task_id = task_id
        self.old_status = old_status
        self.new_status = new_status