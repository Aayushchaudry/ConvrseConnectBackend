# src/services/deliverable_service.py

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.deliverable import Deliverable, DeliverableType, DeliverableStatus # Import Deliverable model and its Enums
from src.models.project import Project # Import Project model for validation/relationship
from src.config.database import AsyncSessionLocal # For session factory
from src.events.event_bus_interface import EventBus # For future event publishing
from uuid import UUID
from typing import Optional, List

logger = logging.getLogger(__name__)

class DeliverableService:
    """
    Service layer for handling deliverable-related business logic.
    Responsible for creating and managing deliverable entities.
    """
    def __init__(self, db_session: AsyncSession, event_bus: EventBus):
        """
        Initializes the DeliverableService.
        Args:
            db_session: An asynchronous SQLAlchemy database session.
            event_bus: An instance of the EventBus interface (for future publishing).
        """
        self.db_session = db_session
        self.event_bus = event_bus

    async def create_deliverable(
        self,
        project_id: UUID,
        deliverable_type: DeliverableType,
        deliverable_sub_type: Optional[str] = None,
        tentative_timeline_days: Optional[int] = None
    ) -> Deliverable:
        """
        Creates a new deliverable in the database.
        
        Args:
            project_id: The ID of the project this deliverable belongs to.
            deliverable_type: The type of deliverable (from DeliverableType enum).
            deliverable_sub_type: Optional sub-type (e.g., 'Interior').
            tentative_timeline_days: Optional suggested timeline.
            
        Returns:
            Deliverable: The newly created Deliverable ORM object.
        Raises:
            ValueError: If the project_id does not exist.
        """
        # 1. Basic validation: Ensure project exists
        from sqlalchemy import select
        project = await self.db_session.execute(
            select(Project).filter(Project.id == project_id)
        )
        project = project.scalar_one_or_none()
        if not project:
            raise ValueError(f"Project with ID {project_id} not found.")

        # 2. Create the Deliverable ORM object
        new_deliverable = Deliverable(
            project_id=project_id,
            deliverable_type=deliverable_type,
            deliverable_sub_type=deliverable_sub_type,
            tentative_timeline_days=tentative_timeline_days,
            current_status=DeliverableStatus.INFO_GATHERING # Initial status for new deliverables
        )
        
        # 3. Add to session and commit to database
        self.db_session.add(new_deliverable)
        await self.db_session.commit() # Commit changes to DB
        await self.db_session.refresh(new_deliverable) # Refresh to get ID and other auto-generated fields

        logger.info(f"Deliverable created: ID={new_deliverable.id}, Type={new_deliverable.deliverable_type.value}, Project={new_deliverable.project_id}")

        # In a SAGA, events like DeliverableCreatedEvent might be published here
        # IF there's a listener directly interested in individual deliverable creations.
        # However, our SAGA initiates Deliverable Sagas from a COMMAND
        # (StartDeliverableSagaCommand) which is sent by Project Orchestrator.
        # So, no direct event publishing from this service for SAGA initiation here.
        
        return new_deliverable

    async def get_deliverable_by_id(self, deliverable_id: UUID) -> Optional[Deliverable]:
        """Fetches a deliverable by its ID."""
        from sqlalchemy import select
        result = await self.db_session.execute(
            select(Deliverable).filter(Deliverable.id == deliverable_id)
        )
        return result.scalar_one_or_none()

    async def get_deliverables_for_project(self, project_id: UUID) -> List[Deliverable]:
        """Fetches all deliverables for a given project ID."""
        from sqlalchemy import select
        result = await self.db_session.execute(
            select(Deliverable).filter(Deliverable.project_id == project_id)
        )
        return result.scalars().all()

    # You can add other deliverable-related methods here (e.g., update_deliverable_status)