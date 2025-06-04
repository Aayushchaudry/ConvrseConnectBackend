#!/usr/bin/env python3

import asyncio
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.config.kafka_event_bus import KafkaEventBus
from src.events.deliverable_events import DeliverableInfoGatheredEvent
from uuid import UUID
from datetime import datetime

async def trigger_deliverable_saga():
    """Manually trigger the Deliverable SAGA flow by publishing DeliverableInfoGatheredEvent"""
    
    # Test project details from our successful previous test
    project_id = "7b04f6c9-4cf8-493f-8572-af65b48bac38"
    deliverable_ids = [
        "64c6e2e8-3f65-4cc8-9a8d-da03fa6199ce",  # video_walkthrough
        "94a84656-7e12-478f-baf9-82906a35285d"   # location_map
    ]
    
    print(f"🚀 Triggering Deliverable SAGA for project: {project_id}")
    print(f"📦 Deliverables: {deliverable_ids}")
    
    # Create Kafka event bus
    event_bus = KafkaEventBus()
    await event_bus.connect()
    
    try:
        # Publish DeliverableInfoGatheredEvent for each deliverable
        for deliverable_id in deliverable_ids:
            deliverable_info_gathered_event = DeliverableInfoGatheredEvent(
                project_id=UUID(project_id),
                deliverable_id=UUID(deliverable_id)
            )
            
            print(f"📤 Publishing DeliverableInfoGatheredEvent for deliverable {deliverable_id}...")
            await event_bus.publish(
                topic="deliverable.info_gathered",
                message=deliverable_info_gathered_event.__dict__
            )
            
            print(f"✅ DeliverableInfoGatheredEvent published for deliverable {deliverable_id}!")
        
        print(f"🔄 Deliverable SAGA flow should now be triggered...")
        
    finally:
        await event_bus.disconnect()

if __name__ == "__main__":
    asyncio.run(trigger_deliverable_saga()) 