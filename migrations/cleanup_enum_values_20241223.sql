-- Migration: Clean up unnecessary lowercase enum values
-- Date: 2024-12-23
-- Description: Remove lowercase enum values from ReviewItemType and ReviewStatus enums

-- Start transaction
BEGIN;

-- 1. Clean up ReviewItemType enum (remove lowercase values)
-- Create new enum with only the needed values
CREATE TYPE connect_backend.reviewitemtype_new AS ENUM (
    'RENDER_OPTION',
    'STATIC_RENDER', 
    'TECHNICAL_MODEL',
    'THREE_SIXTY_VIEW',
    'VIDEO_SEGMENT',
    'VIDEO_DRAFT',
    'MAP_DRAFT',
    'UI_PROTOTYPE',
    'DRONE_FOOTAGE',
    'STORYBOARD',
    'OTHER',
    'TEXTURE_REVIEW',
    'FINAL_RENDER',
    'WORK_REVIEW'
);

-- Update the table to use the new enum (this converts all existing values)
ALTER TABLE connect_backend.review_items 
ALTER COLUMN item_type TYPE connect_backend.reviewitemtype_new 
USING item_type::text::connect_backend.reviewitemtype_new;

-- Drop old enum and rename new one
DROP TYPE connect_backend.reviewitemtype;
ALTER TYPE connect_backend.reviewitemtype_new RENAME TO reviewitemtype;

-- 2. Clean up ReviewStatus enum (remove lowercase values) 
-- Create new enum with only uppercase values
CREATE TYPE connect_backend.reviewstatus_new AS ENUM (
    'PENDING_REVIEW',
    'APPROVED',
    'REJECTED', 
    'NEEDS_REVISION'
);

-- Update the table to use the new enum
ALTER TABLE connect_backend.review_items 
ALTER COLUMN review_status TYPE connect_backend.reviewstatus_new 
USING review_status::text::connect_backend.reviewstatus_new;

-- Drop old enum and rename new one
DROP TYPE connect_backend.reviewstatus;
ALTER TYPE connect_backend.reviewstatus_new RENAME TO reviewstatus;

-- Add comments for documentation
COMMENT ON TYPE connect_backend.reviewitemtype IS 'Enum for review item types with business-specific production workflow types';
COMMENT ON TYPE connect_backend.reviewstatus IS 'Enum for review status with uppercase values for consistency';

-- Commit transaction
COMMIT; 