# src/listeners/project_events_listener.py

import asyncio
import logging
from typing import Any, Callable, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import (
    AsyncSessionLocal,
)  # Import AsyncSessionLocal for DB sessions
from src.config.settings import settings
from src.events.event_bus_interface import EventBus
from src.orchestrators.project_lifecycle_orchestrator.project_lifecycle_orchestrator import (
    ProjectLifecycleOrchestrator,
)

logger = logging.getLogger(__name__)

# Define the Kafka topic(s) this listener will subscribe to
# This should match where project-level events are published (e.g., "project.created")
PROJECT_EVENTS_TOPIC = "project.created"  # Topic where ProjectCreatedEvent is published
DELIVERABLE_REPORT_TOPICS = [
    "deliverable.delivered",
    "deliverable.failed",
]  # Topics from colleague's Deliverable SAGA

# Topics for automatic project status progression
PROJECT_PROGRESSION_TOPICS = [
    "internal_task.completed",          # Task completion triggers progression to in_progress
    "internal_task.completed_with_media", # Task completion with files triggers progression to in_progress  
    "internal_task.status.updated",     # Task status changes (e.g., to in-progress)
    "requirement.updated",              # Requirement completion triggers progression to in_progress
]


async def start_listening(event_bus: EventBus):
    logger.info("🚨 [PROJECT EVENTS LISTENER] Entered start_listening - function is being called.")
    """
    Starts the Project Events Listener, consuming messages from the Event Bus
    and dispatching them to the ProjectLifecycleOrchestrator.
    """
    logger.info("🚦 Project Events Listener: STARTUP - This log should always appear if the listener is running.")
    try:
        logger.info(
            f"Project Events Listener starting for topic(s): {PROJECT_EVENTS_TOPIC}, {DELIVERABLE_REPORT_TOPICS}, and {PROJECT_PROGRESSION_TOPICS}"
        )

        # Create an instance of the ProjectLifecycleOrchestrator
        # It needs a factory for DB sessions and the event_bus itself.
        project_orchestrator = ProjectLifecycleOrchestrator(
            db_session_factory=AsyncSessionLocal,  # Pass the sessionmaker factory
            event_bus=event_bus,
        )

        # Get a consumer for the project creation topic
        project_created_consumer = event_bus.get_consumer(
            topic=PROJECT_EVENTS_TOPIC,
            group_id=settings.KAFKA_CONSUMER_GROUP_ID + "-project-creator",
        )

        # Get a consumer for deliverable report topics (if different group is desired)
        deliverable_report_consumer = event_bus.get_consumer(
            topic=DELIVERABLE_REPORT_TOPICS[0],  # Start with first topic for now
            group_id=settings.KAFKA_CONSUMER_GROUP_ID + "-deliverable-reporter",
        )

        # Get a consumer for project progression events (task completions, requirement updates)
        project_progression_consumer = event_bus.get_consumer(
            topic=PROJECT_PROGRESSION_TOPICS,  # Listen to all progression topics
            group_id=settings.KAFKA_CONSUMER_GROUP_ID + "-project-progression",
        )

        # Start the consumers
        await project_created_consumer.start()
        logger.info(f"Started consumer for topic: {PROJECT_EVENTS_TOPIC}")

        await deliverable_report_consumer.start()
        logger.info(f"Started consumer for topic: {DELIVERABLE_REPORT_TOPICS[0]}")

        await project_progression_consumer.start()
        logger.info(f"Started consumer for topics: {PROJECT_PROGRESSION_TOPICS}")

        # Start separate async tasks for each consumer loop
        # Using 'asyncio.create_task' ensures these run in the background
        # We pass the orchestrator's handle_event method as the handler.
        project_created_task = asyncio.create_task(
            _listen_loop(project_created_consumer, project_orchestrator.handle_event)
        )
        deliverable_report_task = asyncio.create_task(
            _listen_loop(deliverable_report_consumer, project_orchestrator.handle_event)
        )
        project_progression_task = asyncio.create_task(
            _listen_loop(project_progression_consumer, project_orchestrator.handle_event)
        )

        # Keep these tasks running indefinitely or until cancelled
        await asyncio.gather(project_created_task, deliverable_report_task, project_progression_task)
    except Exception as e:
        logger.error(f"❌ Project Events Listener failed to start: {e}", exc_info=True)
        raise


async def _listen_loop(consumer: Any, handler: Callable[[Dict[str, Any]], Any]):
    """
    Generic loop to consume messages from a given consumer and call a handler.
    """
    try:
        # Use async iteration for AIOKafkaConsumer
        async for message in consumer:
            logger.info(
                f"Listener received message from Topic='{message.topic}', Offset={message.offset}"
            )
            try:
                # The handler expects the deserialized message value (dict)
                await handler(message.value)
            except Exception as e:
                logger.error(
                    f"Error processing message in listener handler: {e}", exc_info=True
                )
                # In a production system, you might implement dead-letter queues here.
    except asyncio.CancelledError:
        logger.info("Listener loop cancelled.")
    except Exception as e:
        logger.error(f"Listener loop crashed: {e}", exc_info=True)
    finally:
        await consumer.stop()
        logger.info("Listener consumer closed.")
