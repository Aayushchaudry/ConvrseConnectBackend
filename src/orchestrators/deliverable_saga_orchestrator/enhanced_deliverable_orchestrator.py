# Enhanced Deliverable Saga Orchestrator for Phase 4 Integration

import logging
from datetime import datetime
from typing import Any, Callable, Dict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.events.deliverable_events import DeliverableInfoGatheredEvent
from src.events.task_events import InternalTaskCreatedEvent
from src.models.deliverable import Deliverable
from src.models.internal_task import InternalTask

# Import Phase 2 Services
from src.services.task_management_service import TaskManagementService
from src.services.pricing_service import PricingService

logger = logging.getLogger(__name__)


class EnhancedDeliverableSagaOrchestrator:
    """Enhanced Deliverable Saga Orchestrator for Phase 4 Integration."""

    def __init__(self, db_session_factory: Callable[[], AsyncSession]):
        self.db_session_factory = db_session_factory
        
        # Don't initialize services here since they require db_session
        # Services will be created in individual methods when needed

    async def on_deliverable_info_gathered_enhanced(self, event: DeliverableInfoGatheredEvent):
        """Enhanced deliverable info gathering with task sharing and pricing setup."""
        logger.info(f"Enhanced processing for deliverable {event.deliverable_id}")
        
        async with self.db_session_factory() as session:
            try:
                # Create services with session
                task_management_service = TaskManagementService(session)
                pricing_service = PricingService(session)
                
                # Check for existing similar tasks in the project that can be shared
                deliverable = await session.get(Deliverable, event.deliverable_id)
                if not deliverable:
                    return
                
                # Find existing tasks in the project that could be shared
                shared_tasks = await task_management_service.get_shared_tasks_for_project(
                    project_id=event.project_id
                )
                
                # If we have shared tasks, suggest sharing them with this deliverable
                if shared_tasks:
                    for task in shared_tasks:
                        # Check if this task type is relevant for the deliverable
                        if self._is_task_relevant_for_deliverable(task, deliverable):
                            await task_management_service.associate_task_with_deliverable(
                                task_id=task.id,
                                deliverable_id=event.deliverable_id,
                                estimated_hours=8  # Default estimation
                            )
                            logger.info(f"Shared task {task.id} with deliverable {event.deliverable_id}")
                
                # Set up default pricing for this deliverable if not exists
                try:
                    await pricing_service.create_deliverable_pricing(
                        project_id=event.project_id,
                        deliverable_id=event.deliverable_id,
                        base_price=1000.0,  # Default base price
                        markup_percentage=20.0,  # Default 20% markup
                        cost_breakdown={
                            "base_labor": 800.0,
                            "materials": 100.0,
                            "overhead": 100.0
                        }
                    )
                    logger.info(f"Created default pricing for deliverable {event.deliverable_id}")
                except Exception as e:
                    logger.debug(f"Pricing may already exist for deliverable {event.deliverable_id}: {e}")
                
                # Recalculate project budget with the new deliverable
                await pricing_service.recalculate_project_budget(
                    project_id=event.project_id
                )
                
                logger.info(f"Enhanced deliverable processing completed for {event.deliverable_id}")
                
            except Exception as e:
                logger.error(f"Error in enhanced deliverable processing: {e}")

    async def on_task_created_for_deliverable(self, event: InternalTaskCreatedEvent):
        """Handle new task creation with intelligent sharing suggestions."""
        async with self.db_session_factory() as session:
            try:
                # Create services with session
                task_management_service = TaskManagementService(session)
                
                # Find similar tasks in the project
                similar_tasks = await task_management_service.find_similar_tasks_in_project(
                    project_id=event.project_id,
                    task_title=event.task_title,
                    task_type=getattr(event, 'task_type', None),
                    exclude_task_id=event.task_id
                )
                
                if similar_tasks:
                    # Log suggestion for task sharing
                    sharing_suggestions = await task_management_service.suggest_task_sharing(
                        project_id=event.project_id,
                        new_task_title=event.task_title,
                        new_task_type=getattr(event, 'task_type', None)
                    )
                    
                    logger.info(f"Task sharing suggestions for {event.task_id}: {len(sharing_suggestions)} similar tasks found")
                
            except Exception as e:
                logger.error(f"Error in task creation processing: {e}")

    def _is_task_relevant_for_deliverable(self, task: InternalTask, deliverable: Deliverable) -> bool:
        """Determine if a task is relevant for a specific deliverable."""
        # Simple heuristic - can be enhanced with more sophisticated logic
        task_type = getattr(task, 'task_type', '').lower()
        deliverable_type = (deliverable.deliverable_type or '').lower()
        
        # Common tasks that apply to most deliverables
        common_tasks = ['planning', 'review', 'quality_check', 'documentation']
        if any(common in task_type for common in common_tasks):
            return True
            
        # Type-specific matching
        if 'model' in deliverable_type and 'model' in task_type:
            return True
        if 'render' in deliverable_type and 'render' in task_type:
            return True
        if 'texture' in deliverable_type and 'texture' in task_type:
            return True
            
        return False
