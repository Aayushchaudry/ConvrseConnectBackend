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

# --- PROJECT-LEVEL REQUIREMENTS (created once per project, shared across deliverables) ---
PROJECT_LEVEL_REQUIREMENTS = [
    ("Floor Plan Cad File", RequirementType.FILE_UPLOAD, True),
    ("Theme/Mood Board", RequirementType.FILE_UPLOAD, True),
    ("Material Detail", RequirementType.FILE_UPLOAD, False),
    ("Texture Detail", RequirementType.FILE_UPLOAD, False),
    ("Site Plan/ Master Plan CAD", RequirementType.FILE_UPLOAD, True),
    ("Elevation Detail CAD", RequirementType.FILE_UPLOAD, True),
    ("Section Detail CAD", RequirementType.FILE_UPLOAD, True),
    ("Landscape detail CAD", RequirementType.FILE_UPLOAD, False),
    ("Plant Detail CAD", RequirementType.FILE_UPLOAD, False),
    ("Club detail CAD", RequirementType.FILE_UPLOAD, False),
    ("Max/Sketchup file (If Possible)", RequirementType.FILE_UPLOAD, False),
    ("Ref. Image (if any)", RequirementType.FILE_UPLOAD, False),
    ("Furniture Detail", RequirementType.FILE_UPLOAD, False),
]

# --- DELIVERABLE-SPECIFIC REQUIREMENTS (created per deliverable type) ---
DELIVERABLE_REQUIREMENTS_MAP: Dict[DeliverableType, List[tuple]] = {
    DeliverableType.RENDERED_IMAGES: [
        # Project-level requirements removed, only deliverable-specific ones remain
    ],
    DeliverableType.TECHNICAL_RENDERS: [
        # Project-level requirements removed, only deliverable-specific ones remain
    ],
    DeliverableType.EXTERIOR_VR_TOUR: [
        # Project-level requirements removed, only deliverable-specific ones remain
    ],
    DeliverableType.ANIMATED_VR_TOUR: [
        # Project-level requirements removed, only deliverable-specific ones remain
    ],
    DeliverableType.VIDEO_WALKTHROUGH: [
        # Project-level requirements removed, only deliverable-specific ones remain
    ],
    DeliverableType.INVENTORY_MODULE: [
        ("Inventory Details", RequirementType.FILE_UPLOAD, True),  # Deliverable-specific
        ("Floor & Flat Plans", RequirementType.FILE_UPLOAD, True),
        ("Nomenclature", RequirementType.TEXT_INPUT, True),
        ("ERP integration confirmation", RequirementType.BOOLEAN_INPUT, True),
        ("ERP API details", RequirementType.JSON_INPUT, False),  # If ERP integration is Yes
        ("Inventory data format specified", RequirementType.TEXT_INPUT, False),  # If ERP is No
    ],
    DeliverableType.LOCATION_MAP: [
        ("Project Location", RequirementType.TEXT_INPUT, True),  # Deliverable-specific
        ("Key Location Highlights", RequirementType.JSON_INPUT, True),  # e.g., [{"name": "Mall", "type": "mall", "lat": X, "lon": Y}]
    ],
    DeliverableType.INTERACTIVE_SALES_APP: [
        ("Brochure", RequirementType.FILE_UPLOAD, True),  # Deliverable-specific
        ("Specifications in tabular format", RequirementType.FILE_UPLOAD, True),  # Assuming spreadsheet
        ("2D layouts of floor & flat", RequirementType.FILE_UPLOAD, True),
        ("3D isos of floor & flat", RequirementType.FILE_UPLOAD, True),
        ("Masterplan", RequirementType.FILE_UPLOAD, True),
        ("Landing page details", RequirementType.JSON_INPUT, True),  # For content
        ("Project & Company Logo", RequirementType.FILE_UPLOAD, True),
        ("Brand Guidelines", RequirementType.FILE_UPLOAD, False),
    ],
    DeliverableType.INTERACTIVE_DRONE_SHOOT: [
        ("Permission for Drone Shoot", RequirementType.BOOLEAN_INPUT, True),  # Deliverable-specific
        ("Specific Area to be covered", RequirementType.TEXT_INPUT, True),  # Or JSON for coords
        ("Landmarks to be highlighted", RequirementType.JSON_INPUT, True),  # For video markers
    ],
    DeliverableType.INTERPLAYER_SOFTWARE: [
        ("Scope Confirmation", RequirementType.BOOLEAN_INPUT, True),  # Deliverable-specific
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
        1. First create project-level requirements (once per project).
        2. Then create deliverable-specific requirements for each deliverable.
        3. Publish DeliverableInfoGatheredEvent (or Failed event).
        """
        logger.info(
            f"InformationGatheringService: Received StartInformationGatheringCommand for Project ID: {command.project_id}"
        )

        async with self.db_session_factory() as session:
            try:
                # 1. Fetch the project and relevant deliverables
                from sqlalchemy import select

                # Get the project
                project_result = await session.execute(
                    select(Project).filter(Project.id == command.project_id)
                )
                project = project_result.scalar_one_or_none()

                if not project:
                    logger.error(f"Project {command.project_id} not found.")
                    # Publish a failure event or handle error
                    return

                # Get deliverables for this project
                deliverables_result = await session.execute(
                    select(Deliverable).filter(
                        Deliverable.project_id == command.project_id,
                        Deliverable.id.in_(command.deliverable_ids),
                    )
                )
                deliverables = deliverables_result.scalars().all()

                if not deliverables:
                    logger.warning(
                        f"No deliverables found for project {command.project_id} with specified IDs: {command.deliverable_ids}"
                    )
                    return

                # 2. CREATE PROJECT-LEVEL REQUIREMENTS (once per project)
                logger.info(f"🔄 Creating project-level requirements for project {command.project_id}")
                project_requirements_created = 0
                
                for req_name, req_type_enum, is_mandatory in PROJECT_LEVEL_REQUIREMENTS:
                    # Check if project-level requirement already exists
                    existing_req = await session.execute(
                        select(Requirement).filter(
                            Requirement.project_id == command.project_id,
                            Requirement.requirement_name == req_name,
                            Requirement.is_project_level == True,
                            Requirement.deliverable_id.is_(None),  # Project-level requirements have no deliverable_id
                        )
                    )
                    if existing_req.scalar_one_or_none():
                        logger.debug(
                            f"Project-level requirement '{req_name}' already exists for project {command.project_id}. Skipping creation."
                        )
                        continue  # Skip if already exists

                    # Create project-level requirement
                    new_requirement = Requirement(
                        deliverable_id=None,  # Project-level requirement
                        project_id=project.id,
                        requirement_name=req_name,
                        requirement_type=req_type_enum,
                        status=RequirementStatus.PENDING,
                        is_mandatory=is_mandatory,
                        is_project_level=True,  # Mark as project-level
                    )
                    session.add(new_requirement)
                    project_requirements_created += 1
                    logger.info(
                        f"✅ Created project-level requirement: '{req_name}' for project {command.project_id}"
                    )

                # Commit project-level requirements
                if project_requirements_created > 0:
                    await session.commit()
                    logger.info(
                        f"✅ Created {project_requirements_created} project-level requirements for project {command.project_id}"
                    )

                # 3. CREATE DELIVERABLE-SPECIFIC REQUIREMENTS
                logger.info(f"🔄 Creating deliverable-specific requirements for {len(deliverables)} deliverables")
                
                for deliverable in deliverables:
                    deliverable_type_enum = DeliverableType(deliverable.deliverable_type)
                    logger.info(
                        f"Processing deliverable {deliverable.id} of type {deliverable_type_enum.value}"
                    )

                    # Get deliverable-specific requirements for this type
                    required_items = DELIVERABLE_REQUIREMENTS_MAP.get(deliverable_type_enum, [])

                    if not required_items:
                        logger.info(
                            f"No deliverable-specific requirements defined for {deliverable_type_enum.value}. Skipping."
                        )
                        continue

                    try:
                        deliverable_requirements_created = 0
                        for req_name, req_type_enum, is_mandatory in required_items:
                            # Check if deliverable-specific requirement already exists
                            existing_req = await session.execute(
                                select(Requirement).filter(
                                    Requirement.deliverable_id == deliverable.id,
                                    Requirement.requirement_name == req_name,
                                    Requirement.is_project_level == False,
                                )
                            )
                            if existing_req.scalar_one_or_none():
                                logger.debug(
                                    f"Deliverable-specific requirement '{req_name}' already exists for deliverable {deliverable.id}. Skipping creation."
                                )
                                continue  # Skip if already exists

                            # Create deliverable-specific requirement
                            new_requirement = Requirement(
                                deliverable_id=deliverable.id,
                                project_id=project.id,
                                requirement_name=req_name,
                                requirement_type=req_type_enum,
                                status=RequirementStatus.PENDING,
                                is_mandatory=is_mandatory,
                                is_project_level=False,  # Mark as deliverable-specific
                            )
                            session.add(new_requirement)
                            deliverable_requirements_created += 1
                            logger.info(
                                f"✅ Created deliverable-specific requirement: '{req_name}' for deliverable {deliverable.id}"
                            )

                        # Commit deliverable-specific requirements for this deliverable
                        if deliverable_requirements_created > 0:
                            await session.commit()
                            logger.info(
                                f"✅ Created {deliverable_requirements_created} deliverable-specific requirements for deliverable {deliverable.id}"
                            )

                    except Exception as e:
                        logger.error(
                            f"Error creating requirements for deliverable {deliverable.id}: {e}"
                        )
                        await session.rollback()

                # 4. Publish success event (simplified for this example)
                # In a real implementation, you'd publish a specific event for each deliverable or project
                logger.info(
                    f"✅ InformationGatheringService: Successfully completed requirements creation for Project {command.project_id}"
                )

                # Publish DeliverableInfoGatheredEvent for each deliverable
                for deliverable in deliverables:
                    await self.event_bus.publish(
                        topic="deliverable.info_gathered",
                        message=DeliverableInfoGatheredEvent(
                            project_id=command.project_id,
                            deliverable_id=deliverable.id
                        ).__dict__,
                    )
                    logger.info(f"✅ Published DeliverableInfoGatheredEvent for deliverable {deliverable.id}")

            except Exception as e:
                logger.error(
                    f"InformationGatheringService: Error handling StartInformationGatheringCommand for Project {command.project_id}: {e}",
                    exc_info=True,
                )
                await session.rollback()
                # Publish a failure event here if needed
