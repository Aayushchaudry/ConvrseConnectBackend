-- ================================================================
-- DATABASE VERIFICATION SCRIPT
-- ================================================================
-- This script verifies that all schemas and tables were created
-- correctly for all three services
-- ================================================================

-- Show current database info
SELECT 
    current_database() as database_name,
    current_user as current_user,
    NOW() as verification_time;

-- ================================================================
-- SCHEMA VERIFICATION
-- ================================================================
\echo ''
\echo '=== SCHEMA VERIFICATION ==='

SELECT 
    'Schema Check' as verification_type,
    schema_name,
    CASE 
        WHEN schema_name IN ('connect_backend', 'auth_service', 'platform_service') 
        THEN '✅ FOUND' 
        ELSE '❌ MISSING' 
    END as status
FROM information_schema.schemata 
WHERE schema_name IN ('connect_backend', 'auth_service', 'platform_service')
ORDER BY schema_name;

-- Count of expected schemas
SELECT 
    'Expected Schemas' as info,
    3 as expected_count,
    COUNT(*) as actual_count,
    CASE WHEN COUNT(*) = 3 THEN '✅ PASS' ELSE '❌ FAIL' END as status
FROM information_schema.schemata 
WHERE schema_name IN ('connect_backend', 'auth_service', 'platform_service');

-- ================================================================
-- TABLE COUNT VERIFICATION
-- ================================================================
\echo ''
\echo '=== TABLE COUNT VERIFICATION ==='

SELECT 
    'Table Count by Schema' as verification_type,
    table_schema as schema_name,
    COUNT(*) as table_count,
    CASE table_schema
        WHEN 'connect_backend' THEN 
            CASE WHEN COUNT(*) >= 15 THEN '✅ PASS' ELSE '❌ FAIL' END
        WHEN 'auth_service' THEN 
            CASE WHEN COUNT(*) >= 8 THEN '✅ PASS' ELSE '❌ FAIL' END
        WHEN 'platform_service' THEN 
            CASE WHEN COUNT(*) >= 5 THEN '✅ PASS' ELSE '❌ FAIL' END
        ELSE '❓ UNKNOWN'
    END as status
FROM information_schema.tables 
WHERE table_schema IN ('connect_backend', 'auth_service', 'platform_service')
GROUP BY table_schema
ORDER BY table_schema;

-- ================================================================
-- CONNECT_BACKEND TABLES
-- ================================================================
\echo ''
\echo '=== CONNECT_BACKEND TABLES ==='

SELECT 
    'connect_backend' as schema_name,
    table_name,
    '✅ EXISTS' as status
FROM information_schema.tables 
WHERE table_schema = 'connect_backend'
ORDER BY table_name;

-- Expected connect_backend tables
WITH expected_tables(table_name) AS (
    VALUES 
        ('projects'), ('deliverables'), ('requirements'), ('internal_tasks'),
        ('activity_logs'), ('review_items'), ('saga_state'), ('task_progress'),
        ('client_feedbacks'), ('project_outputs'), ('requirement_files'),
        ('task_deliverable_associations'), ('project_timeline'), ('requirement_templates')
)
SELECT 
    'Expected Tables Check' as verification_type,
    et.table_name,
    CASE 
        WHEN t.table_name IS NOT NULL THEN '✅ FOUND'
        ELSE '❌ MISSING'
    END as status
FROM expected_tables et
LEFT JOIN information_schema.tables t 
    ON et.table_name = t.table_name AND t.table_schema = 'connect_backend'
ORDER BY et.table_name;

-- ================================================================
-- AUTH_SERVICE TABLES
-- ================================================================
\echo ''
\echo '=== AUTH_SERVICE TABLES ==='

SELECT 
    'auth_service' as schema_name,
    table_name,
    '✅ EXISTS' as status
FROM information_schema.tables 
WHERE table_schema = 'auth_service'
ORDER BY table_name;

-- Expected auth_service tables
WITH expected_tables(table_name) AS (
    VALUES 
        ('businesses'), ('users'), ('roles'), ('permissions'),
        ('user_roles'), ('role_permissions'), ('refresh_tokens'),
        ('service_clients'), ('permission_audit_logs'), ('rate_limit_usage')
)
SELECT 
    'Expected Tables Check' as verification_type,
    et.table_name,
    CASE 
        WHEN t.table_name IS NOT NULL THEN '✅ FOUND'
        ELSE '❌ MISSING'
    END as status
FROM expected_tables et
LEFT JOIN information_schema.tables t 
    ON et.table_name = t.table_name AND t.table_schema = 'auth_service'
ORDER BY et.table_name;

-- ================================================================
-- PLATFORM_SERVICE TABLES
-- ================================================================
\echo ''
\echo '=== PLATFORM_SERVICE TABLES ==='

SELECT 
    'platform_service' as schema_name,
    table_name,
    '✅ EXISTS' as status
FROM information_schema.tables 
WHERE table_schema = 'platform_service'
ORDER BY table_name;

-- Expected platform_service tables
WITH expected_tables(table_name) AS (
    VALUES 
        ('file_features'), ('contents'), ('content_id_mapping'),
        ('notifications'), ('notification_preferences')
)
SELECT 
    'Expected Tables Check' as verification_type,
    et.table_name,
    CASE 
        WHEN t.table_name IS NOT NULL THEN '✅ FOUND'
        ELSE '❌ MISSING'
    END as status
FROM expected_tables et
LEFT JOIN information_schema.tables t 
    ON et.table_name = t.table_name AND t.table_schema = 'platform_service'
ORDER BY et.table_name;

-- ================================================================
-- ENUM VERIFICATION (connect_backend only)
-- ================================================================
\echo ''
\echo '=== ENUM VERIFICATION ==='

SELECT 
    'Enum Types' as verification_type,
    typname as enum_name,
    '✅ EXISTS' as status
FROM pg_type t
JOIN pg_namespace n ON n.oid = t.typnamespace
WHERE n.nspname = 'connect_backend' 
AND t.typtype = 'e'
ORDER BY typname;

-- Expected enums
WITH expected_enums(enum_name) AS (
    VALUES 
        ('projectstatus'), ('deliverabletype'), ('deliverablestatus'),
        ('requirementtype'), ('requirementstatus'), ('tasktype'),
        ('taskstatus'), ('priority'), ('reviewitemtype'),
        ('reviewstatus'), ('sagastatus'), ('sagatype'), ('feedbacktype')
)
SELECT 
    'Expected Enums Check' as verification_type,
    ee.enum_name,
    CASE 
        WHEN t.typname IS NOT NULL THEN '✅ FOUND'
        ELSE '❌ MISSING'
    END as status
FROM expected_enums ee
LEFT JOIN pg_type t ON ee.enum_name = t.typname
LEFT JOIN pg_namespace n ON n.oid = t.typnamespace AND n.nspname = 'connect_backend'
WHERE t.typtype = 'e' OR t.typtype IS NULL
ORDER BY ee.enum_name;

-- ================================================================
-- INDEX VERIFICATION
-- ================================================================
\echo ''
\echo '=== INDEX VERIFICATION ==='

SELECT 
    'Index Count by Schema' as verification_type,
    schemaname as schema_name,
    COUNT(*) as index_count,
    '✅ INFO' as status
FROM pg_indexes 
WHERE schemaname IN ('connect_backend', 'auth_service', 'platform_service')
GROUP BY schemaname
ORDER BY schemaname;

-- ================================================================
-- FOREIGN KEY VERIFICATION
-- ================================================================
\echo ''
\echo '=== FOREIGN KEY VERIFICATION ==='

SELECT 
    'Foreign Key Count by Schema' as verification_type,
    n.nspname as schema_name,
    COUNT(*) as fk_count,
    '✅ INFO' as status
FROM pg_constraint c
JOIN pg_namespace n ON n.oid = c.connamespace
WHERE c.contype = 'f' 
AND n.nspname IN ('connect_backend', 'auth_service', 'platform_service')
GROUP BY n.nspname
ORDER BY n.nspname;

-- ================================================================
-- SPECIFIC FIELD VERIFICATION (business_id UUID fix)
-- ================================================================
\echo ''
\echo '=== BUSINESS_ID FIELD VERIFICATION ==='

SELECT 
    'business_id Field Check' as verification_type,
    'connect_backend.projects' as table_name,
    column_name,
    data_type,
    CASE 
        WHEN data_type = 'uuid' THEN '✅ CORRECT (UUID)'
        ELSE '❌ WRONG TYPE'
    END as status
FROM information_schema.columns 
WHERE table_schema = 'connect_backend' 
AND table_name = 'projects' 
AND column_name = 'business_id';

-- ================================================================
-- SUMMARY
-- ================================================================
\echo ''
\echo '=== VERIFICATION SUMMARY ==='

WITH verification_summary AS (
    SELECT 
        'Schemas' as component,
        COUNT(*) as count,
        3 as expected,
        COUNT(*) = 3 as is_correct
    FROM information_schema.schemata 
    WHERE schema_name IN ('connect_backend', 'auth_service', 'platform_service')
    
    UNION ALL
    
    SELECT 
        'Tables Total' as component,
        COUNT(*) as count,
        28 as expected,  -- Approximate expected total
        COUNT(*) >= 28 as is_correct
    FROM information_schema.tables 
    WHERE table_schema IN ('connect_backend', 'auth_service', 'platform_service')
    
    UNION ALL
    
    SELECT 
        'Enums' as component,
        COUNT(*) as count,
        13 as expected,
        COUNT(*) >= 13 as is_correct
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'connect_backend' 
    AND t.typtype = 'e'
)
SELECT 
    component,
    count as actual_count,
    expected as expected_count,
    CASE 
        WHEN is_correct THEN '✅ PASS'
        ELSE '❌ FAIL'
    END as status
FROM verification_summary;

-- Final message
\echo ''
\echo '=== VERIFICATION COMPLETE ==='
SELECT 
    'Database Recreation Verification' as message,
    NOW() as completed_at,
    'Check the status column above for any ❌ FAIL items' as note; 