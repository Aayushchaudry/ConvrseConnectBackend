#!/usr/bin/env python3

import asyncio
import logging
from uuid import uuid4
from src.config.event_bus import get_event_bus
from src.commands.project_commands import StartInformationGatheringCommand

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_event_bus():
    """Test if event bus can publish commands"""
    try:
        # Get event bus
        event_bus = await get_event_bus()
        logger.info("✅ Event bus connected successfully")
        
        # Create test command
        test_project_id = uuid4()
        test_deliverable_id = uuid4()
        
        command = StartInformationGatheringCommand(
            project_id=test_project_id,
            deliverable_ids=[test_deliverable_id]
        )
        
        logger.info(f"Publishing test command for project: {test_project_id}")
        
        # Publish command
        await event_bus.publish(
            topic="project.command.start_info_gathering",
            message=command.__dict__
        )
        
        logger.info("✅ Test command published successfully!")
        
    except Exception as e:
        logger.error(f"❌ Event bus test failed: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(test_event_bus()) 