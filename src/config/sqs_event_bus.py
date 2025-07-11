# src/config/sqs_event_bus.py

"""
SQS Event Bus Implementation (Mock).
Mock implementation of EventBus for local development without AWS SQS.
"""

import json
import logging
from typing import Any, Callable, Dict
from dataclasses import asdict

from src.events.event_bus_interface import EventBus
from src.events.project_events import ProjectCreatedEvent
from src.events.deliverable_events import DeliverableInfoGatheredEvent, RequirementUpdatedEvent
from src.events.task_events import (
    InternalTaskCreatedEvent, 
    InternalTaskCompletedEvent, 
    InternalTaskStatusUpdatedEvent,
    InternalTaskCompletedWithMediaEvent,
    InternalTaskFailedEvent,
)

logger = logging.getLogger(__name__)

# Event type mapping for deserialization
EVENT_TYPE_MAP = {
    "ProjectCreatedEvent": ProjectCreatedEvent,
    "DeliverableInfoGatheredEvent": DeliverableInfoGatheredEvent,
    "RequirementUpdatedEvent": RequirementUpdatedEvent,
    "InternalTaskCreatedEvent": InternalTaskCreatedEvent,
    "InternalTaskCompletedEvent": InternalTaskCompletedEvent,
    "InternalTaskStatusUpdatedEvent": InternalTaskStatusUpdatedEvent,
    "InternalTaskCompletedWithMediaEvent": InternalTaskCompletedWithMediaEvent,
    "InternalTaskFailedEvent": InternalTaskFailedEvent,
}

class SQSEventBus(EventBus):
    """Mock SQS implementation of the EventBus interface for local development."""

    def __init__(self):
        self.connected = False
        self.subscriptions = {}

    async def connect(self) -> None:
        """Mock connection to SQS."""
        self.connected = True
        logger.info("Mock SQS Event Bus connected (no real SQS connection)")

    async def disconnect(self) -> None:
        """Mock disconnection from SQS."""
        self.connected = False
        self.subscriptions.clear()
        logger.info("Mock SQS Event Bus disconnected")

    async def publish(self, topic: str, message: Dict[str, Any]) -> None:
        """Mock publishing a message to SQS."""
        if not self.connected:
            raise RuntimeError("SQS event bus not connected. Call connect() first.")

        logger.info(f"Mock SQS: Published message to topic '{topic}': {json.dumps(message)}")

        # Simulate immediate delivery to subscribers (for testing)
        if topic in self.subscriptions:
            callback = self.subscriptions[topic]
            try:
                # Convert dictionary message back to event object
                event_type = message.get('event_type')
                if event_type in EVENT_TYPE_MAP:
                    event_class = EVENT_TYPE_MAP[event_type]
                    event = event_class(**message)
                    logger.info(f"Mock SQS: Reconstructed event of type {event_type}")
                    await callback(event)
                else:
                    logger.warning(f"Mock SQS: Unknown event type {event_type}, passing raw message")
                    await callback(message)
            except Exception as e:
                logger.error(f"Error in mock SQS callback for topic '{topic}': {e}", exc_info=True)

    async def subscribe(self, topic: str, callback: Callable) -> None:
        """Mock subscription to an SQS queue."""
        if not self.connected:
            raise RuntimeError("SQS event bus not connected. Call connect() first.")

        self.subscriptions[topic] = callback
        logger.info(f"Mock SQS: Subscribed to topic '{topic}'")

    async def create_topic(self, topic_name: str) -> None:
        """Mock topic creation."""
        logger.info(f"Mock SQS: Created topic '{topic_name}'")

    def get_consumer(self, topic: str, group_id: str):
        """Mock consumer creation."""
        logger.info(f"Mock SQS: Created consumer for topic '{topic}' with group '{group_id}'")
        return None  # Not needed for mock implementation
