-- Migration: Create error recovery and monitoring tables
-- Date: 2025-01-24
-- Description: Add tables for tracking failed uploads and comprehensive error logging

-- Create failed_upload_records table for tracking uploads that need recovery
CREATE TABLE IF NOT EXISTS failed_upload_records (
    id VARCHAR(36) PRIMARY KEY,
    service VARCHAR(100) NOT NULL,
    resource_id VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50) NOT NULL CHECK (resource_type IN ('requirement', 'review_item')),
    error_type VARCHAR(100) NOT NULL,
    error_details TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    next_retry_at TIMESTAMP,
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'retrying', 'resolved', 'failed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    context_data TEXT,
    recovery_notes TEXT
);

-- Create indexes for failed_upload_records
CREATE INDEX IF NOT EXISTS idx_failed_upload_records_status ON failed_upload_records(status);
CREATE INDEX IF NOT EXISTS idx_failed_upload_records_service ON failed_upload_records(service);
CREATE INDEX IF NOT EXISTS idx_failed_upload_records_resource ON failed_upload_records(resource_id, resource_type);
CREATE INDEX IF NOT EXISTS idx_failed_upload_records_next_retry ON failed_upload_records(next_retry_at);
CREATE INDEX IF NOT EXISTS idx_failed_upload_records_created_at ON failed_upload_records(created_at);

-- Create error_log_records table for comprehensive error logging
CREATE TABLE IF NOT EXISTS error_log_records (
    id VARCHAR(36) PRIMARY KEY,
    error_id VARCHAR(50) NOT NULL,
    service VARCHAR(100) NOT NULL,
    error_type VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    category VARCHAR(50) NOT NULL,
    user_message TEXT,
    technical_message TEXT,
    error_details TEXT,
    context_data TEXT,
    recovery_suggestions TEXT,
    stack_trace TEXT,
    user_id VARCHAR(100),
    session_id VARCHAR(100),
    request_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved BOOLEAN DEFAULT FALSE,
    resolution_notes TEXT
);

-- Create indexes for error_log_records
CREATE INDEX IF NOT EXISTS idx_error_log_records_error_id ON error_log_records(error_id);
CREATE INDEX IF NOT EXISTS idx_error_log_records_service ON error_log_records(service);
CREATE INDEX IF NOT EXISTS idx_error_log_records_error_type ON error_log_records(error_type);
CREATE INDEX IF NOT EXISTS idx_error_log_records_severity ON error_log_records(severity);
CREATE INDEX IF NOT EXISTS idx_error_log_records_created_at ON error_log_records(created_at);
CREATE INDEX IF NOT EXISTS idx_error_log_records_resolved ON error_log_records(resolved);

-- Create composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_failed_upload_recovery_query ON failed_upload_records(status, next_retry_at, retry_count);
CREATE INDEX IF NOT EXISTS idx_error_log_monitoring_query ON error_log_records(created_at, severity, service);

-- Add trigger to update updated_at timestamp for failed_upload_records
CREATE OR REPLACE FUNCTION update_failed_upload_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_failed_upload_updated_at
    BEFORE UPDATE ON failed_upload_records
    FOR EACH ROW
    EXECUTE FUNCTION update_failed_upload_updated_at();

-- Insert initial configuration data if needed
-- This could include default retry configurations, alert thresholds, etc.

COMMENT ON TABLE failed_upload_records IS 'Tracks failed file uploads for automatic recovery';
COMMENT ON TABLE error_log_records IS 'Comprehensive error logging for monitoring and analysis';

COMMENT ON COLUMN failed_upload_records.resource_type IS 'Type of resource: requirement or review_item';
COMMENT ON COLUMN failed_upload_records.status IS 'Current status: pending, retrying, resolved, or failed';
COMMENT ON COLUMN failed_upload_records.context_data IS 'JSON string containing additional context for recovery';
COMMENT ON COLUMN failed_upload_records.recovery_notes IS 'Notes about recovery attempts and resolution';

COMMENT ON COLUMN error_log_records.error_id IS 'Unique identifier for the error instance';
COMMENT ON COLUMN error_log_records.severity IS 'Error severity level: low, medium, high, or critical';
COMMENT ON COLUMN error_log_records.error_details IS 'JSON string containing detailed error information';
COMMENT ON COLUMN error_log_records.context_data IS 'JSON string containing request/session context';
COMMENT ON COLUMN error_log_records.recovery_suggestions IS 'JSON array of suggested recovery actions';