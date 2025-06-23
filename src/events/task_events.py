# src/events/task_events.py

import uuid  # For uuid.uuid4()
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from uuid import UUID


# --- Base Event Definition ---
@dataclass
class BaseEvent:
    event_id: UUID
    timestamp: datetime
    event_type: str

    def __post_init__(self):
        if not hasattr(self, "event_type") or self.event_type is None:
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

    def __init__(
        self,
        project_id: UUID,
        deliverable_id: UUID,
        task_id: UUID,
        task_name: str,
        task_type: str,
        assigned_to_user_id: Optional[UUID] = None,
    ):
        super().__init__(
            event_id=uuid.uuid4(),
            timestamp=datetime.utcnow(),
            event_type="InternalTaskCreatedEvent",
        )
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

    def __init__(
        self,
        project_id: UUID,
        deliverable_id: UUID,
        task_id: UUID,
        task_name: str,
        task_type: str,
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
            event_type = "InternalTaskCompletedEvent"

        # Convert UUIDs from strings if needed
        if isinstance(project_id, str):
            project_id = UUID(project_id)
        if isinstance(deliverable_id, str):
            deliverable_id = UUID(deliverable_id)
        if isinstance(task_id, str):
            task_id = UUID(task_id)

        super().__init__(event_id=event_id, timestamp=timestamp, event_type=event_type)
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.task_id = task_id
        self.task_name = task_name
        self.task_type = task_type


@dataclass
class InternalTaskCompletedWithMediaEvent(BaseEvent):
    """
    Event published when an internal production task has been completed with media files.
    Published by: Task Completion API
    Consumed by: Deliverable SAGA Orchestrator (to create multiple review items with file references)
    """

    project_id: UUID
    deliverable_id: UUID
    task_id: UUID
    task_name: str
    task_type: str
    platform_file_ids: List[UUID]  # List of file UUIDs from platform-service (updated from int to UUID)

    def __init__(
        self,
        project_id: UUID,
        deliverable_id: UUID,
        task_id: UUID,
        task_name: str,
        task_type: str,
        platform_file_ids: List[Union[UUID, str]],  # Accept both UUID and string for flexibility
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
            event_type = "InternalTaskCompletedWithMediaEvent"

        # Convert UUIDs from strings if needed
        if isinstance(project_id, str):
            project_id = UUID(project_id)
        if isinstance(deliverable_id, str):
            deliverable_id = UUID(deliverable_id)
        if isinstance(task_id, str):
            task_id = UUID(task_id)

        # Convert platform_file_ids to UUIDs
        converted_file_ids = []
        for file_id in platform_file_ids:
            if isinstance(file_id, str):
                try:
                    converted_file_ids.append(UUID(file_id))
                except ValueError:
                    # If string is not a valid UUID, it might be an integer ID
                    # During transition period, convert int to UUID using deterministic method
                    import uuid as uuid_lib
                    namespace = uuid_lib.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
                    converted_file_ids.append(uuid_lib.uuid5(namespace, f"content_id_{file_id}"))
            elif isinstance(file_id, int):
                # Convert integer ID to UUID using deterministic method (transition period)
                import uuid as uuid_lib
                namespace = uuid_lib.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
                converted_file_ids.append(uuid_lib.uuid5(namespace, f"content_id_{file_id}"))
            elif isinstance(file_id, UUID):
                converted_file_ids.append(file_id)
            else:
                raise ValueError(f"Invalid file_id type: {type(file_id)}")

        super().__init__(event_id=event_id, timestamp=timestamp, event_type=event_type)
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.task_id = task_id
        self.task_name = task_name
        self.task_type = task_type
        self.platform_file_ids = converted_file_ids


@dataclass
class InternalTaskFailedEvent(BaseEvent):
    """
    Event published when an internal production task has failed (e.g., render job failed).
    Published by: Production Management Service
    Consumed by: Deliverable SAGA Orchestrator (to trigger rework or mark deliverable failed)
    """

    project_id: UUID
    deliverable_id: UUID
    task_id: Optional[UUID]  # Task ID can be None if task creation failed
    task_name: str
    task_type: str
    reason: str
    error_details: Optional[Dict[str, Any]] = None

    def __init__(
        self,
        project_id: UUID,
        deliverable_id: UUID,
        task_id: Optional[UUID],
        task_name: str,
        task_type: str,
        reason: str,
        error_details: Optional[Dict[str, Any]] = None,
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
            event_type = "InternalTaskFailedEvent"

        # Convert UUIDs from strings if needed
        if isinstance(project_id, str):
            project_id = UUID(project_id)
        if isinstance(deliverable_id, str):
            deliverable_id = UUID(deliverable_id)
        if isinstance(task_id, str) and task_id is not None:
            task_id = UUID(task_id)

        super().__init__(event_id=event_id, timestamp=timestamp, event_type=event_type)
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

    def __init__(
        self,
        project_id: UUID,
        deliverable_id: UUID,
        task_id: UUID,
        old_status: str,
        new_status: str,
    ):
        super().__init__(
            event_id=uuid.uuid4(),
            timestamp=datetime.utcnow(),
            event_type="InternalTaskStatusUpdatedEvent",
        )
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.task_id = task_id
        self.old_status = old_status
        self.new_status = new_status
