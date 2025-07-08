#!/usr/bin/env python3
"""
Test script to verify deliverable creation API endpoints using HTTP requests.
This tests the actual flow that the frontend uses through the API.
"""

import requests
import json
import time

# API Configuration
BASE_URL = "http://localhost/api/connect"  # ConvrseConnect Backend via nginx connect route
PROJECTS_URL = f"{BASE_URL}/api/v1/projects"

def test_api_deliverable_creation():
    """Test the API-based deliverable creation flow"""
    
    print("=== Testing API Deliverable Creation Flow ===")
    print(f"Backend URL: {BASE_URL}")
    
    # Step 1: Test if backend is running
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"✅ Backend is running: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Backend not reachable: {e}")
        return False
    
    # Step 2: Create a project (like frontend does)
    project_data = {
        "name": "API Test Project",
        "budget": 15000.0,
        "start_date": "2024-01-15",
        "end_date": "2024-04-15",
        "business_id": "biz_convrse_default",
        "assigned_to": "00000000-0000-0000-0000-000000000001"
    }
    
    print(f"\n📝 Step 1: Creating project via API...")
    try:
        response = requests.post(PROJECTS_URL, json=project_data, timeout=10)
        if response.status_code == 201:
            created_project = response.json()
            project_id = created_project["id"]
            print(f"✅ Project created: {project_id}")
            print(f"   Name: {created_project['name']}")
        else:
            print(f"❌ Failed to create project: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Project creation request failed: {e}")
        return False
    
    # Step 3: Create deliverables separately (like frontend does)
    deliverables_to_create = [
        {
            "deliverable_type": "rendered_images",
            "deliverable_sub_type": "Interior Renders",
            "tentative_timeline_days": 14
        },
        {
            "deliverable_type": "technical_renders", 
            "deliverable_sub_type": "Exterior Views",
            "tentative_timeline_days": 21
        }
    ]
    
    print(f"\n📦 Step 2: Creating {len(deliverables_to_create)} deliverables separately...")
    
    created_deliverables = []
    for i, deliverable_data in enumerate(deliverables_to_create):
        try:
            print(f"  Creating deliverable {i+1}: {deliverable_data['deliverable_type']}")
            
            # Make API call to create deliverable
            deliverable_url = f"{PROJECTS_URL}/{project_id}/deliverables/"
            response = requests.post(deliverable_url, json=deliverable_data, timeout=10)
            
            if response.status_code == 201:
                created_deliverable = response.json()
                created_deliverables.append(created_deliverable)
                print(f"  ✅ Created: {created_deliverable['id']}")
                print(f"     Type: {created_deliverable['deliverable_type']}")
                print(f"     Status: {created_deliverable['current_status']}")
            else:
                print(f"  ❌ Failed to create deliverable: {response.status_code}")
                print(f"     Response: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"  ❌ Deliverable creation request failed: {e}")
    
    # Step 4: Verify deliverables were created by getting them from API
    print(f"\n🔍 Step 3: Verifying deliverables via API...")
    try:
        deliverables_url = f"{PROJECTS_URL}/{project_id}/deliverables/"
        response = requests.get(deliverables_url, timeout=10)
        
        if response.status_code == 200:
            project_deliverables = response.json()
            print(f"📋 Found {len(project_deliverables)} deliverables for project {project_id}")
            
            for deliverable in project_deliverables:
                print(f"  • {deliverable['deliverable_type']} - {deliverable.get('deliverable_sub_type', 'N/A')}")
                print(f"    Status: {deliverable['current_status']}")
                print(f"    Timeline: {deliverable.get('tentative_timeline_days', 'N/A')} days")
                print()
            
            if len(project_deliverables) >= len(deliverables_to_create):
                print("✅ SUCCESS: API deliverable creation works!")
                print("✅ Frontend should now be able to create deliverables after project creation")
                return True
            else:
                print("❌ ISSUE: Not all deliverables were created via API")
                return False
        else:
            print(f"❌ Failed to fetch deliverables: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Deliverable fetch request failed: {e}")
        return False

if __name__ == "__main__":
    success = test_api_deliverable_creation()
    if success:
        print("\n🎉 API test completed successfully!")
        print("💡 The frontend deliverable creation flow should now work properly.")
    else:
        print("\n💥 API test failed!")
        print("🔧 Check the backend logs for more details.") 