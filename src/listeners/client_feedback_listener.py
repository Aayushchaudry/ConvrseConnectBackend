# src/listeners/client_feedback_listener.py

import asyncio
import logging
from typing import Any, Callable, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import AsyncSessionLocal  # For getting session factory
from src.config.settings import settings
from src.events.client_feedback_events import (
    ClientFeedbackSubmittedEvent,
)  # Import the event to consume
from src.events.event_bus_interface import EventBus
from src.orchestrators.deliverable_saga_orchestrator.deliverable_saga_orchestrator import (
    DeliverableSagaOrchestrator,
)  # Import the orchestrator to call
from src.services.review_management_service import (
    ReviewManagementService,
)  # Import the service to call

logger = logging.getLogger(__name__)

# Define the Kafka topic this listener will subscribe to for client feedback events
CLIENT_FEEDBACK_TOPIC = (
    "client.feedback.submitted"  # Topic where ClientFeedbackSubmittedEvent is published
)


async def start_listening(event_bus: EventBus):
    """
    Starts the Client Feedback Listener, consuming events from the Event Bus
    and dispatching them to both the DeliverableSagaOrchestrator and ReviewManagementService.
    """
    logger.info(f"Client Feedback Listener starting for topic: {CLIENT_FEEDBACK_TOPIC}")

    # Create an instance of the DeliverableSagaOrchestrator
    # This orchestrator needs to react to client feedback events
    deliverable_orchestrator = DeliverableSagaOrchestrator(
        db_session_factory=AsyncSessionLocal,  # Pass the sessionmaker factory
        event_bus=event_bus,
    )

    # Create an instance of the ReviewManagementService
    # This service needs to store the feedback in the database
    review_service = ReviewManagementService(
        db_session_factory=AsyncSessionLocal,  # Pass the sessionmaker factory
        event_bus=event_bus,
    )

    # Get a consumer for the client feedback topic
    consumer = event_bus.get_consumer(
        topic=CLIENT_FEEDBACK_TOPIC,
        group_id=settings.KAFKA_CONSUMER_GROUP_ID
        + "-client-feedback",  # A distinct consumer group ID
    )

    # Start the async task for the consumer loop
    client_feedback_listener_task = asyncio.create_task(
        _listen_loop(
            consumer, deliverable_orchestrator, review_service
        )  # Pass both handlers
    )

    # Keep this task running indefinitely or until cancelled
    await client_feedback_listener_task


async def _listen_loop(
    consumer: Any,
    orchestrator: DeliverableSagaOrchestrator,
    review_service: ReviewManagementService,
):
    """
    Consumer loop that processes ClientFeedbackSubmittedEvent through both orchestrator and service.
    """
    try:
        await consumer.start()
        async for message in consumer:
            logger.info(
                f"Client Feedback Listener received event: Topic='{message.topic}', Offset={message.offset}, Type='{message.value.get('event_type')}'"
            )
            try:
                event_data = message.value
                event_type = event_data.get("event_type")

                if event_type == "ClientFeedbackSubmittedEvent":
                    # Reconstruct the event object
                    event = ClientFeedbackSubmittedEvent(**event_data)

                    # Call both handlers:
                    # 1. ReviewManagementService to store feedback in database
                    await review_service.handle_client_feedback_submitted(event)
                    logger.info(
                        f"Client Feedback Listener: Feedback stored in database for ReviewItem {event.review_item_id}"
                    )

                    # 2. DeliverableSagaOrchestrator to process SAGA state transitions
                    await orchestrator.handle_event(event_data)
                    logger.info(
                        f"Client Feedback Listener: SAGA state updated for Deliverable {event.deliverable_id}"
                    )
                else:
                    logger.warning(
                        f"Client Feedback Listener: Unexpected event type {event_type}, expected ClientFeedbackSubmittedEvent"
                    )

            except Exception as e:
                logger.error(
                    f"Error processing message in client_feedback_listener handler: {e}",
                    exc_info=True,
                )
                # Implement dead-letter queues or retry logic here in production.
    except asyncio.CancelledError:
        logger.info("Client Feedback Listener loop cancelled.")
    except Exception as e:
        logger.error(f"Client Feedback Listener loop crashed: {e}", exc_info=True)
    finally:
        await consumer.stop()
        logger.info("Client Feedback Listener consumer closed.")
