# src/services/project_service.py (UPDATED)

import logging
from sqlalchemy.ext.asyncio import AsyncSession
# Import Project model and its status Enum
from src.models.project import Project, ProjectStatus
# Import the event to be published
from src.events.project_events import ProjectCreatedEvent
# Import the EventBus interface
from src.events.event_bus_interface import EventBus
from uuid import UUID
from datetime import datetime # Added for date parsing in create_new_project
from typing import Optional, List, Dict, Any # <--- ADD THIS LINE FOR OPTIONAL, LIST, DICT, ANY

logger = logging.getLogger(__name__)

class ProjectService:
    """
    Service layer for handling project-related business logic.
    Responsible for creating projects and publishing related events.
    """
    def __init__(self, db_session: AsyncSession, event_bus: EventBus):
        self.db_session = db_session
        self.event_bus = event_bus

    async def create_new_project(self, name: str, budget: float, start_date: str, end_date: str) -> Project:
        """
        Creates a new project in the database and publishes a ProjectCreatedEvent.
        
        Args:
            name (str): The name of the project.
            budget (float): The budget for the project.
            start_date (str): The project's start date (as string, will be parsed).
            end_date (str): The project's end date (as string, will be parsed).
            
        Returns:
            Project: The newly created Project ORM object.
        """
        # For simplicity, parsing dates here. In a real app,
        # you might do this in a Pydantic schema or a dedicated helper.
        try:
            parsed_start_date = datetime.fromisoformat(start_date) if start_date else None
            parsed_end_date = datetime.fromisoformat(end_date) if end_date else None
        except ValueError as e:
            raise ValueError(f"Invalid date format for start_date or end_date: {e}")

        new_project = Project(
            name=name,
            budget=budget,
            start_date=parsed_start_date,
            end_date=parsed_end_date,
            status=ProjectStatus.INITIATED
        )
        
        self.db_session.add(new_project)
        await self.db_session.commit()
        await self.db_session.refresh(new_project)

        # Create and publish the ProjectCreatedEvent for SAGA orchestration
        event = ProjectCreatedEvent(
            project_id=new_project.id,
            project_name=new_project.name,
            initial_status=new_project.status.value
        )
        
        try:
            await self.event_bus.publish(topic="project.created", message=event.__dict__)
            logger.info(f"ProjectCreatedEvent published to topic 'project.created' for project {new_project.id} ({new_project.name})")
        except Exception as e:
            logger.error(f"Failed to publish ProjectCreatedEvent for project {new_project.id}: {e}")
            # Note: In production, you might want to implement retry logic or compensation here
            raise

        return new_project

    async def get_project_by_id(self, project_id: UUID) -> Optional[Project]:
        """Fetches a project by its ID."""
        from sqlalchemy import select
        result = await self.db_session.execute(
            select(Project).filter(Project.id == project_id)
        )
        return result.scalar_one_or_none()