#!/usr/bin/env python3

import asyncio
import sys
import os

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.config.event_bus import get_event_bus, close_event_bus
from src.commands.project_commands import StartInformationGatheringCommand

async def trigger_information_gathering():
    try:
        # Initialize event bus
        event_bus = await get_event_bus()
        print("✅ Event bus connected")
        
        # Create the command to trigger information gathering
        command = StartInformationGatheringCommand(
            project_id="07aa3aeb-2604-4238-8440-5a77f962ba40",
            deliverable_ids=["9c56914d-c069-4a05-8f63-374109b404b7"]
        )
        
        # Publish the command
        await event_bus.publish(
            topic="project.commands.start_info_gathering",
            message=command.__dict__
        )
        print("✅ StartInformationGatheringCommand published")
        
        # Close event bus
        await close_event_bus()
        print("✅ Event bus closed")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    return True

if __name__ == "__main__":
    result = asyncio.run(trigger_information_gathering())
    print("✅ SAGA step triggered successfully!" if result else "❌ Failed to trigger SAGA step") 