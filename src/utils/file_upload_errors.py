# src/utils/file_upload_errors.py

import logging
import asyncio
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID
from datetime import datetime, timedelta
import json

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ErrorSeverity(str, Enum):
    """Severity levels for file upload errors"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    """Categories of file upload errors"""
    VALIDATION = "validation"
    NETWORK = "network"
    STORAGE = "storage"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    BUSINESS_LOGIC = "business_logic"
    SYSTEM = "system"
    EXTERNAL_SERVICE = "external_service"


class RetryStrategy(str, Enum):
    """Retry strategies for different error types"""
    NONE = "none"
    IMMEDIATE = "immediate"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    CUSTOM = "custom"


class FileUploadError(Exception):
    """
    Enhanced exception class for file upload errors with detailed context,
    retry information, and recovery suggestions.
    """
    
    def __init__(
        self,
        service: str,
        error_type: str,
        details: Dict[str, Any],
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        category: ErrorCategory = ErrorCategory.SYSTEM,
        retry_strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
        user_message: Optional[str] = None,
        technical_message: Optional[str] = None,
        recovery_suggestions: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        self.service = service
        self.error_type = error_type
        self.details = details
        self.severity = severity
        self.category = category
        self.retry_strategy = retry_strategy
        self.user_message = user_message or self._generate_user_message()
        self.technical_message = technical_message or f"{service} error ({error_type}): {details}"
        self.recovery_suggestions = recovery_suggestions or []
        self.context = context or {}
        self.timestamp = datetime.utcnow()
        self.error_id = self._generate_error_id()
        
        super().__init__(self.technical_message)
    
    def _generate_error_id(self) -> str:
        """Generate unique error ID for tracking"""
        import hashlib
        error_data = f"{self.service}_{self.error_type}_{self.timestamp.isoformat()}"
        return hashlib.md5(error_data.encode()).hexdigest()[:12]
    
    def _generate_user_message(self) -> str:
        """Generate user-friendly error message"""
        if self.error_type == "VALIDATION_ERROR":
            return "The uploaded files contain validation errors. Please check the file types and sizes."
        elif self.error_type == "NETWORK_ERROR":
            return "There was a network issue while uploading your files. Please try again."
        elif self.error_type == "STORAGE_ERROR":
            return "There was an issue storing your files. Please try again later."
        elif self.error_type == "NOT_FOUND":
            return "The requested resource was not found. Please verify your request."
        elif self.error_type == "PERMISSION_DENIED":
            return "You don't have permission to perform this action."
        else:
            return "An unexpected error occurred while processing your files. Please try again."
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for logging and API responses"""
        return {
            "error_id": self.error_id,
            "service": self.service,
            "error_type": self.error_type,
            "severity": self.severity.value,
            "category": self.category.value,
            "retry_strategy": self.retry_strategy.value,
            "user_message": self.user_message,
            "technical_message": self.technical_message,
            "details": self.details,
            "recovery_suggestions": self.recovery_suggestions,
            "context": self.context,
            "timestamp": self.timestamp.isoformat()
        }
    
    def is_retryable(self) -> bool:
        """Check if error is retryable based on strategy"""
        return self.retry_strategy != RetryStrategy.NONE


class ValidationError(FileUploadError):
    """Specific error for validation failures"""
    
    def __init__(self, service: str, validation_errors: List[str], **kwargs):
        super().__init__(
            service=service,
            error_type="VALIDATION_ERROR",
            details={"validation_errors": validation_errors},
            severity=ErrorSeverity.LOW,
            category=ErrorCategory.VALIDATION,
            retry_strategy=RetryStrategy.NONE,
            recovery_suggestions=[
                "Check file types and ensure they are supported",
                "Verify file sizes are within limits",
                "Remove any invalid characters from filenames"
            ],
            **kwargs
        )


class NetworkError(FileUploadError):
    """Specific error for network-related failures"""
    
    def __init__(self, service: str, network_details: Dict[str, Any], **kwargs):
        super().__init__(
            service=service,
            error_type="NETWORK_ERROR",
            details=network_details,
            severity=ErrorSeverity.HIGH,
            category=ErrorCategory.NETWORK,
            retry_strategy=RetryStrategy.EXPONENTIAL,
            recovery_suggestions=[
                "Check your internet connection",
                "Try uploading smaller files",
                "Wait a moment and try again"
            ],
            **kwargs
        )


class StorageError(FileUploadError):
    """Specific error for storage-related failures"""
    
    def __init__(self, service: str, storage_details: Dict[str, Any], **kwargs):
        super().__init__(
            service=service,
            error_type="STORAGE_ERROR",
            details=storage_details,
            severity=ErrorSeverity.HIGH,
            category=ErrorCategory.STORAGE,
            retry_strategy=RetryStrategy.LINEAR,
            recovery_suggestions=[
                "Try again in a few minutes",
                "Contact support if the issue persists"
            ],
            **kwargs
        )


class AuthenticationError(FileUploadError):
    """Specific error for authentication failures"""
    
    def __init__(self, service: str, auth_details: Dict[str, Any], **kwargs):
        super().__init__(
            service=service,
            error_type="AUTHENTICATION_ERROR",
            details=auth_details,
            severity=ErrorSeverity.CRITICAL,
            category=ErrorCategory.AUTHENTICATION,
            retry_strategy=RetryStrategy.NONE,
            recovery_suggestions=[
                "Please log in again",
                "Check your session hasn't expired"
            ],
            **kwargs
        )


class AuthorizationError(FileUploadError):
    """Specific error for authorization failures"""
    
    def __init__(self, service: str, auth_details: Dict[str, Any], **kwargs):
        super().__init__(
            service=service,
            error_type="AUTHORIZATION_ERROR",
            details=auth_details,
            severity=ErrorSeverity.HIGH,
            category=ErrorCategory.AUTHORIZATION,
            retry_strategy=RetryStrategy.NONE,
            recovery_suggestions=[
                "Contact your administrator for access",
                "Verify you have the required permissions"
            ],
            **kwargs
        )


class ExternalServiceError(FileUploadError):
    """Specific error for external service failures"""
    
    def __init__(self, service: str, external_service: str, service_details: Dict[str, Any], **kwargs):
        super().__init__(
            service=service,
            error_type="EXTERNAL_SERVICE_ERROR",
            details={**service_details, "external_service": external_service},
            severity=ErrorSeverity.HIGH,
            category=ErrorCategory.EXTERNAL_SERVICE,
            retry_strategy=RetryStrategy.EXPONENTIAL,
            recovery_suggestions=[
                f"The {external_service} service is temporarily unavailable",
                "Please try again in a few minutes"
            ],
            **kwargs
        )


class RetryConfig(BaseModel):
    """Configuration for retry mechanisms"""
    max_attempts: int = Field(default=3, ge=1, le=10)
    base_delay: float = Field(default=1.0, ge=0.1, le=60.0)
    max_delay: float = Field(default=60.0, ge=1.0, le=300.0)
    backoff_factor: float = Field(default=2.0, ge=1.0, le=10.0)
    jitter: bool = Field(default=True)
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number"""
        if attempt <= 0:
            return 0.0
        
        delay = self.base_delay * (self.backoff_factor ** (attempt - 1))
        delay = min(delay, self.max_delay)
        
        if self.jitter:
            import random
            delay *= (0.5 + random.random() * 0.5)  # Add 0-50% jitter
        
        return delay


class ErrorMetrics(BaseModel):
    """Metrics for error tracking and monitoring"""
    total_errors: int = 0
    errors_by_type: Dict[str, int] = Field(default_factory=dict)
    errors_by_service: Dict[str, int] = Field(default_factory=dict)
    errors_by_severity: Dict[str, int] = Field(default_factory=dict)
    retry_success_rate: float = 0.0
    average_retry_attempts: float = 0.0
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    
    def add_error(self, error: FileUploadError):
        """Add error to metrics"""
        self.total_errors += 1
        
        # Update error type count
        if error.error_type not in self.errors_by_type:
            self.errors_by_type[error.error_type] = 0
        self.errors_by_type[error.error_type] += 1
        
        # Update service count
        if error.service not in self.errors_by_service:
            self.errors_by_service[error.service] = 0
        self.errors_by_service[error.service] += 1
        
        # Update severity count
        severity_key = error.severity.value
        if severity_key not in self.errors_by_severity:
            self.errors_by_severity[severity_key] = 0
        self.errors_by_severity[severity_key] += 1
        
        self.last_updated = datetime.utcnow()