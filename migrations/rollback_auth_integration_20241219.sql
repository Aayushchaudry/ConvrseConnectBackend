-- Rollback Migration: Auth Integration for ConvrseConnectBackend
-- Date: 2024-12-19
-- Description: Rollback auth integration changes

-- Drop activity_logs table
DROP TABLE IF EXISTS activity_logs;

-- Remove auth integration columns from deliverables
ALTER TABLE deliverables 
DROP COLUMN IF EXISTS assigned_to,
DROP COLUMN IF EXISTS created_by;

-- Remove auth integration columns from projects
ALTER TABLE projects 
DROP COLUMN IF EXISTS business_id,
DROP COLUMN IF EXISTS created_by,
DROP COLUMN IF EXISTS assigned_to;

-- Note: Indexes will be automatically dropped when columns are dropped 