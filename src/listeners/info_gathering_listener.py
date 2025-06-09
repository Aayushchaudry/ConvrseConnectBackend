# src/listeners/info_gathering_listener.py

import asyncio
import logging
from typing import Any, Callable, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from src.commands.project_commands import (
    StartInformationGatheringCommand,
)  # Import the command to consume
from src.config.database import (
    AsyncSessionLocal,
)  # Import AsyncSessionLocal for DB sessions
from src.config.settings import settings
from src.events.event_bus_interface import EventBus
from src.services.info_gathering_service import (
    InformationGatheringService,
)  # Import the service to call

logger = logging.getLogger(__name__)

# Define the Kafka topic(s) this listener will subscribe to
INFO_GATHERING_COMMAND_TOPIC = "project.command.start_info_gathering"  # Topic where StartInformationGatheringCommand is published


async def start_listening(event_bus: EventBus):
    """
    Starts the Information Gathering Listener, consuming commands from the Event Bus
    and dispatching them to the InformationGatheringService.
    """
    logger.info(
        f"Information Gathering Listener starting for topic: {INFO_GATHERING_COMMAND_TOPIC}"
    )

    # Create an instance of the InformationGatheringService
    info_gathering_service = InformationGatheringService(
        db_session_factory=AsyncSessionLocal,  # Pass the sessionmaker factory
        event_bus=event_bus,
    )

    # Get a consumer for the information gathering command topic
    consumer = event_bus.get_consumer(
        topic=INFO_GATHERING_COMMAND_TOPIC,
        group_id=settings.KAFKA_CONSUMER_GROUP_ID
        + "-info-gatherer",  # A distinct consumer group ID
    )

    # Start the consumer
    await consumer.start()
    logger.info(f"Started consumer for topic: {INFO_GATHERING_COMMAND_TOPIC}")

    # Start the async task for the consumer loop
    # We pass the service's handler method.
    info_gathering_task = asyncio.create_task(
        _listen_loop(
            consumer, info_gathering_service.handle_start_information_gathering_command
        )
    )

    # Keep this task running indefinitely or until cancelled
    await info_gathering_task


async def _listen_loop(consumer: Any, handler: Callable[[Dict[str, Any]], Any]):
    """
    Generic loop to consume messages from a given consumer and call a handler.
    """
    try:
        # Use async iteration for AIOKafkaConsumer
        async for message in consumer:
            logger.info(
                f"Listener received command from Topic='{message.topic}', Offset={message.offset}"
            )
            try:
                # The handler expects the deserialized message value (dict)
                # Convert the dict back to the specific Command dataclass for type safety/completeness
                command_obj = StartInformationGatheringCommand(**message.value)
                await handler(command_obj)
            except Exception as e:
                logger.error(
                    f"Error processing command in info_gathering_listener handler: {e}",
                    exc_info=True,
                )
                # In a production system, implement dead-letter queues or retry logic here.
    except asyncio.CancelledError:
        logger.info("Information Gathering Listener loop cancelled.")
    except Exception as e:
        logger.error(f"Information Gathering Listener loop crashed: {e}", exc_info=True)
    finally:
        await consumer.stop()
        logger.info("Information Gathering Listener consumer closed.")
