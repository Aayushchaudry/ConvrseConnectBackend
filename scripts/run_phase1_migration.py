#!/usr/bin/env python3
"""
Script to run the Phase 1 Enhanced Task Management migration
Creates new tables and modifies existing tables for enhanced task management, 
deliverable pricing (BOQ), and timeline tracking.
"""

import os
import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def get_db_connection():
    """Get database connection using docker-compose.yml settings"""
    # Database connection parameters from docker-compose.yml
    db_params = {
        'host': 'localhost',  # postgres service accessible on localhost
        'port': '5432',
        'database': 'convrse_db',
        'user': 'convrse_user',
        'password': 'convrse_password'
    }
    
    try:
        conn = psycopg2.connect(**db_params)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        return conn
    except psycopg2.Error as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)

def check_table_exists(cursor, table_name, schema='connect_backend'):
    """Check if a table already exists"""
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = %s 
            AND table_name = %s
        );
    """, (schema, table_name))
    return cursor.fetchone()[0]

def check_column_exists(cursor, table_name, column_name, schema='connect_backend'):
    """Check if a column exists in a table"""
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_schema = %s 
            AND table_name = %s 
            AND column_name = %s
        );
    """, (schema, table_name, column_name))
    return cursor.fetchone()[0]

def run_migration():
    """Run the Phase 1 migration"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        print("🚀 Starting Phase 1: Enhanced Task Management Migration")
        print("=" * 60)
        
        # Read and execute the migration SQL
        migration_file = os.path.join(os.path.dirname(__file__), '..', 'migrations', 'create_enhanced_task_management_tables.sql')
        
        # Check if migration file exists
        if not os.path.exists(migration_file):
            print(f"❌ Migration file not found: {migration_file}")
            sys.exit(1)
        
        print(f"📖 Reading migration from: {migration_file}")
        
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        print("🔧 Executing migration...")
        
        # Execute the migration
        cursor.execute(migration_sql)
        
        print("✅ Migration SQL executed successfully!")
        
        # Verify that new tables were created
        new_tables = [
            'task_deliverable_associations',
            'deliverable_pricing', 
            'task_progress',
            'project_timeline',
            'requirement_templates'
        ]
        
        print("\n📋 Verifying new tables...")
        for table in new_tables:
            exists = check_table_exists(cursor, table)
            status = "✅" if exists else "❌"
            print(f"  {status} {table}: {'Created' if exists else 'NOT FOUND'}")
        
        # Verify that new columns were added to existing tables
        print("\n📋 Verifying new columns...")
        column_checks = [
            ('internal_tasks', 'estimated_hours'),
            ('internal_tasks', 'actual_hours'),
            ('internal_tasks', 'is_project_level'),
            ('internal_tasks', 'task_template_id'),
            ('requirements', 'is_project_level'),
            ('requirements', 'template_id'),
            ('projects', 'calculated_budget'),
            ('projects', 'actual_cost'),
            ('projects', 'budget_variance'),
            ('projects', 'budget_last_calculated'),
        ]
        
        for table, column in column_checks:
            exists = check_column_exists(cursor, table, column)
            status = "✅" if exists else "❌"
            print(f"  {status} {table}.{column}: {'Added' if exists else 'NOT FOUND'}")
        
        # Check if requirement templates were inserted
        cursor.execute("SELECT COUNT(*) FROM connect_backend.requirement_templates;")
        template_count = cursor.fetchone()[0]
        print(f"\n📋 Requirement templates: {template_count} templates inserted")
        
        if template_count > 0:
            print("   ✅ Sample requirement templates created successfully")
        else:
            print("   ⚠️  No requirement templates found")
        
        print("\n🎉 Phase 1 Migration completed successfully!")
        print("=" * 60)
        print("New capabilities:")
        print("• Task-deliverable association tracking")
        print("• Deliverable pricing (BOQ) management")
        print("• Daily task progress tracking")
        print("• Project timeline and milestone management")
        print("• Requirement template system")
        print("• Enhanced budget tracking")
        
    except psycopg2.Error as e:
        print(f"❌ Error running migration: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    print("Enhanced Task Management - Phase 1 Migration")
    print("ConvrseConnect Backend Enhancement")
    print()
    
    # Check if postgres service is running
    print("🔍 Checking database connection...")
    run_migration() 