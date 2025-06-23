#!/usr/bin/env python3
"""
Test script to verify deliverable creation and requirements generation
"""

import asyncio
import uuid
import sys
import os
from datetime import datetime

# Add the src directory to Python path
sys.path.append('/Users/tonystark/convrse/ConvrseConnectBackend/src')

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.config.database import AsyncSessionLocal
from src.models.project import Project
from src.models.deliverable import Deliverable, DeliverableType, DeliverableStatus
from src.models.requirement import Requirement
from src.commands.project_commands import StartInformationGatheringCommand
from src.services.info_gathering_service import InformationGatheringService
from src.config.event_bus import get_event_bus

async def test_deliverable_creation_and_requirements():
    """Test if deliverable creation automatically creates requirement items"""
    print("🧪 Testing deliverable creation and requirements generation...")
    
    # Generate test IDs
    project_id = str(uuid.uuid4())
    deliverable_id = str(uuid.uuid4())
    
    try:
        # 1. Create a project and deliverable directly in the database
        print(f"📝 Creating project: {project_id}")
        print(f"📝 Creating deliverable: {deliverable_id}")
        
        async with AsyncSessionLocal() as session:
            # Create Project
            project = Project(
                id=project_id,
                name="Test Project for Requirements",
                budget=50000,
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 3, 1),
                business_id="1",
                created_by="1",
                assigned_to="1"
            )
            session.add(project)
            
            # Create Deliverable
            deliverable = Deliverable(
                id=deliverable_id,
                project_id=project_id,
                deliverable_type="rendered_images",  # Use string value directly
                deliverable_sub_type="Interior Requirement",
                current_status="info_gathering",  # Use string value directly
                tentative_timeline_days=10,
                created_by=1,
                assigned_to=1
            )
            session.add(deliverable)
            
            await session.commit()
            print(f"✅ Project created with ID: {project_id}")
            print(f"✅ Deliverable created with ID: {deliverable_id}")
        
        # 2. Test information gathering service
        print("\n🔍 Testing information gathering service...")
        
        # Get event bus and create service
        event_bus = await get_event_bus()
        
        async with AsyncSessionLocal() as session:
            info_gathering_service = InformationGatheringService(session, event_bus)
            
            # Create the command
            command = StartInformationGatheringCommand(
                project_id=project_id,
                deliverable_ids=[deliverable_id]
            )
            
            # Execute the command
            await info_gathering_service.handle_start_information_gathering_command(command)
            print("✅ Information gathering service executed successfully")
        
        # 3. Check if requirements were created
        print("\n📋 Checking if requirements were created...")
        
        async with AsyncSessionLocal() as session:
            requirements_result = await session.execute(
                select(Requirement).where(
                    Requirement.project_id == project_id,
                    Requirement.deliverable_id == deliverable_id
                )
            )
            requirements = requirements_result.scalars().all()
            
            print(f"✅ Found {len(requirements)} requirement(s) created:")
            for req in requirements:
                print(f"   - ID: {req.id}")
                print(f"   - Name: {req.requirement_name}")
                print(f"   - Status: {req.status.value}")
                print(f"   - Type: {req.requirement_type}")
                print(f"   - Project ID: {req.project_id}")
                print(f"   - Deliverable ID: {req.deliverable_id}")
                print("   ---")
            
            if len(requirements) > 0:
                print("🎉 SUCCESS: Requirements were automatically created!")
                return True
            else:
                print("❌ FAILURE: No requirements were created")
                return False
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main function"""
    print("🚀 Starting deliverable creation test...")
    
    success = await test_deliverable_creation_and_requirements()
    
    if success:
        print("\n✅ Test completed successfully!")
        return 0
    else:
        print("\n❌ Test failed!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 