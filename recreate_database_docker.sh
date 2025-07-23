#!/bin/bash

# ================================================================
# DOCKER DATABASE RECREATION SCRIPT
# ================================================================
# This script recreates the database using Docker containers
# Works with docker-compose or standalone containers
# ================================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DB_CONTAINER_NAME="postgres"  # Default container name
DB_NAME="convrse_db"
DB_USER="convrse_user"
DB_PASSWORD="convrse_password"
SQL_FILE="database_recreation.sql"

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
    echo "Database Recreation Script for Docker"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -c, --container NAME    PostgreSQL container name (default: postgres)"
    echo "  -d, --database NAME     Database name (default: convrse_db)"
    echo "  -u, --user NAME         Database user (default: convrse_user)"
    echo "  -p, --password PASS     Database password (default: convrse_password)"
    echo "  -f, --file FILE         SQL file path (default: database_recreation.sql)"
    echo "  --dry-run              Show commands without executing"
    echo "  --docker-compose       Use docker-compose exec instead of docker exec"
    echo "  -h, --help             Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Use default settings"
    echo "  $0 --container my_postgres            # Use custom container name"
    echo "  $0 --docker-compose                  # Use docker-compose"
    echo "  $0 --dry-run                         # See what would be executed"
}

# Parse command line arguments
DRY_RUN=false
USE_DOCKER_COMPOSE=false

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
        -f|--file)
            SQL_FILE="$2"
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
    if [ ! -f "$SQL_FILE" ]; then
        print_error "SQL file not found: $SQL_FILE"
        echo "Please ensure the database_recreation.sql file exists in the current directory."
        exit 1
    fi
    print_success "SQL file found: $SQL_FILE"
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

# Test database connection
test_connection() {
    local test_cmd
    if [ "$USE_DOCKER_COMPOSE" = true ]; then
        test_cmd="docker-compose exec -T $DB_CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -c 'SELECT 1;'"
    else
        test_cmd="docker exec -i $DB_CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -c 'SELECT 1;'"
    fi
    
    execute_docker_cmd "$test_cmd" "Testing database connection"
}

# Execute the SQL file
execute_sql() {
    local sql_cmd
    if [ "$USE_DOCKER_COMPOSE" = true ]; then
        sql_cmd="docker-compose exec -T $DB_CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -f /tmp/database_recreation.sql"
        # Copy file to container first
        execute_docker_cmd "docker cp $SQL_FILE \$(docker-compose ps -q $DB_CONTAINER_NAME):/tmp/database_recreation.sql" "Copying SQL file to container"
    else
        sql_cmd="docker exec -i $DB_CONTAINER_NAME psql -U $DB_USER -d $DB_NAME < $SQL_FILE"
        # Copy file to container first
        execute_docker_cmd "docker cp $SQL_FILE $DB_CONTAINER_NAME:/tmp/database_recreation.sql" "Copying SQL file to container"
        sql_cmd="docker exec -i $DB_CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -f /tmp/database_recreation.sql"
    fi
    
    execute_docker_cmd "$sql_cmd" "Executing database recreation SQL"
}

# Verify recreation
verify_recreation() {
    local verify_cmd
    local verification_sql="
        SELECT 
            'Schema verification:' as info,
            COUNT(*) as schema_count 
        FROM information_schema.schemata 
        WHERE schema_name IN ('connect_backend', 'auth_service', 'platform_service');
        
        SELECT 
            'Tables created:' as info,
            schema_name,
            COUNT(*) as table_count
        FROM information_schema.tables 
        WHERE table_schema IN ('connect_backend', 'auth_service', 'platform_service')
        GROUP BY schema_name
        ORDER BY schema_name;
    "
    
    if [ "$USE_DOCKER_COMPOSE" = true ]; then
        verify_cmd="docker-compose exec -T $DB_CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -c \"$verification_sql\""
    else
        verify_cmd="docker exec -i $DB_CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -c \"$verification_sql\""
    fi
    
    execute_docker_cmd "$verify_cmd" "Verifying database recreation"
}

# Main execution
main() {
    echo "================================================================"
    echo "🗃️  CONVRSE DATABASE RECREATION (DOCKER)"
    echo "================================================================"
    echo "Container: $DB_CONTAINER_NAME"
    echo "Database: $DB_NAME"
    echo "User: $DB_USER"
    echo "SQL File: $SQL_FILE"
    echo "Mode: $([ "$DRY_RUN" = true ] && echo "DRY RUN" || echo "EXECUTION")"
    echo "Docker: $([ "$USE_DOCKER_COMPOSE" = true ] && echo "docker-compose" || echo "docker exec")"
    echo "================================================================"
    
    if [ "$DRY_RUN" = false ]; then
        echo ""
        print_warning "⚠️  This will PERMANENTLY DELETE all data in the database!"
        read -p "Do you want to continue? (yes/no): " -r
        if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            print_info "Operation cancelled"
            exit 0
        fi
    fi
    
    echo ""
    print_info "Starting database recreation process..."
    
    # Step 1: Check prerequisites
    check_sql_file
    check_container
    
    # Step 2: Test connection
    test_connection
    
    # Step 3: Execute SQL
    execute_sql
    
    # Step 4: Verify results
    verify_recreation
    
    echo ""
    echo "================================================================"
    print_success "🎉 Database recreation completed successfully!"
    echo "================================================================"
    echo ""
    echo "Next steps:"
    echo "1. Restart your application containers"
    echo "2. Verify that applications can connect to the database"
    echo "3. Run any data seeding scripts if needed"
    echo ""
}

# Run main function
main "$@" 