-- Migration: Add Uppercase Review Status Enum Values
-- Date: 2024-12-23
-- Description: Add uppercase enum values to ReviewStatus for consistency with other enums

-- Add uppercase versions of review status enum values
ALTER TYPE connect_backend.reviewstatus ADD VALUE IF NOT EXISTS 'PENDING_REVIEW';
ALTER TYPE connect_backend.reviewstatus ADD VALUE IF NOT EXISTS 'APPROVED';
ALTER TYPE connect_backend.reviewstatus ADD VALUE IF NOT EXISTS 'REJECTED';
ALTER TYPE connect_backend.reviewstatus ADD VALUE IF NOT EXISTS 'NEEDS_REVISION';

-- Comments for documentation
COMMENT ON TYPE connect_backend.reviewstatus IS 'Enum for review status including both legacy lowercase and current uppercase values for compatibility'; 