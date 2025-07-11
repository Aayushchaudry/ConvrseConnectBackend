# src/listeners/deliverable_events_listener.py

import asyncio
import logging
from typing import Any, Callable, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import AsyncSessionLocal  # For getting session factory
from src.config.settings import settings
from src.events.event_bus_interface import EventBus
from src.orchestrators.deliverable_saga_orchestrator.deliverable_saga_orchestrator import (
    DeliverableSagaOrchestrator,
)  # Import the orchestrator to call

logger = logging.getLogger(__name__)

# Define the Kafka topics this listener will subscribe to for deliverable events
DELIVERABLE_EVENTS_TOPICS = [
    "deliverable.info_gathered",  # From Information Gathering Service
    "deliverable.info_gathering.failed",  # From Information Gathering Service
    "internal_task.completed",  # From Production Management Service
    "internal_task.failed",  # From Production Management Service
    "internal_task.created",  # From Production Management Service - Fixed topic name
    # Add other topics as they are defined and consumed by DeliverableSagaOrchestrator
    # "deliverable.delivered.final" # Final event from Delivery Service
]

# Note: Client feedback events might be in a separate listener for clarity/scalability.
# The "StartDeliverableSagaCommand" is also consumed by this orchestrator,
# but it often comes from a different topic that only this orchestrator subscribes to.
DELIVERABLE_COMMANDS_TOPIC = (
    "project.command.start_deliverable_saga"  # From Project Orchestrator
)


async def start_listening(event_bus: EventBus):
    """
    Starts the Deliverable Events Listener, consuming events from the Event Bus
    and dispatching them to the DeliverableSagaOrchestrator.
    """
    logger.info(
        f"Deliverable Events Listener starting for topics: {DELIVERABLE_EVENTS_TOPICS} and {DELIVERABLE_COMMANDS_TOPIC}"
    )

    # Create an instance of the DeliverableSagaOrchestrator
    deliverable_orchestrator = DeliverableSagaOrchestrator(
        db_session_factory=AsyncSessionLocal, event_bus=event_bus
    )

    # Get a consumer for the general deliverable events
    general_deliverable_consumer = event_bus.get_consumer(
        topic=DELIVERABLE_EVENTS_TOPICS,
        group_id=settings.KAFKA_CONSUMER_GROUP_ID + "-deliverable-events",
    )

    # Get a consumer for the start deliverable saga command
    start_saga_command_consumer = event_bus.get_consumer(
        topic=DELIVERABLE_COMMANDS_TOPIC,
        group_id=settings.KAFKA_CONSUMER_GROUP_ID + "-start-deliverable-saga",
    )

    # Start both consumers
    await general_deliverable_consumer.start()
    await start_saga_command_consumer.start()
    logger.info(f"Started consumers for deliverable events")

    # Start separate async tasks for each consumer loop
    general_events_task = asyncio.create_task(
        _listen_loop(
            general_deliverable_consumer, deliverable_orchestrator.handle_event
        )
    )
    start_saga_command_task = asyncio.create_task(
        _listen_loop(start_saga_command_consumer, deliverable_orchestrator.handle_event)
    )

    # Keep these tasks running indefinitely or until cancelled
    await asyncio.gather(general_events_task, start_saga_command_task)


async def _listen_loop(consumer: Any, handler: Callable[[Dict[str, Any]], Any]):
    """
    Generic loop to consume messages from a given consumer and call a handler.
    """
    try:
        # Use async iteration for AIOKafkaConsumer (FIXED!)
        async for message in consumer:
            logger.info(
                f"Deliverable Listener received message: Topic='{message.topic}', Offset={message.offset}, Type='{message.value.get('event_type') or message.value.get('command_type')}'"
            )
            try:
                # The handler expects the deserialized message value (dict)
                await handler(message.value)  # Call the orchestrator's generic handler
            except Exception as e:
                logger.error(
                    f"Error processing message in deliverable_events_listener handler: {e}",
                    exc_info=True,
                )
                # Implement dead-letter queues or retry logic here in production.
    except asyncio.CancelledError:
        logger.info("Deliverable Events Listener loop cancelled.")
    except Exception as e:
        logger.error(f"Deliverable Events Listener loop crashed: {e}", exc_info=True)
    finally:
        await consumer.stop()  # Use stop() instead of close() for AIOKafkaConsumer
        logger.info("Deliverable Events Listener consumer closed.")
