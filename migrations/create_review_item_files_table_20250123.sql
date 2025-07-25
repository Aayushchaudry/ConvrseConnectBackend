-- Migration: Create ReviewItemFile table for enhanced file management
-- Date: 2025-01-23
-- Description: Create review_item_files table to support multiple files per review item
--              with proper sequencing and platform-service integration

-- Create review_item_files table
CREATE TABLE IF NOT EXISTS connect_backend.review_item_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_item_id UUID NOT NULL REFERENCES connect_backend.review_items(id) ON DELETE CASCADE,
    platform_file_id UUID NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_type VARCHAR(50),
    file_size INTEGER,
    sequence_order INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Create indexes for performance optimization
CREATE INDEX IF NOT EXISTS idx_review_item_files_review_item_id 
ON connect_backend.review_item_files(review_item_id);

CREATE INDEX IF NOT EXISTS idx_review_item_files_platform_file_id 
ON connect_backend.review_item_files(platform_file_id);

CREATE INDEX IF NOT EXISTS idx_review_item_files_sequence 
ON connect_backend.review_item_files(review_item_id, sequence_order);

-- Create composite index for common queries
CREATE INDEX IF NOT EXISTS idx_review_item_files_item_type_sequence 
ON connect_backend.review_item_files(review_item_id, file_type, sequence_order);

-- Add trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION connect_backend.update_review_item_files_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_review_item_files_updated_at
    BEFORE UPDATE ON connect_backend.review_item_files
    FOR EACH ROW
    EXECUTE FUNCTION connect_backend.update_review_item_files_updated_at();

-- Add comments for documentation
COMMENT ON TABLE connect_backend.review_item_files IS 'Files associated with review items for client review';
COMMENT ON COLUMN connect_backend.review_item_files.platform_file_id IS 'Reference to file stored in platform-service';
COMMENT ON COLUMN connect_backend.review_item_files.sequence_order IS 'Order of files within a review item';
COMMENT ON COLUMN connect_backend.review_item_files.file_size IS 'File size in bytes';