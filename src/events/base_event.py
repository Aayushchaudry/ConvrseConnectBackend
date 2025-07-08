# src/events/base_event.py

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class BaseEvent:
    """
    Base class for all events in the system.
    Provides common fields and functionality for all events.
    """
    event_id: UUID  # Unique ID for this specific event instance
    timestamp: datetime  # When the event occurred
    event_type: str  # A string identifier for the type of event

    def __post_init__(self):
        if not hasattr(self, "event_type") or self.event_type is None:
            self.event_type = self.__class__.__name__ 