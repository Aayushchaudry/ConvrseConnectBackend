-- Migration: Create FileVersion table for version tracking
-- Date: 2025-01-23
-- Description: Create file_versions table to support file versioning and history tracking
--              with proper version types and relationships

-- Create file_versions table
CREATE TABLE IF NOT EXISTS connect_backend.file_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_file_id UUID NOT NULL,
    current_file_id UUID NOT NULL,
    version_number INTEGER NOT NULL DEFAULT 1,
    version_type VARCHAR(20) NOT NULL,
    version_notes VARCHAR(500),
    created_by UUID,
    is_final BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Create indexes for performance optimization
CREATE INDEX IF NOT EXISTS idx_file_versions_original_file_id 
ON connect_backend.file_versions(original_file_id);

CREATE INDEX IF NOT EXISTS idx_file_versions_current_file_id 
ON connect_backend.file_versions(current_file_id);

CREATE INDEX IF NOT EXISTS idx_file_versions_version_number 
ON connect_backend.file_versions(original_file_id, version_number);

-- Create composite index for common queries
CREATE INDEX IF NOT EXISTS idx_file_versions_final_active 
ON connect_backend.file_versions(original_file_id, is_final, is_active);

-- Add trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION connect_backend.update_file_versions_updated_at()
RETURNS TRIGGER AS $
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_file_versions_updated_at
    BEFORE UPDATE ON connect_backend.file_versions
    FOR EACH ROW
    EXECUTE FUNCTION connect_backend.update_file_versions_updated_at();

-- Add comments for documentation
COMMENT ON TABLE connect_backend.file_versions IS 'Tracks version history for files across the system';
COMMENT ON COLUMN connect_backend.file_versions.original_file_id IS 'Reference to the original file ID in platform-service';
COMMENT ON COLUMN connect_backend.file_versions.current_file_id IS 'Reference to the current version file ID in platform-service';
COMMENT ON COLUMN connect_backend.file_versions.version_number IS 'Sequential version number for the file';
COMMENT ON COLUMN connect_backend.file_versions.version_type IS 'Type of version (INITIAL, REVISION, FINAL)';
COMMENT ON COLUMN connect_backend.file_versions.is_final IS 'Indicates if this is the final approved version';