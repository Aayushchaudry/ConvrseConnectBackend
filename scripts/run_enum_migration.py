#!/usr/bin/env python3
"""
Script to run the ReviewItemType enum migration
Uses database connection info from docker-compose.yml
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

def run_migration():
    """Run the enum migration"""
    migration_sql = """
    -- Migration: Add Business-Specific Review Item Types
    -- Date: 2024-12-23
    -- Description: Add business-specific enum values to ReviewItemType for production workflow

    -- Add new enum values to the existing ReviewItemType enum
    ALTER TYPE connect_backend.reviewitemtype ADD VALUE IF NOT EXISTS 'static_render';
    ALTER TYPE connect_backend.reviewitemtype ADD VALUE IF NOT EXISTS 'texture_review';
    ALTER TYPE connect_backend.reviewitemtype ADD VALUE IF NOT EXISTS 'final_render';
    ALTER TYPE connect_backend.reviewitemtype ADD VALUE IF NOT EXISTS 'work_review';

    -- Comments for documentation
    COMMENT ON TYPE connect_backend.reviewitemtype IS 'Enum for review item types including generic content types and business-specific production workflow types';
    """
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        print("Running ReviewItemType enum migration...")
        cursor.execute(migration_sql)
        print("✅ Migration completed successfully!")
        
        # Verify the enum values were added
        cursor.execute("""
            SELECT enumlabel 
            FROM pg_enum e 
            JOIN pg_type t ON e.enumtypid = t.oid 
            WHERE t.typname = 'reviewitemtype'
            AND t.typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'connect_backend')
            ORDER BY enumlabel;
        """)
        
        enum_values = [row[0] for row in cursor.fetchall()]
        print(f"Current ReviewItemType enum values: {enum_values}")
        
        # Check if our new values are present
        new_values = ['static_render', 'texture_review', 'final_render', 'work_review']
        missing_values = [v for v in new_values if v not in enum_values]
        
        if missing_values:
            print(f"⚠️  Warning: Some enum values were not added: {missing_values}")
        else:
            print("✅ All new enum values successfully added!")
            
    except psycopg2.Error as e:
        print(f"❌ Error running migration: {e}")
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    print("ReviewItemType Enum Migration Script")
    print("=" * 40)
    
    # Check if postgres service is running
    print("Checking database connection...")
    run_migration() 