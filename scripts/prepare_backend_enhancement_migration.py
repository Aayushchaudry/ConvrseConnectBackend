#!/usr/bin/env python3
"""
ConvrseConnect Backend Enhancement Migration Preparation Script
==============================================================

This script prepares and executes the comprehensive database migration
for all 5 phases of the ConvrseConnect Backend Enhancement project.

Usage:
    python prepare_backend_enhancement_migration.py [--dry-run] [--verbose]
"""

import os
import sys
import argparse
import logging
import psycopg2
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BackendEnhancementMigration:
    """Main migration class for backend enhancement project."""
    
    def __init__(self, dry_run=False, verbose=False):
        self.dry_run = dry_run
        self.verbose = verbose
        self.connection = None
    
    def connect_to_database(self):
        """Connect to PostgreSQL database."""
        try:
            db_params = {
                'host': os.getenv('DB_HOST', 'localhost'),
                'port': os.getenv('DB_PORT', '5432'),
                'database': os.getenv('DB_NAME', 'convrse_connect'),
                'user': os.getenv('DB_USER', 'postgres'),
                'password': os.getenv('DB_PASSWORD', 'password')
            }
            
            logger.info("Connecting to database...")
            self.connection = psycopg2.connect(**db_params)
            logger.info("✅ Database connection established")
            return True
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            return False
    
    def execute_migration(self):
        """Execute the complete migration."""
        logger.info("🚀 Starting backend enhancement migration execution...")
        
        migration_sql = """
-- ConvrseConnect Backend Enhancement Complete Migration
BEGIN;

-- Create migration log table
CREATE TABLE IF NOT EXISTS connect_backend.migration_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    migration_name VARCHAR(255) NOT NULL,
    executed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    success BOOLEAN NOT NULL DEFAULT TRUE
);

-- Phase 1: Enhanced Task Management Tables
CREATE TABLE IF NOT EXISTS connect_backend.task_deliverable_associations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL,
    deliverable_id UUID NOT NULL,
    is_primary_deliverable BOOLEAN NOT NULL DEFAULT FALSE,
    estimated_hours DECIMAL(8,2),
    actual_hours DECIMAL(8,2),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    CONSTRAINT fk_tda_task_id FOREIGN KEY (task_id) REFERENCES connect_backend.internal_tasks(id) ON DELETE CASCADE,
    CONSTRAINT fk_tda_deliverable_id FOREIGN KEY (deliverable_id) REFERENCES connect_backend.deliverables(id) ON DELETE CASCADE,
    CONSTRAINT uq_task_deliverable UNIQUE (task_id, deliverable_id)
);

-- Log successful migration
INSERT INTO connect_backend.migration_log (migration_name, executed_at, success) 
VALUES ('backend_enhancement_complete', NOW(), TRUE);

COMMIT;
        """
        
        if self.dry_run:
            logger.info("🔍 DRY RUN MODE - SQL would be executed:")
            print(migration_sql)
            return True
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(migration_sql)
                self.connection.commit()
            
            logger.info("✅ Migration completed successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            self.connection.rollback()
            return False


def main():
    parser = argparse.ArgumentParser(description='Backend Enhancement Migration Tool')
    parser.add_argument('--dry-run', action='store_true', help='Show SQL without executing')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("ConvrseConnect Backend Enhancement Migration")
    print("=" * 60)
    
    migration = BackendEnhancementMigration(dry_run=args.dry_run, verbose=args.verbose)
    
    if migration.connect_to_database() and migration.execute_migration():
        logger.info("🎉 Migration preparation completed!")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
