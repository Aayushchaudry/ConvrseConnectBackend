#!/usr/bin/env python3

import asyncio
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.config.kafka_event_bus import KafkaEventBus
from src.events.project_events import ProjectCreatedEvent
from uuid import UUID
from datetime import datetime

async def trigger_saga_for_test_project():
    """Manually trigger the SAGA flow for our test project"""
    
    # Test project details
    project_id = "7b04f6c9-4cf8-493f-8572-af65b48bac38"
    deliverable_ids = [
        "64c6e2e8-3f65-4cc8-9a8d-da03fa6199ce",  # video_walkthrough
        "94a84656-7e12-478f-baf9-82906a35285d"   # location_map
    ]
    
    print(f"🚀 Triggering SAGA for project: {project_id}")
    print(f"📦 Deliverables: {deliverable_ids}")
    
    # Create Kafka event bus
    event_bus = KafkaEventBus()
    await event_bus.connect()
    
    try:
        # Create and publish ProjectCreatedEvent
        project_created_event = ProjectCreatedEvent(
            project_id=UUID(project_id),
            project_name="END-TO-END SAGA VERIFICATION",
            initial_status="initiated"
        )
        
        print(f"📤 Publishing ProjectCreatedEvent...")
        await event_bus.publish(
            topic="project.created",
            message=project_created_event.__dict__
        )
        
        print(f"✅ ProjectCreatedEvent published successfully!")
        print(f"🔄 SAGA flow should now be triggered...")
        
    finally:
        await event_bus.disconnect()

if __name__ == "__main__":
    asyncio.run(trigger_saga_for_test_project()) 