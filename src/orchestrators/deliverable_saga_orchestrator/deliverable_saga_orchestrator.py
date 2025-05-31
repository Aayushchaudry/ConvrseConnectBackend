# src/orchestrators/deliverable_saga_orchestrator/deliverable_saga_orchestrator.py

import logging
import uuid
from datetime import datetime
from typing import Callable, Any, Dict, Optional, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models.saga_state import SagaState, SagaStatus, SagaType
from src.models.deliverable import Deliverable, DeliverableStatus # Needed for status updates
from src.events.event_bus_interface import EventBus
from src.orchestrators.saga_processor import SagaProcessor

# --- Import Commands specific to Deliverable SAGA ---
from src.commands.project_commands import StartDeliverableSagaCommand # This command initiates *this* SAGA
from src.orchestrators.deliverable_saga_orchestrator.commands import (
    StartDeliverableInfoGatheringCommand,
    InitiateModelingCommand,
    InitiateTexturingCommand,
    InitiateRenderingCommand,
    GenerateReviewItemCommand,
    GenerateFinalOutputCommand,
    UpdateDeliverableStatusInDBCommand,
)
from src.commands.production_commands import CreateReworkTaskCommand, UpdateInternalTaskStatusCommand
# --- Import Events specific to Deliverable SAGA ---
from src.events.deliverable_events import DeliverableInfoGatheredEvent, DeliverableInfoGatheringFailedEvent
from src.events.project_events import DeliverableDeliveredEvent
from src.events.task_events import InternalTaskCreatedEvent, InternalTaskCompletedEvent, InternalTaskFailedEvent, InternalTaskStatusUpdatedEvent
from src.events.client_feedback_events import ClientFeedbackSubmittedEvent, ReviewItemApprovedEvent, ReviewItemRejectedEvent
# --- Import Deliverable SAGA States ---
from src.orchestrators.deliverable_saga_orchestrator.states import DeliverableSagaState

logger = logging.getLogger(__name__)

class DeliverableSagaOrchestrator:
    """
    Orchestrates the lifecycle of a single Deliverable, from information gathering
    through production, review, and final delivery.
    """
    def __init__(self, db_session_factory: Callable[[], AsyncSession], event_bus: EventBus):
        """
        Initializes the DeliverableSagaOrchestrator.
        Args:
            db_session_factory: A factory function to get a new AsyncSession.
            event_bus: The EventBus instance for publishing commands/events.
        """
        self.db_session_factory = db_session_factory
        self.event_bus = event_bus
        self.saga_processor = SagaProcessor(event_bus=event_bus)

        # Mappings of SAGA states to event handlers
        self.event_handlers: Dict[str, Callable[[Any], Any]] = {
            "StartDeliverableSagaCommand": self.on_start_deliverable_saga, # This is a command, but it acts as an event to initiate this SAGA
            "DeliverableInfoGatheredEvent": self.on_deliverable_info_gathered,
            "DeliverableInfoGatheringFailedEvent": self.on_deliverable_info_gathering_failed,
            "InternalTaskCompletedEvent": self.on_internal_task_completed,
            "InternalTaskFailedEvent": self.on_internal_task_failed,
            "ClientFeedbackSubmittedEvent": self.on_client_feedback_submitted,
            # Add handlers for other events as needed for more granular control
            "DeliverableDeliveredEvent": self.on_deliverable_delivered_final # The final success event for this SAGA
        }

    async def _get_deliverable(self, session: AsyncSession, deliverable_id: UUID) -> Optional[Deliverable]:
        """Helper to retrieve a deliverable."""
        result = await session.execute(
            select(Deliverable).filter(Deliverable.id == deliverable_id)
        )
        return result.scalar_one_or_none()

    async def on_start_deliverable_saga(self, command: StartDeliverableSagaCommand):
        """
        Handles the StartDeliverableSagaCommand published by the Project Orchestrator.
        This is the entry point for a Deliverable SAGA orchestration.
        """
        logger.info(f"DeliverableSagaOrchestrator: Received StartDeliverableSagaCommand for Deliverable ID: {command.deliverable_id}")

        async with self.db_session_factory() as session:
            # 1. Get or create SagaState for this Deliverable SAGA instance
            saga_state = await self.saga_processor.get_or_create_saga_state(
                session=session,
                project_id=command.project_id,
                deliverable_id=command.deliverable_id,
                saga_type=SagaType.DELIVERABLE_PRODUCTION,
                initial_state=DeliverableSagaState.INITIATED.value,
                saga_id=command.deliverable_id # Using deliverable_id as saga_id for this Deliverable SAGA
            )

            # Idempotency check: If this command was already processed, skip.
            if saga_state.current_state != DeliverableSagaState.INITIATED.value and \
               saga_state.last_event_processed_id == str(command.command_id): # Check against command ID for idempotency here
                logger.warning(f"DeliverableSagaOrchestrator: StartDeliverableSagaCommand {command.command_id} already processed for Deliverable {command.deliverable_id}. Idempotent.")
                return
            
            # Update Deliverable status in DB
            deliverable = await self._get_deliverable(session, command.deliverable_id)
            if deliverable:
                await self.saga_processor.publish_message(
                    topic="deliverable.command.update_status_db", # Define this topic
                    message_payload=UpdateDeliverableStatusInDBCommand(
                        project_id=command.project_id,
                        deliverable_id=command.deliverable_id,
                        new_status=DeliverableStatus.INFO_GATHERING.value
                    )
                )

            # 2. Transition SAGA State and Send Next Command (Start Info Gathering)
            next_state = DeliverableSagaState.INFO_GATHERING_STARTED
            cmd_start_info_gathering = StartDeliverableInfoGatheringCommand(
                project_id=command.project_id,
                deliverable_id=command.deliverable_id
            )
            await self.saga_processor.publish_message(
                topic="deliverable.command.start_info_gathering", # Define this topic
                message_payload=cmd_start_info_gathering
            )

            # 3. Update SAGA state
            await self.saga_processor.update_saga_state(
                session=session,
                saga_state=saga_state,
                new_state_enum=next_state,
                event_id=command.command_id, # Use command ID as this is the trigger
                command_id=cmd_start_info_gathering.command_id
            )
            logger.info(f"Deliverable SAGA for {command.deliverable_id} transitioned to {next_state.value} and sent StartDeliverableInfoGatheringCommand.")


    async def on_deliverable_info_gathered(self, event: DeliverableInfoGatheredEvent):
        """
        Handles DeliverableInfoGatheredEvent.
        This event signals that initial requirements for a deliverable have been collected.
        """
        logger.info(f"DeliverableSagaOrchestrator: Received DeliverableInfoGatheredEvent for Deliverable ID: {event.deliverable_id}")

        async with self.db_session_factory() as session:
            saga_state = await self.saga_processor.get_or_create_saga_state( # Use get_or_create for robustness
                session=session,
                project_id=event.project_id,
                deliverable_id=event.deliverable_id,
                saga_type=SagaType.DELIVERABLE_PRODUCTION,
                initial_state=DeliverableSagaState.INFO_GATHERING_COMPLETED.value,
                saga_id=event.deliverable_id # Ensure this matches the saga_id created
            )
            
            # Idempotency check
            if saga_state.last_event_processed_id == str(event.event_id):
                logger.warning(f"DeliverableSagaOrchestrator: DeliverableInfoGatheredEvent {event.event_id} already processed for Deliverable {event.deliverable_id}. Idempotent.")
                return

            # Update Deliverable status in DB
            deliverable = await self._get_deliverable(session, event.deliverable_id)
            if deliverable:
                await self.saga_processor.publish_message(
                    topic="deliverable.command.update_status_db",
                    message_payload=UpdateDeliverableStatusInDBCommand(
                        project_id=event.project_id,
                        deliverable_id=event.deliverable_id,
                        new_status=DeliverableStatus.MODELING_PENDING.value # Assuming modeling is next
                    )
                )

            # Transition SAGA State and Send Next Command (Initiate Modeling)
            next_state = DeliverableSagaState.MODELING_PENDING
            cmd_init_modeling = InitiateModelingCommand(
                project_id=event.project_id,
                deliverable_id=event.deliverable_id
            )
            await self.saga_processor.publish_message(
                topic="deliverable.command.initiate_modeling", # Define this topic
                message_payload=cmd_init_modeling
            )

            # Update SAGA state
            await self.saga_processor.update_saga_state(
                session=session,
                saga_state=saga_state,
                new_state_enum=next_state,
                event_id=event.event_id,
                command_id=cmd_init_modeling.command_id
            )
            logger.info(f"Deliverable SAGA for {event.deliverable_id} transitioned to {next_state.value} and sent InitiateModelingCommand.")


    async def on_deliverable_info_gathering_failed(self, event: DeliverableInfoGatheringFailedEvent):
        """
        Handles DeliverableInfoGatheringFailedEvent.
        This signals a failure during initial information collection for a deliverable.
        """
        logger.error(f"DeliverableSagaOrchestrator: Info Gathering Failed for Deliverable {event.deliverable_id}. Reason: {event.reason}")

        async with self.db_session_factory() as session:
            saga_state = await self.saga_processor.get_or_create_saga_state(
                session=session,
                project_id=event.project_id,
                deliverable_id=event.deliverable_id,
                saga_type=SagaType.DELIVERABLE_PRODUCTION,
                initial_state=DeliverableSagaState.FAILED.value, # If this is the first event, mark as failed
                saga_id=event.deliverable_id
            )

            if saga_state.last_event_processed_id == str(event.event_id):
                logger.warning(f"DeliverableSagaOrchestrator: DeliverableInfoGatheringFailedEvent {event.event_id} already processed for Deliverable {event.deliverable_id}. Idempotent.")
                return
            
            # Compensation (e.g., mark deliverable as failed, notify project orchestrator)
            await self.saga_processor.update_saga_state(
                session=session,
                saga_state=saga_state,
                new_state_enum=DeliverableSagaState.FAILED,
                event_id=event.event_id,
                new_saga_status=SagaStatus.FAILED # Mark the SAGA itself as FAILED
            )
            logger.info(f"Deliverable SAGA for {event.deliverable_id} transitioned to {DeliverableSagaState.FAILED.value} due to info gathering failure.")
            
            # Notify Project Orchestrator about the failure
            from src.events.project_events import DeliverableFailedEvent as ProjectDeliverableFailedEvent # Alias to avoid name conflict
            await self.saga_processor.publish_message(
                topic="project.deliverable.failed", # Define this topic
                message_payload=ProjectDeliverableFailedEvent(
                    project_id=event.project_id,
                    deliverable_id=event.deliverable_id,
                    deliverable_name=deliverable.deliverable_type.value if deliverable else "Unknown", # Get deliverable name if available
                    reason=f"Info gathering failed: {event.reason}"
                )
            )

    async def on_internal_task_completed(self, event: InternalTaskCompletedEvent):
        """
        Handles InternalTaskCompletedEvent.
        This signals that an internal production task has been completed.
        """
        logger.info(f"DeliverableSagaOrchestrator: Received InternalTaskCompletedEvent for Deliverable {event.deliverable_id}, Task {event.task_id} ({event.task_type})")
        
        async with self.db_session_factory() as session:
            saga_state = await self.saga_processor.get_or_create_saga_state(
                session=session,
                project_id=event.project_id,
                deliverable_id=event.deliverable_id,
                saga_type=SagaType.DELIVERABLE_PRODUCTION,
                initial_state=DeliverableSagaState.MODELING_COMPLETED.value, # If this is the very first event, or just a generic state
                saga_id=event.deliverable_id
            )

            if saga_state.last_event_processed_id == str(event.event_id):
                logger.warning(f"DeliverableSagaOrchestrator: InternalTaskCompletedEvent {event.event_id} already processed for Deliverable {event.deliverable_id}. Idempotent.")
                return
            
            # Logic to determine next state based on task type and current SAGA state
            next_state = saga_state.current_state # Default to no change
            next_command = None
            command_topic = None

            if saga_state.current_state == DeliverableSagaState.MODELING_PENDING.value and event.task_type == "modeling":
                next_state = DeliverableSagaState.MODELING_COMPLETED
                next_command = InitiateTexturingCommand(project_id=event.project_id, deliverable_id=event.deliverable_id)
                command_topic = "deliverable.command.initiate_texturing"
            elif saga_state.current_state == DeliverableSagaState.TEXTURING_PENDING.value and event.task_type == "texturing":
                next_state = DeliverableSagaState.TEXTURING_COMPLETED
                next_command = InitiateRenderingCommand(project_id=event.project_id, deliverable_id=event.deliverable_id, render_type="first_draft")
                command_topic = "deliverable.command.initiate_rendering"
            # ... and so on for other task types and transitions

            if next_command:
                await self.saga_processor.publish_message(topic=command_topic, message_payload=next_command)
                command_id_to_record = next_command.command_id
            else:
                command_id_to_record = None # No command sent

            await self.saga_processor.update_saga_state(
                session=session,
                saga_state=saga_state,
                new_state_enum=next_state,
                event_id=event.event_id,
                command_id=command_id_to_record
            )
            logger.info(f"Deliverable SAGA for {event.deliverable_id} transitioned to {next_state.value} after task '{event.task_name}' completion.")

    async def on_internal_task_failed(self, event: InternalTaskFailedEvent):
        """
        Handles InternalTaskFailedEvent.
        This signals a failure in an internal production task.
        """
        logger.error(f"DeliverableSagaOrchestrator: Internal Task Failed for Deliverable {event.deliverable_id}, Task {event.task_id} ({event.task_type}). Reason: {event.reason}")

        async with self.db_session_factory() as session:
            saga_state = await self.saga_processor.get_or_create_saga_state(
                session=session,
                project_id=event.project_id,
                deliverable_id=event.deliverable_id,
                saga_type=SagaType.DELIVERABLE_PRODUCTION,
                initial_state=DeliverableSagaState.FAILED.value, # If this is the very first event, mark as failed
                saga_id=event.deliverable_id
            )

            if saga_state.last_event_processed_id == str(event.event_id):
                logger.warning(f"DeliverableSagaOrchestrator: InternalTaskFailedEvent {event.event_id} already processed for Deliverable {event.deliverable_id}. Idempotent.")
                return
            
            # Compensation/Retry Logic:
            # Here, you decide if to retry the task, create rework task, or mark deliverable failed
            next_state_enum = DeliverableSagaState.FAILED # Default to failed for simplicity
            new_saga_status = SagaStatus.FAILED

            # Example: If task type is 'rendering', maybe try a retry logic or create rework task.
            # If not, mark deliverable as failed.
            if event.task_type == "rendering" and saga_state.retry_attempts < settings.SAGA_RETRY_ATTEMPTS:
                saga_state.retry_attempts += 1
                next_state_enum = saga_state.current_state # Stay in current state, schedule retry
                new_saga_status = SagaStatus.IN_PROGRESS
                # (Future): Send a command to retry the task with a delay
                logger.info(f"Deliverable SAGA {event.deliverable_id}: Task '{event.task_name}' failed. Retrying in {settings.SAGA_RETRY_DELAY_SECONDS}s.")
            else:
                # If retries exhausted or severe error, mark deliverable as FAILED
                logger.error(f"Deliverable SAGA {event.deliverable_id}: Task '{event.task_name}' failed unrecoverably. Marking deliverable SAGA as FAILED.")
                # Also notify Project Orchestrator
                from src.events.project_events import DeliverableFailedEvent as ProjectDeliverableFailedEvent
                await self.saga_processor.publish_message(
                    topic="project.deliverable.failed",
                    message_payload=ProjectDeliverableFailedEvent(
                        project_id=event.project_id,
                        deliverable_id=event.deliverable_id,
                        deliverable_name=deliverable.deliverable_type.value if deliverable else "Unknown", # Needs deliverable obj from DB
                        reason=f"Internal task failed: {event.reason}"
                    )
                )

            await self.saga_processor.update_saga_state(
                session=session,
                saga_state=saga_state,
                new_state_enum=next_state_enum,
                event_id=event.event_id,
                new_saga_status=new_saga_status
            )
            logger.info(f"Deliverable SAGA for {event.deliverable_id} handled task failure: {next_state_enum.value}.")


    async def on_client_feedback_submitted(self, event: ClientFeedbackSubmittedEvent):
        """
        Handles ClientFeedbackSubmittedEvent.
        This is a critical event for the review and rework cycle.
        """
        logger.info(f"DeliverableSagaOrchestrator: Received ClientFeedbackSubmittedEvent for Deliverable {event.deliverable_id}, Feedback Type: {event.feedback_type}")

        async with self.db_session_factory() as session:
            saga_state = await self.saga_processor.get_or_create_saga_state(
                session=session,
                project_id=event.project_id,
                deliverable_id=event.deliverable_id,
                saga_type=SagaType.DELIVERABLE_PRODUCTION,
                initial_state=DeliverableSagaState.AWAITING_FIRST_DRAFT_REVIEW.value, # Or current state
                saga_id=event.deliverable_id
            )

            if saga_state.last_event_processed_id == str(event.event_id):
                logger.warning(f"DeliverableSagaOrchestrator: ClientFeedbackSubmittedEvent {event.event_id} already processed for Deliverable {event.deliverable_id}. Idempotent.")
                return

            current_saga_state = DeliverableSagaState(saga_state.current_state) # Get current state as Enum
            next_state_enum = current_saga_state # Default to no change

            # --- Core Logic for Client Feedback ---
            if event.feedback_type == "accept":
                next_state_enum = DeliverableSagaState.CLIENT_REVIEW_ACCEPTED
                # Example: If this is the final approval, send GenerateFinalOutputCommand
                # For now, let's just assume it transitions to accepted state
                # In a real app, you'd check review_round or item_type if this is final.
                
                # Publish event that review item was approved
                review_approved_event = ReviewItemApprovedEvent(
                    project_id=event.project_id,
                    deliverable_id=event.deliverable_id,
                    review_item_id=event.review_item_id,
                    approved_by_user_id=event.client_user_id # If client_user_id is available
                )
                await self.saga_processor.publish_message(
                    topic="deliverable.review_item.approved", # Define this topic
                    message_payload=review_approved_event
                )

                # Send command to update Deliverable Status in DB
                await self.saga_processor.publish_message(
                    topic="deliverable.command.update_status_db",
                    message_payload=UpdateDeliverableStatusInDBCommand(
                        project_id=event.project_id,
                        deliverable_id=event.deliverable_id,
                        new_status=DeliverableStatus.READY_FOR_FINAL_DELIVERY.value # Example transition
                    )
                )

                # If this is the final stage, then send GenerateFinalOutputCommand
                # if current_saga_state == DeliverableSagaState.AWAITING_FINAL_REVIEW_APPROVAL:
                #    command = GenerateFinalOutputCommand(...)
                #    await self.saga_processor.publish_message(topic="deliverable.command.generate_final_output", message_payload=command)

            elif event.feedback_type == "comment":
                next_state_enum = DeliverableSagaState.REVISIONS_IN_PROGRESS
                # Send command to create rework task
                command = CreateReworkTaskCommand(
                    project_id=event.project_id,
                    deliverable_id=event.deliverable_id,
                    original_task_id=None, # You'll need to link this from the ReviewItem data
                    comment_id=event.event_id, # Using event_id as comment_id for simplicity
                    rework_description=event.comment_text or "Client left a comment"
                )
                await self.saga_processor.publish_message(
                    topic="deliverable.command.create_rework_task", # Define this topic
                    message_payload=command
                )
                await self.saga_processor.publish_message( # Also update internal task status for rework
                    topic="production.command.update_internal_task_status", # Define this topic
                    message_payload=UpdateInternalTaskStatusCommand(
                        project_id=event.project_id,
                        deliverable_id=event.deliverable_id,
                        task_id=event.review_item_id, # Assuming review_item_id links to a production task
                        new_status="awaiting_rework" # Placeholder status
                    )
                )
            
            elif event.feedback_type == "reject":
                next_state_enum = DeliverableSagaState.REVISIONS_IN_PROGRESS # Or FAILED, depending on severity
                new_saga_status = SagaStatus.IN_PROGRESS
                
                # Publish event that review item was rejected
                review_rejected_event = ReviewItemRejectedEvent(
                    project_id=event.project_id,
                    deliverable_id=event.deliverable_id,
                    review_item_id=event.review_item_id,
                    rejected_by_user_id=event.client_user_id,
                    reason=event.comment_text or "Rejected by client"
                )
                await self.saga_processor.publish_message(
                    topic="deliverable.review_item.rejected", # Define this topic
                    message_payload=review_rejected_event
                )

                # Send command to mark relevant internal task as rejected/terminated
                await self.saga_processor.publish_message(
                    topic="production.command.update_internal_task_status",
                    message_payload=UpdateInternalTaskStatusCommand(
                        project_id=event.project_id,
                        deliverable_id=event.deliverable_id,
                        task_id=event.review_item_id, # Assuming this links to the main task
                        new_status="rejected_terminated" # Defined in TaskStatus Enum
                    )
                )
                
                # Also notify Project Orchestrator about the deliverable's rejection/failure
                from src.events.project_events import DeliverableFailedEvent as ProjectDeliverableFailedEvent
                await self.saga_processor.publish_message(
                    topic="project.deliverable.failed", # Define this topic
                    message_payload=ProjectDeliverableFailedEvent(
                        project_id=event.project_id,
                        deliverable_id=event.deliverable_id,
                        deliverable_name="Unknown Deliverable Name", # Needs to be fetched if possible
                        reason=f"Deliverable rejected by client: {event.comment_text or 'No reason provided'}"
                    )
                )


            await self.saga_processor.update_saga_state(
                session=session,
                saga_state=saga_state,
                new_state_enum=next_state_enum,
                event_id=event.event_id,
                # command_id=command.command_id # If a single command was sent
            )
            logger.info(f"Deliverable SAGA for {event.deliverable_id} transitioned to {next_state_enum.value} based on client feedback.")

    async def on_deliverable_delivered_final(self, event: DeliverableDeliveredEvent):
        """
        Handles the final DeliverableDeliveredEvent for this SAGA, marking its completion.
        This event is typically published by the Delivery Service.
        """
        logger.info(f"DeliverableSagaOrchestrator: Final Deliverable Delivered Event received for Deliverable ID: {event.deliverable_id}")
        
        async with self.db_session_factory() as session:
            saga_state = await self.saga_processor.get_or_create_saga_state(
                session=session,
                project_id=event.project_id,
                deliverable_id=event.deliverable_id,
                saga_type=SagaType.DELIVERABLE_PRODUCTION,
                initial_state=DeliverableSagaState.DELIVERED.value,
                saga_id=event.deliverable_id
            )

            if saga_state.last_event_processed_id == str(event.event_id):
                logger.warning(f"DeliverableSagaOrchestrator: Final DeliverableDeliveredEvent {event.event_id} already processed for Deliverable {event.deliverable_id}. Idempotent.")
                return
            
            await self.saga_processor.update_saga_state(
                session=session,
                saga_state=saga_state,
                new_state_enum=DeliverableSagaState.DELIVERED,
                event_id=event.event_id,
                new_saga_status=SagaStatus.COMPLETED # Mark this SAGA as COMPLETED
            )
            logger.info(f"Deliverable SAGA for {event.deliverable_id} is now COMPLETED.")


    # --- Generic Event Dispatcher (similar to Project Orchestrator) ---
    async def handle_event(self, event_data: Dict[str, Any]):
        """
        Generic event handler to dispatch incoming event data to specific methods.
        This will be called by the Deliverable Events Listener.
        """
        event_type = event_data.get("event_type")
        if not event_type:
            logger.error(f"Received event with no 'event_type' in DeliverableSagaOrchestrator: {event_data}")
            return
        
        # Mapping event_type strings to the actual dataclass types
        # You would import all necessary event dataclasses here or have a central registry
        # For simplicity, we import relevant modules.
        event_modules = {
            "project_events": "src.events.project_events",
            "deliverable_events": "src.events.deliverable_events",
            "task_events": "src.events.task_events",
            "client_feedback_events": "src.events.client_feedback_events",
            "project_commands": "src.commands.project_commands", # StartDeliverableSagaCommand is a command
            "deliverable_commands": "src.orchestrators.deliverable_saga_orchestrator.commands", # Specific orchestrator commands
            "production_commands": "src.commands.production_commands", # Specific production commands
        }
        
        event_cls = None
        for module_name, module_path in event_modules.items():
            try:
                module = __import__(module_path, fromlist=[event_type])
                event_cls = getattr(module, event_type, None)
                if event_cls:
                    break
            except (ImportError, AttributeError):
                continue

        if not event_cls:
            logger.warning(f"No specific event/command class found for event_type: {event_type} in DeliverableSagaOrchestrator. Processing as generic dict.")
            event_obj = event_data
        else:
            try:
                event_obj = event_cls(**event_data)
            except Exception as e:
                logger.error(f"Failed to deserialize event {event_type} in DeliverableSagaOrchestrator: {e}. Data: {event_data}", exc_info=True)
                return

        # Handle StartDeliverableSagaCommand explicitly as it's a command acting as an initiator
        if event_type == "StartDeliverableSagaCommand":
            handler = self.on_start_deliverable_saga
        else:
            handler = self.event_handlers.get(event_type)

        if handler:
            try:
                await handler(event_obj)
            except Exception as e:
                project_id = event_obj.project_id if hasattr(event_obj, 'project_id') else "N/A"
                deliverable_id = event_obj.deliverable_id if hasattr(event_obj, 'deliverable_id') else "N/A"
                logger.error(f"Error handling event {event_type} for Project {project_id}, Deliverable {deliverable_id}: {e}", exc_info=True)
                # In a production system, you might publish a DeliverableFailedEvent here
                # if the orchestrator fails to process its own event.
        else:
            logger.warning(f"No handler registered for event type: {event_type} in DeliverableSagaOrchestrator.")