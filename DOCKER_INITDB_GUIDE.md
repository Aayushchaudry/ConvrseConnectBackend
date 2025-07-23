# Docker Init-DB Execution Guide

## 🐳 Running init-db.sql in Docker Containers

Since you're running everything in Docker, here's a comprehensive guide for executing the `init-db.sql` script with proper user credentials and database setup.

## 🚀 Quick Start (Recommended)

Use our automated script for the easiest setup:

```bash
# For docker-compose (most common)
./run_initdb_docker.sh --docker-compose --create-db

# For standalone container
./run_initdb_docker.sh --container postgres --create-db

# Dry run to see what will happen
./run_initdb_docker.sh --docker-compose --dry-run
```

## 📋 Script Options

The `run_initdb_docker.sh` script supports various configurations:

### Basic Options:
- `--docker-compose` - Use docker-compose exec (recommended)
- `--container NAME` - Specify container name (default: postgres)
- `--create-db` - Create database and user automatically
- `--dry-run` - Show commands without executing

### Database Configuration:
- `--database NAME` - Database name (default: convrse_db)
- `--user NAME` - Application user (default: convrse_user)
- `--password PASS` - Application password (default: convrse_password)
- `--postgres-user NAME` - PostgreSQL superuser (default: postgres)
- `--postgres-password PASS` - PostgreSQL superuser password (default: postgres)

### File Location:
- `--file PATH` - Custom init SQL file path (default: infra/environments/local/configs/init-db.sql)

## 🔧 Manual Docker Commands

If you prefer to run commands manually:

### Method 1: Docker Compose (Recommended)

```bash
# 1. Copy the SQL file to the container
docker cp infra/environments/local/configs/init-db.sql $(docker-compose ps -q postgres):/tmp/init-db.sql

# 2. Execute the SQL file as the application user
docker-compose exec postgres psql -U convrse_user -d convrse_db -f /tmp/init-db.sql

# 3. Verify the setup
docker-compose exec postgres psql -U convrse_user -d convrse_db -c "
SELECT schema_name FROM information_schema.schemata 
WHERE schema_name IN ('auth_service', 'connect_backend', 'platform_service');
"
```

### Method 2: Standalone Docker Container

```bash
# 1. Copy the SQL file to the container
docker cp infra/environments/local/configs/init-db.sql postgres:/tmp/init-db.sql

# 2. Execute the SQL file
docker exec -i postgres psql -U convrse_user -d convrse_db -f /tmp/init-db.sql

# 3. Verify the setup
docker exec -i postgres psql -U convrse_user -d convrse_db -c "
SELECT COUNT(*) as businesses FROM auth_service.businesses;
"
```

### Method 3: Using Environment Variables

If your Docker setup uses environment variables for credentials:

```bash
# Set environment variables
export DB_HOST=localhost
export DB_NAME=convrse_db
export DB_USER=convrse_user
export DB_PASSWORD=convrse_password

# Execute with environment variables
docker-compose exec postgres psql -U $DB_USER -d $DB_NAME -f /tmp/init-db.sql
```

## 🛠️ Setting Up Database and User

If the database and user don't exist, create them first:

### Option A: Using Superuser Access

```bash
# Connect as postgres superuser
docker-compose exec postgres psql -U postgres

# In psql, run these commands:
CREATE DATABASE convrse_db;
CREATE USER convrse_user WITH PASSWORD 'convrse_password';
GRANT ALL PRIVILEGES ON DATABASE convrse_db TO convrse_user;
ALTER USER convrse_user CREATEDB;
\q
```

### Option B: Using Our Script (Automated)

```bash
# The script will create database and user automatically
./run_initdb_docker.sh --docker-compose --create-db
```

## 🔍 Different Docker Setup Scenarios

### Scenario 1: Standard docker-compose.yml

```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:14
    environment:
      POSTGRES_DB: convrse_db
      POSTGRES_USER: convrse_user
      POSTGRES_PASSWORD: convrse_password
    ports:
      - "5432:5432"
```

**Command:**
```bash
./run_initdb_docker.sh --docker-compose
```

### Scenario 2: Custom Container Name

```yaml
# docker-compose.yml
services:
  database:  # Custom name
    image: postgres:14
    environment:
      POSTGRES_DB: convrse_db
      POSTGRES_USER: convrse_user
      POSTGRES_PASSWORD: convrse_password
```

**Command:**
```bash
./run_initdb_docker.sh --docker-compose --container database
```

### Scenario 3: Different Database Credentials

```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:14
    environment:
      POSTGRES_DB: my_custom_db
      POSTGRES_USER: my_user
      POSTGRES_PASSWORD: my_password
```

**Command:**
```bash
./run_initdb_docker.sh --docker-compose \
  --database my_custom_db \
  --user my_user \
  --password my_password
```

### Scenario 4: Standalone Docker Container

```bash
# Running PostgreSQL as standalone container
docker run -d \
  --name postgres \
  -e POSTGRES_DB=convrse_db \
  -e POSTGRES_USER=convrse_user \
  -e POSTGRES_PASSWORD=convrse_password \
  -p 5432:5432 \
  postgres:14
```

**Command:**
```bash
./run_initdb_docker.sh --container postgres
```

## 🚨 Troubleshooting

### Problem: "database does not exist"

**Solution:** Create the database first
```bash
./run_initdb_docker.sh --docker-compose --create-db
```

### Problem: "role does not exist"

**Solution:** Create the user with proper permissions
```bash
docker-compose exec postgres psql -U postgres -c "
CREATE USER convrse_user WITH PASSWORD 'convrse_password';
GRANT ALL PRIVILEGES ON DATABASE convrse_db TO convrse_user;
ALTER USER convrse_user CREATEDB;
"
```

### Problem: "permission denied for schema"

**Solution:** Grant schema permissions
```bash
docker-compose exec postgres psql -U postgres -d convrse_db -c "
GRANT ALL ON SCHEMA public TO convrse_user;
GRANT USAGE, CREATE ON SCHEMA public TO convrse_user;
"
```

### Problem: "container not found"

**Solution:** Check container name and status
```bash
# List running containers
docker ps

# For docker-compose
docker-compose ps

# Start containers if needed
docker-compose up -d
```

### Problem: "connection refused"

**Solution:** Ensure PostgreSQL is ready
```bash
# Check if PostgreSQL is accepting connections
docker-compose exec postgres pg_isready -U convrse_user -d convrse_db

# Check container logs
docker-compose logs postgres
```

## ✅ Verification Commands

After running init-db.sql, verify the setup:

### Check Schemas Created:
```bash
docker-compose exec postgres psql -U convrse_user -d convrse_db -c "
SELECT schema_name FROM information_schema.schemata 
WHERE schema_name IN ('auth_service', 'connect_backend', 'platform_service', 'conversation_summariser', 'analytics_backend', 'floor_selector', 'sales_apps', 'notifications');
"
```

### Check Tables Created:
```bash
docker-compose exec postgres psql -U convrse_user -d convrse_db -c "
SELECT table_schema, COUNT(*) as table_count
FROM information_schema.tables 
WHERE table_schema IN ('auth_service', 'connect_backend', 'platform_service')
GROUP BY table_schema;
"
```

### Check Demo Data:
```bash
docker-compose exec postgres psql -U convrse_user -d convrse_db -c "
SELECT 'Users' as type, COUNT(*) as count FROM auth_service.users
UNION ALL
SELECT 'Businesses' as type, COUNT(*) as count FROM auth_service.businesses
UNION ALL
SELECT 'Roles' as type, COUNT(*) as count FROM auth_service.roles;
"
```

### Check UUID Fields:
```bash
docker-compose exec postgres psql -U convrse_user -d convrse_db -c "
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_schema = 'auth_service' 
AND table_name = 'businesses' 
AND column_name = 'business_id';
"
```

Expected output: `business_id | uuid`

## 📊 What Gets Created

The init-db.sql script creates:

### Schemas:
- `auth_service` - User authentication and business management
- `connect_backend` - Project and deliverable management  
- `platform_service` - File management and notifications
- `conversation_summariser` - Meeting analysis and summaries
- `analytics_backend` - Analytics and event tracking
- `floor_selector` - Indoor navigation
- `sales_apps` - Sales application data
- `notifications` - Notification system

### Demo Data:
- **Default Convrse business** with admin user
- **Demo businesses** for testing
- **System permissions** and roles
- **Service client** configurations
- **File feature** templates

### Key Features:
- ✅ **UUID consistency** for business_id across all services
- ✅ **Proper foreign keys** and relationships
- ✅ **Comprehensive permissions** system
- ✅ **Demo data** for development
- ✅ **Cross-service** compatibility

## 🎯 Best Practices

1. **Always use --dry-run first** to see what will happen
2. **Use --create-db** for fresh setups
3. **Verify with the verification commands** after execution
4. **Keep credentials consistent** across your docker-compose.yml
5. **Backup existing data** before running if you have important data

## 🔗 Integration with Your Application

After successful initialization:

1. **Update your application** connection strings to use the same credentials
2. **Restart application containers** to pick up the new database
3. **Test API endpoints** to ensure connectivity
4. **Check application logs** for any database-related errors

The database is now ready with all schemas, demo data, and proper UUID types for seamless integration across all your microservices! 🎉 