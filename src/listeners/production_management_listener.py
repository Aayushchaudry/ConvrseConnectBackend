# src/listeners/production_management_listener.py

import asyncio
import logging
from typing import Callable, Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from datetime import datetime

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

    # Get a consumer for the production command topics - start with the first topic
    consumer = event_bus.get_consumer(
        topic=PRODUCTION_COMMAND_TOPICS[0],  # Start with the first topic for now
        group_id=settings.KAFKA_CONSUMER_GROUP_ID + "-production-manager" # A distinct consumer group ID
    )

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
            logger.info(f"Prod Management Listener received command: Topic='{message.topic}', Offset={message.offset}, Type='{message.value.get('command_type')}'")
            try:
                command_data = message.value
                command_type = command_data.get("command_type")

                # Dynamically dispatch command to the correct handler method
                # This requires careful mapping of command_type to method names
                handler_method = None
                command_obj = None

                # Import command dataclasses dynamically to reconstruct the object
                from src.orchestrators.deliverable_saga_orchestrator import commands as deliverable_saga_commands
                from src.commands import production_commands as central_production_commands

                if command_type == "InitiateModelingCommand":
                    # Convert string UUIDs and timestamp back to proper types
                    command_data_converted = {
                        "project_id": UUID(command_data["project_id"]),
                        "deliverable_id": UUID(command_data["deliverable_id"]),
                        "command_id": UUID(command_data["command_id"]),
                        "timestamp": datetime.fromisoformat(command_data["timestamp"]),
                        "command_type": command_data["command_type"]
                    }
                    command_obj = deliverable_saga_commands.InitiateModelingCommand(**command_data_converted)
                    handler_method = service_instance.handle_initiate_modeling_command
                elif command_type == "InitiateTexturingCommand":
                    command_data_converted = {
                        "project_id": UUID(command_data["project_id"]),
                        "deliverable_id": UUID(command_data["deliverable_id"]),
                        "command_id": UUID(command_data["command_id"]),
                        "timestamp": datetime.fromisoformat(command_data["timestamp"]),
                        "command_type": command_data["command_type"]
                    }
                    command_obj = deliverable_saga_commands.InitiateTexturingCommand(**command_data_converted)
                    handler_method = service_instance.handle_initiate_texturing_command # You'll add this to service
                elif command_type == "InitiateRenderingCommand":
                    command_data_converted = {
                        "project_id": UUID(command_data["project_id"]),
                        "deliverable_id": UUID(command_data["deliverable_id"]),
                        "render_type": command_data["render_type"],
                        "command_id": UUID(command_data["command_id"]),
                        "timestamp": datetime.fromisoformat(command_data["timestamp"]),
                        "command_type": command_data["command_type"]
                    }
                    command_obj = deliverable_saga_commands.InitiateRenderingCommand(**command_data_converted)
                    handler_method = service_instance.handle_initiate_rendering_command # You'll add this to service
                elif command_type == "CreateInternalTaskCommand":
                    command_obj = central_production_commands.CreateInternalTaskCommand(**command_data)
                    handler_method = service_instance.handle_create_internal_task_command # You'll add this to service
                elif command_type == "UpdateInternalTaskStatusCommand":
                    command_obj = central_production_commands.UpdateInternalTaskStatusCommand(**command_data)
                    handler_method = service_instance.handle_update_internal_task_status_command
                elif command_type == "CreateReworkTaskCommand":
                    command_obj = central_production_commands.CreateReworkTaskCommand(**command_data)
                    handler_method = service_instance.handle_create_rework_task_command
                
                if handler_method and command_obj:
                    await handler_method(command_obj)
                else:
                    logger.warning(f"No handler or command class found for command type: {command_type}. Data: {command_data}")

            except Exception as e:
                logger.error(f"Error processing command in production_management_listener handler for {command_type}: {e}", exc_info=True)
                # Implement dead-letter queues or retry logic here in production.
    except asyncio.CancelledError:
        logger.info("Production Management Listener loop cancelled.")
    except Exception as e:
        logger.error(f"Production Management Listener loop crashed: {e}", exc_info=True)
    finally:
        await consumer.stop()
        logger.info("Production Management Listener consumer closed.")