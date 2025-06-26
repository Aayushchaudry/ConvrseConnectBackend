# Enhanced Project Lifecycle Orchestrator for Phase 4 Integration

import logging
from datetime import datetime
from typing import Any, Callable, Dict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.events.project_events import (
    DeliverableDeliveredEvent,
    ProjectCreatedEvent,
)
from src.events.task_events import (
    InternalTaskCompletedEvent,
    InternalTaskStatusUpdatedEvent,
)
from src.events.deliverable_events import RequirementUpdatedEvent
from src.models.deliverable import Deliverable

# Import Phase 2 Services for Auto-Generation
from src.services.requirement_service import RequirementService
from src.services.pricing_service import PricingService
from src.services.timeline_tracking_service import TimelineTrackingService
from src.services.task_management_service import TaskManagementService

logger = logging.getLogger(__name__)


class EnhancedProjectLifecycleOrchestrator:
    """Enhanced Project Lifecycle Orchestrator for Phase 4 Integration."""

    def __init__(self, db_session_factory: Callable[[], AsyncSession]):
        self.db_session_factory = db_session_factory
        
        # Initialize Phase 2 Services
        self.requirement_service = RequirementService()
        self.pricing_service = PricingService()
        self.timeline_service = TimelineTrackingService()
        self.task_management_service = TaskManagementService()

    async def on_project_created_enhanced(self, event: ProjectCreatedEvent):
        """Auto-generate requirements, timeline, and budget on project creation."""
        logger.info(f"Enhanced auto-generation for project {event.project_id}")
        
        async with self.db_session_factory() as session:
            try:
                # Get project deliverables
                deliverables_result = await session.execute(
                    select(Deliverable).filter(Deliverable.project_id == event.project_id)
                )
                deliverables = deliverables_result.scalars().all()
                
                # Auto-generate requirements for each deliverable
                for deliverable in deliverables:
                    await self.requirement_service.auto_generate_requirements(
                        session=session,
                        project_id=event.project_id,
                        deliverable_id=deliverable.id,
                        deliverable_type=deliverable.deliverable_type or "standard"
                    )
                
                # Auto-generate project-level requirements
                await self.requirement_service.auto_generate_requirements(
                    session=session,
                    project_id=event.project_id,
                    deliverable_id=None,
                    deliverable_type="project"
                )
                
                # Initialize project budget
                budget_result = await self.pricing_service.calculate_project_budget(
                    session=session,
                    project_id=event.project_id
                )
                
                # Create project milestones
                milestones = await self.timeline_service.create_project_milestones(
                    session=session,
                    project_id=event.project_id
                )
                
                logger.info(f"Auto-generation completed for project {event.project_id}")
                
            except Exception as e:
                logger.error(f"Error in enhanced project creation: {e}")

    async def on_task_completed_enhanced(self, event):
        """Enhanced task completion with timeline tracking."""
        async with self.db_session_factory() as session:
            try:
                await self.timeline_service.log_daily_progress(
                    session=session,
                    task_id=event.task_id,
                    progress_date=datetime.now().date(),
                    percentage_complete=100,
                    hours_spent=getattr(event, 'hours_spent', 0),
                    notes=f"Task completed via {type(event).__name__}",
                    created_by=getattr(event, 'user_id', None)
                )
                
                logger.info(f"Logged completion for task {event.task_id}")
                
            except Exception as e:
                logger.error(f"Error in task completion tracking: {e}")

    async def on_task_status_updated_enhanced(self, event: InternalTaskStatusUpdatedEvent):
        """Enhanced handler for task status updates with timeline integration."""
        if event.new_status.lower() in ['in-progress', 'in_progress']:
            async with self.db_session_factory() as session:
                try:
                    # Log task start progress
                    await self.timeline_service.log_daily_progress(
                        session=session,
                        task_id=event.task_id,
                        progress_date=datetime.now().date(),
                        percentage_complete=10,  # Initial progress when started
                        hours_spent=0,
                        notes=f"Task started - status updated to {event.new_status}",
                        created_by=getattr(event, 'user_id', None)
                    )
                    
                    logger.info(f"Logged start progress for task {event.task_id}")
                    
                except Exception as e:
                    logger.error(f"Error logging task start progress: {e}")

    async def on_requirement_updated_enhanced(self, event: RequirementUpdatedEvent):
        """Enhanced handler for requirement updates with budget recalculation."""
        if event.new_status.lower() in ['received', 'approved']:
            async with self.db_session_factory() as session:
                try:
                    # Recalculate project budget as requirements may affect scope
                    await self.pricing_service.recalculate_project_budget(
                        session=session,
                        project_id=event.project_id
                    )
                    
                    logger.info(f"Recalculated budget after requirement {event.requirement_id} update")
                    
                except Exception as e:
                    logger.error(f"Error recalculating budget after requirement update: {e}")

    async def on_deliverable_delivered_enhanced(self, event: DeliverableDeliveredEvent):
        """Enhanced handler for deliverable completion with budget and timeline updates."""
        async with self.db_session_factory() as session:
            try:
                # Update budget tracking
                await self.pricing_service.recalculate_project_budget(
                    session=session,
                    project_id=event.project_id
                )
                
                # Update timeline completion
                await self.timeline_service.calculate_project_completion(
                    session=session,
                    project_id=event.project_id
                )
                
                logger.info(f"Updated budget and timeline for completed deliverable {event.deliverable_id}")
                
            except Exception as e:
                logger.error(f"Error in enhanced deliverable completion: {e}")
 