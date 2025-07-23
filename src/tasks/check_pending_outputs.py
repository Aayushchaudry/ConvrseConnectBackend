"""
Scheduled task to check for pending outputs.
"""

import asyncio
import logging
from datetime import datetime

from src.config.database import AsyncSessionLocal
from src.events.event_bus_interface import EventBus
from src.services.project_output_service import ProjectOutputService

logger = logging.getLogger(__name__)


async def check_pending_outputs(event_bus: EventBus):
    """
    Check for deliverables with all reviews approved and generate outputs.
    This task should be scheduled to run periodically.
    """
    logger.info("Running scheduled task: check_pending_outputs")
    
    try:
        # Create service
        service = ProjectOutputService(AsyncSessionLocal, event_bus)
        
        # Generate outputs for approved deliverables
        created_outputs = await service.generate_outputs_for_approved_deliverables()
        
        if created_outputs:
            logger.info(f"Created {len(created_outputs)} project outputs for approved deliverables")
            
            # Process project completion for each project with new outputs
            projects_processed = set()
            for deliverable_id, output_id in created_outputs.items():
                # Get project ID for this deliverable
                async with AsyncSessionLocal() as session:
                    from sqlalchemy import select
                    from src.models.deliverable import Deliverable
                    
                    result = await session.execute(
                        select(Deliverable.project_id)
                        .filter(Deliverable.id == deliverable_id)
                    )
                    project_id = result.scalar_one_or_none()
                    
                    if project_id and project_id not in projects_processed:
                        # Process project completion
                        await service.process_project_completion(project_id)
                        projects_processed.add(project_id)
        else:
            logger.info("No pending outputs to generate")
        
    except Exception as e:
        logger.error(f"Error in check_pending_outputs task: {e}", exc_info=True)


if __name__ == "__main__":
    # This allows running the task directly for testing
    import sys
    sys.path.append(".")  # Add project root to path
    
    from src.config.event_bus import get_event_bus
    
    async def main():
        event_bus = get_event_bus()
        await check_pending_outputs(event_bus)
    
    asyncio.run(main())