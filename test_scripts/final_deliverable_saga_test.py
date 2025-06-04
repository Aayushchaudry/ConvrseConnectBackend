#!/usr/bin/env python3
"""
Final Deliverable SAGA Orchestration Test
=========================================
This script demonstrates the Deliverable SAGA orchestration by processing 
DeliverableInfoGatheredEvent for our existing test project.
"""

import asyncio
import sys
import os
from uuid import UUID

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.config.kafka_event_bus import KafkaEventBus
from src.config.database import AsyncSessionLocal
from src.events.deliverable_events import DeliverableInfoGatheredEvent
from src.orchestrators.deliverable_saga_orchestrator.deliverable_saga_orchestrator import DeliverableSagaOrchestrator

async def final_deliverable_saga_test():
    """Demonstrates Deliverable SAGA orchestration for existing test project"""
    
    print("🚀 FINAL DELIVERABLE SAGA ORCHESTRATION TEST")
    print("=" * 50)
    
    # Use our existing test project data
    project_id = "7b04f6c9-4cf8-493f-8572-af65b48bac38"
    deliverable_ids = [
        "64c6e2e8-3f65-4cc8-9a8d-da03fa6199ce",  # video_walkthrough
        "94a84656-7e12-478f-baf9-82906a35285d"   # location_map
    ]
    
    print(f"📋 Using Test Project ID: {project_id}")
    print(f"📦 Using Test Deliverable IDs: {deliverable_ids}")
    print()
    
    # Initialize components
    event_bus = KafkaEventBus()
    await event_bus.connect()
    
    try:
        print("🔌 Connected to Kafka Event Bus")
        
        # Initialize Deliverable SAGA Orchestrator
        deliverable_orchestrator = DeliverableSagaOrchestrator(
            db_session_factory=AsyncSessionLocal,
            event_bus=event_bus
        )
        
        print("✅ DeliverableSagaOrchestrator initialized")
        print()
        
        # Process DeliverableInfoGatheredEvent for each deliverable
        for i, deliverable_id in enumerate(deliverable_ids, 1):
            print(f"🎯 PROCESSING DELIVERABLE {i}: {deliverable_id}")
            print("-" * 40)
            
            deliverable_info_gathered_event = DeliverableInfoGatheredEvent(
                project_id=UUID(project_id),
                deliverable_id=UUID(deliverable_id)
            )
            
            print(f"📤 Publishing DeliverableInfoGatheredEvent...")
            await event_bus.publish(
                topic="deliverable.info_gathered",
                message=deliverable_info_gathered_event.__dict__
            )
            
            # Process through Deliverable SAGA Orchestrator
            print(f"🔄 Processing through DeliverableSagaOrchestrator...")
            await deliverable_orchestrator.handle_event(deliverable_info_gathered_event.__dict__)
            
            print(f"✅ Deliverable SAGA {i} orchestration completed!")
            print()
        
        print("🎉 DELIVERABLE SAGA ORCHESTRATION TEST COMPLETED!")
        print("=" * 50)
        print()
        print("📊 VERIFICATION COMMANDS:")
        print()
        print("1. Check SAGA States (should show new DELIVERABLE_PRODUCTION SAGAs):")
        print(f"""   docker exec project_portal_db psql -U ConvrseConnect -d project_db -c \\
     "SELECT project_id, deliverable_id, saga_type, current_state, status \\
      FROM saga_state WHERE project_id = '{project_id}' ORDER BY saga_type, created_at;" """)
        print()
        print("2. Check InitiateModelingCommand was published:")
        print("""   docker exec kafka kafka-console-consumer --bootstrap-server localhost:9092 \\
     --topic deliverable.command.initiate_modeling --from-beginning --timeout-ms 3000""")
        print()
        print("3. Check UpdateDeliverableStatusInDBCommand was published:")
        print("""   docker exec kafka kafka-console-consumer --bootstrap-server localhost:9092 \\
     --topic deliverable.command.update_status_db --from-beginning --timeout-ms 3000""")
        
    finally:
        await event_bus.disconnect()
        print()
        print("🔌 Disconnected from Kafka Event Bus")

if __name__ == "__main__":
    asyncio.run(final_deliverable_saga_test()) 