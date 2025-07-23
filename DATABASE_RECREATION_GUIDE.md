# Database Models and Recreation Guide (Docker Version)

## 📊 Database Models Summary

I found database models across 3 repositories (devsecops has no models):

### 1. ConvrseConnectBackend (Schema: `connect_backend`)
**15 Models Found:**
- `Project` ✅ (business_id fixed to UUID)
- `Deliverable`
- `Requirement` 
- `InternalTask`
- `ActivityLog`
- `ReviewItem`
- `SagaState`
- `TaskProgress`
- `ClientFeedback`
- `ProjectOutput`
- `RequirementFile`
- `TaskDeliverableAssociation`
- `ProjectTimeline`
- `RequirementTemplate`

### 2. auth-service (Schema: `auth_service`)
**8 Models Found:**
- `Business`
- `User`
- `Role`
- `Permission`
- `RefreshToken`
- `ServiceClient`
- `PermissionAuditLog`
- `RateLimitUsage`

### 3. platform-service (Schema: `platform_service`)
**5 Models Found:**
- `Notification`
- `NotificationPreference`
- `FileFeature`
- `Content`
- `ContentIdMapping`

## 🐳 Docker-Based Database Recreation

Since you're running everything in Docker containers, I've created a comprehensive Docker-compatible solution:

### 🗂️ Files Created:
- **`database_recreation.sql`** - Complete SQL script to recreate all schemas and tables
- **`recreate_database_docker.sh`** - Docker execution script
- **`verify_database.sql`** - Verification script to ensure everything was created correctly

## 🔧 Quick Start

### Step 1: Ensure Files Are Present

Make sure these files are in your current directory:
```bash
ls -la database_recreation.sql recreate_database_docker.sh verify_database.sql
```

### Step 2: Run Database Recreation

**Option A: Using docker-compose (Recommended)**
```bash
# Dry run first to see what will happen
./recreate_database_docker.sh --docker-compose --dry-run

# Execute the recreation
./recreate_database_docker.sh --docker-compose
```

**Option B: Using standalone Docker container**
```bash
# For container named 'postgres'
./recreate_database_docker.sh --container postgres

# For custom container name
./recreate_database_docker.sh --container your_postgres_container_name
```

**Option C: Custom Configuration**
```bash
# With custom settings
./recreate_database_docker.sh \
  --docker-compose \
  --container db \
  --database your_db_name \
  --user your_db_user \
  --password your_db_password
```

### Step 3: Verify Recreation

**Run verification via Docker:**
```bash
# For docker-compose
docker-compose exec postgres psql -U convrse_user -d convrse_db -f /tmp/verify_database.sql

# For standalone container
docker exec -i postgres_container psql -U convrse_user -d convrse_db < verify_database.sql
```

## 📋 Expected Output

The script will show detailed progress:

```
================================================================
🗃️  CONVRSE DATABASE RECREATION (DOCKER)
================================================================
Container: postgres
Database: convrse_db
User: convrse_user
SQL File: database_recreation.sql
Mode: EXECUTION
Docker: docker-compose
================================================================

⚠️  This will PERMANENTLY DELETE all data in the database!
Do you want to continue? (yes/no): yes

[INFO] Starting database recreation process...
[SUCCESS] SQL file found: database_recreation.sql
[SUCCESS] Container 'postgres' is running
[INFO] Testing database connection
[SUCCESS] Testing database connection completed
[INFO] Copying SQL file to container
[SUCCESS] Copying SQL file to container completed
[INFO] Executing database recreation SQL
[SUCCESS] Executing database recreation SQL completed
[INFO] Verifying database recreation
[SUCCESS] Verifying database recreation completed

================================================================
🎉 Database recreation completed successfully!
================================================================

Next steps:
1. Restart your application containers
2. Verify that applications can connect to the database
3. Run any data seeding scripts if needed
```

## 🚨 Important Changes Made

### ✅ Fixed business_id in Project Model

**Before:**
```python
business_id = Column(String(255), nullable=False, index=True)
```

**After:**
```python
business_id = Column(UUID(as_uuid=True), nullable=False, index=True)
```

This ensures the `business_id` field matches the UUID format used in the auth-service `Business` model.

## 🗂️ Database Schema Organization

```
convrse_db (PostgreSQL Database)
├── connect_backend (schema)
│   ├── projects ✅ (business_id now UUID)
│   ├── deliverables  
│   ├── requirements
│   ├── internal_tasks
│   ├── activity_logs
│   ├── review_items
│   ├── saga_state
│   ├── task_progress
│   ├── client_feedbacks
│   ├── project_outputs
│   ├── requirement_files
│   ├── task_deliverable_associations
│   ├── project_timeline
│   └── requirement_templates
├── auth_service (schema)
│   ├── businesses
│   ├── users
│   ├── roles
│   ├── permissions
│   ├── user_roles
│   ├── role_permissions
│   ├── refresh_tokens
│   ├── service_clients
│   ├── permission_audit_logs
│   └── rate_limit_usage
└── platform_service (schema)
    ├── notifications
    ├── notification_preferences
    ├── file_features
    ├── contents
    └── content_id_mapping
```

## 🛠️ Manual Docker Commands

If the script doesn't work for your setup, you can run the commands manually:

### For docker-compose:

1. **Copy SQL file to container:**
   ```bash
   docker cp database_recreation.sql $(docker-compose ps -q postgres):/tmp/
   ```

2. **Execute recreation:**
   ```bash
   docker-compose exec postgres psql -U convrse_user -d convrse_db -f /tmp/database_recreation.sql
   ```

3. **Verify results:**
   ```bash
   docker cp verify_database.sql $(docker-compose ps -q postgres):/tmp/
   docker-compose exec postgres psql -U convrse_user -d convrse_db -f /tmp/verify_database.sql
   ```

### For standalone container:

1. **Copy SQL file to container:**
   ```bash
   docker cp database_recreation.sql postgres_container:/tmp/
   ```

2. **Execute recreation:**
   ```bash
   docker exec -i postgres_container psql -U convrse_user -d convrse_db -f /tmp/database_recreation.sql
   ```

3. **Verify results:**
   ```bash
   docker cp verify_database.sql postgres_container:/tmp/
   docker exec -i postgres_container psql -U convrse_user -d convrse_db -f /tmp/verify_database.sql
   ```

## 🛠️ Troubleshooting

### Common Issues:

1. **Permission Denied:**
   ```bash
   chmod +x recreate_database_docker.sh
   ```

2. **Container Not Found:**
   - Check your container name: `docker ps`
   - For docker-compose: `docker-compose ps`

3. **Connection Refused:**
   - Ensure PostgreSQL container is running
   - Check container logs: `docker logs container_name`

4. **Wrong Database Credentials:**
   - Update the script parameters
   - Check your docker-compose.yml or container environment variables

### Check Container Status:
```bash
# List running containers
docker ps

# Check docker-compose services
docker-compose ps

# Check PostgreSQL logs
docker logs postgres_container_name
```

### Test Database Connection:
```bash
# Test connection manually
docker exec -it postgres_container psql -U convrse_user -d convrse_db -c "SELECT current_database();"
```

## 🎯 Next Steps After Recreation

1. **Restart Application Containers:**
   ```bash
   docker-compose restart
   # or for specific services
   docker-compose restart convrse-connect-backend auth-service platform-service
   ```

2. **Verify Application Connectivity:**
   - Check application logs for database connection errors
   - Test API endpoints to ensure they can read/write to database

3. **Create Initial Data:**
   - Create a test business in auth-service
   - Create a test user
   - Create a test project in ConvrseConnectBackend

4. **Run Verification Again:**
   ```bash
   # Run the verification script to double-check
   docker-compose exec postgres psql -U convrse_user -d convrse_db -f /tmp/verify_database.sql
   ```

## 📞 Support

If you encounter issues:

1. **Check the script output** for specific error messages
2. **Verify your Docker setup** is working correctly
3. **Test database connectivity** manually using the commands above
4. **Check container logs** for PostgreSQL errors

The scripts provide comprehensive error handling and detailed logging to help identify any issues during the recreation process.

## 🔍 Script Options

The `recreate_database_docker.sh` script supports various options:

```bash
# Show help
./recreate_database_docker.sh --help

# Use docker-compose
./recreate_database_docker.sh --docker-compose

# Custom container name
./recreate_database_docker.sh --container my_postgres

# Custom database credentials
./recreate_database_docker.sh --database mydb --user myuser --password mypass

# Dry run to see what would happen
./recreate_database_docker.sh --dry-run

# Custom SQL file
./recreate_database_docker.sh --file my_custom_recreation.sql
```

This Docker-based approach ensures compatibility with your containerized environment and provides a reliable way to recreate your database schemas and tables. 