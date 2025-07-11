# ConvrseConnect - Project Timeline Flow Testing Guide

## Overview
This guide walks you through testing the complete project timeline orchestration flow using the provided Postman collection.

## Prerequisites

### 1. Server Setup
```bash
# Ensure your backend server is running
cd ConvrseConnectBackend
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Database Setup
- Ensure PostgreSQL is running
- Database migrations are applied
- Event bus is configured (SQS mock or real SQS)

### 3. Import Postman Collection
1. Open Postman
2. Click "Import" 
3. Select `Postman_Collection_Timeline_Flow.json`
4. Collection will be imported with environment variables

## Testing Flow

### Step 1: Health Check
**Request:** `GET /health`
- **Purpose:** Verify server is running
- **Expected Response:** `200 OK` with health status
- **What to Check:** Server connectivity and basic functionality

### Step 2: Create Project with Deliverables
**Request:** `POST /api/projects/`
```json
{
  "name": "Test Project - Mixed Interior/Exterior",
  "budget": 25000,
  "start_date": "2024-01-01",
  "end_date": "2024-06-01",
  "deliverable_types": ["rendered_images", "vr_tour", "technical_renders"],
  "deliverable_sub_types": {
    "rendered_images": "exterior",
    "vr_tour": "interior", 
    "technical_renders": "exterior"
  },
  "deliverable_timeline_days": {
    "rendered_images": 14,
    "vr_tour": 21,
    "technical_renders": 10
  }
}
```

**Expected Orchestration Flow:**
1. ✅ Project created in database
2. ✅ `ProjectCreatedEvent` published
3. ✅ `EnhancedProjectOrchestrator` receives event
4. ✅ Auto-creates 3 deliverables from `deliverable_types`
5. ✅ Groups deliverables by interior/exterior
6. ✅ Creates 2 separate timelines (interior + exterior)
7. ✅ Creates tasks for each timeline phase
8. ✅ Links tasks to deliverables and phases

**What to Check:**
- Response has project ID (auto-saved to collection variable)
- Status: `201 Created`
- Project details match input

### Step 3: Verify Auto-Created Deliverables
**Request:** `GET /api/projects/{project_id}/deliverables/`

**Expected Results:**
- **3 deliverables** auto-created:
  1. `rendered_images` (exterior) - 14 days
  2. `vr_tour` (interior) - 21 days  
  3. `technical_renders` (exterior) - 10 days
- Each has correct `deliverable_sub_type`
- Each has correct `tentative_timeline_days`

### Step 4: Check Timeline Creation
**Request:** `GET /api/projects/{project_id}/timeline`

**Expected Timeline Structure:**

**Interior Timeline (for vr_tour):**
1. Kick-off Meeting (1 day)
2. Theme Approval (3 days)
3. Modeling & Texturing (7 days)
4. Lighting (3 days)
5. Deliverables Completion (21 days - max from interior deliverables)

**Exterior Timeline (for rendered_images + technical_renders):**
1. Kick-off Meeting (1 day)
2. Modeling (7 days)
3. Texturing & Landscaping (8 days)
4. Lighting (3 days)
5. Deliverables Completion (14 days - max from exterior deliverables)

### Step 5: Verify Task Creation
**Request:** `GET /api/projects/{project_id}/tasks`

**Expected Task Structure:**
- **Interior Tasks:** Created for vr_tour deliverable
- **Exterior Tasks:** Created for rendered_images + technical_renders
- Tasks should be linked to timeline phases
- Dependencies between tasks based on phase order

### Step 6: Test Manual Deliverable Creation
**Request:** `POST /api/projects/{project_id}/deliverables/`
```json
{
  "deliverable_type": "video_walkthrough",
  "deliverable_sub_type": "interior",
  "tentative_timeline_days": 18
}
```

**Expected Results:**
- New deliverable created
- Should not automatically create new timeline (existing interior timeline should accommodate it)

## What to Monitor in Logs

### 1. Project Creation Logs
```
✅ ProjectService - Project created in database: {project_id}
✅ ProjectService - ProjectCreatedEvent published successfully
```

### 2. Orchestration Logs
```
🔄 Enhanced auto-generation for project {project_id}
🔄 Auto-creating 3 deliverables for project {project_id}
✅ Created deliverable: {id} (rendered_images)
✅ Created deliverable: {id} (vr_tour)  
✅ Created deliverable: {id} (technical_renders)
```

### 3. Timeline Creation Logs
```
✅ Creating interior timeline milestones for project {project_id}
✅ Creating exterior timeline milestones for project {project_id}
✅ Created {count} timeline milestones for project {project_id}
```

### 4. Task Creation Logs
```
✅ Creating task 'Project Kick-off Meeting' of type 'meeting'
✅ Creating task 'Create 3D Model - {deliverable}' of type 'modeling'
✅ Created task with ID: {task_id}
```

## Common Issues & Troubleshooting

### Issue 1: Project Created but No Deliverables
**Symptoms:** Project exists but deliverables list is empty
**Cause:** Orchestrator not receiving/processing ProjectCreatedEvent
**Check:** 
- Event bus configuration
- SQS mock service running
- Orchestrator event handlers registered

### Issue 2: Deliverables Created but No Timeline
**Symptoms:** Deliverables exist but timeline is empty
**Check:**
- Timeline service imports and dependencies
- ProjectTimeline model accessibility
- Database permissions for timeline table

### Issue 3: Timeline Created but No Tasks
**Symptoms:** Timeline exists but no tasks created
**Check:**
- TaskManagementService.create_task() method
- InternalTask model and relationships
- Task creation dependencies

### Issue 4: Mixed Interior/Exterior Not Separating
**Symptoms:** Only one timeline created instead of two
**Check:**
- Deliverable sub_type classification logic
- Interior/exterior grouping in orchestrator

## Advanced Testing Scenarios

### Scenario 1: Pure Interior Project
```json
{
  "deliverable_types": ["vr_tour", "video_walkthrough"],
  "deliverable_sub_types": {
    "vr_tour": "interior",
    "video_walkthrough": "interior"
  }
}
```
**Expected:** Only interior timeline created

### Scenario 2: Pure Exterior Project  
```json
{
  "deliverable_types": ["rendered_images", "technical_renders"],
  "deliverable_sub_types": {
    "rendered_images": "exterior", 
    "technical_renders": "exterior"
  }
}
```
**Expected:** Only exterior timeline created

### Scenario 3: Large Mixed Project
```json
{
  "deliverable_types": ["rendered_images", "vr_tour", "technical_renders", "video_walkthrough", "location_map"],
  "deliverable_sub_types": {
    "rendered_images": "exterior",
    "vr_tour": "interior",
    "technical_renders": "exterior", 
    "video_walkthrough": "interior",
    "location_map": "exterior"
  }
}
```
**Expected:** Both timelines with multiple deliverables in each

## Success Criteria

✅ **Project Creation:** Project created with all metadata  
✅ **Auto-Deliverable Creation:** All deliverable_types become actual deliverables  
✅ **Timeline Separation:** Interior and exterior get separate timelines  
✅ **Phase Structure:** Correct phases for each timeline type  
✅ **Task Generation:** Tasks created for each phase  
✅ **Task-Deliverable Linking:** Tasks properly linked to deliverables  
✅ **Dependencies:** Task dependencies respect phase order  
✅ **Event Flow:** All events properly published and handled  

## API Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Server health check |
| `/api/projects/` | POST | Create project with auto-deliverables |
| `/api/projects/{id}` | GET | Get project details |
| `/api/projects/{id}/deliverables/` | GET | List project deliverables |
| `/api/projects/{id}/timeline` | GET | Get project timeline |
| `/api/projects/{id}/tasks` | GET | Get project tasks |
| `/api/projects/{id}/deliverables/` | POST | Create additional deliverable |
| `/api/deliverables/{id}/status` | PATCH | Update deliverable status |
| `/api/internal-tasks/` | POST | Create manual task |

---

**Note:** This testing flow validates the complete end-to-end orchestration from project creation through timeline and task generation. Monitor logs closely to understand the internal flow and catch any issues early. 