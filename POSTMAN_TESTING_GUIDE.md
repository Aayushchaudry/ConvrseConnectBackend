# ConvrseConnect Backend API Testing Guide

## Overview

This Postman collection provides comprehensive testing for the ConvrseConnect Backend system, including integrations with Auth Service and Platform Service. The collection covers all implemented features from your file-upload-review-integration specification.

## Setup Instructions

### 1. Import Collection and Environment

1. Import `ConvrseConnect_API_Collection.postman_collection.json` into Postman
2. Import `ConvrseConnect_Environment.postman_environment.json` as an environment
3. Select the "ConvrseConnect Development" environment

### 2. Configure Service URLs

Update the environment variables if your services run on different ports:

- `base_url`: ConvrseConnect Backend (default: http://localhost:8000)
- `auth_service_url`: Auth Service (default: http://localhost:8001)
- `platform_service_url`: Platform Service (default: http://localhost:8002)

### 3. Start Your Services

Ensure all three services are running:
```bash
# ConvrseConnect Backend
cd ConvrseConnectBackend
uvicorn src.main:app --reload --port 8000

# Auth Service (separate terminal)
cd auth-service
uvicorn main:app --reload --port 8001

# Platform Service (separate terminal)
cd platform-service
uvicorn main:app --reload --port 8002
```

## Testing Workflow

### Phase 1: Service Health Checks

1. **🏥 Health Checks** folder
   - Run all health check requests to verify services are running
   - Verify auth service connectivity
   - Check platform service availability

### Phase 2: Authentication Setup

1. **🔐 Authentication** folder
   - Register a new user (if needed)
   - Login to get authentication token
   - Token is automatically stored in `auth_token` variable
   - Validate token to ensure it's working

### Phase 3: Core Project Workflow

Follow this sequence to test the complete project lifecycle:

#### 3.1 Project Creation
1. **📁 Projects Management** → "Create Project"
   - Creates a new project and stores `project_id`

#### 3.2 Deliverable Setup
2. **📋 Deliverables Management** → "Create Deliverable"
   - Creates a deliverable for the project
   - Stores `deliverable_id`

#### 3.3 Requirements with File Upload
3. **📄 Requirements Management**:
   - "Create Requirement" → stores `requirement_id`
   - "Upload Requirement Files" → test file upload integration
   - "Get Requirement Files" → verify files were uploaded

#### 3.4 Task Management and Completion
4. **🔧 Internal Tasks Management**:
   - "Create Internal Task" → stores `task_id`
   - "Complete Task with Files" → creates review items, stores `review_item_id`

#### 3.5 Review Process
5. **👁️ Review Items Management**:
   - "Get Review Item Files" → stores `file_id`
   - "Submit Review Feedback - Request Changes" → test rejection workflow
   - "Submit Review Feedback - Approve" → test approval workflow
   - "Get Review Feedback History" → verify feedback tracking

### Phase 4: Advanced Features Testing

#### 4.1 Project Outputs
6. **📊 Project Outputs**:
   - Test output generation
   - Project compilation
   - Deliverable output creation

#### 4.2 Pricing Management
7. **💰 Pricing Management**:
   - Set and update pricing
   - Get budget summaries
   - Track actual costs

#### 4.3 Timeline Tracking
8. **📅 Timeline Management**:
   - Log task progress
   - Track project timelines
   - Create milestones

#### 4.4 Task Dependencies
9. **🎯 Task Management**:
   - Test task dependencies
   - Resource allocation
   - Critical path analysis

### Phase 5: Platform Service Integration

10. **📁 Platform Service Integration**:
    - Direct file upload to platform service
    - File metadata retrieval
    - File download and viewing

### Phase 6: Debug and Monitoring

11. **🔧 Debug & Testing**:
    - Test event bus functionality
    - Debug workflows
    - Service integration testing

## Key Integration Points to Test

### 1. File Upload Integration
- **Requirement Files**: Upload files through requirements API
- **Review Item Files**: Complete tasks with file attachments
- **Platform Service**: Direct file operations

### 2. Review Workflow Integration
- **Task Completion**: Files automatically create review items
- **Feedback Processing**: Approval/rejection creates appropriate workflows
- **Rework Tasks**: Rejected items generate new tasks

### 3. Service Communication
- **Auth Service**: Token validation and user management
- **Platform Service**: File storage and retrieval
- **Event Bus**: Cross-service communication

### 4. Data Flow Validation
- **Project → Deliverable → Task → Review Item → Output**
- **File Upload → Review → Feedback → Rework/Approval**
- **Timeline → Progress → Milestones**

## Testing Scenarios

### Scenario 1: Complete Project Lifecycle
1. Create project and deliverable
2. Add requirements with files
3. Create and complete tasks with files
4. Review and approve all items
5. Generate final outputs

### Scenario 2: Rework Workflow
1. Complete task with files
2. Submit rejection feedback
3. Verify rework task creation
4. Complete rework task
5. Approve revised work

### Scenario 3: File Version Management
1. Upload initial files
2. Request changes with feedback
3. Upload new file versions
4. Track version history

### Scenario 4: Cross-Service Integration
1. Upload files to platform service
2. Reference files in backend operations
3. Verify file accessibility across services

## Troubleshooting

### Common Issues

1. **Authentication Failures**
   - Verify auth service is running
   - Check token expiration
   - Ensure proper login credentials

2. **File Upload Issues**
   - Verify platform service connectivity
   - Check file size limits
   - Ensure proper file formats

3. **Service Communication**
   - Check service URLs in environment
   - Verify network connectivity
   - Review service logs for errors

### Debug Endpoints

Use the **🔧 Debug & Testing** folder for:
- Event bus testing
- Service integration debugging
- Workflow troubleshooting

## Expected Response Codes

- **200**: Successful GET requests
- **201**: Successful POST requests (creation)
- **204**: Successful DELETE requests
- **400**: Bad request (validation errors)
- **401**: Authentication required
- **403**: Insufficient permissions
- **404**: Resource not found
- **500**: Internal server error

## File Upload Testing

For file upload endpoints, you'll need to:
1. Select files in the form-data body
2. Use appropriate file types (images, documents, 3D models)
3. Verify files are properly stored and referenced

## Monitoring and Validation

After running tests, verify:
1. Database records are created correctly
2. Files are stored in platform service
3. Event bus messages are processed
4. Timeline and pricing data is accurate
5. Review workflows function properly

## Collection Variables

The collection automatically manages these variables:
- `auth_token`: Authentication token from login
- `project_id`: Created project identifier
- `deliverable_id`: Created deliverable identifier
- `requirement_id`: Created requirement identifier
- `task_id`: Created task identifier
- `review_item_id`: Created review item identifier
- `file_id`: Uploaded file identifier
- `platform_file_id`: Platform service file identifier

These variables are automatically set by test scripts in the requests, enabling seamless workflow testing.