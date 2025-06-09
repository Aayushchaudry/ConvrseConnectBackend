# src/api/debug_controller.py

import logging
from typing import List
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.commands.project_commands import StartInformationGatheringCommand
from src.config.database import get_db_session
from src.config.event_bus import get_event_bus
from src.events.client_feedback_events import ClientFeedbackSubmittedEvent
from src.events.event_bus_interface import EventBus
from src.models.client_feedback import ClientFeedback, FeedbackType
from src.models.review_item import ReviewItem, ReviewStatus
from src.orchestrators.deliverable_saga_orchestrator.deliverable_saga_orchestrator import (
    DeliverableSagaOrchestrator,
)
from src.services.deliverable_service import DeliverableService
from src.services.info_gathering_service import InformationGatheringService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Debug"])


# Pydantic schemas for debug endpoints
class TriggerInfoGatheringRequest(BaseModel):
    project_id: UUID
    deliverable_ids: List[UUID]


class SubmitClientFeedbackRequest(BaseModel):
    review_item_id: UUID
    project_id: UUID
    deliverable_id: UUID
    feedback_type: str
    comment_text: str


@router.post("/debug/trigger-info-gathering/")
async def trigger_info_gathering_debug(
    request: TriggerInfoGatheringRequest,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
):
    """Debug endpoint to trigger information gathering for testing purposes"""
    try:
        logger.info(
            f"🔧 DEBUG: Triggering info gathering for project {request.project_id}"
        )

        # Create the service and command
        info_gathering_service = InformationGatheringService(db_session, event_bus)
        command = StartInformationGatheringCommand(
            project_id=request.project_id, deliverable_ids=request.deliverable_ids
        )

        # Execute the command directly
        await info_gathering_service.handle_start_information_gathering_command(command)

        logger.info(f"🔧 DEBUG: Info gathering completed successfully")

        return {
            "status": "success",
            "message": "Information gathering triggered successfully",
            "project_id": str(request.project_id),
            "deliverable_ids": [str(d_id) for d_id in request.deliverable_ids],
        }

    except Exception as e:
        logger.error(f"🔧 DEBUG: Info gathering failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/debug/submit-client-feedback/")
async def submit_client_feedback_debug(
    request: SubmitClientFeedbackRequest,
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
):
    """Debug endpoint to submit client feedback and trigger SAGA flow"""
    try:
        logger.info(
            f"🔧 DEBUG: Submitting client feedback for review item {request.review_item_id}"
        )

        # Create client feedback record
        feedback = ClientFeedback(
            id=str(uuid4()),
            review_item_id=request.review_item_id,
            project_id=request.project_id,
            deliverable_id=request.deliverable_id,
            feedback_type=(
                FeedbackType.ACCEPT
                if request.feedback_type == "ACCEPT"
                else FeedbackType.REJECT
            ),
            comment_text=request.comment_text,
        )

        db_session.add(feedback)
        await db_session.commit()

        # Create the feedback event
        feedback_event = ClientFeedbackSubmittedEvent(
            project_id=request.project_id,
            deliverable_id=request.deliverable_id,
            review_item_id=request.review_item_id,
            client_user_id=None,
            feedback_type=request.feedback_type,
            comment_text=request.comment_text,
        )

        # Trigger the deliverable SAGA orchestrator directly
        deliverable_orchestrator = DeliverableSagaOrchestrator(db_session, event_bus)
        await deliverable_orchestrator.on_client_feedback_submitted(feedback_event)

        logger.info(f"🔧 DEBUG: Client feedback processed successfully")

        return {
            "status": "success",
            "message": "Client feedback submitted and SAGA triggered successfully",
            "feedback_id": feedback.id,
            "feedback_type": request.feedback_type,
        }

    except Exception as e:
        logger.error(f"🔧 DEBUG: Client feedback submission failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/debug/test-event-bus")
async def test_event_bus_endpoint(
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
):
    """Test endpoint to verify event bus functionality"""
    try:
        logger.info(f"🔧 DEBUG: Event bus type: {type(event_bus)}")
        logger.info(f"🔧 DEBUG: Event bus instance: {event_bus}")

        # Create test command
        test_project_id = uuid4()
        test_deliverable_id = uuid4()

        command = StartInformationGatheringCommand(
            project_id=test_project_id, deliverable_ids=[test_deliverable_id]
        )

        logger.info(f"🔧 DEBUG: Publishing command: {command.__dict__}")

        await event_bus.publish(
            topic="project.command.start_info_gathering", message=command.__dict__
        )

        logger.info("🔧 DEBUG: Command published successfully!")

        return {
            "status": "success",
            "message": "Event published successfully",
            "project_id": str(test_project_id),
            "deliverable_id": str(test_deliverable_id),
            "event_bus_type": str(type(event_bus)),
        }

    except Exception as e:
        logger.error(f"🔧 DEBUG: Event bus test failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "event_bus_type": (
                str(type(event_bus)) if "event_bus" in locals() else "unknown"
            ),
        }


@router.post("/debug/test-deliverable-service-event-bus")
async def test_deliverable_service_event_bus(
    db_session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
):
    """Test the DeliverableService event bus specifically"""
    try:
        logger.info(f"🔧 DELIVERABLE DEBUG: Creating DeliverableService")

        # Create deliverable service (same as in deliverable controller)
        deliverable_service = DeliverableService(
            db_session=db_session, event_bus=event_bus
        )

        logger.info(
            f"🔧 DELIVERABLE DEBUG: Service created with event_bus: {type(deliverable_service.event_bus)}"
        )

        # Test publishing directly from service
        test_project_id = uuid4()
        test_deliverable_id = uuid4()

        command = StartInformationGatheringCommand(
            project_id=test_project_id, deliverable_ids=[test_deliverable_id]
        )

        logger.info(f"🔧 DELIVERABLE DEBUG: Publishing via service event bus")

        await deliverable_service.event_bus.publish(
            topic="project.command.start_info_gathering", message=command.__dict__
        )

        logger.info(f"🔧 DELIVERABLE DEBUG: Published successfully!")

        return {
            "status": "success",
            "message": "DeliverableService event bus test successful",
            "project_id": str(test_project_id),
            "deliverable_id": str(test_deliverable_id),
            "service_event_bus_type": str(type(deliverable_service.event_bus)),
        }

    except Exception as e:
        logger.error(f"🔧 DELIVERABLE DEBUG: Failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
