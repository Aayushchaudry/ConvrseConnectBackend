# src/config/sqs_event_bus.py

"""
SQS Event Bus Implementation (Mock).
Mock implementation of EventBus for local development without AWS SQS.
"""

import json
import logging
from typing import Any, Callable, Dict

from src.events.event_bus_interface import EventBus

logger = logging.getLogger(__name__)


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

        logger.info(
            f"Mock SQS: Published message to topic '{topic}': {json.dumps(message)}"
        )

        # Simulate immediate delivery to subscribers (for testing)
        if topic in self.subscriptions:
            callback = self.subscriptions[topic]
            try:
                await callback(message)
            except Exception as e:
                logger.error(f"Error in mock SQS callback for topic '{topic}': {e}")

    async def subscribe(self, topic: str, callback: Callable) -> None:
        """Mock subscription to an SQS queue."""
        if not self.connected:
            raise RuntimeError("SQS event bus not connected. Call connect() first.")

        self.subscriptions[topic] = callback
        logger.info(f"Mock SQS: Subscribed to topic '{topic}'")

    async def create_topic(self, topic_name: str) -> None:
        """Mock creation of an SQS queue."""
        logger.info(f"Mock SQS: Created topic '{topic_name}' (no real queue created)")

    def get_consumer(self, topic: str, group_id: str):
        """
        Mock consumer for SQS (returns None as SQS doesn't have direct consumers).
        """
        logger.info(
            f"Mock SQS: get_consumer called for topic '{topic}', group '{group_id}' (returns None)"
        )
        return None
