#!/usr/bin/env python3

import asyncio
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.config.database import AsyncSessionLocal
from src.services.info_gathering_service import InformationGatheringService
from src.commands.project_commands import StartInformationGatheringCommand
from src.events.event_bus_interface import EventBus
from src.config.kafka_event_bus import KafkaEventBus
from uuid import UUID
import uuid
from datetime import datetime

class MockEventBus(EventBus):
    """Mock event bus for testing that logs published events instead of sending to Kafka"""
    
    async def connect(self):
        print("🔌 MockEventBus: Connected")
    
    async def disconnect(self):
        print("🔌 MockEventBus: Disconnected")
    
    async def publish(self, topic: str, message: dict) -> None:
        print(f"📤 PUBLISHED EVENT to {topic}: {message}")
    
    async def subscribe(self, topic: str, handler):
        print(f"📥 MockEventBus: Subscribed to {topic}")
    
    def get_consumer(self, topic: str, group_id: str):
        print(f"📥 MockEventBus: Created consumer for {topic} with group {group_id}")
        return None  # Not needed for this test
    
    async def create_topic(self, topic: str, num_partitions: int = 1, replication_factor: int = 1):
        print(f"📋 MockEventBus: Created topic {topic}")

async def test_service_handler_directly():
    """Test the InformationGatheringService handler directly with the exact same setup as Kafka listener"""
    
    # Test project ID (the one we know has 1 deliverable)
    project_id = "6debd43f-6654-4f06-9fde-1674500c4b57"
    deliverable_id = "1b41f43f-d188-49b4-af10-9006b48df174"  # The INVENTORY_MODULE deliverable
    
    print(f"🔬 Testing InformationGatheringService handler directly for project: {project_id}")
    
    # Create mock event bus
    mock_event_bus = MockEventBus()
    
    # Create the service EXACTLY as done in the listener
    info_gathering_service = InformationGatheringService(
        db_session_factory=AsyncSessionLocal,  # Same as in listener
        event_bus=mock_event_bus
    )
    
    # Create the command
    command = StartInformationGatheringCommand(
        project_id=UUID(project_id),
        deliverable_ids=[UUID(deliverable_id)]
    )
    
    print(f"📋 Created command: {command}")
    
    # Call the handler directly
    print(f"🚀 Calling service handler...")
    try:
        await info_gathering_service.handle_start_information_gathering_command(command)
        print(f"✅ Service handler completed successfully!")
    except Exception as e:
        print(f"❌ Service handler failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_service_handler_directly()) 