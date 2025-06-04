# src/listeners/production_management_listener.py

import asyncio
import logging
from typing import Callable, Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from datetime import datetime
import traceback

from src.config.settings import settings
from src.config.database import AsyncSessionLocal # For getting session factory
from src.events.event_bus_interface import EventBus
from src.services.production_management_service import ProductionManagementService # Import the service to call

# --- Import Commands Consumed by this Listener ---
from src.orchestrators.deliverable_saga_orchestrator.commands import (
    InitiateModelingCommand,
    InitiateTexturingCommand,
    InitiateRenderingCommand
)
from src.commands.production_commands import (
    CreateInternalTaskCommand,
    UpdateInternalTaskStatusCommand,
    CreateReworkTaskCommand
)

logger = logging.getLogger(__name__)

# Define the Kafka topics this listener will subscribe to for production commands
PRODUCTION_COMMAND_TOPICS = [
    "deliverable.command.initiate_modeling",
    "deliverable.command.initiate_texturing",
    "deliverable.command.initiate_rendering",
    "deliverable.command.create_rework_task", # From Deliverable Orchestrator
    "production.command.update_internal_task_status" # From Deliverable Orchestrator (or other sources)
]

async def start_listening(event_bus: EventBus):
    """
    Starts the Production Management Listener, consuming commands from the Event Bus
    and dispatching them to the ProductionManagementService.
    """
    logger.info(f"Production Management Listener starting for topics: {PRODUCTION_COMMAND_TOPICS}")

    # Create an instance of the ProductionManagementService
    production_service = ProductionManagementService(
        db_session_factory=AsyncSessionLocal, # Pass the sessionmaker factory
        event_bus=event_bus
    )

    # Get a consumer for the production command topics
    consumer = event_bus.get_consumer(
        topic=PRODUCTION_COMMAND_TOPICS,  # Subscribe to all topics
        group_id=settings.KAFKA_CONSUMER_GROUP_ID + "-production-manager" # A distinct consumer group ID
    )
    logger.info(f"Production Management Listener subscribed to topics: {PRODUCTION_COMMAND_TOPICS}")

    # Start the consumer - this was missing!
    await consumer.start()
    logger.info(f"Started consumer for topic: {PRODUCTION_COMMAND_TOPICS[0]}")

    # Start the async task for the consumer loop
    production_task_listener = asyncio.create_task(
        _listen_loop(consumer, production_service) # Pass the service instance directly
    )

    # Keep this task running indefinitely or until cancelled
    await production_task_listener


async def _listen_loop(consumer: Any, service_instance: ProductionManagementService):
    """
    Generic loop to consume messages from a given consumer and call the appropriate service handler.
    """
    try:
        # Use async iteration for AIOKafkaConsumer - this was the main issue!
        async for message in consumer:
            logger.info(f"Received message on topic: {message.topic}")
            logger.info(f"Message value: {message.value}")
            
            if message.topic == "deliverable.command.initiate_modeling":
                logger.info("Processing initiate_modeling command")
                command = InitiateModelingCommand(**message.value)
                await service_instance.handle_initiate_modeling_command(command)
                logger.info(f"Created modeling task for deliverable {command.deliverable_id}")
            elif message.topic == "deliverable.command.create_rework_task":
                logger.info("Processing create_rework_task command")
                command = CreateReworkTaskCommand(**message.value)
                await service_instance.handle_create_rework_task_command(command)
                logger.info(f"Created rework task for original task {command.original_task_id}")
            elif message.topic == "production.command.update_internal_task_status":
                logger.info("Processing update_internal_task_status command")
                command = UpdateInternalTaskStatusCommand(**message.value)
                await service_instance.handle_update_internal_task_status_command(command)
                logger.info(f"Updated internal task {command.task_id} status to {command.new_status}")

    except asyncio.CancelledError:
        logger.info("Production Management Listener loop cancelled.")
    except Exception as e:
        logger.error(f"Production Management Listener loop crashed: {str(e)}")
        logger.error(traceback.format_exc())
    finally:
        await consumer.stop()
        logger.info("Production Management Listener consumer closed.")