# src/events/event_bus_interface.py

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict


class EventBus(ABC):
    """
    Abstract base class for Event Bus implementations.
    Defines the contract for publishing and subscribing to events.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the event bus."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the event bus."""
        pass

    @abstractmethod
    async def publish(self, topic: str, message: Dict[str, Any]) -> None:
        """Publish a message to a topic."""
        pass

    @abstractmethod
    async def subscribe(self, topic: str, callback: Callable) -> None:
        """Subscribe to a topic with a callback function."""
        pass

    @abstractmethod
    async def create_topic(self, topic_name: str) -> None:
        """Create a topic if it doesn't exist."""
        pass

    @abstractmethod
    def get_consumer(self, topic: str, group_id: str):
        """
        Returns a consumer instance for direct iteration (for background listeners).
        This method might vary significantly between implementations.
        """
        pass
