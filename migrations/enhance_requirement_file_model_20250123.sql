-- Migration: Enhance RequirementFile model for platform-service integration
-- Date: 2025-01-23
-- Description: Add platform_file_id, file_size, uploaded_by, upload_timestamp, and is_active columns
--              to support enhanced file upload infrastructure with dual context support

-- Add new columns to requirement_files table
ALTER TABLE connect_backend.requirement_files 
ADD COLUMN IF NOT EXISTS platform_file_id UUID,
ADD COLUMN IF NOT EXISTS file_size INTEGER,
ADD COLUMN IF NOT EXISTS uploaded_by UUID,
ADD COLUMN IF NOT EXISTS upload_timestamp TIMESTAMP DEFAULT NOW(),
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

-- Make file_path nullable since we're moving to platform_file_id as primary reference
ALTER TABLE connect_backend.requirement_files 
ALTER COLUMN file_path DROP NOT NULL;

-- Create indexes for performance optimization
CREATE INDEX IF NOT EXISTS idx_requirement_files_platform_file_id 
ON connect_backend.requirement_files(platform_file_id);

CREATE INDEX IF NOT EXISTS idx_requirement_files_requirement_id_active 
ON connect_backend.requirement_files(requirement_id, is_active);

CREATE INDEX IF NOT EXISTS idx_requirement_files_uploaded_by 
ON connect_backend.requirement_files(uploaded_by);

CREATE INDEX IF NOT EXISTS idx_requirement_files_upload_timestamp 
ON connect_backend.requirement_files(upload_timestamp);

-- Add composite index for common queries
CREATE INDEX IF NOT EXISTS idx_requirement_files_req_type_active 
ON connect_backend.requirement_files(requirement_id, file_type, is_active);

-- Update existing records to set default values
UPDATE connect_backend.requirement_files 
SET 
    upload_timestamp = COALESCE(created_at, NOW()),
    is_active = TRUE
WHERE upload_timestamp IS NULL OR is_active IS NULL;

-- Add comments for documentation
COMMENT ON COLUMN connect_backend.requirement_files.platform_file_id IS 'Reference to file stored in platform-service';
COMMENT ON COLUMN connect_backend.requirement_files.file_size IS 'File size in bytes';
COMMENT ON COLUMN connect_backend.requirement_files.uploaded_by IS 'User ID who uploaded the file';
COMMENT ON COLUMN connect_backend.requirement_files.upload_timestamp IS 'Timestamp when file was uploaded';
COMMENT ON COLUMN connect_backend.requirement_files.is_active IS 'Soft delete flag - false means file is deleted';