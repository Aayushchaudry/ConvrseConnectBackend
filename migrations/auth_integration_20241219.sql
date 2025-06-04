-- Migration: Auth Integration for ConvrseConnectBackend
-- Date: 2024-12-19
-- Description: Add business context and user fields to projects and deliverables, create activity logs table

-- Add business context and user fields to projects table
ALTER TABLE projects 
ADD COLUMN business_id INTEGER NOT NULL DEFAULT 1,
ADD COLUMN created_by INTEGER NOT NULL DEFAULT 1,
ADD COLUMN assigned_to INTEGER NULL;

-- Add indexes for performance
CREATE INDEX idx_projects_business_id ON projects(business_id);
CREATE INDEX idx_projects_created_by ON projects(created_by);
CREATE INDEX idx_projects_assigned_to ON projects(assigned_to);

-- Add user fields to deliverables table
ALTER TABLE deliverables 
ADD COLUMN assigned_to INTEGER NULL,
ADD COLUMN created_by INTEGER NOT NULL DEFAULT 1;

-- Add indexes for deliverables
CREATE INDEX idx_deliverables_assigned_to ON deliverables(assigned_to);
CREATE INDEX idx_deliverables_created_by ON deliverables(created_by);

-- Create activity_logs table for audit trail
CREATE TABLE activity_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    business_id INTEGER NOT NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(100),
    details JSONB,
    ip_address VARCHAR(45),
    user_agent TEXT,
    service_name VARCHAR(50) NOT NULL DEFAULT 'convrse-connect-backend',
    correlation_id VARCHAR(36),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Add indexes for activity_logs
CREATE INDEX idx_activity_logs_user_id ON activity_logs(user_id);
CREATE INDEX idx_activity_logs_business_id ON activity_logs(business_id);
CREATE INDEX idx_activity_logs_action ON activity_logs(action);
CREATE INDEX idx_activity_logs_resource_type ON activity_logs(resource_type);
CREATE INDEX idx_activity_logs_resource_id ON activity_logs(resource_id);
CREATE INDEX idx_activity_logs_correlation_id ON activity_logs(correlation_id);
CREATE INDEX idx_activity_logs_created_at ON activity_logs(created_at);

-- Comments for documentation
COMMENT ON TABLE activity_logs IS 'Audit trail for user activities across the system';
COMMENT ON COLUMN projects.business_id IS 'Foreign key to businesses table in auth-service';
COMMENT ON COLUMN projects.created_by IS 'Foreign key to users table in auth-service';
COMMENT ON COLUMN projects.assigned_to IS 'Foreign key to users table in auth-service';
COMMENT ON COLUMN deliverables.assigned_to IS 'Foreign key to users table in auth-service';
COMMENT ON COLUMN deliverables.created_by IS 'Foreign key to users table in auth-service'; 