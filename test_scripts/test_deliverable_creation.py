#!/usr/bin/env python3

import asyncio
import sys
import os

# Add the ConvrseConnectBackend src to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from uuid import uuid4
from services.deliverable_service import DeliverableService
from models.deliverable import DeliverableType
from config.database import AsyncSessionLocal
from config.event_bus import get_event_bus
import time

async def test_deliverable_creation():
    """Test if deliverable creation automatically creates requirement items"""
    
    # Get a project ID that exists in the database
    project_id = "2210344f-b557-432f-93b7-71eb76edf344"  # Use an existing project
    
    print("🚀 Testing Deliverable Creation Flow...")
    
    # 1. Create a deliverable using DeliverableService
    try:
        async with AsyncSessionLocal() as db_session:
            event_bus = await get_event_bus()
            deliverable_service = DeliverableService(
                db_session=db_session,
                event_bus=event_bus
            )
            
            print("📝 Creating a new deliverable...")
            deliverable = await deliverable_service.create_deliverable(
                project_id=project_id,
                deliverable_type=DeliverableType.RENDERED_IMAGES,
                deliverable_sub_type="Interior",
                tentative_timeline_days=7,
                created_by=1,
                assigned_to=1
            )
            
            deliverable_id = deliverable.id
            print(f"✅ Deliverable created with ID: {deliverable_id}")
            
            # 2. Wait for async processing
            print("⏳ Waiting for requirement items to be created (5 seconds)...")
            await asyncio.sleep(5)
            
            # 3. Check if requirement items were created
            print("🔍 Checking if requirement items were created automatically...")
            
            import psycopg2
            from psycopg2.extras import RealDictCursor
            
            # Connect to database
            conn = psycopg2.connect(
                host="localhost",
                port="5432",
                user="convrse_user",
                password="convrse_password",
                database="convrse_db"
            )
            
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Check requirements
                cursor.execute("""
                    SELECT COUNT(*) as count 
                    FROM connect_backend.requirements 
                    WHERE deliverable_id = %s
                """, (str(deliverable_id),))
                
                requirements_count = cursor.fetchone()['count']
                print(f"📋 Requirements created: {requirements_count}")
                
                if requirements_count > 0:
                    cursor.execute("""
                        SELECT requirement_name, requirement_type, is_mandatory 
                        FROM connect_backend.requirements 
                        WHERE deliverable_id = %s
                    """, (str(deliverable_id),))
                    
                    requirements = cursor.fetchall()
                    print("📝 Requirements details:")
                    for req in requirements:
                        print(f"  - {req['requirement_name']} ({req['requirement_type']}) - Mandatory: {req['is_mandatory']}")
                
                # Check internal tasks
                cursor.execute("""
                    SELECT COUNT(*) as count 
                    FROM connect_backend.internal_tasks 
                    WHERE deliverable_id = %s
                """, (str(deliverable_id),))
                
                tasks_count = cursor.fetchone()['count']
                print(f"📋 Internal tasks created: {tasks_count}")
                
                if tasks_count > 0:
                    cursor.execute("""
                        SELECT task_name, task_type, status 
                        FROM connect_backend.internal_tasks 
                        WHERE deliverable_id = %s
                    """, (str(deliverable_id),))
                    
                    tasks = cursor.fetchall()
                    print("🔧 Internal tasks details:")
                    for task in tasks:
                        print(f"  - {task['task_name']} ({task['task_type']}) - Status: {task['status']}")
            
            conn.close()
            
            # 4. Summary
            print("\n📊 SUMMARY:")
            if requirements_count > 0 or tasks_count > 0:
                print("✅ SUCCESS: Automatic item creation is working!")
                if requirements_count > 0:
                    print(f"   ✓ {requirements_count} requirement items created")
                if tasks_count > 0:
                    print(f"   ✓ {tasks_count} internal task items created")
            else:
                print("❌ ISSUE: No requirements or tasks were created automatically")
                print("   This indicates the information gathering service is not working properly")
            
            return True
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(test_deliverable_creation())
    sys.exit(0 if result else 1) 