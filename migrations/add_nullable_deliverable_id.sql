-- Migration: Allow deliverable_id to be nullable in internal_tasks table
-- This enables project-level tasks that are not tied to specific deliverables

-- Make deliverable_id nullable
ALTER TABLE internal_tasks ALTER COLUMN deliverable_id DROP NOT NULL;

-- Add a comment to explain the change
COMMENT ON COLUMN internal_tasks.deliverable_id IS 'Foreign key to deliverables table. Nullable for project-level tasks that are not tied to specific deliverables.';

-- Optional: Add an index for project-level tasks (where deliverable_id is NULL)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_internal_tasks_project_level 
ON internal_tasks (project_id, task_type) 
WHERE deliverable_id IS NULL; 