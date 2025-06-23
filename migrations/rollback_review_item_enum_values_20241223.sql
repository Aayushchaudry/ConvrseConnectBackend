-- Rollback Migration: Remove Business-Specific Review Item Types
-- Date: 2024-12-23
-- Description: Remove business-specific enum values from ReviewItemType if rollback needed

-- Note: PostgreSQL doesn't support removing enum values directly
-- This would require recreating the enum type and updating all references
-- For safety, this migration provides the manual steps needed:

/*
-- WARNING: This rollback requires careful execution and may cause data loss
-- Only run if absolutely necessary and no data exists with these enum values

-- Step 1: Check if any data uses the new enum values
SELECT item_type, COUNT(*) 
FROM connect_backend.review_items 
WHERE item_type IN ('static_render', 'texture_review', 'final_render', 'work_review')
GROUP BY item_type;

-- Step 2: If data exists, either migrate it to other values or remove it
-- UPDATE connect_backend.review_items SET item_type = 'other' WHERE item_type IN (...);

-- Step 3: Create new enum without the business-specific values
CREATE TYPE connect_backend.reviewitemtype_new AS ENUM (
    'image',
    'video', 
    'document',
    'interactive_content',
    'other'
);

-- Step 4: Update the table to use the new enum
ALTER TABLE connect_backend.review_items 
ALTER COLUMN item_type TYPE connect_backend.reviewitemtype_new 
USING item_type::text::connect_backend.reviewitemtype_new;

-- Step 5: Drop old enum and rename new one
DROP TYPE connect_backend.reviewitemtype;
ALTER TYPE connect_backend.reviewitemtype_new RENAME TO reviewitemtype;
*/

-- For this deployment, we'll keep the enum values as removing them is destructive
SELECT 'Rollback not executed - removing enum values requires manual intervention' AS notice; 