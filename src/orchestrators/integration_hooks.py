# src/orchestrators/integration_hooks.py

import logging
from typing import Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.events.event_bus_interface import EventBus
from src.events.project_events import ProjectCreatedEvent, DeliverableDeliveredEvent
from src.events.deliverable_events import DeliverableInfoGatheredEvent
from src.events.task_events import (
    InternalTaskCreatedEvent,
    InternalTaskCompletedEvent,
    InternalTaskStatusUpdatedEvent,
)
from src.events.deliverable_events import RequirementUpdatedEvent

from src.orchestrators.project_lifecycle_orchestrator.enhanced_project_orchestrator import (
    EnhancedProjectLifecycleOrchestrator
)
from src.orchestrators.deliverable_saga_orchestrator.enhanced_deliverable_orchestrator import (
    EnhancedDeliverableSagaOrchestrator
)

logger = logging.getLogger(__name__)


class Phase4IntegrationHooks:
    """
    Integration hooks that connect Phase 2 services with existing orchestrators
    for auto-generation and enhanced workflow automation.
    """

    def __init__(
        self,
        db_session_factory: Callable[[], AsyncSession],
        event_bus: EventBus
    ):
        """Initialize the integration hooks with enhanced orchestrators."""
        self.db_session_factory = db_session_factory
        self.event_bus = event_bus
        
        # Initialize enhanced orchestrators
        self.enhanced_project_orchestrator = EnhancedProjectLifecycleOrchestrator(
            db_session_factory=db_session_factory,
            event_bus=event_bus
        )
        self.enhanced_deliverable_orchestrator = EnhancedDeliverableSagaOrchestrator(
            db_session_factory=db_session_factory
        )

        # Register event handlers
        self._register_event_handlers()

    def _register_event_handlers(self):
        """Register enhanced event handlers with the event bus."""
        
        # Project lifecycle events
        self.event_bus.subscribe(
            "project.created",
            self._handle_project_created
        )
        
        # Deliverable events
        self.event_bus.subscribe(
            "deliverable.info_gathered",
            self._handle_deliverable_info_gathered
        )
        
        self.event_bus.subscribe(
            "deliverable.delivered",
            self._handle_deliverable_delivered
        )
        
        # Task events - Fixed topic names to match actual publishing
        self.event_bus.subscribe(
            "internal_task.created",
            self._handle_task_created
        )
        
        self.event_bus.subscribe(
            "internal_task.completed",
            self._handle_task_completed
        )
        
        self.event_bus.subscribe(
            "internal_task.status_updated",
            self._handle_task_status_updated
        )
        
        # Requirement events
        self.event_bus.subscribe(
            "requirement.updated",
            self._handle_requirement_updated
        )

    async def _handle_project_created(self, event: ProjectCreatedEvent):
        """Handle project creation with enhanced auto-generation."""
        logger.info(f"Phase4Integration: Handling project creation for {event.project_id}")
        
        try:
            await self.enhanced_project_orchestrator.on_project_created_enhanced(event)
            logger.info(f"Phase4Integration: Successfully processed project creation for {event.project_id}")
        except Exception as e:
            logger.error(f"Phase4Integration: Error in project creation handling: {e}")

    async def _handle_deliverable_info_gathered(self, event: DeliverableInfoGatheredEvent):
        """Handle deliverable info gathering with task sharing and pricing setup."""
        logger.info(f"Phase4Integration: Handling deliverable info gathered for {event.deliverable_id}")
        
        try:
            await self.enhanced_deliverable_orchestrator.on_deliverable_info_gathered_enhanced(event)
            logger.info(f"Phase4Integration: Successfully processed deliverable info gathering for {event.deliverable_id}")
        except Exception as e:
            logger.error(f"Phase4Integration: Error in deliverable info gathering handling: {e}")

    async def _handle_deliverable_delivered(self, event: DeliverableDeliveredEvent):
        """Handle deliverable delivery with budget and timeline updates."""
        logger.info(f"Phase4Integration: Handling deliverable delivery for {event.deliverable_id}")
        
        try:
            await self.enhanced_project_orchestrator.on_deliverable_delivered_enhanced(event)
            logger.info(f"Phase4Integration: Successfully processed deliverable delivery for {event.deliverable_id}")
        except Exception as e:
            logger.error(f"Phase4Integration: Error in deliverable delivery handling: {e}")

    async def _handle_task_created(self, event: InternalTaskCreatedEvent):
        """Handle task creation with intelligent sharing suggestions."""
        logger.info(f"Phase4Integration: Handling task creation for {event.task_id}")
        
        try:
            await self.enhanced_deliverable_orchestrator.on_task_created_for_deliverable(event)
            logger.info(f"Phase4Integration: Successfully processed task creation for {event.task_id}")
        except Exception as e:
            logger.error(f"Phase4Integration: Error in task creation handling: {e}")

    async def _handle_task_completed(self, event: InternalTaskCompletedEvent):
        """Handle task completion with timeline tracking."""
        logger.info(f"Phase4Integration: Handling task completion for {event.task_id}")
        
        try:
            await self.enhanced_project_orchestrator.on_task_completed_enhanced(event)
            logger.info(f"Phase4Integration: Successfully processed task completion for {event.task_id}")
        except Exception as e:
            logger.error(f"Phase4Integration: Error in task completion handling: {e}")

    async def _handle_task_status_updated(self, event: InternalTaskStatusUpdatedEvent):
        """Handle task status updates with timeline integration."""
        logger.info(f"Phase4Integration: Handling task status update for {event.task_id}")
        
        try:
            await self.enhanced_project_orchestrator.on_task_status_updated_enhanced(event)
            logger.info(f"Phase4Integration: Successfully processed task status update for {event.task_id}")
        except Exception as e:
            logger.error(f"Phase4Integration: Error in task status update handling: {e}")

    async def _handle_requirement_updated(self, event: RequirementUpdatedEvent):
        """Handle requirement updates with budget recalculation."""
        logger.info(f"Phase4Integration: Handling requirement update for {event.requirement_id}")
        
        try:
            await self.enhanced_project_orchestrator.on_requirement_updated_enhanced(event)
            logger.info(f"Phase4Integration: Successfully processed requirement update for {event.requirement_id}")
        except Exception as e:
            logger.error(f"Phase4Integration: Error in requirement update handling: {e}")


# Factory function to create and initialize the integration hooks
def create_phase4_integration_hooks(
    db_session_factory: Callable[[], AsyncSession],
    event_bus: EventBus
) -> Phase4IntegrationHooks:
    """
    Factory function to create and initialize Phase 4 integration hooks.
    
    Args:
        db_session_factory: Database session factory
        event_bus: Event bus instance
        
    Returns:
        Configured Phase4IntegrationHooks instance
    """
    logger.info("Creating Phase 4 integration hooks")
    
    hooks = Phase4IntegrationHooks(
        db_session_factory=db_session_factory,
        event_bus=event_bus
    )
    
    logger.info("Phase 4 integration hooks created and registered")
    return hooks


# Configuration helper for existing orchestrators
class OrchestrationConfig:
    """Configuration helper for orchestration integration."""
    
    @staticmethod
    def enable_phase4_integration():
        """Enable Phase 4 integration features."""
        return {
            "auto_generate_requirements": True,
            "auto_calculate_budget": True,
            "auto_create_timeline": True,
            "enable_task_sharing": True,
            "enable_real_time_updates": True,
            "enable_milestone_tracking": True,
        }
    
    @staticmethod
    def get_auto_generation_settings():
        """Get auto-generation settings for Phase 4."""
        return {
            "requirement_templates": {
                "project": ["scope", "timeline", "budget", "quality"],
                "modeling": ["geometry", "topology", "materials", "textures"],
                "rendering": ["lighting", "camera", "quality", "format"],
                "animation": ["duration", "fps", "style", "format"],
            },
            "default_milestone_phases": [
                "project_initiation",
                "requirements_gathering",
                "design_phase",
                "production_phase",
                "review_phase",
                "delivery_phase",
            ],
            "budget_defaults": {
                "markup_percentage": 20.0,
                "discount_percentage": 0.0,
                "cost_categories": ["labor", "materials", "overhead", "margin"],
            },
            "timeline_defaults": {
                "buffer_percentage": 10.0,
                "working_hours_per_day": 8,
                "working_days_per_week": 5,
            }
        } 