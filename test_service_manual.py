#!/usr/bin/env python3

import asyncio
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.config.database import AsyncSessionLocal
from src.models.project import Project
from src.models.deliverable import Deliverable, DeliverableType
from src.models.requirement import Requirement, RequirementType, RequirementStatus
from sqlalchemy import select

async def test_service_logic():
    """Test the InformationGatheringService logic manually"""
    
    # Test project ID (ULTIMATE TEST)
    project_id = "6debd43f-6654-4f06-9fde-1674500c4b57"
    
    print(f"Testing service logic for project: {project_id}")
    
    async with AsyncSessionLocal() as session:
        # 1. Fetch the project
        print("1. Fetching project...")
        project_result = await session.execute(select(Project).filter(Project.id == project_id))
        project = project_result.scalar_one_or_none()
        
        if not project:
            print(f"❌ Project {project_id} not found!")
            return
        
        print(f"✅ Found project: {project.name}")
        
        # 2. Fetch deliverables
        print("2. Fetching deliverables...")
        deliverables_result = await session.execute(
            select(Deliverable).filter(Deliverable.project_id == project_id)
        )
        deliverables = deliverables_result.scalars().all()
        
        print(f"✅ Found {len(deliverables)} deliverables")
        
        for deliverable in deliverables:
            print(f"   - Deliverable {deliverable.id}: {deliverable.deliverable_type}")
            print(f"     Type object: {type(deliverable.deliverable_type)}")
            print(f"     Type value: {deliverable.deliverable_type.value}")
            
            # 3. Test the requirements map lookup
            from src.services.info_gathering_service import DELIVERABLE_REQUIREMENTS_MAP
            
            print(f"3. Testing requirements map lookup...")
            print(f"   Map keys: {list(DELIVERABLE_REQUIREMENTS_MAP.keys())}")
            
            required_items = DELIVERABLE_REQUIREMENTS_MAP.get(deliverable.deliverable_type)
            
            if required_items:
                print(f"✅ Found {len(required_items)} requirements for {deliverable.deliverable_type}")
                for req_name, req_type, is_mandatory in required_items:
                    print(f"   - {req_name} ({req_type}, mandatory: {is_mandatory})")
                    
                    # 4. Test requirement creation
                    print(f"4. Testing requirement creation for: {req_name}")
                    try:
                        new_requirement = Requirement(
                            deliverable_id=deliverable.id,
                            project_id=project.id,
                            requirement_name=req_name,
                            requirement_type=req_type,
                            status=RequirementStatus.PENDING,
                            is_mandatory=is_mandatory
                        )
                        session.add(new_requirement)
                        print(f"✅ Created requirement object: {req_name}")
                        
                        # Try to commit
                        await session.commit()
                        print(f"✅ Committed requirement: {req_name}")
                        
                    except Exception as e:
                        print(f"❌ Error creating requirement {req_name}: {e}")
                        await session.rollback()
                        
            else:
                print(f"❌ No requirements found for {deliverable.deliverable_type}")
                print(f"   Deliverable type: {deliverable.deliverable_type}")
                print(f"   Available map keys: {list(DELIVERABLE_REQUIREMENTS_MAP.keys())}")

if __name__ == "__main__":
    asyncio.run(test_service_logic()) 