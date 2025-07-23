#!/bin/bash

# ================================================================
# DOCKER INIT-DB EXECUTION SCRIPT
# ================================================================
# This script runs the init-db.sql file in Docker containers
# Works with docker-compose or standalone PostgreSQL containers
# ================================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default configuration
DB_CONTAINER_NAME="postgres"
DB_NAME="convrse_db"
DB_USER="convrse_user"
DB_PASSWORD="convrse_password"
POSTGRES_USER="postgres"
POSTGRES_PASSWORD="postgres"
INIT_SQL_PATH="../infra/environments/local/configs/init-db.sql"

# Print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Help function
show_help() {
    echo "Docker Init-DB Execution Script"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -c, --container NAME       PostgreSQL container name (default: postgres)"
    echo "  -d, --database NAME        Database name (default: convrse_db)"
    echo "  -u, --user NAME           Application user (default: convrse_user)"
    echo "  -p, --password PASS       Application user password (default: convrse_password)"
    echo "  --postgres-user NAME      PostgreSQL superuser (default: postgres)"
    echo "  --postgres-password PASS  PostgreSQL superuser password (default: postgres)"
    echo "  -f, --file FILE           Init SQL file path (default: infra/environments/local/configs/init-db.sql)"
    echo "  --dry-run                 Show commands without executing"
    echo "  --docker-compose          Use docker-compose exec instead of docker exec"
    echo "  --create-db               Create database and user first"
    echo "  -h, --help                Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Use default settings"
    echo "  $0 --docker-compose                  # Use docker-compose"
    echo "  $0 --container my_postgres            # Use custom container name"
    echo "  $0 --create-db                       # Create database and user first"
    echo "  $0 --dry-run                         # See what would be executed"
}

# Parse command line arguments
DRY_RUN=false
USE_DOCKER_COMPOSE=false
CREATE_DB=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -c|--container)
            DB_CONTAINER_NAME="$2"
            shift 2
            ;;
        -d|--database)
            DB_NAME="$2"
            shift 2
            ;;
        -u|--user)
            DB_USER="$2"
            shift 2
            ;;
        -p|--password)
            DB_PASSWORD="$2"
            shift 2
            ;;
        --postgres-user)
            POSTGRES_USER="$2"
            shift 2
            ;;
        --postgres-password)
            POSTGRES_PASSWORD="$2"
            shift 2
            ;;
        -f|--file)
            INIT_SQL_PATH="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --docker-compose)
            USE_DOCKER_COMPOSE=true
            shift
            ;;
        --create-db)
            CREATE_DB=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Function to execute Docker command
execute_docker_cmd() {
    local cmd="$1"
    local description="$2"
    
    if [ "$DRY_RUN" = true ]; then
        print_info "DRY RUN: $description"
        echo "Command: $cmd"
        return 0
    fi
    
    print_info "$description"
    if eval "$cmd"; then
        print_success "$description completed"
        return 0
    else
        print_error "$description failed"
        return 1
    fi
}

# Check if SQL file exists
check_sql_file() {
    if [ ! -f "$INIT_SQL_PATH" ]; then
        print_error "SQL file not found: $INIT_SQL_PATH"
        echo "Please ensure the init-db.sql file exists."
        exit 1
    fi
    print_success "SQL file found: $INIT_SQL_PATH"
}

# Check if container exists and is running
check_container() {
    local check_cmd
    if [ "$USE_DOCKER_COMPOSE" = true ]; then
        check_cmd="docker-compose ps -q $DB_CONTAINER_NAME"
    else
        check_cmd="docker ps -q -f name=$DB_CONTAINER_NAME"
    fi
    
    if [ "$DRY_RUN" = true ]; then
        print_info "DRY RUN: Would check container status"
        return 0
    fi
    
    local container_id=$(eval "$check_cmd")
    if [ -z "$container_id" ]; then
        print_error "Container '$DB_CONTAINER_NAME' not found or not running"
        echo "Please ensure your PostgreSQL container is running."
        echo "For docker-compose: docker-compose up -d"
        echo "For standalone container: docker run -d --name $DB_CONTAINER_NAME postgres"
        exit 1
    fi
    print_success "Container '$DB_CONTAINER_NAME' is running"
}

# Create database and user if needed
create_database_and_user() {
    if [ "$CREATE_DB" = false ]; then
        return 0
    fi
    
    local setup_sql="
-- Create database if not exists
SELECT 'CREATE DATABASE $DB_NAME' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')\\gexec

-- Connect to the database
\\c $DB_NAME

-- Create user if not exists
DO \\$\\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = '$DB_USER') THEN
        CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';
    END IF;
END
\\$\\$;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
GRANT ALL ON SCHEMA public TO $DB_USER;
ALTER USER $DB_USER CREATEDB;
"
    
    local create_cmd
    if [ "$USE_DOCKER_COMPOSE" = true ]; then
        create_cmd="echo \"$setup_sql\" | docker-compose exec -T $DB_CONTAINER_NAME psql -U $POSTGRES_USER"
    else
        create_cmd="echo \"$setup_sql\" | docker exec -i $DB_CONTAINER_NAME psql -U $POSTGRES_USER"
    fi
    
    execute_docker_cmd "$create_cmd" "Creating database and user"
}

# Test database connection
test_connection() {
    local test_cmd
    if [ "$USE_DOCKER_COMPOSE" = true ]; then
        test_cmd="docker-compose exec -T $DB_CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -c 'SELECT current_database();'"
    else
        test_cmd="docker exec -i $DB_CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -c 'SELECT current_database();'"
    fi
    
    execute_docker_cmd "$test_cmd" "Testing database connection"
}

# Execute the init SQL file
execute_init_sql() {
    # Copy SQL file to container
    local copy_cmd
    if [ "$USE_DOCKER_COMPOSE" = true ]; then
        copy_cmd="docker cp $INIT_SQL_PATH \$(docker-compose ps -q $DB_CONTAINER_NAME):/tmp/init-db.sql"
    else
        copy_cmd="docker cp $INIT_SQL_PATH $DB_CONTAINER_NAME:/tmp/init-db.sql"
    fi
    
    execute_docker_cmd "$copy_cmd" "Copying init SQL file to container"
    
    # Execute SQL file
    local sql_cmd
    if [ "$USE_DOCKER_COMPOSE" = true ]; then
        sql_cmd="docker-compose exec -T $DB_CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -f /tmp/init-db.sql"
    else
        sql_cmd="docker exec -i $DB_CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -f /tmp/init-db.sql"
    fi
    
    execute_docker_cmd "$sql_cmd" "Executing init-db.sql"
}

# Verify initialization
verify_initialization() {
    local verify_sql="
        SELECT 'Schema verification:' as info, COUNT(*) as schema_count 
        FROM information_schema.schemata 
        WHERE schema_name IN ('next_cms', 'connect_backend', 'conversation_summariser', 'auth_service', 'platform_service', 'analytics_backend', 'floor_selector', 'sales_apps', 'notifications');
        
        SELECT 'Tables created:' as info, schema_name, COUNT(*) as table_count
        FROM information_schema.tables 
        WHERE table_schema IN ('next_cms', 'connect_backend', 'conversation_summariser', 'auth_service', 'platform_service', 'analytics_backend', 'floor_selector', 'sales_apps', 'notifications')
        GROUP BY schema_name
        ORDER BY schema_name;
        
        SELECT 'Users created:' as info, COUNT(*) as user_count
        FROM auth_service.users;
        
        SELECT 'Businesses created:' as info, COUNT(*) as business_count
        FROM auth_service.businesses;
    "
    
    local verify_cmd
    if [ "$USE_DOCKER_COMPOSE" = true ]; then
        verify_cmd="echo \"$verify_sql\" | docker-compose exec -T $DB_CONTAINER_NAME psql -U $DB_USER -d $DB_NAME"
    else
        verify_cmd="echo \"$verify_sql\" | docker exec -i $DB_CONTAINER_NAME psql -U $DB_USER -d $DB_NAME"
    fi
    
    execute_docker_cmd "$verify_cmd" "Verifying database initialization"
}

# Main execution
main() {
    echo "================================================================"
    echo "🗃️  CONVRSE INIT-DB EXECUTION (DOCKER)"
    echo "================================================================"
    echo "Container: $DB_CONTAINER_NAME"
    echo "Database: $DB_NAME"
    echo "User: $DB_USER"
    echo "SQL File: $INIT_SQL_PATH"
    echo "Mode: $([ "$DRY_RUN" = true ] && echo "DRY RUN" || echo "EXECUTION")"
    echo "Docker: $([ "$USE_DOCKER_COMPOSE" = true ] && echo "docker-compose" || echo "docker exec")"
    echo "Create DB: $([ "$CREATE_DB" = true ] && echo "Yes" || echo "No")"
    echo "================================================================"
    
    if [ "$DRY_RUN" = false ] && [ "$CREATE_DB" = false ]; then
        echo ""
        print_warning "⚠️  Make sure the database '$DB_NAME' and user '$DB_USER' exist!"
        print_warning "⚠️  Use --create-db flag to create them automatically."
        echo ""
        read -p "Do you want to continue? (yes/no): " -r
        if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            print_info "Operation cancelled"
            exit 0
        fi
    fi
    
    echo ""
    print_info "Starting database initialization process..."
    
    # Step 1: Check prerequisites
    check_sql_file
    check_container
    
    # Step 2: Create database and user (if requested)
    create_database_and_user
    
    # Step 3: Test connection
    test_connection
    
    # Step 4: Execute init SQL
    execute_init_sql
    
    # Step 5: Verify results
    verify_initialization
    
    echo ""
    echo "================================================================"
    print_success "🎉 Database initialization completed successfully!"
    echo "================================================================"
    echo ""
    echo "Database initialized with:"
    echo "- All microservice schemas created"
    echo "- Default permissions and roles set up"
    echo "- Demo businesses and users created"
    echo "- Service clients configured"
    echo ""
    echo "Next steps:"
    echo "1. Restart your application containers"
    echo "2. Test API endpoints to verify connectivity"
    echo "3. Check application logs for any issues"
    echo ""
}

# Run main function
main "$@" 