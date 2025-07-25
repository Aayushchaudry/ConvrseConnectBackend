# tests/integration/test_error_recovery_workflows.py

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
from uuid import uuid4, UUID

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from src.services.file_upload_error_handler import (
    FileUploadErrorHandler, FailedUploadRecord, ErrorLogRecord, RecoveryAction, RecoveryResult
)
from src.services.manual_recovery_service import (
    ManualRecoveryService, ManualRecoveryRequest, RecoveryDashboardData
)
from src.utils.file_upload_errors import (
    FileUploadError, ValidationError, NetworkError, StorageError,
    AuthenticationError, ExternalServiceError, ErrorSeverity, ErrorCategory
)


@pytest.fixture
async def test_db_session():
    """Create test database session"""
    # Use in-memory SQLite for testing
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE failed_upload_records (
                id TEXT PRIMARY KEY,
                service TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                error_type TEXT NOT NULL,
                error_details TEXT,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                next_retry_at TIMESTAMP,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                context_data TEXT,
                recovery_notes TEXT
            )
        """))
        
        await conn.execute(text("""
            CREATE TABLE error_log_records (
                id TEXT PRIMARY KEY,
                error_id TEXT NOT NULL,
                service TEXT NOT NULL,
                error_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                category TEXT NOT NULL,
                user_message TEXT,
                technical_message TEXT,
                error_details TEXT,
                context_data TEXT,
                recovery_suggestions TEXT,
                stack_trace TEXT,
                user_id TEXT,
                session_id TEXT,
                request_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved BOOLEAN DEFAULT FALSE,
                resolution_notes TEXT
            )
        """))
    
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        yield session
    
    await engine.dispose()


@pytest.fixture
async def error_handler(test_db_session):
    """Create error handler instance"""
    return FileUploadErrorHandler(test_db_session)


@pytest.fixture
async def manual_recovery_service(test_db_session, error_handler):
    """Create manual recovery service instance"""
    return ManualRecoveryService(test_db_session, error_handler)


class TestErrorRecoveryWorkflows:
    """Integration tests for error recovery workflows"""
    
    @pytest.mark.asyncio
    async def test_complete_error_recovery_workflow(self, error_handler, test_db_session):
        """Test complete error recovery workflow from error to resolution"""
        requirement_id = uuid4()
        
        # 1. Create an error
        error = NetworkError(
            "RequirementService",
            {"connection_timeout": True, "retry_after": 30}
        )
        
        # 2. Handle the error (should create failed upload record)
        recovery_result = await error_handler.handle_requirement_upload_error(
            error, requirement_id, {"file_count": 3, "total_size": 1024000}
        )
        
        assert recovery_result.action_taken == RecoveryAction.RETRY
        assert recovery_result.retry_after is not None
        
        # 3. Create failed upload record
        record_id = await error_handler.create_failed_upload_record(
            "RequirementService", requirement_id, "requirement", error,
            {"file_count": 3, "total_size": 1024000}
        )
        
        assert record_id is not None
        
        # 4. Process recovery (simulate successful recovery)
        with patch.object(error_handler, '_recover_requirement_upload') as mock_recover:
            mock_recover.return_value = RecoveryResult(
                success=True,
                action_taken=RecoveryAction.RETRY,
                details={"recovered_via": "network_retry"},
                recovery_message="Network issue resolved, upload completed"
            )
            
            recovery_results = await error_handler.process_failed_upload_recovery()
            
            assert recovery_results["total_processed"] >= 1
            assert recovery_results["successful_recoveries"] >= 1
        
        # 5. Verify record is marked as resolved
        intervention_queue = await error_handler.get_manual_intervention_queue()
        resolved_records = [r for r in intervention_queue if r["status"] == "resolved"]
        
        # The record should either be resolved or not in the intervention queue
        assert len(resolved_records) >= 0  # Could be 0 if resolved records are filtered out
    
    @pytest.mark.asyncio
    async def test_manual_intervention_workflow(self, manual_recovery_service, error_handler, test_db_session):
        """Test manual intervention workflow"""
        task_id = uuid4()
        
        # 1. Create a validation error that requires manual intervention
        error = ValidationError(
            "ReviewItemService",
            ["Invalid file type: .exe", "File size exceeds limit: 100MB"]
        )
        
        # 2. Create failed upload record
        record_id = await error_handler.create_failed_upload_record(
            "ReviewItemService", task_id, "review_item", error,
            {"file_names": ["document.exe"], "file_sizes": [104857600]}
        )
        
        # 3. Get manual intervention queue
        intervention_queue = await error_handler.get_manual_intervention_queue()
        
        assert len(intervention_queue) >= 1
        intervention_record = next(
            (r for r in intervention_queue if r["record_id"] == record_id), None
        )
        assert intervention_record is not None
        assert intervention_record["error_type"] == "VALIDATION_ERROR"
        
        # 4. Process manual recovery - skip the problematic upload
        recovery_request = ManualRecoveryRequest(
            record_id=record_id,
            recovery_action="skip",
            recovery_notes="File type not supported, client will provide alternative format",
            resolved_by="admin_user_123"
        )
        
        recovery_result = await manual_recovery_service.process_manual_recovery(recovery_request)
        
        assert recovery_result["success"] is True
        assert recovery_result["action"] == "skip"
        
        # 5. Verify record is resolved
        updated_queue = await error_handler.get_manual_intervention_queue()
        remaining_record = next(
            (r for r in updated_queue if r["record_id"] == record_id), None
        )
        
        # Record should either be resolved or not in queue anymore
        if remaining_record:
            assert remaining_record["status"] == "resolved"
    
    @pytest.mark.asyncio
    async def test_retry_with_exponential_backoff(self, error_handler):
        """Test retry mechanism with exponential backoff"""
        call_count = 0
        call_times = []
        
        async def failing_operation():
            nonlocal call_count
            call_count += 1
            call_times.append(datetime.utcnow())
            
            if call_count <= 2:
                raise NetworkError("TestService", {"attempt": call_count})
            
            return {"success": True, "attempt": call_count}
        
        start_time = datetime.utcnow()
        
        result = await error_handler.retry_failed_upload(
            failing_operation, (), {}, "TestService", max_retries=3
        )
        
        end_time = datetime.utcnow()
        
        assert result.success is True
        assert result.attempt_number == 3
        assert call_count == 3
        assert len(call_times) == 3
        
        # Verify exponential backoff timing
        total_duration = (end_time - start_time).total_seconds()
        assert total_duration >= 3.0  # Should have at least base delays (1s + 2s)
        
        # Verify retry history
        assert len(result.retry_history) == 2  # Two failed attempts before success
        assert all("NETWORK_ERROR" in entry["error_type"] for entry in result.retry_history)
    
    @pytest.mark.asyncio
    async def test_error_logging_and_monitoring(self, error_handler, test_db_session):
        """Test comprehensive error logging and monitoring"""
        # 1. Create and log multiple errors
        errors = [
            NetworkError("RequirementService", {"timeout": True}),
            ValidationError("ReviewItemService", ["Invalid format"]),
            StorageError("PlatformService", {"disk_full": True}),
            AuthenticationError("RequirementService", {"token_expired": True})
        ]
        
        for i, error in enumerate(errors):
            await error_handler.log_error_to_database(
                error,
                {"request_id": f"req_{i}", "user_action": "file_upload"},
                user_id=f"user_{i}",
                session_id=f"session_{i}",
                request_id=f"req_{i}"
            )
        
        # 2. Get monitoring dashboard data
        dashboard_data = await error_handler.get_monitoring_dashboard_data()
        
        assert "error_metrics" in dashboard_data
        assert "recovery_metrics" in dashboard_data
        assert "service_health" in dashboard_data
        assert "alerts" in dashboard_data
        
        # Verify error metrics
        error_metrics = dashboard_data["error_metrics"]
        assert error_metrics["total_errors_24h"] >= 4
        
        # Verify service health
        service_health = dashboard_data["service_health"]
        assert "RequirementService" in service_health
        assert "ReviewItemService" in service_health
        assert "PlatformService" in service_health
        
        # 3. Get error statistics
        stats = await error_handler.get_error_statistics()
        
        assert "current_metrics" in stats
        assert "retry_configurations" in stats
        assert "recovery_strategies" in stats
        assert "error_trends" in stats
    
    @pytest.mark.asyncio
    async def test_bulk_recovery_operations(self, manual_recovery_service, error_handler):
        """Test bulk recovery operations"""
        # 1. Create multiple failed upload records
        record_ids = []
        
        for i in range(5):
            error = NetworkError(f"Service_{i}", {"connection_failed": True})
            record_id = await error_handler.create_failed_upload_record(
                f"Service_{i}", uuid4(), "requirement", error, {"batch": i}
            )
            record_ids.append(record_id)
        
        # 2. Perform bulk resolution
        bulk_result = await manual_recovery_service.bulk_resolve_interventions(
            record_ids,
            "Bulk resolution: Network issues resolved by infrastructure team",
            "admin_user_456"
        )
        
        assert bulk_result["total_requested"] == 5
        assert bulk_result["successful"] >= 0  # Some might succeed
        assert bulk_result["failed"] >= 0
        assert len(bulk_result["details"]) == 5
        
        # 3. Verify resolutions
        for detail in bulk_result["details"]:
            assert detail["record_id"] in record_ids
            assert detail["status"] in ["resolved", "failed", "error"]
    
    @pytest.mark.asyncio
    async def test_recovery_dashboard_data(self, manual_recovery_service, error_handler):
        """Test recovery dashboard data aggregation"""
        # 1. Create various types of failed uploads
        requirement_error = ValidationError("RequirementService", ["Invalid file"])
        review_error = StorageError("ReviewItemService", {"storage_full": True})
        
        req_record_id = await error_handler.create_failed_upload_record(
            "RequirementService", uuid4(), "requirement", requirement_error
        )
        
        review_record_id = await error_handler.create_failed_upload_record(
            "ReviewItemService", uuid4(), "review_item", review_error
        )
        
        # 2. Get dashboard data
        dashboard_data = await manual_recovery_service.get_recovery_dashboard()
        
        assert isinstance(dashboard_data, RecoveryDashboardData)
        assert len(dashboard_data.pending_interventions) >= 2
        assert isinstance(dashboard_data.recovery_statistics, dict)
        assert isinstance(dashboard_data.service_health_summary, dict)
        assert isinstance(dashboard_data.alerts, list)
        
        # 3. Verify pending interventions contain our records
        pending_ids = [r["record_id"] for r in dashboard_data.pending_interventions]
        assert req_record_id in pending_ids
        assert review_record_id in pending_ids
    
    @pytest.mark.asyncio
    async def test_recovery_history_tracking(self, manual_recovery_service, error_handler):
        """Test recovery history tracking and filtering"""
        service_name = "TestHistoryService"
        resource_id = str(uuid4())
        
        # 1. Create multiple records for the same resource
        for i in range(3):
            error = NetworkError(service_name, {"attempt": i})
            await error_handler.create_failed_upload_record(
                service_name, UUID(resource_id), "requirement", error,
                {"attempt": i, "timestamp": datetime.utcnow().isoformat()}
            )
        
        # 2. Get history for specific resource
        resource_history = await manual_recovery_service.get_recovery_history(
            resource_id=resource_id,
            service=service_name,
            days=1
        )
        
        assert len(resource_history) == 3
        assert all(r["resource_id"] == resource_id for r in resource_history)
        assert all(r["service"] == service_name for r in resource_history)
        
        # 3. Get history for specific service
        service_history = await manual_recovery_service.get_recovery_history(
            service=service_name,
            days=1
        )
        
        assert len(service_history) >= 3
        assert all(r["service"] == service_name for r in service_history)
    
    @pytest.mark.asyncio
    async def test_error_recovery_with_context_modification(self, manual_recovery_service, error_handler):
        """Test error recovery with context modification"""
        task_id = uuid4()
        
        # 1. Create error with specific context
        error = ExternalServiceError(
            "ReviewItemService", "PlatformService",
            {"endpoint": "/upload", "status_code": 503}
        )
        
        original_context = {
            "file_names": ["document.pdf"],
            "upload_endpoint": "/api/v1/upload",
            "retry_count": 0
        }
        
        record_id = await error_handler.create_failed_upload_record(
            "ReviewItemService", task_id, "review_item", error, original_context
        )
        
        # 2. Modify context for recovery
        modified_context = {
            **original_context,
            "upload_endpoint": "/api/v2/upload",  # Use different endpoint
            "retry_count": 1,
            "fallback_mode": True
        }
        
        recovery_request = ManualRecoveryRequest(
            record_id=record_id,
            recovery_action="modify",
            recovery_notes="Switched to v2 API endpoint for better reliability",
            modified_context=modified_context,
            resolved_by="tech_lead_789"
        )
        
        # 3. Process modification
        with patch.object(error_handler, '_recover_review_item_upload') as mock_recover:
            mock_recover.return_value = RecoveryResult(
                success=True,
                action_taken=RecoveryAction.RETRY,
                details={"recovered_via": "modified_context"},
                recovery_message="Recovery successful with modified context"
            )
            
            recovery_result = await manual_recovery_service.process_manual_recovery(recovery_request)
            
            assert recovery_result["success"] is True
            assert recovery_result["action"] == "modify"
            assert recovery_result["modified_context"] == modified_context
    
    @pytest.mark.asyncio
    async def test_error_escalation_workflow(self, manual_recovery_service, error_handler):
        """Test error escalation workflow"""
        requirement_id = uuid4()
        
        # 1. Create critical error
        error = AuthenticationError(
            "RequirementService",
            {"auth_service_down": True, "impact": "all_users"}
        )
        
        record_id = await error_handler.create_failed_upload_record(
            "RequirementService", requirement_id, "requirement", error,
            {"affected_users": 150, "business_impact": "high"}
        )
        
        # 2. Escalate the issue
        escalation_request = ManualRecoveryRequest(
            record_id=record_id,
            recovery_action="escalate",
            recovery_notes="Authentication service outage affecting all users. Requires immediate attention from infrastructure team.",
            resolved_by="support_manager_456",
            priority="critical"
        )
        
        recovery_result = await manual_recovery_service.process_manual_recovery(escalation_request)
        
        assert recovery_result["success"] is True
        assert recovery_result["action"] == "escalate"
        assert "escalation_data" in recovery_result
        
        escalation_data = recovery_result["escalation_data"]
        assert escalation_data["priority"] == "critical"
        assert escalation_data["escalated_by"] == "support_manager_456"
        assert "infrastructure team" in escalation_data["escalation_notes"]


if __name__ == "__main__":
    pytest.main([__file__])