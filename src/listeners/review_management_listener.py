# src/listeners/review_management_listener.py

import asyncio
import logging
from typing import Any, Callable, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import AsyncSessionLocal  # For getting session factory
from src.config.settings import settings
from src.events.event_bus_interface import EventBus

# --- Import Commands Consumed by this Listener ---
from src.orchestrators.deliverable_saga_orchestrator.commands import (
    GenerateReviewItemCommand,
)  # Main command to consume
from src.services.review_management_service import (
    ReviewManagementService,
)  # Import the service to call

# Note: Client feedback events (ClientFeedbackSubmittedEvent) are published by API/another service
# and consumed directly by the Deliverable SAGA Orchestrator, or a specific listener for client feedback.

logger = logging.getLogger(__name__)

# Define the Kafka topics this listener will subscribe to for review management commands
REVIEW_MANAGEMENT_COMMAND_TOPICS = [
    "deliverable.command.generate_review_item",  # From Deliverable SAGA Orchestrator
    # Add other review-related commands here if they are directly consumed by this service
]


async def start_listening(event_bus: EventBus):
    """
    Starts the Review Management Listener, consuming commands from the Event Bus
    and dispatching them to the ReviewManagementService.
    """
    logger.info(
        f"Review Management Listener starting for topics: {REVIEW_MANAGEMENT_COMMAND_TOPICS}"
    )

    # Create an instance of the ReviewManagementService
    review_service = ReviewManagementService(
        db_session_factory=AsyncSessionLocal,  # Pass the sessionmaker factory
        event_bus=event_bus,
    )

    # Get a consumer for the review management command topics
    consumer = event_bus.get_consumer(
        topic=REVIEW_MANAGEMENT_COMMAND_TOPICS,
        group_id=settings.KAFKA_CONSUMER_GROUP_ID
        + "-review-manager",  # A distinct consumer group ID
    )

    # Start the async task for the consumer loop
    review_command_listener_task = asyncio.create_task(
        _listen_loop(consumer, review_service)  # Pass the service instance directly
    )

    # Keep this task running indefinitely or until cancelled
    await review_command_listener_task


async def _listen_loop(consumer: Any, service_instance: ReviewManagementService):
    """
    Generic loop to consume messages from a given consumer and call the appropriate service handler.
    """
    try:
        await consumer.start()  # Start the AIOKafkaConsumer
        # Use async iteration for AIOKafkaConsumer (FIXED!)
        async for message in consumer:
            logger.info(
                f"Review Management Listener received command: Topic='{message.topic}', Offset={message.offset}, Type='{message.value.get('command_type')}'"
            )
            try:
                command_data = message.value
                command_type = command_data.get("command_type")

                # Dynamically dispatch command to the correct handler method
                handler_method = None
                command_obj = None

                # Import command dataclasses dynamically to reconstruct the object
                from src.orchestrators.deliverable_saga_orchestrator import (
                    commands as deliverable_saga_commands,
                )

                if command_type == "GenerateReviewItemCommand":
                    command_obj = deliverable_saga_commands.GenerateReviewItemCommand(
                        **command_data
                    )
                    handler_method = (
                        service_instance.handle_generate_review_item_command
                    )
                # Add other command handlers here if ReviewManagementService consumes more command types

                if handler_method and command_obj:
                    await handler_method(command_obj)
                else:
                    logger.warning(
                        f"No handler or command class found for command type: {command_type} in ReviewManagementListener. Data: {command_data}"
                    )

            except Exception as e:
                logger.error(
                    f"Error processing command in review_management_listener handler for {command_type}: {e}",
                    exc_info=True,
                )
                # Implement dead-letter queues or retry logic here in production.
    except asyncio.CancelledError:
        logger.info("Review Management Listener loop cancelled.")
    except Exception as e:
        logger.error(f"Review Management Listener loop crashed: {e}", exc_info=True)
    finally:
        await consumer.stop()  # Use stop() instead of close() for AIOKafkaConsumer
        logger.info("Review Management Listener consumer closed.")
