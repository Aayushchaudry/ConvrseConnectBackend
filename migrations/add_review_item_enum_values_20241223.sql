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