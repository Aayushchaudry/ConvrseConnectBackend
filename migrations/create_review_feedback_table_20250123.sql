-- migrations/create_review_feedback_table_20250123.sql

-- Create review_feedback table for enhanced feedback with coordinate and timestamp support

-- First, ensure the FeedbackType enum exists (if not already created by client_feedbacks table)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'feedbacktype') THEN
        CREATE TYPE connect_backend.feedbacktype AS ENUM (
            'accept',
            'reject',
            'comment',
            'like',
            'final_approval'
        );
    END IF;
END$$;

-- Create the review_feedback table
CREATE TABLE IF NOT EXISTS connect_backend.review_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_item_id UUID NOT NULL REFERENCES connect_backend.review_items(id),
    feedback_type connect_backend.feedbacktype NOT NULL,
    comment_text TEXT,
    timestamp_seconds INTEGER,
    coordinates JSONB,
    submitted_by UUID,
    submitted_at TIMESTAMP NOT NULL DEFAULT NOW(),
    generated_task_id UUID REFERENCES connect_backend.internal_tasks(id),
    
    -- Add indexes for performance
    CONSTRAINT fk_review_item FOREIGN KEY (review_item_id) 
        REFERENCES connect_backend.review_items(id) ON DELETE CASCADE,
    CONSTRAINT fk_generated_task FOREIGN KEY (generated_task_id) 
        REFERENCES connect_backend.internal_tasks(id) ON DELETE SET NULL
);

-- Add indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_review_feedback_review_item_id ON connect_backend.review_feedback(review_item_id);
CREATE INDEX IF NOT EXISTS idx_review_feedback_submitted_by ON connect_backend.review_feedback(submitted_by);
CREATE INDEX IF NOT EXISTS idx_review_feedback_generated_task_id ON connect_backend.review_feedback(generated_task_id);

-- Add comment to the table
COMMENT ON TABLE connect_backend.review_feedback IS 'Stores detailed feedback on review items with support for coordinates and timestamps';