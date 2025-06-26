-- Migration: Create Enhanced Task Management Tables and Modify Existing Tables
-- Phase 1 of ConvrseConnect Backend Enhancement
-- Date: 2024-12-30

-- ================================================
-- 1. CREATE NEW TABLES
-- ================================================

-- 1.1 Create task_deliverable_associations table (junction table)
CREATE TABLE IF NOT EXISTS connect_backend.task_deliverable_associations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL,
    deliverable_id UUID NOT NULL,
    is_primary_deliverable BOOLEAN NOT NULL DEFAULT FALSE,
    estimated_hours DECIMAL(8,2),
    actual_hours DECIMAL(8,2),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Foreign key constraints
    CONSTRAINT fk_tda_task_id FOREIGN KEY (task_id) REFERENCES connect_backend.internal_tasks(id) ON DELETE CASCADE,
    CONSTRAINT fk_tda_deliverable_id FOREIGN KEY (deliverable_id) REFERENCES connect_backend.deliverables(id) ON DELETE CASCADE,
    
    -- Unique constraint to prevent duplicate associations
    CONSTRAINT uq_task_deliverable UNIQUE (task_id, deliverable_id)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_tda_task_id ON connect_backend.task_deliverable_associations(task_id);
CREATE INDEX IF NOT EXISTS idx_tda_deliverable_id ON connect_backend.task_deliverable_associations(deliverable_id);

-- 1.2 Create deliverable_pricing table (BOQ)
CREATE TABLE IF NOT EXISTS connect_backend.deliverable_pricing (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    deliverable_id UUID NOT NULL,
    base_price DECIMAL(12,2) NOT NULL,
    markup_percentage DECIMAL(5,2) NOT NULL DEFAULT 0,
    markup_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    discount_percentage DECIMAL(5,2) NOT NULL DEFAULT 0,
    discount_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    final_price DECIMAL(12,2) NOT NULL,
    cost_breakdown JSONB,
    is_custom_pricing BOOLEAN NOT NULL DEFAULT FALSE,
    pricing_notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Foreign key constraints
    CONSTRAINT fk_dp_project_id FOREIGN KEY (project_id) REFERENCES connect_backend.projects(id) ON DELETE CASCADE,
    CONSTRAINT fk_dp_deliverable_id FOREIGN KEY (deliverable_id) REFERENCES connect_backend.deliverables(id) ON DELETE CASCADE,
    
    -- Unique constraint to prevent duplicate pricing for same project-deliverable
    CONSTRAINT uq_project_deliverable_pricing UNIQUE (project_id, deliverable_id),
    
    -- Check constraints for valid pricing
    CONSTRAINT chk_base_price_positive CHECK (base_price >= 0),
    CONSTRAINT chk_final_price_positive CHECK (final_price >= 0),
    CONSTRAINT chk_markup_percentage_valid CHECK (markup_percentage >= 0 AND markup_percentage <= 100),
    CONSTRAINT chk_discount_percentage_valid CHECK (discount_percentage >= 0 AND discount_percentage <= 100)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_dp_project_id ON connect_backend.deliverable_pricing(project_id);
CREATE INDEX IF NOT EXISTS idx_dp_deliverable_id ON connect_backend.deliverable_pricing(deliverable_id);

-- 1.3 Create task_progress table (daily progress tracking)
CREATE TABLE IF NOT EXISTS connect_backend.task_progress (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL,
    progress_date DATE NOT NULL,
    percentage_complete DECIMAL(5,2) NOT NULL DEFAULT 0,
    hours_spent DECIMAL(8,2) NOT NULL DEFAULT 0,
    notes TEXT,
    created_by UUID NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Foreign key constraints
    CONSTRAINT fk_tp_task_id FOREIGN KEY (task_id) REFERENCES connect_backend.internal_tasks(id) ON DELETE CASCADE,
    
    -- Unique constraint to prevent duplicate progress entries for same task and date
    CONSTRAINT uq_task_progress_date UNIQUE (task_id, progress_date),
    
    -- Check constraints for valid values
    CONSTRAINT chk_percentage_range CHECK (percentage_complete >= 0 AND percentage_complete <= 100),
    CONSTRAINT chk_hours_positive CHECK (hours_spent >= 0)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_tp_task_id ON connect_backend.task_progress(task_id);
CREATE INDEX IF NOT EXISTS idx_tp_progress_date ON connect_backend.task_progress(progress_date);
CREATE INDEX IF NOT EXISTS idx_tp_created_by ON connect_backend.task_progress(created_by);

-- 1.4 Create project_timeline table (project phases and milestones)
CREATE TABLE IF NOT EXISTS connect_backend.project_timeline (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    phase_name VARCHAR(255) NOT NULL,
    phase_order INTEGER NOT NULL,
    planned_start_date DATE,
    planned_end_date DATE,
    actual_start_date DATE,
    actual_end_date DATE,
    is_milestone BOOLEAN NOT NULL DEFAULT FALSE,
    percentage_complete DECIMAL(5,2) NOT NULL DEFAULT 0,
    dependencies JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Foreign key constraints
    CONSTRAINT fk_pt_project_id FOREIGN KEY (project_id) REFERENCES connect_backend.projects(id) ON DELETE CASCADE,
    
    -- Check constraints for valid values
    CONSTRAINT chk_timeline_percentage_range CHECK (percentage_complete >= 0 AND percentage_complete <= 100),
    CONSTRAINT chk_phase_order_positive CHECK (phase_order > 0)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_pt_project_id ON connect_backend.project_timeline(project_id);
CREATE INDEX IF NOT EXISTS idx_pt_phase_order ON connect_backend.project_timeline(phase_order);
CREATE INDEX IF NOT EXISTS idx_pt_is_milestone ON connect_backend.project_timeline(is_milestone);

-- 1.5 Create requirement_templates table (templates for auto-generation)
CREATE TABLE IF NOT EXISTS connect_backend.requirement_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deliverable_type VARCHAR(100) NOT NULL,
    requirement_name VARCHAR(255) NOT NULL,
    requirement_type connect_backend.requirementtype NOT NULL,
    is_mandatory BOOLEAN NOT NULL DEFAULT FALSE,
    default_value TEXT,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_rt_deliverable_type ON connect_backend.requirement_templates(deliverable_type);
CREATE INDEX IF NOT EXISTS idx_rt_is_active ON connect_backend.requirement_templates(is_active);

-- ================================================
-- 2. MODIFY EXISTING TABLES
-- ================================================

-- 2.1 Add new columns to internal_tasks table
ALTER TABLE connect_backend.internal_tasks 
ADD COLUMN IF NOT EXISTS estimated_hours DECIMAL(8,2),
ADD COLUMN IF NOT EXISTS actual_hours DECIMAL(8,2),
ADD COLUMN IF NOT EXISTS is_project_level BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS task_template_id UUID;

-- Update existing records to set appropriate defaults
UPDATE connect_backend.internal_tasks 
SET is_project_level = FALSE 
WHERE is_project_level IS NULL;

-- 2.2 Modify requirements table to support project-level requirements
-- Make deliverable_id nullable (if not already)
ALTER TABLE connect_backend.requirements 
ALTER COLUMN deliverable_id DROP NOT NULL;

-- Add new columns to requirements table
ALTER TABLE connect_backend.requirements
ADD COLUMN IF NOT EXISTS is_project_level BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS template_id UUID;

-- Update existing records to set appropriate defaults
UPDATE connect_backend.requirements 
SET is_project_level = FALSE 
WHERE is_project_level IS NULL;

-- 2.3 Add new budget tracking columns to projects table
ALTER TABLE connect_backend.projects
ADD COLUMN IF NOT EXISTS calculated_budget DECIMAL(12,2),
ADD COLUMN IF NOT EXISTS actual_cost DECIMAL(12,2) NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS budget_variance DECIMAL(12,2) NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS budget_last_calculated TIMESTAMP;

-- ================================================
-- 3. CREATE UPDATE TRIGGERS FOR AUTOMATIC TIMESTAMPS
-- ================================================

-- Update trigger for task_deliverable_associations
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_task_deliverable_associations_updated_at 
    BEFORE UPDATE ON connect_backend.task_deliverable_associations 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_deliverable_pricing_updated_at 
    BEFORE UPDATE ON connect_backend.deliverable_pricing 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_task_progress_updated_at 
    BEFORE UPDATE ON connect_backend.task_progress 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_project_timeline_updated_at 
    BEFORE UPDATE ON connect_backend.project_timeline 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_requirement_templates_updated_at 
    BEFORE UPDATE ON connect_backend.requirement_templates 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ================================================
-- 4. INSERT SAMPLE REQUIREMENT TEMPLATES
-- ================================================

-- Insert some basic requirement templates for common deliverable types
INSERT INTO connect_backend.requirement_templates (deliverable_type, requirement_name, requirement_type, is_mandatory, description) VALUES
('3D_RENDERING', 'Reference Images', 'FILE_UPLOAD', true, 'Upload reference images for the 3D rendering project'),
('3D_RENDERING', 'Preferred Style', 'TEXT_INPUT', false, 'Describe the preferred artistic style for the rendering'),
('3D_RENDERING', 'Resolution Requirements', 'TEXT_INPUT', true, 'Specify the required resolution for final renders'),
('3D_RENDERING', 'Camera Angles', 'JSON_INPUT', false, 'Specify desired camera angles and views'),
('ANIMATION', 'Storyboard', 'FILE_UPLOAD', true, 'Upload storyboard or animation sequence plan'),
('ANIMATION', 'Duration', 'TEXT_INPUT', true, 'Specify the desired animation duration'),
('ANIMATION', 'Frame Rate', 'TEXT_INPUT', true, 'Specify the required frame rate (e.g., 24fps, 30fps)'),
('PRODUCT_VISUALIZATION', 'Product CAD Files', 'FILE_UPLOAD', true, 'Upload CAD files or technical drawings of the product'),
('PRODUCT_VISUALIZATION', 'Material Specifications', 'TEXT_INPUT', true, 'Specify materials and surface finishes'),
('PRODUCT_VISUALIZATION', 'Environment Setting', 'TEXT_INPUT', false, 'Describe the environment or setting for product placement'),
('ARCHITECTURAL_VISUALIZATION', 'Floor Plans', 'FILE_UPLOAD', true, 'Upload architectural floor plans'),
('ARCHITECTURAL_VISUALIZATION', 'Material Palette', 'FILE_UPLOAD', false, 'Upload material palette or finish specifications'),
('ARCHITECTURAL_VISUALIZATION', 'Lighting Preferences', 'TEXT_INPUT', false, 'Specify lighting preferences (natural, artificial, time of day)');

-- ================================================
-- 5. GRANT PERMISSIONS (if needed)
-- ================================================

-- Grant necessary permissions to application role (adjust role name as needed)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA connect_backend TO your_app_role;
-- GRANT USAGE ON SCHEMA connect_backend TO your_app_role;

-- ================================================
-- MIGRATION COMPLETED
-- ================================================

-- Log completion
INSERT INTO connect_backend.migration_log (migration_name, executed_at) 
VALUES ('create_enhanced_task_management_tables', NOW())
ON CONFLICT DO NOTHING; 