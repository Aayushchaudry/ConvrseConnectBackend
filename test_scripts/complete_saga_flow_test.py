#!/usr/bin/env python3
"""
Complete SAGA Orchestration Flow Test
=====================================
This script demonstrates the entire end-to-end SAGA flow:
1. Create Project → ProjectCreatedEvent → Project SAGA
2. Project Orchestrator → StartInformationGatheringCommand
3. Information Gathering → Requirements Creation → DeliverableInfoGatheredEvent  
4. Deliverable Events Listener → DeliverableSagaOrchestrator
5. Deliverable SAGA → InitiateModelingCommand
"""

import asyncio
import sys
import os
from uuid import UUID, uuid4
from datetime import datetime

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.config.kafka_event_bus import KafkaEventBus
from src.config.database import AsyncSessionLocal

# Events
from src.events.project_events import ProjectCreatedEvent
from src.events.deliverable_events import DeliverableInfoGatheredEvent

# Commands  
from src.commands.project_commands import StartInformationGatheringCommand

# Orchestrators
from src.orchestrators.project_lifecycle_orchestrator.project_lifecycle_orchestrator import ProjectLifecycleOrchestrator
from src.orchestrators.deliverable_saga_orchestrator.deliverable_saga_orchestrator import DeliverableSagaOrchestrator

# Services
from src.services.info_gathering_service import InformationGatheringService

async def complete_saga_flow_test():
    """Demonstrates the complete SAGA orchestration flow"""
    
    print("🚀 COMPLETE SAGA ORCHESTRATION FLOW TEST")
    print("=" * 50)
    
    # Test data
    project_id = uuid4()
    deliverable_id_1 = uuid4() 
    deliverable_id_2 = uuid4()
    
    print(f"📋 Test Project ID: {project_id}")
    print(f"📦 Test Deliverable IDs: {deliverable_id_1}, {deliverable_id_2}")
    print()
    
    # Initialize components
    event_bus = KafkaEventBus()
    await event_bus.connect()
    
    try:
        print("🔌 Connected to Kafka Event Bus")
        
        # Initialize orchestrators
        project_orchestrator = ProjectLifecycleOrchestrator(
            db_session_factory=AsyncSessionLocal,
            event_bus=event_bus
        )
        
        deliverable_orchestrator = DeliverableSagaOrchestrator(
            db_session_factory=AsyncSessionLocal,
            event_bus=event_bus
        )
        
        info_gathering_service = InformationGatheringService(
            db_session_factory=AsyncSessionLocal,
            event_bus=event_bus
        )
        
        print("✅ All orchestrators and services initialized")
        print()
        
        # STEP 1: Simulate Project Creation → Project SAGA
        print("🎯 STEP 1: Project Creation → Project SAGA")
        print("-" * 40)
        
        project_created_event = ProjectCreatedEvent(
            project_id=project_id,
            project_name="Complete SAGA Flow Test Project",
            initial_status="INITIATED"
        )
        
        print(f"📤 Publishing ProjectCreatedEvent...")
        await event_bus.publish(
            topic="project.created",
            message=project_created_event.__dict__
        )
        
        # Process the event through Project Orchestrator
        await project_orchestrator.handle_event(project_created_event.__dict__)
        print("✅ Project SAGA initiated and StartInformationGatheringCommand sent")
        print()
        
        # STEP 2: Simulate Information Gathering Command Processing
        print("🎯 STEP 2: Information Gathering Command Processing")
        print("-" * 40)
        
        start_info_gathering_cmd = StartInformationGatheringCommand(
            project_id=project_id,
            deliverable_ids=[deliverable_id_1, deliverable_id_2]
        )
        
        print(f"🔄 Processing StartInformationGatheringCommand...")
        await info_gathering_service.handle_start_information_gathering(start_info_gathering_cmd)
        print("✅ Information gathering completed and DeliverableInfoGatheredEvents published")
        print()
        
        # STEP 3: Simulate Deliverable SAGA Orchestration
        print("🎯 STEP 3: Deliverable SAGA Orchestration")
        print("-" * 40)
        
        # Process DeliverableInfoGatheredEvent for each deliverable
        for i, deliverable_id in enumerate([deliverable_id_1, deliverable_id_2], 1):
            print(f"📦 Processing deliverable {i}: {deliverable_id}")
            
            deliverable_info_gathered_event = DeliverableInfoGatheredEvent(
                project_id=project_id,
                deliverable_id=deliverable_id
            )
            
            print(f"📤 Publishing DeliverableInfoGatheredEvent...")
            await event_bus.publish(
                topic="deliverable.info_gathered",
                message=deliverable_info_gathered_event.__dict__
            )
            
            # Process through Deliverable SAGA Orchestrator
            await deliverable_orchestrator.handle_event(deliverable_info_gathered_event.__dict__)
            print(f"✅ Deliverable SAGA {i} initiated and InitiateModelingCommand sent")
            print()
        
        print("🎉 COMPLETE SAGA FLOW TEST COMPLETED SUCCESSFULLY!")
        print("=" * 50)
        print()
        print("📊 DATABASE VERIFICATION:")
        print("Run the following SQL commands to verify the complete flow:")
        print()
        print("1. Check SAGA States:")
        print(f"   SELECT project_id, deliverable_id, saga_type, current_state, status")
        print(f"   FROM saga_state WHERE project_id = '{project_id}';")
        print()
        print("2. Check Kafka Topics:")
        print("   docker exec kafka kafka-console-consumer --bootstrap-server localhost:9092 \\")
        print("     --topic project.created --from-beginning --timeout-ms 3000")
        print()
        print("   docker exec kafka kafka-console-consumer --bootstrap-server localhost:9092 \\") 
        print("     --topic deliverable.info_gathered --from-beginning --timeout-ms 3000")
        print()
        print("   docker exec kafka kafka-console-consumer --bootstrap-server localhost:9092 \\")
        print("     --topic deliverable.command.initiate_modeling --from-beginning --timeout-ms 3000")
        
    finally:
        await event_bus.disconnect()
        print()
        print("🔌 Disconnected from Kafka Event Bus")

if __name__ == "__main__":
    asyncio.run(complete_saga_flow_test()) 