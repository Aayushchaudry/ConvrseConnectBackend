# ConvrseConnect Backend Enhancement Migration Guide

## Overview

This document provides comprehensive guidance for executing the database migration for the ConvrseConnect Backend Enhancement project. The migration covers all 5 phases of the enhancement project and ensures a smooth transition from the current system to the enhanced backend architecture.

## Migration Phases

### Phase 1: Enhanced Task Management Tables
- **Task-Deliverable Associations**: Junction table linking tasks to deliverables
- **Deliverable Pricing**: Bill of Quantities (BOQ) for project pricing
- **Task Progress Tracking**: Daily progress monitoring
- **Project Timeline**: Project phases and milestones
- **Requirement Templates**: Auto-generation templates

### Phase 2: Performance Optimization Tables
- **Query Cache**: Intelligent caching system
- **Performance Metrics**: System performance tracking

### Phase 3: Monitoring and Analytics Tables
- **Project Analytics**: Project health and progress analytics
- **System Alerts**: Intelligent alerting system

### Phase 4: Integration Orchestration Tables
- **Orchestration Events**: Event-driven workflows
- **Orchestration Configuration**: System configuration management

### Phase 5: Testing and Verification
- **Indexes and Performance Optimization**
- **Data Integrity Validation**
- **Migration Verification**

## Prerequisites

Before running the migration, ensure:

1. **Database Access**: Valid PostgreSQL connection credentials
2. **Schema Exists**: `connect_backend` schema is properly set up
3. **Base Tables**: Core tables (projects, deliverables, internal_tasks, requirements) exist
4. **Enum Types**: Required enum types (requirementtype) are defined
5. **Backup**: Database backup has been created

## Migration Files

### 1. Main Migration SQL
```
ConvrseConnectBackend/migrations/complete_backend_enhancement_migration_20241230.sql
```
- Complete SQL migration script
- All phases in a single transaction
- Includes rollback safety

### 2. Migration Preparation Script
```
ConvrseConnectBackend/scripts/prepare_backend_enhancement_migration.py
```
- Python script for migration execution
- Validation and error handling
- Dry-run capability

## Execution Instructions

### Option 1: Direct SQL Execution

```bash
# Connect to PostgreSQL
psql -h localhost -U postgres -d convrse_connect

# Execute migration
\i ConvrseConnectBackend/migrations/complete_backend_enhancement_migration_20241230.sql
```

### Option 2: Python Script Execution

```bash
# Set environment variables
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=convrse_connect
export DB_USER=postgres
export DB_PASSWORD=your_password

# Navigate to backend directory
cd ConvrseConnectBackend

# Run dry-run first
python scripts/prepare_backend_enhancement_migration.py --dry-run --verbose

# Execute actual migration
python scripts/prepare_backend_enhancement_migration.py --verbose
```

## New Database Schema

### Core Enhancement Tables

#### 1. task_deliverable_associations
```sql
CREATE TABLE connect_backend.task_deliverable_associations (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL,
    deliverable_id UUID NOT NULL,
    is_primary_deliverable BOOLEAN DEFAULT FALSE,
    estimated_hours DECIMAL(8,2),
    actual_hours DECIMAL(8,2),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

#### 2. deliverable_pricing
```sql
CREATE TABLE connect_backend.deliverable_pricing (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    deliverable_id UUID NOT NULL,
    base_price DECIMAL(12,2) NOT NULL,
    markup_percentage DECIMAL(5,2) DEFAULT 0,
    final_price DECIMAL(12,2) NOT NULL,
    cost_breakdown JSONB,
    pricing_notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### 3. task_progress
```sql
CREATE TABLE connect_backend.task_progress (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL,
    progress_date DATE NOT NULL,
    percentage_complete DECIMAL(5,2) DEFAULT 0,
    hours_spent DECIMAL(8,2) DEFAULT 0,
    notes TEXT,
    created_by UUID NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### 4. project_timeline
```sql
CREATE TABLE connect_backend.project_timeline (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    phase_name VARCHAR(255) NOT NULL,
    phase_order INTEGER NOT NULL,
    planned_start_date DATE,
    planned_end_date DATE,
    actual_start_date DATE,
    actual_end_date DATE,
    is_milestone BOOLEAN DEFAULT FALSE,
    percentage_complete DECIMAL(5,2) DEFAULT 0
);
```

#### 5. requirement_templates
```sql
CREATE TABLE connect_backend.requirement_templates (
    id UUID PRIMARY KEY,
    deliverable_type VARCHAR(100) NOT NULL,
    requirement_name VARCHAR(255) NOT NULL,
    requirement_type connect_backend.requirementtype NOT NULL,
    is_mandatory BOOLEAN DEFAULT FALSE,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE
);
```

### Performance and Monitoring Tables

#### 6. query_cache
```sql
CREATE TABLE connect_backend.query_cache (
    id UUID PRIMARY KEY,
    cache_key VARCHAR(255) UNIQUE NOT NULL,
    cache_data JSONB NOT NULL,
    cache_type VARCHAR(50) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    access_count INTEGER DEFAULT 1
);
```

#### 7. project_analytics
```sql
CREATE TABLE connect_backend.project_analytics (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    analysis_date DATE NOT NULL,
    completion_rate DECIMAL(5,2) DEFAULT 0,
    budget_utilization DECIMAL(5,2) DEFAULT 0,
    project_health_score DECIMAL(5,2) DEFAULT 0,
    risk_level VARCHAR(20) DEFAULT 'LOW',
    recommendations JSONB
);
```

#### 8. system_alerts
```sql
CREATE TABLE connect_backend.system_alerts (
    id UUID PRIMARY KEY,
    alert_type VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    project_id UUID,
    is_acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Integration and Orchestration Tables

#### 9. orchestration_events
```sql
CREATE TABLE connect_backend.orchestration_events (
    id UUID PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    event_name VARCHAR(255) NOT NULL,
    source_service VARCHAR(100) NOT NULL,
    event_data JSONB NOT NULL,
    status VARCHAR(50) DEFAULT 'PENDING',
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### 10. orchestration_config
```sql
CREATE TABLE connect_backend.orchestration_config (
    id UUID PRIMARY KEY,
    config_key VARCHAR(255) UNIQUE NOT NULL,
    config_value JSONB NOT NULL,
    config_type VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    description TEXT
);
```

## Performance Optimizations

### Indexes Created
- Task associations: `idx_tda_task_id`, `idx_tda_deliverable_id`
- Pricing: `idx_dp_project_id`, `idx_dp_deliverable_id`
- Progress tracking: `idx_tp_task_id`, `idx_tp_progress_date`
- Timeline: `idx_pt_project_id`, `idx_pt_phase_order`
- Cache: `idx_qc_cache_key`, `idx_qc_expires_at`
- Analytics: `idx_pa_project_id`, `idx_pa_analysis_date`
- Alerts: `idx_sa_alert_type`, `idx_sa_severity`

### Triggers Created
- Automatic `updated_at` timestamp updates
- Cache access tracking
- Data validation triggers

## Configuration Data

### Default Orchestration Configuration
```json
{
  "auto_generate_requirements": {"enabled": true, "delay_seconds": 0},
  "task_sharing_suggestions": {"enabled": true, "similarity_threshold": 0.8},
  "budget_auto_calculation": {"enabled": true, "recalculate_on_change": true},
  "performance_monitoring": {"enabled": true, "cache_ttl_hours": 24}
}
```

### Requirement Templates
- 3D Rendering templates
- Animation templates
- Product Visualization templates
- Architectural Visualization templates
- VR Experience templates
- Video Walkthrough templates

## Verification Steps

After migration completion, verify:

1. **Table Creation**: All 11 new tables exist
2. **Index Creation**: All performance indexes are in place
3. **Trigger Functionality**: Update triggers work correctly
4. **Data Integrity**: Foreign key constraints are valid
5. **Configuration**: Default configuration entries exist
6. **Templates**: Requirement templates are populated

### Verification Queries

```sql
-- Check table existence
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'connect_backend' 
AND table_name IN (
    'task_deliverable_associations', 'deliverable_pricing', 
    'task_progress', 'project_timeline', 'requirement_templates',
    'query_cache', 'performance_metrics', 'project_analytics',
    'system_alerts', 'orchestration_events', 'orchestration_config'
);

-- Check configuration entries
SELECT config_key, is_active FROM connect_backend.orchestration_config;

-- Check requirement templates
SELECT deliverable_type, COUNT(*) as template_count 
FROM connect_backend.requirement_templates 
GROUP BY deliverable_type;

-- Check migration log
SELECT * FROM connect_backend.migration_log 
WHERE migration_name = 'backend_enhancement_complete';
```

## Rollback Strategy

If rollback is needed:

1. **Stop Application**: Ensure no active connections
2. **Restore Backup**: Restore from pre-migration backup
3. **Verify Integrity**: Run integrity checks
4. **Resume Application**: Restart with original schema

### Manual Rollback (if needed)
```sql
-- Drop new tables in reverse dependency order
DROP TABLE IF EXISTS connect_backend.orchestration_config CASCADE;
DROP TABLE IF EXISTS connect_backend.orchestration_events CASCADE;
DROP TABLE IF EXISTS connect_backend.system_alerts CASCADE;
DROP TABLE IF EXISTS connect_backend.project_analytics CASCADE;
DROP TABLE IF EXISTS connect_backend.performance_metrics CASCADE;
DROP TABLE IF EXISTS connect_backend.query_cache CASCADE;
DROP TABLE IF EXISTS connect_backend.requirement_templates CASCADE;
DROP TABLE IF EXISTS connect_backend.project_timeline CASCADE;
DROP TABLE IF EXISTS connect_backend.task_progress CASCADE;
DROP TABLE IF EXISTS connect_backend.deliverable_pricing CASCADE;
DROP TABLE IF EXISTS connect_backend.task_deliverable_associations CASCADE;

-- Remove added columns from existing tables
ALTER TABLE connect_backend.internal_tasks 
DROP COLUMN IF EXISTS estimated_hours,
DROP COLUMN IF EXISTS actual_hours,
DROP COLUMN IF EXISTS is_project_level,
DROP COLUMN IF EXISTS task_template_id;

ALTER TABLE connect_backend.requirements 
DROP COLUMN IF EXISTS is_project_level,
DROP COLUMN IF EXISTS template_id;

ALTER TABLE connect_backend.projects
DROP COLUMN IF EXISTS calculated_budget,
DROP COLUMN IF EXISTS actual_cost,
DROP COLUMN IF EXISTS budget_variance,
DROP COLUMN IF EXISTS budget_last_calculated;
```

## Post-Migration Tasks

1. **Update Application Configuration**: Enable new features
2. **Deploy Backend Updates**: Deploy enhanced backend code
3. **Update API Documentation**: Reflect new endpoints
4. **Train Team**: Brief team on new capabilities
5. **Monitor Performance**: Watch for any performance issues
6. **Validate Functionality**: Test critical workflows

## Support and Troubleshooting

### Common Issues

1. **Permission Errors**: Ensure user has CREATE, INSERT, UPDATE privileges
2. **Foreign Key Violations**: Verify referenced tables exist
3. **Enum Type Missing**: Ensure `requirementtype` enum is defined
4. **Connection Issues**: Check database connectivity and credentials

### Contact Information
- **Database Team**: backend-team@convrse.io
- **Project Lead**: project-lead@convrse.io
- **Emergency Contact**: emergency@convrse.io

---

**Migration Date**: December 30, 2024  
**Version**: 1.0.0  
**Status**: Ready for Execution 