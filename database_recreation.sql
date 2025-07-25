-- ================================================================
-- CONVRSE DATABASE RECREATION SCRIPT
-- ================================================================
-- This script recreates all database schemas and tables for:
-- - ConvrseConnectBackend (connect_backend schema)
-- - auth-service (auth_service schema)  
-- - platform-service (platform_service schema)
--
-- Usage: psql -f database_recreation.sql
-- ================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ================================================================
-- DROP ALL SCHEMAS (CASCADE removes all tables/functions/etc)
-- ================================================================
DROP SCHEMA IF EXISTS connect_backend CASCADE;
DROP SCHEMA IF EXISTS auth_service CASCADE;
DROP SCHEMA IF EXISTS platform_service CASCADE;

-- ================================================================
-- CREATE SCHEMAS
-- ================================================================
CREATE SCHEMA connect_backend;
CREATE SCHEMA auth_service;
CREATE SCHEMA platform_service;

-- ================================================================
-- AUTH-SERVICE TABLES (auth_service schema)
-- ================================================================

-- Set search path for auth_service
SET search_path TO auth_service;

-- Association tables for many-to-many relationships
CREATE TABLE user_roles (
    user_id UUID,
    role_id UUID,
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE role_permissions (
    role_id UUID,
    permission_id UUID,
    PRIMARY KEY (role_id, permission_id)
);

-- Business table
CREATE TABLE businesses (
    business_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    business_name VARCHAR NOT NULL,
    description TEXT,
    industry VARCHAR,
    employee_count INTEGER,
    location VARCHAR,
    website VARCHAR,
    contact_email VARCHAR,
    contact_phone VARCHAR,
    chat_enabled BOOLEAN DEFAULT FALSE NOT NULL,
    identifier VARCHAR UNIQUE,
    parent_business_id UUID,
    s3_bucket VARCHAR,
    rate_limits JSONB DEFAULT '{}',
    business_settings JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Users table
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR UNIQUE NOT NULL,
    email VARCHAR UNIQUE NOT NULL,
    password_hash VARCHAR NOT NULL,
    full_name VARCHAR,
    role_id UUID,
    business_id UUID,
    is_admin BOOLEAN DEFAULT FALSE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    last_login_at TIMESTAMP,
    password_changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    salary FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Roles table
CREATE TABLE roles (
    role_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR NOT NULL,
    description TEXT,
    business_id UUID,
    is_inherited BOOLEAN DEFAULT FALSE NOT NULL,
    is_system_role BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Permissions table
CREATE TABLE permissions (
    permission_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR UNIQUE NOT NULL,
    description TEXT,
    resource_type VARCHAR,
    action VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Refresh tokens table
CREATE TABLE refresh_tokens (
    token_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    token_hash VARCHAR NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    is_revoked BOOLEAN DEFAULT FALSE NOT NULL,
    device_info JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Service clients table
CREATE TABLE service_clients (
    client_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_name VARCHAR UNIQUE NOT NULL,
    client_secret_hash VARCHAR NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    allowed_scopes JSONB DEFAULT '[]',
    rate_limit_per_minute INTEGER DEFAULT 1000 NOT NULL,
    last_used_at TIMESTAMP,
    service_type VARCHAR NOT NULL,
    service_version VARCHAR,
    callback_urls JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Permission audit logs
CREATE TABLE permission_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    business_id UUID NOT NULL,
    action VARCHAR NOT NULL,
    resource_type VARCHAR NOT NULL,
    resource_id UUID,
    details JSONB,
    ip_address VARCHAR,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Rate limit usage
CREATE TABLE rate_limit_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    business_id UUID,
    endpoint VARCHAR NOT NULL,
    request_count INTEGER DEFAULT 0,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- ================================================================
-- PLATFORM-SERVICE TABLES (platform_service schema)
-- ================================================================

-- Set search path for platform_service
SET search_path TO platform_service;

-- File features table
CREATE TABLE file_features (
    id SERIAL PRIMARY KEY,
    file_feature_name VARCHAR(255) UNIQUE NOT NULL,
    valid_extensions JSONB NOT NULL,
    bucket_name VARCHAR(255) NOT NULL,
    folder_path VARCHAR(500) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Contents table
CREATE TABLE contents (
    id SERIAL PRIMARY KEY,
    id_uuid UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    feature_name VARCHAR(255) NOT NULL,
    bucket_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(1000) NOT NULL,
    original_filename VARCHAR(500),
    file_size INTEGER,
    content_type VARCHAR(100),
    upload_status VARCHAR(50) DEFAULT 'pending',
    business_id UUID,
    uploaded_by_user_id UUID,
    project_id UUID,
    conversation_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Content ID mapping table
CREATE TABLE content_id_mapping (
    old_id INTEGER PRIMARY KEY,
    new_uuid UUID NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Notifications table
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    notification_type VARCHAR(50) NOT NULL DEFAULT 'INFO',
    project_id UUID,
    data JSONB,
    unread BOOLEAN DEFAULT TRUE NOT NULL,
    sender_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    read_at TIMESTAMP WITH TIME ZONE,
    deleted_at TIMESTAMP WITH TIME ZONE
);

-- Notification preferences table
CREATE TABLE notification_preferences (
    id SERIAL PRIMARY KEY,
    user_id UUID UNIQUE NOT NULL,
    email_notifications BOOLEAN DEFAULT TRUE,
    push_notifications BOOLEAN DEFAULT TRUE,
    comment_notifications BOOLEAN DEFAULT TRUE,
    mention_notifications BOOLEAN DEFAULT TRUE,
    task_update_notifications BOOLEAN DEFAULT TRUE,
    system_notifications BOOLEAN DEFAULT TRUE,
    project_preferences JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ================================================================
-- CONVRSE-CONNECT-BACKEND TABLES (connect_backend schema)
-- ================================================================

-- Set search path for connect_backend
SET search_path TO connect_backend;

-- Create ENUMs for connect_backend
CREATE TYPE projectstatus AS ENUM ('initiated', 'info_gathering', 'in_progress', 'completed');

CREATE TYPE deliverabletype AS ENUM (
    'rendered_images', 'technical_renders', 'exterior_vr_tour', 'animated_vr_tour',
    'video_walkthrough', 'inventory_module', 'location_map', 'interactive_sales_app',
    'interactive_drone_shoot', 'interplayer_software_av_room'
);

CREATE TYPE deliverablestatus AS ENUM (
    'info_gathering', 'modeling_pending', 'texturing_pending', 'rendering_pending',
    'awaiting_client_review', 'revisions_in_progress', 'ready_for_delivery',
    'delivered', 'failed', 'canceled'
);

CREATE TYPE requirementtype AS ENUM ('FILE_UPLOAD', 'TEXT_INPUT', 'BOOLEAN_INPUT', 'JSON_INPUT');

CREATE TYPE requirementstatus AS ENUM ('PENDING', 'COMPLETED', 'PARTIALLY_COMPLETED', 'FAILED');

CREATE TYPE tasktype AS ENUM (
    'MODELING', 'TEXTURING', 'RENDERING', 'REVIEW', 'REVISION', 'COORDINATION',
    'RESEARCH', 'QUALITY_CONTROL', 'CLIENT_COMMUNICATION', 'PROJECT_SETUP'
);

CREATE TYPE taskstatus AS ENUM (
    'NOT_STARTED', 'IN_PROGRESS', 'UNDER_REVIEW', 'NEEDS_REVISION',
    'COMPLETED', 'BLOCKED', 'CANCELLED'
);

CREATE TYPE priority AS ENUM ('LOW', 'NORMAL', 'HIGH', 'URGENT');

CREATE TYPE reviewitemtype AS ENUM (
    'RENDER_OPTION', 'STATIC_RENDER', 'TECHNICAL_MODEL', 'THREE_SIXTY_VIEW',
    'VIDEO_SEGMENT', 'VIDEO_DRAFT', 'MAP_DRAFT', 'UI_PROTOTYPE',
    'DRONE_FOOTAGE', 'STORYBOARD', 'OTHER', 'TEXTURE_REVIEW',
    'FINAL_RENDER', 'WORK_REVIEW'
);

CREATE TYPE reviewstatus AS ENUM ('PENDING_REVIEW', 'APPROVED', 'REJECTED', 'NEEDS_REVISION');

CREATE TYPE sagastatus AS ENUM ('STARTED', 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'COMPENSATING');

CREATE TYPE sagatype AS ENUM ('PROJECT_SAGA', 'DELIVERABLE_SAGA');

CREATE TYPE feedbacktype AS ENUM ('accept', 'reject', 'comment', 'like', 'final_approval');

-- Projects table
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    status projectstatus DEFAULT 'initiated' NOT NULL,
    budget DECIMAL(10,2),
    calculated_budget DECIMAL(12,2),
    actual_cost DECIMAL(12,2) DEFAULT 0 NOT NULL,
    budget_variance DECIMAL(12,2) DEFAULT 0 NOT NULL,
    budget_last_calculated TIMESTAMP,
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    business_id UUID NOT NULL,  -- Fixed to UUID
    created_by UUID NOT NULL,
    assigned_to UUID,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Deliverables table
CREATE TABLE deliverables (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    deliverable_type deliverabletype NOT NULL,
    deliverable_sub_type VARCHAR(100),
    current_status deliverablestatus DEFAULT 'info_gathering' NOT NULL,
    tentative_timeline_days INTEGER,
    assigned_to UUID,
    created_by UUID NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Requirements table
CREATE TABLE requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deliverable_id UUID,
    project_id UUID NOT NULL,
    requirement_name VARCHAR(255) NOT NULL,
    requirement_type requirementtype NOT NULL,
    value TEXT,
    status requirementstatus DEFAULT 'PENDING' NOT NULL,
    is_mandatory BOOLEAN DEFAULT FALSE NOT NULL,
    notes TEXT,
    is_project_level BOOLEAN DEFAULT FALSE NOT NULL,
    template_id UUID,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Internal tasks table
CREATE TABLE internal_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deliverable_id UUID,
    project_id UUID NOT NULL,
    parent_task_id UUID,
    task_name VARCHAR(255) NOT NULL,
    task_type tasktype NOT NULL,
    status taskstatus NOT NULL,
    priority priority DEFAULT 'NORMAL' NOT NULL,
    start_date TIMESTAMP,
    tentative_end_date TIMESTAMP,
    actual_end_date TIMESTAMP,
    description TEXT,
    estimated_hours DECIMAL(8,2),
    actual_hours DECIMAL(8,2),
    is_project_level BOOLEAN DEFAULT FALSE NOT NULL,
    task_template_id UUID,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Activity logs table
CREATE TABLE activity_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    business_id UUID NOT NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id UUID,
    details JSONB,
    ip_address VARCHAR(45),
    user_agent TEXT,
    service_name VARCHAR(50) NOT NULL DEFAULT 'convrse-connect-backend',
    correlation_id UUID,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Review items table
CREATE TABLE review_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deliverable_id UUID NOT NULL,
    project_id UUID NOT NULL,
    source_internal_task_id UUID NOT NULL,
    item_type reviewitemtype NOT NULL,
    platform_file_id UUID,
    item_url TEXT,
    description TEXT,
    review_status reviewstatus DEFAULT 'PENDING_REVIEW' NOT NULL,
    sequence_number INTEGER,
    review_round INTEGER,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Saga state table
CREATE TABLE saga_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    saga_id UUID NOT NULL UNIQUE,
    saga_type sagatype NOT NULL,
    project_id UUID NOT NULL,
    deliverable_id UUID,
    current_state VARCHAR(100) NOT NULL,
    status sagastatus DEFAULT 'IN_PROGRESS' NOT NULL,
    last_event_processed_id UUID,
    last_event_processed_timestamp TIMESTAMP,
    last_command_sent_id UUID,
    last_command_sent_timestamp TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Task progress table
CREATE TABLE task_progress (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL,
    progress_date DATE NOT NULL,
    percentage_complete DECIMAL(5,2) DEFAULT 0 NOT NULL,
    hours_spent DECIMAL(8,2) DEFAULT 0 NOT NULL,
    notes TEXT,
    created_by UUID NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Client feedback table
CREATE TABLE client_feedbacks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_item_id UUID,
    project_output_id UUID,
    project_id UUID NOT NULL,
    deliverable_id UUID NOT NULL,
    feedback_type feedbacktype NOT NULL,
    comment_text TEXT,
    timestamp_seconds INTEGER,
    context_coordinates JSONB,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Project outputs table
CREATE TABLE project_outputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deliverable_id UUID NOT NULL,
    project_id UUID NOT NULL,
    output_name VARCHAR(255) NOT NULL,
    output_url TEXT NOT NULL,
    delivery_date TIMESTAMP DEFAULT NOW() NOT NULL,
    comments_allowed_on_output BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Requirement files table
CREATE TABLE requirement_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requirement_id UUID NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Task deliverable associations table
CREATE TABLE task_deliverable_associations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL,
    deliverable_id UUID NOT NULL,
    is_primary_deliverable BOOLEAN DEFAULT FALSE NOT NULL,
    estimated_hours DECIMAL(8,2),
    actual_hours DECIMAL(8,2),
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Project timeline table
CREATE TABLE project_timeline (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    phase_name VARCHAR(255) NOT NULL,
    phase_order INTEGER NOT NULL,
    planned_start_date DATE,
    planned_end_date DATE,
    actual_start_date DATE,
    actual_end_date DATE,
    is_milestone BOOLEAN DEFAULT FALSE NOT NULL,
    percentage_complete DECIMAL(5,2) DEFAULT 0 NOT NULL,
    dependencies JSONB,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Requirement templates table
CREATE TABLE requirement_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deliverable_type VARCHAR(100) NOT NULL,
    requirement_name VARCHAR(255) NOT NULL,
    requirement_type requirementtype NOT NULL,
    is_mandatory BOOLEAN DEFAULT FALSE NOT NULL,
    default_value TEXT,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- ================================================================
-- CREATE INDEXES FOR PERFORMANCE
-- ================================================================

-- Auth service indexes
SET search_path TO auth_service;
CREATE INDEX idx_businesses_user_id ON businesses(user_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_business_id ON users(business_id);
CREATE INDEX idx_roles_business_id ON roles(business_id);
CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);

-- Platform service indexes
SET search_path TO platform_service;
CREATE INDEX idx_file_features_name ON file_features(file_feature_name);
CREATE INDEX idx_contents_feature_name ON contents(feature_name);
CREATE INDEX idx_contents_business_id ON contents(business_id);
CREATE INDEX idx_contents_project_id ON contents(project_id);
CREATE INDEX idx_notifications_user_id ON notifications(user_id);
CREATE INDEX idx_notifications_project_id ON notifications(project_id);

-- Connect backend indexes
SET search_path TO connect_backend;
CREATE INDEX idx_projects_business_id ON projects(business_id);
CREATE INDEX idx_projects_created_by ON projects(created_by);
CREATE INDEX idx_projects_assigned_to ON projects(assigned_to);
CREATE INDEX idx_projects_name ON projects(name);
CREATE INDEX idx_deliverables_project_id ON deliverables(project_id);
CREATE INDEX idx_deliverables_assigned_to ON deliverables(assigned_to);
CREATE INDEX idx_requirements_project_id ON requirements(project_id);
CREATE INDEX idx_requirements_deliverable_id ON requirements(deliverable_id);
CREATE INDEX idx_internal_tasks_project_id ON internal_tasks(project_id);
CREATE INDEX idx_internal_tasks_deliverable_id ON internal_tasks(deliverable_id);
CREATE INDEX idx_activity_logs_user_id ON activity_logs(user_id);
CREATE INDEX idx_activity_logs_business_id ON activity_logs(business_id);
CREATE INDEX idx_review_items_project_id ON review_items(project_id);
CREATE INDEX idx_review_items_deliverable_id ON review_items(deliverable_id);
CREATE INDEX idx_task_progress_task_id ON task_progress(task_id);

-- ================================================================
-- FOREIGN KEY CONSTRAINTS
-- ================================================================

-- Connect backend foreign keys
SET search_path TO connect_backend;
ALTER TABLE deliverables ADD CONSTRAINT fk_deliverables_project_id 
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;

ALTER TABLE requirements ADD CONSTRAINT fk_requirements_project_id 
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;

ALTER TABLE requirements ADD CONSTRAINT fk_requirements_deliverable_id 
    FOREIGN KEY (deliverable_id) REFERENCES deliverables(id) ON DELETE CASCADE;

ALTER TABLE internal_tasks ADD CONSTRAINT fk_internal_tasks_project_id 
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;

ALTER TABLE internal_tasks ADD CONSTRAINT fk_internal_tasks_deliverable_id 
    FOREIGN KEY (deliverable_id) REFERENCES deliverables(id) ON DELETE CASCADE;

ALTER TABLE internal_tasks ADD CONSTRAINT fk_internal_tasks_parent_task_id 
    FOREIGN KEY (parent_task_id) REFERENCES internal_tasks(id) ON DELETE CASCADE;

ALTER TABLE review_items ADD CONSTRAINT fk_review_items_project_id 
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;

ALTER TABLE review_items ADD CONSTRAINT fk_review_items_deliverable_id 
    FOREIGN KEY (deliverable_id) REFERENCES deliverables(id) ON DELETE CASCADE;

ALTER TABLE review_items ADD CONSTRAINT fk_review_items_source_internal_task_id 
    FOREIGN KEY (source_internal_task_id) REFERENCES internal_tasks(id) ON DELETE CASCADE;

ALTER TABLE saga_state ADD CONSTRAINT fk_saga_state_project_id 
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;

ALTER TABLE task_progress ADD CONSTRAINT fk_task_progress_task_id 
    FOREIGN KEY (task_id) REFERENCES internal_tasks(id) ON DELETE CASCADE;

ALTER TABLE client_feedbacks ADD CONSTRAINT fk_client_feedbacks_project_id 
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;

ALTER TABLE client_feedbacks ADD CONSTRAINT fk_client_feedbacks_deliverable_id 
    FOREIGN KEY (deliverable_id) REFERENCES deliverables(id) ON DELETE CASCADE;

ALTER TABLE client_feedbacks ADD CONSTRAINT fk_client_feedbacks_review_item_id 
    FOREIGN KEY (review_item_id) REFERENCES review_items(id) ON DELETE CASCADE;

ALTER TABLE project_outputs ADD CONSTRAINT fk_project_outputs_project_id 
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;

ALTER TABLE project_outputs ADD CONSTRAINT fk_project_outputs_deliverable_id 
    FOREIGN KEY (deliverable_id) REFERENCES deliverables(id) ON DELETE CASCADE;

ALTER TABLE requirement_files ADD CONSTRAINT fk_requirement_files_requirement_id 
    FOREIGN KEY (requirement_id) REFERENCES requirements(id) ON DELETE CASCADE;

ALTER TABLE task_deliverable_associations ADD CONSTRAINT fk_tda_task_id 
    FOREIGN KEY (task_id) REFERENCES internal_tasks(id) ON DELETE CASCADE;

ALTER TABLE task_deliverable_associations ADD CONSTRAINT fk_tda_deliverable_id 
    FOREIGN KEY (deliverable_id) REFERENCES deliverables(id) ON DELETE CASCADE;

ALTER TABLE project_timeline ADD CONSTRAINT fk_project_timeline_project_id 
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;

-- Auth service foreign keys
SET search_path TO auth_service;
ALTER TABLE user_roles ADD CONSTRAINT fk_user_roles_user_id 
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE;

ALTER TABLE user_roles ADD CONSTRAINT fk_user_roles_role_id 
    FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE CASCADE;

ALTER TABLE role_permissions ADD CONSTRAINT fk_role_permissions_role_id 
    FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE CASCADE;

ALTER TABLE role_permissions ADD CONSTRAINT fk_role_permissions_permission_id 
    FOREIGN KEY (permission_id) REFERENCES permissions(permission_id) ON DELETE CASCADE;

ALTER TABLE refresh_tokens ADD CONSTRAINT fk_refresh_tokens_user_id 
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE;

ALTER TABLE users ADD CONSTRAINT fk_users_business_id 
    FOREIGN KEY (business_id) REFERENCES businesses(business_id) ON DELETE CASCADE;

ALTER TABLE users ADD CONSTRAINT fk_users_role_id 
    FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE SET NULL;

ALTER TABLE roles ADD CONSTRAINT fk_roles_business_id 
    FOREIGN KEY (business_id) REFERENCES businesses(business_id) ON DELETE CASCADE;

ALTER TABLE businesses ADD CONSTRAINT fk_businesses_user_id 
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL;

ALTER TABLE businesses ADD CONSTRAINT fk_businesses_parent_business_id 
    FOREIGN KEY (parent_business_id) REFERENCES businesses(business_id) ON DELETE SET NULL;

ALTER TABLE permission_audit_logs ADD CONSTRAINT fk_permission_audit_logs_business_id 
    FOREIGN KEY (business_id) REFERENCES businesses(business_id) ON DELETE CASCADE;

ALTER TABLE permission_audit_logs ADD CONSTRAINT fk_permission_audit_logs_user_id 
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL;

ALTER TABLE rate_limit_usage ADD CONSTRAINT fk_rate_limit_usage_business_id 
    FOREIGN KEY (business_id) REFERENCES businesses(business_id) ON DELETE CASCADE;

ALTER TABLE rate_limit_usage ADD CONSTRAINT fk_rate_limit_usage_user_id 
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL;

-- ================================================================
-- COMPLETION MESSAGE
-- ================================================================

-- Reset search path
SET search_path TO public;

-- Create a log of this recreation
CREATE TABLE IF NOT EXISTS database_recreation_log (
    id SERIAL PRIMARY KEY,
    recreation_date TIMESTAMP DEFAULT NOW(),
    schemas_created TEXT[] DEFAULT ARRAY['connect_backend', 'auth_service', 'platform_service'],
    status VARCHAR DEFAULT 'completed'
);

INSERT INTO database_recreation_log (recreation_date, status) 
VALUES (NOW(), 'completed');

-- Show completion message
SELECT 
    'Database recreation completed successfully!' as message,
    NOW() as completed_at,
    'connect_backend, auth_service, platform_service' as schemas_created; 