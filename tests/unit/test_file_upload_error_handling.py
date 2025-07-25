# tests/unit/test_file_upload_error_handling.py

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
from uuid import uuid4, UUID

from src.utils.file_upload_errors import (
    FileUploadError, ValidationError, NetworkError, StorageError,
    AuthenticationError, AuthorizationError, ExternalServiceError,
    RetryConfig, ErrorMetrics, ErrorSeverity, ErrorCategory, RetryStrategy
)
from src.services.file_upload_error_handler import (
    FileUploadErrorHandler, RecoveryAction, RecoveryResult, RetryResult
)


class TestFileUploadErrors:
    """Test file upload error classes"""
    
    def test_file_upload_error_creation(self):
        """Test basic FileUploadError creation"""
        error = FileUploadError(
            service="TestService",
            error_type="TEST_ERROR",
            details={"test": "value"}
        )
        
        assert error.service == "TestService"
        assert error.error_type == "TEST_ERROR"
        assert error.details == {"test": "value"}
        assert error.severity == ErrorSeverity.MEDIUM
        assert error.category == ErrorCategory.SYSTEM
        assert error.retry_strategy == RetryStrategy.EXPONENTIAL
        assert error.error_id is not None
        assert len(error.error_id) == 12
        assert error.is_retryable() is True
    
    def test_file_upload_error_to_dict(self):
        """Test error serialization to dictionary"""
        error = FileUploadError(
            service="TestService",
            error_type="TEST_ERROR",
            details={"test": "value"},
            user_message="User friendly message",
            recovery_suggestions=["Try again", "Contact support"]
        )
        
        error_dict = error.to_dict()
        
        assert error_dict["service"] == "TestService"
        assert error_dict["error_type"] == "TEST_ERROR"
        assert error_dict["details"] == {"test": "value"}
        assert error_dict["user_message"] == "User friendly message"
        assert error_dict["recovery_suggestions"] == ["Try again", "Contact support"]
        assert "error_id" in error_dict
        assert "timestamp" in error_dict
    
    def test_validation_error(self):
        """Test ValidationError specific behavior"""
        validation_errors = ["Invalid file type", "File too large"]
        error = ValidationError("TestService", validation_errors)
        
        assert error.error_type == "VALIDATION_ERROR"
        assert error.severity == ErrorSeverity.LOW
        assert error.category == ErrorCategory.VALIDATION
        assert error.retry_strategy == RetryStrategy.NONE
        assert error.is_retryable() is False
        assert error.details["validation_errors"] == validation_errors
        assert "Check file types" in error.recovery_suggestions[0]
    
    def test_network_error(self):
        """Test NetworkError specific behavior"""
        network_details = {"status_code": 500, "timeout": True}
        error = NetworkError("TestService", network_details)
        
        assert error.error_type == "NETWORK_ERROR"
        assert error.severity == ErrorSeverity.HIGH
        assert error.category == ErrorCategory.NETWORK
        assert error.retry_strategy == RetryStrategy.EXPONENTIAL
        assert error.is_retryable() is True
        assert error.details == network_details
        assert "internet connection" in error.recovery_suggestions[0]
    
    def test_storage_error(self):
        """Test StorageError specific behavior"""
        storage_details = {"disk_full": True, "path": "/uploads"}
        error = StorageError("TestService", storage_details)
        
        assert error.error_type == "STORAGE_ERROR"
        assert error.severity == ErrorSeverity.HIGH
        assert error.category == ErrorCategory.STORAGE
        assert error.retry_strategy == RetryStrategy.LINEAR
        assert error.is_retryable() is True
        assert error.details == storage_details
    
    def test_authentication_error(self):
        """Test AuthenticationError specific behavior"""
        auth_details = {"token_expired": True}
        error = AuthenticationError("TestService", auth_details)
        
        assert error.error_type == "AUTHENTICATION_ERROR"
        assert error.severity == ErrorSeverity.CRITICAL
        assert error.category == ErrorCategory.AUTHENTICATION
        assert error.retry_strategy == RetryStrategy.NONE
        assert error.is_retryable() is False
        assert "log in again" in error.recovery_suggestions[0]
    
    def test_authorization_error(self):
        """Test AuthorizationError specific behavior"""
        auth_details = {"permission": "upload", "required_role": "admin"}
        error = AuthorizationError("TestService", auth_details)
        
        assert error.error_type == "AUTHORIZATION_ERROR"
        assert error.severity == ErrorSeverity.HIGH
        assert error.category == ErrorCategory.AUTHORIZATION
        assert error.retry_strategy == RetryStrategy.NONE
        assert error.is_retryable() is False
        assert "administrator" in error.recovery_suggestions[0]
    
    def test_external_service_error(self):
        """Test ExternalServiceError specific behavior"""
        service_details = {"response_code": 503, "service_down": True}
        error = ExternalServiceError("TestService", "PlatformService", service_details)
        
        assert error.error_type == "EXTERNAL_SERVICE_ERROR"
        assert error.severity == ErrorSeverity.HIGH
        assert error.category == ErrorCategory.EXTERNAL_SERVICE
        assert error.retry_strategy == RetryStrategy.EXPONENTIAL
        assert error.is_retryable() is True
        assert error.details["external_service"] == "PlatformService"
        assert "PlatformService service" in error.recovery_suggestions[0]


class TestRetryConfig:
    """Test retry configuration"""
    
    def test_default_retry_config(self):
        """Test default retry configuration"""
        config = RetryConfig()
        
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.backoff_factor == 2.0
        assert config.jitter is True
    
    def test_custom_retry_config(self):
        """Test custom retry configuration"""
        config = RetryConfig(
            max_attempts=5,
            base_delay=2.0,
            max_delay=120.0,
            backoff_factor=3.0,
            jitter=False
        )
        
        assert config.max_attempts == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 120.0
        assert config.backoff_factor == 3.0
        assert config.jitter is False
    
    def test_calculate_delay(self):
        """Test delay calculation"""
        config = RetryConfig(
            base_delay=1.0,
            backoff_factor=2.0,
            max_delay=10.0,
            jitter=False
        )
        
        assert config.calculate_delay(0) == 0.0
        assert config.calculate_delay(1) == 1.0
        assert config.calculate_delay(2) == 2.0
        assert config.calculate_delay(3) == 4.0
        assert config.calculate_delay(4) == 8.0
        assert config.calculate_delay(5) == 10.0  # Capped at max_delay
    
    def test_calculate_delay_with_jitter(self):
        """Test delay calculation with jitter"""
        config = RetryConfig(
            base_delay=2.0,
            backoff_factor=2.0,
            max_delay=100.0,
            jitter=True
        )
        
        # With jitter, delay should be between 50% and 100% of calculated value
        delay = config.calculate_delay(2)  # Base calculation: 4.0
        assert 2.0 <= delay <= 4.0


class TestErrorMetrics:
    """Test error metrics tracking"""
    
    def test_empty_metrics(self):
        """Test empty error metrics"""
        metrics = ErrorMetrics()
        
        assert metrics.total_errors == 0
        assert metrics.errors_by_type == {}
        assert metrics.errors_by_service == {}
        assert metrics.errors_by_severity == {}
        assert metrics.retry_success_rate == 0.0
        assert metrics.average_retry_attempts == 0.0
    
    def test_add_error_to_metrics(self):
        """Test adding errors to metrics"""
        metrics = ErrorMetrics()
        
        error1 = FileUploadError("Service1", "ERROR_TYPE_1", {})
        error2 = FileUploadError("Service1", "ERROR_TYPE_2", {}, severity=ErrorSeverity.HIGH)
        error3 = FileUploadError("Service2", "ERROR_TYPE_1", {})
        
        metrics.add_error(error1)
        metrics.add_error(error2)
        metrics.add_error(error3)
        
        assert metrics.total_errors == 3
        assert metrics.errors_by_type["ERROR_TYPE_1"] == 2
        assert metrics.errors_by_type["ERROR_TYPE_2"] == 1
        assert metrics.errors_by_service["Service1"] == 2
        assert metrics.errors_by_service["Service2"] == 1
        assert metrics.errors_by_severity["medium"] == 2
        assert metrics.errors_by_severity["high"] == 1


@pytest.fixture
def mock_db_session():
    """Mock database session"""
    session = AsyncMock()
    return session


@pytest.fixture
def error_handler(mock_db_session):
    """Create error handler instance"""
    return FileUploadErrorHandler(mock_db_session)


class TestFileUploadErrorHandler:
    """Test file upload error handler"""
    
    def test_error_handler_initialization(self, error_handler):
        """Test error handler initialization"""
        assert error_handler.db_session is not None
        assert isinstance(error_handler.error_metrics, ErrorMetrics)
        assert "RequirementService" in error_handler.retry_configs
        assert "ReviewItemService" in error_handler.retry_configs
        assert "PlatformService" in error_handler.retry_configs
        assert "VALIDATION_ERROR" in error_handler.recovery_strategies
    
    @pytest.mark.asyncio
    async def test_handle_requirement_upload_error_validation(self, error_handler):
        """Test handling validation error for requirement upload"""
        requirement_id = uuid4()
        error = ValidationError("RequirementService", ["Invalid file type"])
        
        result = await error_handler.handle_requirement_upload_error(
            error, requirement_id
        )
        
        assert isinstance(result, RecoveryResult)
        assert result.success is False
        assert result.action_taken == RecoveryAction.MANUAL_INTERVENTION
        assert "manual resolution" in result.recovery_message
        assert error_handler.error_metrics.total_errors == 1
    
    @pytest.mark.asyncio
    async def test_handle_requirement_upload_error_network(self, error_handler):
        """Test handling network error for requirement upload"""
        requirement_id = uuid4()
        error = NetworkError("RequirementService", {"timeout": True})
        
        result = await error_handler.handle_requirement_upload_error(
            error, requirement_id
        )
        
        assert isinstance(result, RecoveryResult)
        assert result.success is False
        assert result.action_taken == RecoveryAction.RETRY
        assert result.retry_after is not None
        assert result.retry_after > 0
        assert "retryable" in result.recovery_message
    
    @pytest.mark.asyncio
    async def test_handle_review_item_upload_error_storage(self, error_handler):
        """Test handling storage error for review item upload"""
        task_id = uuid4()
        error = StorageError("ReviewItemService", {"disk_full": True})
        
        result = await error_handler.handle_review_item_upload_error(
            error, task_id
        )
        
        assert isinstance(result, RecoveryResult)
        assert result.success is False
        assert result.action_taken == RecoveryAction.RETRY
        assert result.retry_after is not None
    
    @pytest.mark.asyncio
    async def test_retry_failed_upload_success(self, error_handler):
        """Test successful retry of failed upload"""
        # Mock successful operation on second attempt
        call_count = 0
        async def mock_operation():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise NetworkError("TestService", {"connection_failed": True})
            return {"success": True, "file_id": str(uuid4())}
        
        result = await error_handler.retry_failed_upload(
            mock_operation, (), {}, "TestService", max_retries=3
        )
        
        assert isinstance(result, RetryResult)
        assert result.success is True
        assert result.attempt_number == 2
        assert result.total_attempts == 3
        assert result.final_error is None
        assert result.result_data is not None
        assert len(result.retry_history) == 1  # One failed attempt
    
    @pytest.mark.asyncio
    async def test_retry_failed_upload_all_attempts_fail(self, error_handler):
        """Test retry when all attempts fail"""
        async def mock_operation():
            raise NetworkError("TestService", {"connection_failed": True})
        
        result = await error_handler.retry_failed_upload(
            mock_operation, (), {}, "TestService", max_retries=2
        )
        
        assert isinstance(result, RetryResult)
        assert result.success is False
        assert result.attempt_number == 2
        assert result.total_attempts == 2
        assert result.final_error is not None
        assert isinstance(result.final_error, NetworkError)
        assert len(result.retry_history) == 2
    
    @pytest.mark.asyncio
    async def test_retry_failed_upload_non_retryable_error(self, error_handler):
        """Test retry with non-retryable error"""
        async def mock_operation():
            raise ValidationError("TestService", ["Invalid file"])
        
        result = await error_handler.retry_failed_upload(
            mock_operation, (), {}, "TestService", max_retries=3
        )
        
        assert isinstance(result, RetryResult)
        assert result.success is False
        assert result.attempt_number == 3  # Should stop after first attempt
        assert isinstance(result.final_error, ValidationError)
        assert len(result.retry_history) == 1
    
    @pytest.mark.asyncio
    async def test_retry_failed_upload_unexpected_error(self, error_handler):
        """Test retry with unexpected error"""
        async def mock_operation():
            raise ValueError("Unexpected error")
        
        result = await error_handler.retry_failed_upload(
            mock_operation, (), {}, "TestService", max_retries=2
        )
        
        assert isinstance(result, RetryResult)
        assert result.success is False
        assert result.final_error is not None
        assert result.final_error.error_type == "UNEXPECTED_ERROR"
        assert "ValueError" in result.final_error.details["type"]
    
    def test_get_recovery_action(self, error_handler):
        """Test recovery action determination"""
        assert error_handler._get_recovery_action(
            ValidationError("Test", [])
        ) == RecoveryAction.MANUAL_INTERVENTION
        
        assert error_handler._get_recovery_action(
            NetworkError("Test", {})
        ) == RecoveryAction.RETRY
        
        assert error_handler._get_recovery_action(
            StorageError("Test", {})
        ) == RecoveryAction.RETRY
        
        assert error_handler._get_recovery_action(
            AuthenticationError("Test", {})
        ) == RecoveryAction.MANUAL_INTERVENTION
    
    @pytest.mark.asyncio
    async def test_requirement_fallback_handling(self, error_handler):
        """Test requirement-specific fallback handling"""
        requirement_id = uuid4()
        error = ExternalServiceError("RequirementService", "PlatformService", {})
        
        # Mock the fallback method to test it directly
        result = await error_handler._handle_requirement_fallback(
            error, requirement_id, {}
        )
        
        assert isinstance(result, RecoveryResult)
        assert result.action_taken == RecoveryAction.FALLBACK
        assert "requirement_id" in result.details
        assert str(requirement_id) == result.details["requirement_id"]
    
    @pytest.mark.asyncio
    async def test_review_item_fallback_handling(self, error_handler):
        """Test review item-specific fallback handling"""
        task_id = uuid4()
        error = ExternalServiceError("ReviewItemService", "PlatformService", {})
        
        result = await error_handler._handle_review_item_fallback(
            error, task_id, {}
        )
        
        assert isinstance(result, RecoveryResult)
        assert result.action_taken == RecoveryAction.FALLBACK
        assert "task_id" in result.details
        assert str(task_id) == result.details["task_id"]
    
    @pytest.mark.asyncio
    async def test_manual_intervention_handling(self, error_handler):
        """Test manual intervention handling"""
        resource_id = uuid4()
        error = AuthenticationError("TestService", {"token_expired": True})
        
        result = await error_handler._handle_manual_intervention(
            error, resource_id, {"user_id": "test_user"}
        )
        
        assert isinstance(result, RecoveryResult)
        assert result.success is False
        assert result.action_taken == RecoveryAction.MANUAL_INTERVENTION
        assert "manual intervention" in result.recovery_message
        assert result.details["resource_id"] == str(resource_id)
        assert result.details["context"]["user_id"] == "test_user"
    
    def test_get_error_metrics(self, error_handler):
        """Test getting error metrics"""
        # Add some errors
        error1 = ValidationError("Service1", ["Error 1"])
        error2 = NetworkError("Service2", {"timeout": True})
        
        error_handler.error_metrics.add_error(error1)
        error_handler.error_metrics.add_error(error2)
        
        metrics = error_handler.get_error_metrics()
        
        assert metrics.total_errors == 2
        assert "VALIDATION_ERROR" in metrics.errors_by_type
        assert "NETWORK_ERROR" in metrics.errors_by_type
    
    def test_reset_error_metrics(self, error_handler):
        """Test resetting error metrics"""
        # Add an error
        error = ValidationError("Service1", ["Error 1"])
        error_handler.error_metrics.add_error(error)
        
        assert error_handler.error_metrics.total_errors == 1
        
        # Reset metrics
        error_handler.reset_error_metrics()
        
        assert error_handler.error_metrics.total_errors == 0
        assert error_handler.error_metrics.errors_by_type == {}
    
    @pytest.mark.asyncio
    async def test_get_error_statistics(self, error_handler):
        """Test getting comprehensive error statistics"""
        # Add some errors to metrics
        error1 = ValidationError("Service1", ["Error 1"])
        error2 = NetworkError("Service2", {"timeout": True})
        
        error_handler.error_metrics.add_error(error1)
        error_handler.error_metrics.add_error(error2)
        
        stats = await error_handler.get_error_statistics()
        
        assert "current_metrics" in stats
        assert "retry_configurations" in stats
        assert "recovery_strategies" in stats
        assert "error_trends" in stats
        
        assert stats["current_metrics"]["total_errors"] == 2
        assert "RequirementService" in stats["retry_configurations"]
        assert "VALIDATION_ERROR" in stats["recovery_strategies"]


if __name__ == "__main__":
    pytest.main([__file__])