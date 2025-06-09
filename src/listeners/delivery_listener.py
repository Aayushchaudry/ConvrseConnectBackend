# src/listeners/delivery_listener.py

import asyncio
import logging
from typing import Any, Callable, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import AsyncSessionLocal  # For getting session factory
from src.config.settings import settings
from src.events.event_bus_interface import EventBus

# --- Import Commands Consumed by this Listener ---
from src.orchestrators.deliverable_saga_orchestrator.commands import (
    GenerateFinalOutputCommand,
)  # Main command to consume
from src.services.delivery_service import DeliveryService  # Import the service to call

logger = logging.getLogger(__name__)

# Define the Kafka topic this listener will subscribe to for delivery commands
DELIVERY_COMMAND_TOPIC = (
    "deliverable.command.generate_final_output"  # From Deliverable SAGA Orchestrator
)


async def start_listening(event_bus: EventBus):
    """
    Starts the Delivery Listener, consuming commands from the Event Bus
    and dispatching them to the DeliveryService.
    """
    logger.info(f"Delivery Listener starting for topic: {DELIVERY_COMMAND_TOPIC}")

    # Create an instance of the DeliveryService
    delivery_service = DeliveryService(
        db_session_factory=AsyncSessionLocal,  # Pass the sessionmaker factory
        event_bus=event_bus,
    )

    # Get a consumer for the delivery command topic
    consumer = event_bus.get_consumer(
        topic=DELIVERY_COMMAND_TOPIC,
        group_id=settings.KAFKA_CONSUMER_GROUP_ID
        + "-delivery-manager",  # A distinct consumer group ID
    )

    # Start the async task for the consumer loop
    delivery_command_listener_task = asyncio.create_task(
        _listen_loop(consumer, delivery_service)  # Pass the service instance directly
    )

    # Keep this task running indefinitely or until cancelled
    await delivery_command_listener_task


async def _listen_loop(consumer: Any, service_instance: DeliveryService):
    """
    Generic loop to consume messages from a given consumer and call the appropriate service handler.
    """
    try:
        await consumer.start()
        async for message in consumer:
            logger.info(
                f"Delivery Listener received command: Topic='{message.topic}', Offset={message.offset}, Type='{message.value.get('command_type')}'"
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

                if command_type == "GenerateFinalOutputCommand":
                    command_obj = deliverable_saga_commands.GenerateFinalOutputCommand(
                        **command_data
                    )
                    handler_method = (
                        service_instance.handle_generate_final_output_command
                    )
                # Add other command handlers here if DeliveryService consumes more command types

                if handler_method and command_obj:
                    await handler_method(command_obj)
                else:
                    logger.warning(
                        f"No handler or command class found for command type: {command_type} in DeliveryListener. Data: {command_data}"
                    )

            except Exception as e:
                logger.error(
                    f"Error processing command in delivery_listener handler for {command_type}: {e}",
                    exc_info=True,
                )
                # Implement dead-letter queues or retry logic here in production.
    except asyncio.CancelledError:
        logger.info("Delivery Listener loop cancelled.")
    except Exception as e:
        logger.error(f"Delivery Listener loop crashed: {e}", exc_info=True)
    finally:
        await consumer.stop()
        logger.info("Delivery Listener consumer closed.")
