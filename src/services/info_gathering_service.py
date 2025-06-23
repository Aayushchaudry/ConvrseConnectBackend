# src/services/info_gathering_service.py

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.commands.project_commands import (
    StartInformationGatheringCommand,
)  # Command to consume
from src.config.database import (
    AsyncSessionLocal,
)  # For getting session if needed by handlers
from src.events.deliverable_events import (  # Events to publish
    DeliverableInfoGatheredEvent,
    DeliverableInfoGatheringFailedEvent,
)
from src.events.event_bus_interface import EventBus
from src.models.deliverable import (  # Import DeliverableType for mapping requirements
    Deliverable,
    DeliverableType,
)
from src.models.project import Project
from src.models.requirement import Requirement, RequirementStatus, RequirementType

logger = logging.getLogger(__name__)

# --- Helper: Map DeliverableType to its specific requirements from the agreement ---
# This dictionary directly reflects the "Development Requirements for Deliverables" section
# from your project agreement document.
# Each key is a DeliverableType, and its value is a list of tuples: (requirement_name, requirement_type_enum, is_mandatory)
# You might need to refine this based on the exact format of your agreement's table.
DELIVERABLE_REQUIREMENTS_MAP: Dict[DeliverableType, List[tuple]] = {
    DeliverableType.RENDERED_IMAGES: [
        ("Floor Plan Cad File", RequirementType.FILE_UPLOAD, True),
        ("Theme/Mood Board", RequirementType.FILE_UPLOAD, True),
        (
            "Material Detail",
            RequirementType.FILE_UPLOAD,
            False,
        ),  # Can be file or text, assuming file for now
        ("Texture Detail", RequirementType.FILE_UPLOAD, False),
        ("Furniture Detail", RequirementType.FILE_UPLOAD, False),
        ("Max/Sketchup file (If Possible)", RequirementType.FILE_UPLOAD, False),
        ("Club detail CAD", RequirementType.FILE_UPLOAD, False),
        # Exterior Requirement: (Requires sub-type handling or separate deliverable_type)
        # For simplicity, if RENDERED_IMAGES covers both interior/exterior, you'd add based on sub_type
    ],
    DeliverableType.TECHNICAL_RENDERS: [
        ("Floor Plan Cad File", RequirementType.FILE_UPLOAD, True),
        ("Theme/Mood Board", RequirementType.FILE_UPLOAD, True),
        ("Material Detail", RequirementType.FILE_UPLOAD, False),
        ("Texture Detail", RequirementType.FILE_UPLOAD, False),
        ("Furniture Detail", RequirementType.FILE_UPLOAD, False),
        ("Max/Sketchup file (If Possible)", RequirementType.FILE_UPLOAD, False),
    ],
    DeliverableType.EXTERIOR_VR_TOUR: [
        ("Site Plan/ Master Plan CAD", RequirementType.FILE_UPLOAD, True),
        ("Elevation Detail CAD", RequirementType.FILE_UPLOAD, True),
        ("Section Detail CAD", RequirementType.FILE_UPLOAD, True),
        ("Landscape detail CAD", RequirementType.FILE_UPLOAD, False),
        ("Plant Detail CAD", RequirementType.FILE_UPLOAD, False),
        ("Material Detail", RequirementType.FILE_UPLOAD, False),
        ("Texture Detail", RequirementType.FILE_UPLOAD, False),
        ("Club Details (CAD)", RequirementType.FILE_UPLOAD, False),
        ("Ref. Image (if any)", RequirementType.FILE_UPLOAD, False),
        ("Max/Sketchup file (If Possible)", RequirementType.FILE_UPLOAD, False),
    ],
    DeliverableType.ANIMATED_VR_TOUR: [
        ("Site Plan/ Master Plan CAD", RequirementType.FILE_UPLOAD, True),
        ("Elevation Detail CAD", RequirementType.FILE_UPLOAD, True),
        ("Section Detail CAD", RequirementType.FILE_UPLOAD, True),
        ("Landscape detail CAD", RequirementType.FILE_UPLOAD, False),
        ("Plant Detail CAD", RequirementType.FILE_UPLOAD, False),
        ("Material Detail", RequirementType.FILE_UPLOAD, False),
        ("Texture Detail", RequirementType.FILE_UPLOAD, False),
        ("Ref. Image (if any)", RequirementType.FILE_UPLOAD, False),
        ("Max/Sketchup file (If Possible)", RequirementType.FILE_UPLOAD, False),
    ],
    DeliverableType.VIDEO_WALKTHROUGH: [
        (
            "Floor Plan Cad File",
            RequirementType.FILE_UPLOAD,
            True,
        ),  # Assuming Interior focus for base
        ("Theme/Mood Board", RequirementType.FILE_UPLOAD, True),
        ("Material Detail", RequirementType.FILE_UPLOAD, False),
        ("Texture Detail", RequirementType.FILE_UPLOAD, False),
        ("Furniture Detail", RequirementType.FILE_UPLOAD, False),
        ("Max/Sketchup file (If Possible)", RequirementType.FILE_UPLOAD, False),
        ("Club detail CAD", RequirementType.FILE_UPLOAD, False),
        # Exterior requirements would also be here if one DeliverableType covers both
    ],
    DeliverableType.INVENTORY_MODULE: [
        (
            "Inventory Details",
            RequirementType.FILE_UPLOAD,
            True,
        ),  # Assuming a data file like CSV
        ("Floor & Flat Plans", RequirementType.FILE_UPLOAD, True),
        ("Nomenclature", RequirementType.TEXT_INPUT, True),
        ("ERP integration confirmation", RequirementType.BOOLEAN_INPUT, True),
        (
            "ERP API details",
            RequirementType.JSON_INPUT,
            False,
        ),  # If ERP integration is Yes
        (
            "Inventory data format specified",
            RequirementType.TEXT_INPUT,
            False,
        ),  # If ERP is No
    ],
    DeliverableType.LOCATION_MAP: [
        (
            "Project Location",
            RequirementType.TEXT_INPUT,
            True,
        ),  # Or specific Lat/Long input
        (
            "Key Location Highlights",
            RequirementType.JSON_INPUT,
            True,
        ),  # e.g., [{"name": "Mall", "type": "mall", "lat": X, "lon": Y}]
    ],
    DeliverableType.INTERACTIVE_SALES_APP: [
        ("Brochure", RequirementType.FILE_UPLOAD, True),
        (
            "Specifications in tabular format",
            RequirementType.FILE_UPLOAD,
            True,
        ),  # Assuming spreadsheet
        ("2D layouts of floor & flat", RequirementType.FILE_UPLOAD, True),
        ("3D isos of floor & flat", RequirementType.FILE_UPLOAD, True),
        ("Masterplan", RequirementType.FILE_UPLOAD, True),
        ("Landing page details", RequirementType.JSON_INPUT, True),  # For content
        ("Project & Company Logo", RequirementType.FILE_UPLOAD, True),
        ("Brand Guidelines", RequirementType.FILE_UPLOAD, False),
    ],
    DeliverableType.INTERACTIVE_DRONE_SHOOT: [
        ("Permission for Drone Shoot", RequirementType.BOOLEAN_INPUT, True),
        (
            "Specific Area to be covered",
            RequirementType.TEXT_INPUT,
            True,
        ),  # Or JSON for coords
        (
            "Landmarks to be highlighted",
            RequirementType.JSON_INPUT,
            True,
        ),  # For video markers
    ],
    DeliverableType.INTERPLAYER_SOFTWARE: [
        # No specific requirements listed in agreement's "Development Requirements"
        (
            "Scope Confirmation",
            RequirementType.BOOLEAN_INPUT,
            True,
        ),  # Simple confirmation
    ],
}


class InformationGatheringService:
    """
    Service responsible for managing the information gathering phase for deliverables.
    It creates initial requirements based on the deliverable type.
    """

    def __init__(
        self, db_session_factory: Callable[[], AsyncSession], event_bus: EventBus
    ):
        self.db_session_factory = db_session_factory
        self.event_bus = event_bus

    async def handle_start_information_gathering_command(
        self, command: StartInformationGatheringCommand
    ):
        """
        Handles the StartInformationGatheringCommand.
        This method will:
        1. Fetch the project and relevant deliverables.
        2. Create initial Requirement entries for each deliverable based on its type.
        3. Publish DeliverableInfoGatheredEvent (or Failed event).
        """
        logger.info(
            f"InformationGatheringService: Received StartInformationGatheringCommand for Project ID: {command.project_id}"
        )

        try:
            async with self.db_session_factory() as session:
                # Fetch the project (optional, but good for context/validation)
                from sqlalchemy import select

                project = await session.execute(
                    select(Project).filter(Project.id == command.project_id)
                )
                project = project.scalar_one_or_none()
                if not project:
                    logger.error(
                        f"InformationGatheringService: Project {command.project_id} not found for command. Skipping."
                    )
                    # Publish a failure event if necessary, but this indicates a larger issue.
                    return

                logger.info(
                    f"InformationGatheringService: Found project {project.name} for ID {command.project_id}"
                )

                # Fetch deliverables if specific deliverable_ids are provided
                # If command.deliverable_ids is empty, assume all project deliverables
                deliverables_to_process = []
                if command.deliverable_ids:
                    logger.info(
                        f"InformationGatheringService: Processing specific deliverable IDs: {command.deliverable_ids}"
                    )
                    deliverables_results = await session.execute(
                        select(Deliverable).filter(
                            Deliverable.project_id == command.project_id,
                            Deliverable.id.in_(command.deliverable_ids),
                        )
                    )
                    deliverables_to_process = deliverables_results.scalars().all()
                else:
                    # If command didn't specify deliverable_ids, fetch all for the project
                    # This assumes your Project model has a 'deliverables' relationship backref
                    logger.info(
                        f"InformationGatheringService: Processing all deliverables for project {command.project_id}"
                    )
                    deliverables_results = await session.execute(
                        select(Deliverable).filter(
                            Deliverable.project_id == command.project_id
                        )
                    )
                    deliverables_to_process = deliverables_results.scalars().all()

                logger.info(
                    f"InformationGatheringService: Found {len(deliverables_to_process)} deliverables to process"
                )

                if not deliverables_to_process:
                    logger.warning(
                        f"InformationGatheringService: No deliverables found for project {command.project_id} to process. Command finished."
                    )
                    return

                for deliverable in deliverables_to_process:
                    # Handle both string and enum deliverable_type
                    deliverable_type_str = (
                        deliverable.deliverable_type.value 
                        if hasattr(deliverable.deliverable_type, 'value') 
                        else str(deliverable.deliverable_type)
                    )
                    
                    logger.info(
                        f"InformationGatheringService: Processing deliverable {deliverable.id} ({deliverable_type_str}) for requirements."
                    )

                    # Retrieve requirements from the map
                    # Handle both enum and string keys
                    deliverable_type_key = deliverable.deliverable_type
                    if isinstance(deliverable_type_key, str):
                        # Convert string to enum for map lookup
                        try:
                            deliverable_type_key = DeliverableType(deliverable_type_key)
                        except ValueError:
                            logger.error(f"Invalid deliverable type: {deliverable_type_key}")
                            continue
                    
                    required_items = DELIVERABLE_REQUIREMENTS_MAP.get(deliverable_type_key)

                    if not required_items:
                        logger.warning(
                            f"No predefined requirements found for deliverable type: {deliverable_type_str}. Skipping requirement creation."
                        )
                        # Publish an event indicating requirements were skipped for this deliverable type
                        await self.event_bus.publish(
                            topic="deliverable.info_gathering.failed",  # Or specific warning topic
                            message=DeliverableInfoGatheringFailedEvent(
                                project_id=project.id,
                                deliverable_id=deliverable.id,
                                reason=f"No predefined requirements for type {deliverable_type_str}",
                                error_details={"type": "NO_PREDEFINED_REQUIREMENTS"},
                            ).__dict__,
                        )
                        continue

                    try:
                        for req_name, req_type_enum, is_mandatory in required_items:
                            # Check if requirement already exists to ensure idempotency if command is re-sent
                            existing_req = await session.execute(
                                select(Requirement).filter(
                                    Requirement.deliverable_id == deliverable.id,
                                    Requirement.requirement_name == req_name,
                                )
                            )
                            if existing_req.scalar_one_or_none():
                                logger.debug(
                                    f"Requirement '{req_name}' already exists for deliverable {deliverable.id}. Skipping creation."
                                )
                                continue  # Skip if already exists

                            new_requirement = Requirement(
                                deliverable_id=deliverable.id,
                                project_id=project.id,
                                requirement_name=req_name,
                                requirement_type=req_type_enum,
                                status=RequirementStatus.PENDING,
                                is_mandatory=is_mandatory,
                            )
                            session.add(new_requirement)
                            logger.info(
                                f"Created requirement: '{req_name}' for Deliverable {deliverable.id}"
                            )

                        await session.commit()  # Commit all new requirements for this deliverable
                        logger.info(
                            f"InformationGatheringService: Successfully created requirements for Deliverable {deliverable.id}."
                        )

                        # Publish event indicating info gathering is complete for this deliverable
                        try:
                            event = DeliverableInfoGatheredEvent(
                                project_id=project.id, deliverable_id=deliverable.id
                            )

                            # Create message dictionary manually to ensure proper serialization
                            message_dict = {
                                "event_id": str(event.event_id),
                                "timestamp": event.timestamp.isoformat(),
                                "event_type": event.event_type,
                                "project_id": str(event.project_id),
                                "deliverable_id": str(event.deliverable_id),
                            }

                            logger.info(
                                f"About to publish DeliverableInfoGatheredEvent for deliverable {deliverable.id}"
                            )
                            logger.debug(f"Event message: {message_dict}")

                            await self.event_bus.publish(
                                topic="deliverable.info_gathered", message=message_dict
                            )

                            logger.info(
                                f"✅ Successfully published DeliverableInfoGatheredEvent for deliverable {deliverable.id}"
                            )

                        except Exception as event_error:
                            logger.error(
                                f"❌ FAILED to publish DeliverableInfoGatheredEvent for deliverable {deliverable.id}: {event_error}",
                                exc_info=True,
                            )

                    except Exception as e:
                        logger.error(
                            f"Error creating requirements for Deliverable {deliverable.id}: {e}",
                            exc_info=True,
                        )
                        # Publish a failure event if a deliverable's requirements setup fails
                        await self.event_bus.publish(
                            topic="deliverable.info_gathering.failed",  # Define this topic
                            message=DeliverableInfoGatheringFailedEvent(
                                project_id=project.id,
                                deliverable_id=deliverable.id,
                                reason=f"Failed to create requirements: {str(e)}",
                                error_details={
                                    "deliverable_type": deliverable_type_str
                                },
                            ).__dict__,
                        )
                        await session.rollback()  # Rollback changes for this deliverable if an error occurs

                logger.info(
                    f"InformationGatheringService: Finished processing StartInformationGatheringCommand for Project {command.project_id}."
                )
        except Exception as e:
            logger.error(
                f"Error handling StartInformationGatheringCommand: {e}", exc_info=True
            )
            # Publish a failure event if an error occurs during command processing
            await self.event_bus.publish(
                topic="deliverable.info_gathering.failed",  # Define this topic
                message=DeliverableInfoGatheringFailedEvent(
                    project_id=command.project_id,
                    deliverable_id=None,
                    reason=f"Failed to handle command: {str(e)}",
                    error_details={"command_type": command.__class__.__name__},
                ).__dict__,
            )
