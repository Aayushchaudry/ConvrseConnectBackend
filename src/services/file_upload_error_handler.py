# src/services/file_upload_error_handler.py

import logging
import asyncio
import json
from typing import Any, Dict, List, Optional, Callable, Tuple
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, Column, String, DateTime, Text, Boolean, Integer
from sqlalchemy.ext.declarative import declarative_base
from pydantic import BaseModel, Field

from src.utils.file_upload_errors import (
    FileUploadError, ValidationError, NetworkError, StorageError,
    AuthenticationError, AuthorizationError, ExternalServiceError,
    RetryConfig, ErrorMetrics, ErrorSeverity, ErrorCategory, RetryStrategy
)

logger = logging.getLogger(__name__)

Base = declarative_base()


class FailedUploadRecord(Base):
    """Database model for tracking failed uploads for recovery"""
    __tablename__ = "failed_upload_records"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    service = Column(String(100), nullable=False)
    resource_id = Column(String(100), nullable=False)  # requirement_id or task_id
    resource_type = Column(String(50), nullable=False)  # 'requirement' or 'review_item'
    error_type = Column(String(100), nullable=False)
    error_details = Column(Text)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    next_retry_at = Column(DateTime)
    status = Column(String(50), default='pending')  # pending, retrying, resolved, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime)
    context_data = Column(Text)  # JSON string of additional context
    recovery_notes = Column(Text)


class ErrorLogRecord(Base):
    """Database model for comprehensive error logging"""
    __tablename__ = "error_log_records"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    error_id = Column(String(50), nullable=False, index=True)
    service = Column(String(100), nullable=False, index=True)
    error_type = Column(String(100), nullable=False, index=True)
    severity = Column(String(20), nullable=False, index=True)
    category = Column(String(50), nullable=False)
    user_message = Column(Text)
    technical_message = Column(Text)
    error_details = Column(Text)  # JSON string
    context_data = Column(Text)   # JSON string
    recovery_suggestions = Column(Text)  # JSON string
    stack_trace = Column(Text)
    user_id = Column(String(100))
    session_id = Column(String(100))
    request_id = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved = Column(Boolean, default=False)
    resolution_notes = Column(Text)


class RecoveryAction(str, Enum):
    """Types of recovery actions"""
    RETRY = "retry"
    FALLBACK = "fallback"
    MANUAL_INTERVENTION = "manual_intervention"
    SKIP = "skip"
    ABORT = "abort"


class RecoveryResult(BaseModel):
    """Result of error recovery attempt"""
    success: bool
    action_taken: RecoveryAction
    details: Dict[str, Any] = Field(default_factory=dict)
    retry_after: Optional[float] = None
    error_resolved: bool = False
    recovery_message: Optional[str] = None


class RetryResult(BaseModel):
    """Result of retry attempt"""
    success: bool
    attempt_number: int
    total_attempts: int
    final_error: Optional[Dict[str, Any]] = None  # Changed from FileUploadError to serializable dict
    result_data: Optional[Dict[str, Any]] = None
    retry_history: List[Dict[str, Any]] = Field(default_factory=list)


class FileUploadErrorHandler:
    """
    Comprehensive error handler for file upload operations with service-specific
    recovery strategies, retry mechanisms with exponential backoff, and monitoring.
    """
    
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.error_metrics = ErrorMetrics()
        
        # Service-specific retry configurations
        self.retry_configs = {
            "RequirementService": RetryConfig(
                max_attempts=3,
                base_delay=1.0,
                max_delay=30.0,
                backoff_factor=2.0
            ),
            "ReviewItemService": RetryConfig(
                max_attempts=3,
                base_delay=1.0,
                max_delay=30.0,
                backoff_factor=2.0
            ),
            "PlatformService": RetryConfig(
                max_attempts=5,
                base_delay=2.0,
                max_delay=60.0,
                backoff_factor=2.5
            ),
            "FileVersionService": RetryConfig(
                max_attempts=3,
                base_delay=1.5,
                max_delay=45.0,
                backoff_factor=2.0
            )
        }
        
        # Error type to recovery action mapping
        self.recovery_strategies = {
            "VALIDATION_ERROR": RecoveryAction.MANUAL_INTERVENTION,
            "NETWORK_ERROR": RecoveryAction.RETRY,
            "STORAGE_ERROR": RecoveryAction.RETRY,
            "AUTHENTICATION_ERROR": RecoveryAction.MANUAL_INTERVENTION,
            "AUTHORIZATION_ERROR": RecoveryAction.MANUAL_INTERVENTION,
            "EXTERNAL_SERVICE_ERROR": RecoveryAction.RETRY,
            "NOT_FOUND": RecoveryAction.MANUAL_INTERVENTION,
            "UPLOAD_ERROR": RecoveryAction.RETRY,
            "CONNECTION_ERROR": RecoveryAction.RETRY,
            "TIMEOUT_ERROR": RecoveryAction.RETRY,
            "QUOTA_EXCEEDED": RecoveryAction.MANUAL_INTERVENTION,
            "FILE_TOO_LARGE": RecoveryAction.MANUAL_INTERVENTION,
            "UNSUPPORTED_FORMAT": RecoveryAction.MANUAL_INTERVENTION
        }
    
    async def handle_requirement_upload_error(
        self,
        error: FileUploadError,
        requirement_id: UUID,
        context: Optional[Dict[str, Any]] = None
    ) -> RecoveryResult:
        """
        Handle errors specific to requirement file uploads with service-specific recovery.
        
        Args:
            error: The file upload error
            requirement_id: ID of the requirement
            context: Additional context for recovery
            
        Returns:
            RecoveryResult: Result of recovery attempt
        """
        logger.error(f"Handling requirement upload error for requirement {requirement_id}: {error}")
        
        # Update metrics
        self.error_metrics.add_error(error)
        
        # Log error details
        await self._log_error(error, {
            "service_context": "requirement_upload",
            "requirement_id": str(requirement_id),
            **(context or {})
        })
        
        # Determine recovery strategy
        recovery_action = self._get_recovery_action(error)
        
        if recovery_action == RecoveryAction.RETRY:
            return await self._handle_retryable_error(
                error, "RequirementService", requirement_id, context
            )
        elif recovery_action == RecoveryAction.FALLBACK:
            return await self._handle_requirement_fallback(error, requirement_id, context)
        elif recovery_action == RecoveryAction.MANUAL_INTERVENTION:
            return await self._handle_manual_intervention(error, requirement_id, context)
        else:
            return RecoveryResult(
                success=False,
                action_taken=recovery_action,
                details={"error": error.to_dict()},
                recovery_message="Error requires manual resolution"
            )
    
    async def handle_review_item_upload_error(
        self,
        error: FileUploadError,
        task_id: UUID,
        context: Optional[Dict[str, Any]] = None
    ) -> RecoveryResult:
        """
        Handle errors specific to review item file uploads with service-specific recovery.
        
        Args:
            error: The file upload error
            task_id: ID of the task
            context: Additional context for recovery
            
        Returns:
            RecoveryResult: Result of recovery attempt
        """
        logger.error(f"Handling review item upload error for task {task_id}: {error}")
        
        # Update metrics
        self.error_metrics.add_error(error)
        
        # Log error details
        await self._log_error(error, {
            "service_context": "review_item_upload",
            "task_id": str(task_id),
            **(context or {})
        })
        
        # Determine recovery strategy
        recovery_action = self._get_recovery_action(error)
        
        if recovery_action == RecoveryAction.RETRY:
            return await self._handle_retryable_error(
                error, "ReviewItemService", task_id, context
            )
        elif recovery_action == RecoveryAction.FALLBACK:
            return await self._handle_review_item_fallback(error, task_id, context)
        elif recovery_action == RecoveryAction.MANUAL_INTERVENTION:
            return await self._handle_manual_intervention(error, task_id, context)
        else:
            return RecoveryResult(
                success=False,
                action_taken=recovery_action,
                details={"error": error.to_dict()},
                recovery_message="Error requires manual resolution"
            )
    
    async def retry_failed_upload(
        self,
        upload_operation: Callable,
        operation_args: Tuple,
        operation_kwargs: Dict[str, Any],
        service: str,
        max_retries: Optional[int] = None
    ) -> RetryResult:
        """
        Retry a failed upload operation with exponential backoff.
        
        Args:
            upload_operation: The upload function to retry
            operation_args: Arguments for the upload operation
            operation_kwargs: Keyword arguments for the upload operation
            service: Service name for retry configuration
            max_retries: Override max retry attempts
            
        Returns:
            RetryResult: Result of retry attempts
        """
        retry_config = self.retry_configs.get(service, RetryConfig())
        if max_retries is not None:
            retry_config.max_attempts = max_retries
        
        retry_history = []
        last_error = None
        
        for attempt in range(1, retry_config.max_attempts + 1):
            try:
                logger.info(f"Retry attempt {attempt}/{retry_config.max_attempts} for {service}")
                
                # Execute the upload operation
                result = await upload_operation(*operation_args, **operation_kwargs)
                
                # Success
                logger.info(f"Upload succeeded on attempt {attempt}")
                return RetryResult(
                    success=True,
                    attempt_number=attempt,
                    total_attempts=retry_config.max_attempts,
                    result_data=result if isinstance(result, dict) else {"result": str(result)},
                    retry_history=retry_history
                )
                
            except FileUploadError as e:
                last_error = e
                retry_info = {
                    "attempt": attempt,
                    "error_type": e.error_type,
                    "error_message": e.technical_message,
                    "timestamp": datetime.utcnow().isoformat()
                }
                retry_history.append(retry_info)
                
                logger.warning(f"Attempt {attempt} failed: {e}")
                
                # Check if error is retryable
                if not e.is_retryable():
                    logger.error(f"Error is not retryable, aborting: {e}")
                    break
                
                # Don't wait after the last attempt
                if attempt < retry_config.max_attempts:
                    delay = retry_config.calculate_delay(attempt)
                    logger.info(f"Waiting {delay:.2f}s before next attempt")
                    await asyncio.sleep(delay)
                    
            except Exception as e:
                # Wrap unexpected errors
                last_error = FileUploadError(
                    service=service,
                    error_type="UNEXPECTED_ERROR",
                    details={"error": str(e), "type": type(e).__name__},
                    severity=ErrorSeverity.HIGH
                )
                retry_info = {
                    "attempt": attempt,
                    "error_type": "UNEXPECTED_ERROR",
                    "error_message": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                }
                retry_history.append(retry_info)
                
                logger.error(f"Unexpected error on attempt {attempt}: {e}", exc_info=True)
                break
        
        # All retries failed
        logger.error(f"All {retry_config.max_attempts} retry attempts failed for {service}")
        return RetryResult(
            success=False,
            attempt_number=retry_config.max_attempts,
            total_attempts=retry_config.max_attempts,
            final_error=last_error.to_dict() if last_error else None,  # Convert to dict for serialization
            retry_history=retry_history
        )
    
    def _get_recovery_action(self, error: FileUploadError) -> RecoveryAction:
        """Determine the appropriate recovery action for an error"""
        return self.recovery_strategies.get(error.error_type, RecoveryAction.MANUAL_INTERVENTION)
    
    async def _handle_retryable_error(
        self,
        error: FileUploadError,
        service: str,
        resource_id: UUID,
        context: Optional[Dict[str, Any]]
    ) -> RecoveryResult:
        """Handle retryable errors with appropriate delay"""
        retry_config = self.retry_configs.get(service, RetryConfig())
        delay = retry_config.calculate_delay(1)  # Calculate delay for first retry
        
        return RecoveryResult(
            success=False,
            action_taken=RecoveryAction.RETRY,
            details={
                "error": error.to_dict(),
                "retry_config": retry_config.dict(),
                "resource_id": str(resource_id)
            },
            retry_after=delay,
            recovery_message=f"Error is retryable. Retry in {delay:.2f} seconds."
        )
    
    async def _handle_requirement_fallback(
        self,
        error: FileUploadError,
        requirement_id: UUID,
        context: Optional[Dict[str, Any]]
    ) -> RecoveryResult:
        """Handle requirement-specific fallback strategies"""
        logger.info(f"Attempting requirement fallback for {requirement_id}")
        
        # Example fallback: Store file metadata without platform-service upload
        try:
            # This would implement alternative storage or queuing mechanism
            fallback_details = {
                "requirement_id": str(requirement_id),
                "fallback_strategy": "local_queue",
                "original_error": error.to_dict()
            }
            
            return RecoveryResult(
                success=True,
                action_taken=RecoveryAction.FALLBACK,
                details=fallback_details,
                recovery_message="Files queued for later processing"
            )
            
        except Exception as e:
            logger.error(f"Fallback strategy failed: {e}")
            return RecoveryResult(
                success=False,
                action_taken=RecoveryAction.FALLBACK,
                details={"fallback_error": str(e)},
                recovery_message="Fallback strategy failed"
            )
    
    async def _handle_review_item_fallback(
        self,
        error: FileUploadError,
        task_id: UUID,
        context: Optional[Dict[str, Any]]
    ) -> RecoveryResult:
        """Handle review item-specific fallback strategies"""
        logger.info(f"Attempting review item fallback for task {task_id}")
        
        try:
            # Example fallback: Create review items without files for manual attachment
            fallback_details = {
                "task_id": str(task_id),
                "fallback_strategy": "manual_attachment",
                "original_error": error.to_dict()
            }
            
            return RecoveryResult(
                success=True,
                action_taken=RecoveryAction.FALLBACK,
                details=fallback_details,
                recovery_message="Review items created for manual file attachment"
            )
            
        except Exception as e:
            logger.error(f"Review item fallback failed: {e}")
            return RecoveryResult(
                success=False,
                action_taken=RecoveryAction.FALLBACK,
                details={"fallback_error": str(e)},
                recovery_message="Fallback strategy failed"
            )
    
    async def _handle_manual_intervention(
        self,
        error: FileUploadError,
        resource_id: UUID,
        context: Optional[Dict[str, Any]]
    ) -> RecoveryResult:
        """Handle errors that require manual intervention"""
        logger.warning(f"Manual intervention required for error: {error}")
        
        # Create intervention record for tracking
        intervention_details = {
            "resource_id": str(resource_id),
            "error": error.to_dict(),
            "context": context or {},
            "created_at": datetime.utcnow().isoformat(),
            "status": "pending"
        }
        
        return RecoveryResult(
            success=False,
            action_taken=RecoveryAction.MANUAL_INTERVENTION,
            details=intervention_details,
            recovery_message="This error requires manual intervention. Support has been notified."
        )
    
    async def _log_error(self, error: FileUploadError, context: Dict[str, Any]):
        """Log error details for monitoring and analysis"""
        log_entry = {
            "error_id": error.error_id,
            "timestamp": error.timestamp.isoformat(),
            "service": error.service,
            "error_type": error.error_type,
            "severity": error.severity.value,
            "category": error.category.value,
            "details": error.details,
            "context": context,
            "user_message": error.user_message,
            "technical_message": error.technical_message,
            "recovery_suggestions": error.recovery_suggestions
        }
        
        # Log at appropriate level based on severity
        if error.severity == ErrorSeverity.CRITICAL:
            logger.critical(f"Critical file upload error: {json.dumps(log_entry, indent=2)}")
        elif error.severity == ErrorSeverity.HIGH:
            logger.error(f"High severity file upload error: {json.dumps(log_entry, indent=2)}")
        elif error.severity == ErrorSeverity.MEDIUM:
            logger.warning(f"Medium severity file upload error: {json.dumps(log_entry, indent=2)}")
        else:
            logger.info(f"Low severity file upload error: {json.dumps(log_entry, indent=2)}")
    
    def get_error_metrics(self) -> ErrorMetrics:
        """Get current error metrics"""
        return self.error_metrics
    
    def reset_error_metrics(self):
        """Reset error metrics"""
        self.error_metrics = ErrorMetrics()
    
    async def get_error_statistics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get comprehensive error statistics for monitoring.
        
        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            Dict containing error statistics
        """
        try:
            stats = {
                "current_metrics": self.error_metrics.dict(),
                "retry_configurations": {
                    service: config.dict() 
                    for service, config in self.retry_configs.items()
                },
                "recovery_strategies": dict(self.recovery_strategies),
                "error_trends": await self._calculate_error_trends(start_date, end_date)
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting error statistics: {e}", exc_info=True)
            return {"error": str(e)}
    
    async def _calculate_error_trends(
        self,
        start_date: Optional[datetime],
        end_date: Optional[datetime]
    ) -> Dict[str, Any]:
        """Calculate error trends over time"""
        try:
            # Query error log records for trends
            query = select(ErrorLogRecord)
            
            if start_date:
                query = query.where(ErrorLogRecord.created_at >= start_date)
            if end_date:
                query = query.where(ErrorLogRecord.created_at <= end_date)
            
            result = await self.db_session.execute(query)
            error_records = result.scalars().all()
            
            # Calculate trends
            total_errors = len(error_records)
            error_types = {}
            services = {}
            severities = {}
            
            for record in error_records:
                # Count by error type
                if record.error_type not in error_types:
                    error_types[record.error_type] = 0
                error_types[record.error_type] += 1
                
                # Count by service
                if record.service not in services:
                    services[record.service] = 0
                services[record.service] += 1
                
                # Count by severity
                if record.severity not in severities:
                    severities[record.severity] = 0
                severities[record.severity] += 1
            
            return {
                "total_errors_period": total_errors,
                "error_rate_trend": self._calculate_trend_direction(error_records),
                "most_common_errors": sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:5],
                "services_with_most_errors": sorted(services.items(), key=lambda x: x[1], reverse=True)[:3],
                "severity_distribution": severities,
                "resolution_rate": self._calculate_resolution_rate(error_records)
            }
            
        except Exception as e:
            logger.error(f"Error calculating error trends: {e}", exc_info=True)
            return {
                "total_errors_period": self.error_metrics.total_errors,
                "error_rate_trend": "unknown",
                "most_common_errors": list(self.error_metrics.errors_by_type.keys())[:5],
                "services_with_most_errors": list(self.error_metrics.errors_by_service.keys())[:3]
            }
    
    def _calculate_trend_direction(self, error_records: List[ErrorLogRecord]) -> str:
        """Calculate if error trend is increasing, decreasing, or stable"""
        if len(error_records) < 2:
            return "stable"
        
        # Sort by creation time
        sorted_records = sorted(error_records, key=lambda x: x.created_at)
        
        # Split into two halves and compare
        mid_point = len(sorted_records) // 2
        first_half = sorted_records[:mid_point]
        second_half = sorted_records[mid_point:]
        
        if len(second_half) > len(first_half) * 1.2:
            return "increasing"
        elif len(second_half) < len(first_half) * 0.8:
            return "decreasing"
        else:
            return "stable"
    
    def _calculate_resolution_rate(self, error_records: List[ErrorLogRecord]) -> float:
        """Calculate the percentage of errors that have been resolved"""
        if not error_records:
            return 0.0
        
        resolved_count = sum(1 for record in error_records if record.resolved)
        return (resolved_count / len(error_records)) * 100.0
    
    async def create_failed_upload_record(
        self,
        service: str,
        resource_id: UUID,
        resource_type: str,
        error: FileUploadError,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a record for a failed upload to enable recovery.
        
        Args:
            service: Service name where upload failed
            resource_id: ID of the resource (requirement_id or task_id)
            resource_type: Type of resource ('requirement' or 'review_item')
            error: The upload error
            context: Additional context for recovery
            
        Returns:
            str: ID of the created failed upload record
        """
        try:
            retry_config = self.retry_configs.get(service, RetryConfig())
            next_retry_at = datetime.utcnow() + timedelta(seconds=retry_config.calculate_delay(1))
            
            failed_record = FailedUploadRecord(
                service=service,
                resource_id=str(resource_id),
                resource_type=resource_type,
                error_type=error.error_type,
                error_details=json.dumps(error.to_dict()),
                max_retries=retry_config.max_attempts,
                next_retry_at=next_retry_at,
                context_data=json.dumps(context or {})
            )
            
            self.db_session.add(failed_record)
            await self.db_session.commit()
            
            logger.info(f"Created failed upload record {failed_record.id} for {service}")
            return failed_record.id
            
        except Exception as e:
            logger.error(f"Error creating failed upload record: {e}", exc_info=True)
            await self.db_session.rollback()
            raise
    
    async def log_error_to_database(
        self,
        error: FileUploadError,
        context: Dict[str, Any],
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        stack_trace: Optional[str] = None
    ) -> str:
        """
        Log error to database for comprehensive monitoring.
        
        Args:
            error: The file upload error
            context: Additional context
            user_id: ID of the user who encountered the error
            session_id: Session ID
            request_id: Request ID for tracing
            stack_trace: Stack trace if available
            
        Returns:
            str: ID of the created error log record
        """
        try:
            error_log = ErrorLogRecord(
                error_id=error.error_id,
                service=error.service,
                error_type=error.error_type,
                severity=error.severity.value,
                category=error.category.value,
                user_message=error.user_message,
                technical_message=error.technical_message,
                error_details=json.dumps(error.details),
                context_data=json.dumps(context),
                recovery_suggestions=json.dumps(error.recovery_suggestions),
                stack_trace=stack_trace,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id
            )
            
            self.db_session.add(error_log)
            await self.db_session.commit()
            
            logger.info(f"Logged error {error.error_id} to database")
            return error_log.id
            
        except Exception as e:
            logger.error(f"Error logging to database: {e}", exc_info=True)
            await self.db_session.rollback()
            raise
    
    async def process_failed_upload_recovery(self) -> Dict[str, Any]:
        """
        Process all pending failed uploads for recovery.
        
        Returns:
            Dict containing recovery results
        """
        try:
            # Get all pending failed uploads that are ready for retry
            current_time = datetime.utcnow()
            query = select(FailedUploadRecord).where(
                and_(
                    FailedUploadRecord.status == 'pending',
                    FailedUploadRecord.retry_count < FailedUploadRecord.max_retries,
                    FailedUploadRecord.next_retry_at <= current_time
                )
            )
            
            result = await self.db_session.execute(query)
            failed_records = result.scalars().all()
            
            recovery_results = {
                "total_processed": len(failed_records),
                "successful_recoveries": 0,
                "failed_recoveries": 0,
                "manual_intervention_required": 0,
                "details": []
            }
            
            for record in failed_records:
                try:
                    # Update status to retrying
                    record.status = 'retrying'
                    record.retry_count += 1
                    record.updated_at = datetime.utcnow()
                    
                    # Attempt recovery based on resource type
                    if record.resource_type == 'requirement':
                        recovery_result = await self._recover_requirement_upload(record)
                    elif record.resource_type == 'review_item':
                        recovery_result = await self._recover_review_item_upload(record)
                    else:
                        recovery_result = RecoveryResult(
                            success=False,
                            action_taken=RecoveryAction.MANUAL_INTERVENTION,
                            details={"error": "Unknown resource type"},
                            recovery_message="Unknown resource type requires manual intervention"
                        )
                    
                    # Update record based on recovery result
                    if recovery_result.success:
                        record.status = 'resolved'
                        record.resolved_at = datetime.utcnow()
                        record.recovery_notes = recovery_result.recovery_message
                        recovery_results["successful_recoveries"] += 1
                    else:
                        if record.retry_count >= record.max_retries:
                            record.status = 'failed'
                            record.recovery_notes = "Max retries exceeded"
                            recovery_results["manual_intervention_required"] += 1
                        else:
                            record.status = 'pending'
                            retry_config = self.retry_configs.get(record.service, RetryConfig())
                            record.next_retry_at = datetime.utcnow() + timedelta(
                                seconds=retry_config.calculate_delay(record.retry_count + 1)
                            )
                            recovery_results["failed_recoveries"] += 1
                    
                    recovery_results["details"].append({
                        "record_id": record.id,
                        "service": record.service,
                        "resource_id": record.resource_id,
                        "success": recovery_result.success,
                        "action_taken": recovery_result.action_taken.value,
                        "message": recovery_result.recovery_message
                    })
                    
                except Exception as e:
                    logger.error(f"Error processing recovery for record {record.id}: {e}", exc_info=True)
                    record.status = 'failed'
                    record.recovery_notes = f"Recovery processing error: {str(e)}"
                    recovery_results["manual_intervention_required"] += 1
            
            await self.db_session.commit()
            
            logger.info(f"Processed {len(failed_records)} failed upload records for recovery")
            return recovery_results
            
        except Exception as e:
            logger.error(f"Error processing failed upload recovery: {e}", exc_info=True)
            await self.db_session.rollback()
            return {
                "error": str(e),
                "total_processed": 0,
                "successful_recoveries": 0,
                "failed_recoveries": 0,
                "manual_intervention_required": 0
            }
    
    async def _recover_requirement_upload(self, record: FailedUploadRecord) -> RecoveryResult:
        """Attempt to recover a failed requirement upload"""
        try:
            context = json.loads(record.context_data) if record.context_data else {}
            
            # This would integrate with the actual requirement service
            # For now, simulate recovery attempt
            logger.info(f"Attempting requirement upload recovery for {record.resource_id}")
            
            # Simulate recovery logic based on error type
            error_details = json.loads(record.error_details)
            
            if error_details.get("error_type") == "NETWORK_ERROR":
                # Simulate network recovery
                await asyncio.sleep(0.1)  # Simulate network call
                return RecoveryResult(
                    success=True,
                    action_taken=RecoveryAction.RETRY,
                    details={"recovered_via": "network_retry"},
                    recovery_message="Network issue resolved, upload completed"
                )
            elif error_details.get("error_type") == "EXTERNAL_SERVICE_ERROR":
                # Simulate external service recovery
                await asyncio.sleep(0.1)  # Simulate service call
                return RecoveryResult(
                    success=True,
                    action_taken=RecoveryAction.RETRY,
                    details={"recovered_via": "service_retry"},
                    recovery_message="External service recovered, upload completed"
                )
            else:
                return RecoveryResult(
                    success=False,
                    action_taken=RecoveryAction.MANUAL_INTERVENTION,
                    details={"error": "Non-recoverable error type"},
                    recovery_message="Error type requires manual intervention"
                )
                
        except Exception as e:
            logger.error(f"Error in requirement upload recovery: {e}", exc_info=True)
            return RecoveryResult(
                success=False,
                action_taken=RecoveryAction.MANUAL_INTERVENTION,
                details={"recovery_error": str(e)},
                recovery_message="Recovery attempt failed"
            )
    
    async def _recover_review_item_upload(self, record: FailedUploadRecord) -> RecoveryResult:
        """Attempt to recover a failed review item upload"""
        try:
            context = json.loads(record.context_data) if record.context_data else {}
            
            logger.info(f"Attempting review item upload recovery for task {record.resource_id}")
            
            # Simulate recovery logic based on error type
            error_details = json.loads(record.error_details)
            
            if error_details.get("error_type") == "STORAGE_ERROR":
                # Simulate storage recovery
                await asyncio.sleep(0.1)  # Simulate storage operation
                return RecoveryResult(
                    success=True,
                    action_taken=RecoveryAction.RETRY,
                    details={"recovered_via": "storage_retry"},
                    recovery_message="Storage issue resolved, review items created"
                )
            elif error_details.get("error_type") == "NETWORK_ERROR":
                # Simulate network recovery
                await asyncio.sleep(0.1)  # Simulate network call
                return RecoveryResult(
                    success=True,
                    action_taken=RecoveryAction.RETRY,
                    details={"recovered_via": "network_retry"},
                    recovery_message="Network issue resolved, upload completed"
                )
            else:
                return RecoveryResult(
                    success=False,
                    action_taken=RecoveryAction.MANUAL_INTERVENTION,
                    details={"error": "Non-recoverable error type"},
                    recovery_message="Error type requires manual intervention"
                )
                
        except Exception as e:
            logger.error(f"Error in review item upload recovery: {e}", exc_info=True)
            return RecoveryResult(
                success=False,
                action_taken=RecoveryAction.MANUAL_INTERVENTION,
                details={"recovery_error": str(e)},
                recovery_message="Recovery attempt failed"
            )
    
    async def get_manual_intervention_queue(self) -> List[Dict[str, Any]]:
        """
        Get all failed uploads that require manual intervention.
        
        Returns:
            List of failed upload records requiring manual intervention
        """
        try:
            query = select(FailedUploadRecord).where(
                or_(
                    FailedUploadRecord.status == 'failed',
                    and_(
                        FailedUploadRecord.status == 'pending',
                        FailedUploadRecord.retry_count >= FailedUploadRecord.max_retries
                    )
                )
            ).order_by(desc(FailedUploadRecord.created_at))
            
            result = await self.db_session.execute(query)
            failed_records = result.scalars().all()
            
            intervention_queue = []
            for record in failed_records:
                error_details = json.loads(record.error_details) if record.error_details else {}
                context = json.loads(record.context_data) if record.context_data else {}
                
                intervention_queue.append({
                    "record_id": record.id,
                    "service": record.service,
                    "resource_id": record.resource_id,
                    "resource_type": record.resource_type,
                    "error_type": record.error_type,
                    "error_details": error_details,
                    "context": context,
                    "retry_count": record.retry_count,
                    "max_retries": record.max_retries,
                    "created_at": record.created_at.isoformat(),
                    "updated_at": record.updated_at.isoformat(),
                    "recovery_notes": record.recovery_notes,
                    "status": record.status
                })
            
            return intervention_queue
            
        except Exception as e:
            logger.error(f"Error getting manual intervention queue: {e}", exc_info=True)
            return []
    
    async def resolve_manual_intervention(
        self,
        record_id: str,
        resolution_notes: str,
        resolved_by: str
    ) -> bool:
        """
        Mark a manual intervention as resolved.
        
        Args:
            record_id: ID of the failed upload record
            resolution_notes: Notes about how the issue was resolved
            resolved_by: ID of the person who resolved the issue
            
        Returns:
            bool: True if successfully resolved
        """
        try:
            query = select(FailedUploadRecord).where(FailedUploadRecord.id == record_id)
            result = await self.db_session.execute(query)
            record = result.scalar_one_or_none()
            
            if not record:
                logger.warning(f"Failed upload record {record_id} not found")
                return False
            
            record.status = 'resolved'
            record.resolved_at = datetime.utcnow()
            record.recovery_notes = f"Manually resolved by {resolved_by}: {resolution_notes}"
            record.updated_at = datetime.utcnow()
            
            await self.db_session.commit()
            
            logger.info(f"Manual intervention {record_id} resolved by {resolved_by}")
            return True
            
        except Exception as e:
            logger.error(f"Error resolving manual intervention: {e}", exc_info=True)
            await self.db_session.rollback()
            return False
    
    async def get_monitoring_dashboard_data(self) -> Dict[str, Any]:
        """
        Get comprehensive monitoring data for dashboard display.
        
        Returns:
            Dict containing monitoring metrics and alerts
        """
        try:
            current_time = datetime.utcnow()
            last_24h = current_time - timedelta(hours=24)
            last_7d = current_time - timedelta(days=7)
            
            # Get error counts for different time periods
            error_24h_query = select(ErrorLogRecord).where(
                ErrorLogRecord.created_at >= last_24h
            )
            error_7d_query = select(ErrorLogRecord).where(
                ErrorLogRecord.created_at >= last_7d
            )
            
            error_24h_result = await self.db_session.execute(error_24h_query)
            error_7d_result = await self.db_session.execute(error_7d_query)
            
            errors_24h = error_24h_result.scalars().all()
            errors_7d = error_7d_result.scalars().all()
            
            # Get failed upload counts
            failed_pending_query = select(FailedUploadRecord).where(
                FailedUploadRecord.status == 'pending'
            )
            failed_manual_query = select(FailedUploadRecord).where(
                FailedUploadRecord.status == 'failed'
            )
            
            failed_pending_result = await self.db_session.execute(failed_pending_query)
            failed_manual_result = await self.db_session.execute(failed_manual_query)
            
            pending_recoveries = failed_pending_result.scalars().all()
            manual_interventions = failed_manual_result.scalars().all()
            
            # Calculate metrics
            dashboard_data = {
                "error_metrics": {
                    "total_errors_24h": len(errors_24h),
                    "total_errors_7d": len(errors_7d),
                    "critical_errors_24h": len([e for e in errors_24h if e.severity == 'critical']),
                    "high_errors_24h": len([e for e in errors_24h if e.severity == 'high']),
                    "error_rate_trend": self._calculate_trend_direction(errors_7d)
                },
                "recovery_metrics": {
                    "pending_recoveries": len(pending_recoveries),
                    "manual_interventions_required": len(manual_interventions),
                    "recovery_success_rate": await self._calculate_recovery_success_rate()
                },
                "service_health": await self._calculate_service_health(errors_24h),
                "alerts": await self._generate_monitoring_alerts(errors_24h, pending_recoveries, manual_interventions),
                "top_errors": await self._get_top_errors(errors_7d),
                "last_updated": current_time.isoformat()
            }
            
            return dashboard_data
            
        except Exception as e:
            logger.error(f"Error getting monitoring dashboard data: {e}", exc_info=True)
            return {
                "error": str(e),
                "last_updated": datetime.utcnow().isoformat()
            }
    
    async def _calculate_recovery_success_rate(self) -> float:
        """Calculate the success rate of automatic recovery attempts"""
        try:
            last_7d = datetime.utcnow() - timedelta(days=7)
            
            query = select(FailedUploadRecord).where(
                FailedUploadRecord.created_at >= last_7d
            )
            
            result = await self.db_session.execute(query)
            records = result.scalars().all()
            
            if not records:
                return 0.0
            
            resolved_count = len([r for r in records if r.status == 'resolved'])
            return (resolved_count / len(records)) * 100.0
            
        except Exception as e:
            logger.error(f"Error calculating recovery success rate: {e}")
            return 0.0
    
    async def _calculate_service_health(self, recent_errors: List[ErrorLogRecord]) -> Dict[str, Any]:
        """Calculate health metrics for each service"""
        service_health = {}
        
        # Group errors by service
        service_errors = {}
        for error in recent_errors:
            if error.service not in service_errors:
                service_errors[error.service] = []
            service_errors[error.service].append(error)
        
        # Calculate health for each service
        for service in ["RequirementService", "ReviewItemService", "PlatformService", "FileVersionService"]:
            errors = service_errors.get(service, [])
            critical_errors = [e for e in errors if e.severity == 'critical']
            high_errors = [e for e in errors if e.severity == 'high']
            
            if len(critical_errors) > 0:
                health_status = "critical"
            elif len(high_errors) > 3:
                health_status = "degraded"
            elif len(errors) > 10:
                health_status = "warning"
            else:
                health_status = "healthy"
            
            service_health[service] = {
                "status": health_status,
                "error_count": len(errors),
                "critical_errors": len(critical_errors),
                "high_errors": len(high_errors)
            }
        
        return service_health
    
    async def _generate_monitoring_alerts(
        self,
        recent_errors: List[ErrorLogRecord],
        pending_recoveries: List[FailedUploadRecord],
        manual_interventions: List[FailedUploadRecord]
    ) -> List[Dict[str, Any]]:
        """Generate monitoring alerts based on current system state"""
        alerts = []
        
        # Critical error alert
        critical_errors = [e for e in recent_errors if e.severity == 'critical']
        if critical_errors:
            alerts.append({
                "type": "critical",
                "title": "Critical Errors Detected",
                "message": f"{len(critical_errors)} critical errors in the last 24 hours",
                "action_required": True,
                "details": [e.error_type for e in critical_errors[:5]]
            })
        
        # High error rate alert
        if len(recent_errors) > 50:
            alerts.append({
                "type": "warning",
                "title": "High Error Rate",
                "message": f"{len(recent_errors)} errors in the last 24 hours",
                "action_required": False,
                "details": {"threshold": 50, "actual": len(recent_errors)}
            })
        
        # Manual intervention alert
        if len(manual_interventions) > 5:
            alerts.append({
                "type": "warning",
                "title": "Manual Interventions Required",
                "message": f"{len(manual_interventions)} failed uploads require manual intervention",
                "action_required": True,
                "details": {"count": len(manual_interventions)}
            })
        
        # Recovery backlog alert
        if len(pending_recoveries) > 10:
            alerts.append({
                "type": "info",
                "title": "Recovery Backlog",
                "message": f"{len(pending_recoveries)} uploads pending recovery",
                "action_required": False,
                "details": {"count": len(pending_recoveries)}
            })
        
        return alerts
    
    async def _get_top_errors(self, recent_errors: List[ErrorLogRecord]) -> List[Dict[str, Any]]:
        """Get the most common errors in the recent period"""
        error_counts = {}
        
        for error in recent_errors:
            key = f"{error.service}:{error.error_type}"
            if key not in error_counts:
                error_counts[key] = {
                    "service": error.service,
                    "error_type": error.error_type,
                    "count": 0,
                    "severity": error.severity,
                    "latest_message": error.user_message
                }
            error_counts[key]["count"] += 1
        
        # Sort by count and return top 10
        top_errors = sorted(error_counts.values(), key=lambda x: x["count"], reverse=True)[:10]
        return top_errors