# src/config/event_bus.py (UPDATED)

import logging
from typing import Optional
from src.config.settings import settings
from src.events.event_bus_interface import EventBus
from src.config.kafka_event_bus import KafkaEventBus # Import specific implementations
from src.config.sqs_event_bus import SQSEventBus # Import specific implementations

logger = logging.getLogger(__name__)

# Global instance of the chosen EventBus implementation
_event_bus_instance: Optional[EventBus] = None

async def get_event_bus() -> EventBus:
    """
    Returns the singleton instance of the configured EventBus.
    """
    global _event_bus_instance
    if _event_bus_instance is None:
        if settings.ACTIVE_EVENT_BUS == "kafka":
            _event_bus_instance = KafkaEventBus()
            logger.info("Using KafkaEventBus as the active event bus.")
        elif settings.ACTIVE_EVENT_BUS == "sqs_mock": # For local testing without real AWS SQS
            _event_bus_instance = SQSEventBus() # Placeholder/Mock SQS implementation
            logger.warning("Using SQSEventBus (Mock) as the active event bus. Real SQS not connected.")
        # elif settings.ACTIVE_EVENT_BUS == "sqs":
        #    _event_bus_instance = ActualSQSImplementation() # Your real SQS implementation
        #    logger.info("Using actual SQS as the active event bus.")
        else:
            raise ValueError(f"Unknown event bus type: {settings.ACTIVE_EVENT_BUS}")
        
        await _event_bus_instance.connect() # Establish connection during retrieval
    return _event_bus_instance

async def close_event_bus():
    """Closes the active event bus connection."""
    global _event_bus_instance
    if _event_bus_instance:
        await _event_bus_instance.disconnect()
        _event_bus_instance = None