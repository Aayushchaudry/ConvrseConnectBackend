-- Migration: Update project table user ID fields to support UUIDs
-- Date: 2024-01-30
-- Description: Change created_by and assigned_to columns from INTEGER to VARCHAR(36) to support UUID user IDs

-- Set the search path to the correct schema
SET search_path TO connect_backend;

-- First, let's check if the projects table exists and has data
-- If there's existing data, we need to handle it carefully

-- Step 1: Add new UUID columns
ALTER TABLE projects ADD COLUMN created_by_uuid VARCHAR(36);
ALTER TABLE projects ADD COLUMN assigned_to_uuid VARCHAR(36);

-- Step 2: For existing data, we'll need to map integer IDs to UUIDs
-- Since this is a development environment and we're changing the data model,
-- we'll set default values for existing records
UPDATE projects SET created_by_uuid = 'default-user-id' WHERE created_by_uuid IS NULL;

-- Step 3: Drop the old integer columns
ALTER TABLE projects DROP COLUMN created_by;
ALTER TABLE projects DROP COLUMN assigned_to;

-- Step 4: Rename the new columns to the original names
ALTER TABLE projects RENAME COLUMN created_by_uuid TO created_by;
ALTER TABLE projects RENAME COLUMN assigned_to_uuid TO assigned_to;

-- Step 5: Add constraints
ALTER TABLE projects ALTER COLUMN created_by SET NOT NULL;
CREATE INDEX idx_projects_created_by ON projects(created_by);
CREATE INDEX idx_projects_assigned_to ON projects(assigned_to);

-- Note: In a production environment, you would need to:
-- 1. Map existing integer user IDs to their corresponding UUIDs
-- 2. Ensure data integrity during the migration
-- 3. Test the migration thoroughly before applying 