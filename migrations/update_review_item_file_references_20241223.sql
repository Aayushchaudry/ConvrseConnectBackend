-- Migration: Update ReviewItem file references
-- Date: 2024-12-23
-- Description: Add platform_file_id field and make item_url nullable for better file management

-- Start transaction
BEGIN;

-- 1. Add platform_file_id column to reference files from platform-service
ALTER TABLE connect_backend.review_items 
ADD COLUMN platform_file_id UUID NULL;

-- 2. Make item_url nullable since some review items may not need file attachments
ALTER TABLE connect_backend.review_items 
ALTER COLUMN item_url DROP NOT NULL;

-- 3. Add index for platform_file_id for performance
CREATE INDEX idx_review_items_platform_file_id ON connect_backend.review_items(platform_file_id);

-- 4. Add comments for documentation
COMMENT ON COLUMN connect_backend.review_items.platform_file_id IS 'Reference to file ID in platform-service for review assets';
COMMENT ON COLUMN connect_backend.review_items.item_url IS 'Optional URL to the asset - nullable for review items that do not require file attachments';

-- Commit transaction
COMMIT; 