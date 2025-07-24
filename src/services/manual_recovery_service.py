# src/services/manual_recovery_service.py

import logging
import json
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, func
from pydantic import BaseModel, Field

from src.services.file_upload_error_handler import (
    FileUploadErrorHandler, FailedUploadRecord, ErrorLogRecord
)
from src.utils.file_upload_errors import FileUploadError

logger = logging.getLogger(__name__)


class ManualRecoveryRequest(BaseModel):
    """Request model for manual recovery operations"""
    record_id: str
    recovery_action: str  # 'retry', 'skip', 'modify', 'escalate'
    recovery_notes: str
    modified_context: Optional[Dict[str, Any]] = None
    resolved_by: str
    priority: str = Field(default="normal", regex="^(low|normal|high|critical)$")


class RecoveryDashboardData(BaseModel):
    """Dashboard data for manual recovery interface"""
    pending_interventions: List[Dict[str, Any]]
    recent_resolutions: List[Dict[str, Any]]
    recovery_statistics: Dict[str, Any]
    service_health_summary: Dict[str, Any]
    alerts: List[Dict[str, Any]]


class ManualRecoveryService:
    """
    Service for managing manual recovery operations and providing
    interfaces for critical failure resolution.
    """
    
    def __init__(self, db_session: AsyncSession, error_handler: FileUploadErrorHandler):
        self.db_session = db_session
        self.error_handler = error_handler
    
    async def get_recovery_dashboard(self) -> RecoveryDashboardData:
        """
        Get comprehensive dashboard data for manual recovery interface.
        
        Returns:
            RecoveryDashboardData: Dashboard data including pending interventions and statistics
        """
        try:
            # Get pending interventions
            pending_interventions = await self.error_handler.get_manual_intervention_queue()
            
            # Get recent resolutions (last 7 days)
            recent_resolutions = await self._get_recent_resolutions()
            
            # Get recovery statistics
            recovery_stats = await self._get_recovery_statistics()
            
            # Get service health summary
            service_health = await self._get_service_health_summary()
            
            # Get monitoring dashboard data for alerts
            monitoring_data = await self.error_handler.get_monitoring_dashboard_data()
            alerts = monitoring_data.get("alerts", [])
            
            return RecoveryDashboardData(
                pending_interventions=pending_interventions,
                recent_resolutions=recent_resolutions,
                recovery_statistics=recovery_stats,
                service_health_summary=service_health,
                alerts=alerts
            )
            
        except Exception as e:
            logger.error(f"Error getting recovery dashboard: {e}", exc_info=True)
            return RecoveryDashboardData(
                pending_interventions=[],
                recent_resolutions=[],
                recovery_statistics={"error": str(e)},
                service_health_summary={},
                alerts=[{
                    "type": "error",
                    "title": "Dashboard Error",
                    "message": f"Error loading dashboard: {str(e)}",
                    "action_required": True
                }]
            )
    
    async def process_manual_recovery(self, request: ManualRecoveryRequest) -> Dict[str, Any]:
        """
        Process a manual recovery request.
        
        Args:
            request: Manual recovery request details
            
        Returns:
            Dict containing the result of the recovery operation
        """
        try:
            logger.info(f"Processing manual recovery request for record {request.record_id}")
            
            # Get the failed upload record
            query = select(FailedUploadRecord).where(FailedUploadRecord.id == request.record_id)
            result = await self.db_session.execute(query)
            record = result.scalar_one_or_none()
            
            if not record:
                return {
                    "success": False,
                    "error": "Failed upload record not found",
                    "record_id": request.record_id
                }
            
            # Process based on recovery action
            if request.recovery_action == "retry":
                return await self._process_manual_retry(record, request)
            elif request.recovery_action == "skip":
                return await self._process_manual_skip(record, request)
            elif request.recovery_action == "modify":
                return await self._process_manual_modify(record, request)
            elif request.recovery_action == "escalate":
                return await self._process_manual_escalate(record, request)
            else:
                return {
                    "success": False,
                    "error": f"Unknown recovery action: {request.recovery_action}",
                    "record_id": request.record_id
                }
                
        except Exception as e:
            logger.error(f"Error processing manual recovery: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "record_id": request.record_id
            }
    
    async def _process_manual_retry(
        self, 
        record: FailedUploadRecord, 
        request: ManualRecoveryRequest
    ) -> Dict[str, Any]:
        """Process manual retry request"""
        try:
            # Reset retry count and status for manual retry
            record.retry_count = 0
            record.status = 'pending'
            record.next_retry_at = datetime.utcnow()
            record.recovery_notes = f"Manual retry initiated by {request.resolved_by}: {request.recovery_notes}"
            record.updated_at = datetime.utcnow()
            
            await self.db_session.commit()
            
            # Trigger immediate recovery attempt
            recovery_results = await self.error_handler.process_failed_upload_recovery()
            
            return {
                "success": True,
                "action": "retry",
                "message": "Manual retry initiated successfully",
                "record_id": record.id,
                "recovery_results": recovery_results
            }
            
        except Exception as e:
            await self.db_session.rollback()
            logger.error(f"Error in manual retry: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "record_id": record.id
            }
    
    async def _process_manual_skip(
        self, 
        record: FailedUploadRecord, 
        request: ManualRecoveryRequest
    ) -> Dict[str, Any]:
        """Process manual skip request"""
        try:
            # Mark as resolved with skip action
            record.status = 'resolved'
            record.resolved_at = datetime.utcnow()
            record.recovery_notes = f"Manually skipped by {request.resolved_by}: {request.recovery_notes}"
            record.updated_at = datetime.utcnow()
            
            await self.db_session.commit()
            
            return {
                "success": True,
                "action": "skip",
                "message": "Upload marked as skipped successfully",
                "record_id": record.id
            }
            
        except Exception as e:
            await self.db_session.rollback()
            logger.error(f"Error in manual skip: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "record_id": record.id
            }
    
    async def _process_manual_modify(
        self, 
        record: FailedUploadRecord, 
        request: ManualRecoveryRequest
    ) -> Dict[str, Any]:
        """Process manual modify request"""
        try:
            # Update context data with modifications
            if request.modified_context:
                record.context_data = json.dumps(request.modified_context)
            
            # Reset for retry with modified context
            record.retry_count = 0
            record.status = 'pending'
            record.next_retry_at = datetime.utcnow()
            record.recovery_notes = f"Context modified by {request.resolved_by}: {request.recovery_notes}"
            record.updated_at = datetime.utcnow()
            
            await self.db_session.commit()
            
            # Trigger recovery with modified context
            recovery_results = await self.error_handler.process_failed_upload_recovery()
            
            return {
                "success": True,
                "action": "modify",
                "message": "Context modified and retry initiated",
                "record_id": record.id,
                "modified_context": request.modified_context,
                "recovery_results": recovery_results
            }
            
        except Exception as e:
            await self.db_session.rollback()
            logger.error(f"Error in manual modify: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "record_id": record.id
            }
    
    async def _process_manual_escalate(
        self, 
        record: FailedUploadRecord, 
        request: ManualRecoveryRequest
    ) -> Dict[str, Any]:
        """Process manual escalate request"""
        try:
            # Mark as escalated (still failed but with escalation notes)
            record.status = 'failed'
            record.recovery_notes = f"Escalated by {request.resolved_by}: {request.recovery_notes}"
            record.updated_at = datetime.utcnow()
            
            await self.db_session.commit()
            
            # Create escalation notification (this would integrate with notification system)
            escalation_data = {
                "record_id": record.id,
                "service": record.service,
                "resource_id": record.resource_id,
                "resource_type": record.resource_type,
                "error_type": record.error_type,
                "escalated_by": request.resolved_by,
                "escalation_notes": request.recovery_notes,
                "priority": request.priority,
                "escalated_at": datetime.utcnow().isoformat()
            }
            
            logger.warning(f"Manual escalation created: {json.dumps(escalation_data, indent=2)}")
            
            return {
                "success": True,
                "action": "escalate",
                "message": "Issue escalated successfully",
                "record_id": record.id,
                "escalation_data": escalation_data
            }
            
        except Exception as e:
            await self.db_session.rollback()
            logger.error(f"Error in manual escalate: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "record_id": record.id
            }
    
    async def _get_recent_resolutions(self) -> List[Dict[str, Any]]:
        """Get recently resolved interventions"""
        try:
            last_7d = datetime.utcnow() - timedelta(days=7)
            
            query = select(FailedUploadRecord).where(
                and_(
                    FailedUploadRecord.status == 'resolved',
                    FailedUploadRecord.resolved_at >= last_7d
                )
            ).order_by(desc(FailedUploadRecord.resolved_at)).limit(20)
            
            result = await self.db_session.execute(query)
            records = result.scalars().all()
            
            resolutions = []
            for record in records:
                resolutions.append({
                    "record_id": record.id,
                    "service": record.service,
                    "resource_id": record.resource_id,
                    "resource_type": record.resource_type,
                    "error_type": record.error_type,
                    "resolved_at": record.resolved_at.isoformat() if record.resolved_at else None,
                    "recovery_notes": record.recovery_notes,
                    "retry_count": record.retry_count
                })
            
            return resolutions
            
        except Exception as e:
            logger.error(f"Error getting recent resolutions: {e}", exc_info=True)
            return []
    
    async def _get_recovery_statistics(self) -> Dict[str, Any]:
        """Get recovery statistics for dashboard"""
        try:
            current_time = datetime.utcnow()
            last_24h = current_time - timedelta(hours=24)
            last_7d = current_time - timedelta(days=7)
            last_30d = current_time - timedelta(days=30)
            
            # Get counts for different time periods and statuses
            stats_queries = {
                "total_failures_24h": select(func.count(FailedUploadRecord.id)).where(
                    FailedUploadRecord.created_at >= last_24h
                ),
                "total_failures_7d": select(func.count(FailedUploadRecord.id)).where(
                    FailedUploadRecord.created_at >= last_7d
                ),
                "total_failures_30d": select(func.count(FailedUploadRecord.id)).where(
                    FailedUploadRecord.created_at >= last_30d
                ),
                "resolved_24h": select(func.count(FailedUploadRecord.id)).where(
                    and_(
                        FailedUploadRecord.resolved_at >= last_24h,
                        FailedUploadRecord.status == 'resolved'
                    )
                ),
                "resolved_7d": select(func.count(FailedUploadRecord.id)).where(
                    and_(
                        FailedUploadRecord.resolved_at >= last_7d,
                        FailedUploadRecord.status == 'resolved'
                    )
                ),
                "pending_recoveries": select(func.count(FailedUploadRecord.id)).where(
                    FailedUploadRecord.status == 'pending'
                ),
                "manual_interventions": select(func.count(FailedUploadRecord.id)).where(
                    FailedUploadRecord.status == 'failed'
                )
            }
            
            stats = {}
            for key, query in stats_queries.items():
                result = await self.db_session.execute(query)
                stats[key] = result.scalar() or 0
            
            # Calculate rates
            recovery_rate_24h = 0.0
            if stats["total_failures_24h"] > 0:
                recovery_rate_24h = (stats["resolved_24h"] / stats["total_failures_24h"]) * 100
            
            recovery_rate_7d = 0.0
            if stats["total_failures_7d"] > 0:
                recovery_rate_7d = (stats["resolved_7d"] / stats["total_failures_7d"]) * 100
            
            return {
                **stats,
                "recovery_rate_24h": round(recovery_rate_24h, 2),
                "recovery_rate_7d": round(recovery_rate_7d, 2),
                "last_updated": current_time.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting recovery statistics: {e}", exc_info=True)
            return {"error": str(e)}
    
    async def _get_service_health_summary(self) -> Dict[str, Any]:
        """Get service health summary for dashboard"""
        try:
            last_24h = datetime.utcnow() - timedelta(hours=24)
            
            # Get error counts by service
            query = select(
                ErrorLogRecord.service,
                ErrorLogRecord.severity,
                func.count(ErrorLogRecord.id).label('count')
            ).where(
                ErrorLogRecord.created_at >= last_24h
            ).group_by(
                ErrorLogRecord.service,
                ErrorLogRecord.severity
            )
            
            result = await self.db_session.execute(query)
            service_errors = result.all()
            
            # Organize by service
            services = {}
            for row in service_errors:
                service = row.service
                if service not in services:
                    services[service] = {
                        "total_errors": 0,
                        "critical": 0,
                        "high": 0,
                        "medium": 0,
                        "low": 0,
                        "health_status": "healthy"
                    }
                
                services[service]["total_errors"] += row.count
                services[service][row.severity] += row.count
            
            # Determine health status for each service
            for service, data in services.items():
                if data["critical"] > 0:
                    data["health_status"] = "critical"
                elif data["high"] > 5:
                    data["health_status"] = "degraded"
                elif data["total_errors"] > 20:
                    data["health_status"] = "warning"
                else:
                    data["health_status"] = "healthy"
            
            # Add services with no errors
            all_services = ["RequirementService", "ReviewItemService", "PlatformService", "FileVersionService"]
            for service in all_services:
                if service not in services:
                    services[service] = {
                        "total_errors": 0,
                        "critical": 0,
                        "high": 0,
                        "medium": 0,
                        "low": 0,
                        "health_status": "healthy"
                    }
            
            return services
            
        except Exception as e:
            logger.error(f"Error getting service health summary: {e}", exc_info=True)
            return {}
    
    async def get_recovery_history(
        self, 
        resource_id: Optional[str] = None,
        service: Optional[str] = None,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get recovery history with optional filtering.
        
        Args:
            resource_id: Optional resource ID filter
            service: Optional service filter
            days: Number of days to look back
            
        Returns:
            List of recovery history records
        """
        try:
            start_date = datetime.utcnow() - timedelta(days=days)
            
            query = select(FailedUploadRecord).where(
                FailedUploadRecord.created_at >= start_date
            )
            
            if resource_id:
                query = query.where(FailedUploadRecord.resource_id == resource_id)
            
            if service:
                query = query.where(FailedUploadRecord.service == service)
            
            query = query.order_by(desc(FailedUploadRecord.created_at))
            
            result = await self.db_session.execute(query)
            records = result.scalars().all()
            
            history = []
            for record in records:
                error_details = json.loads(record.error_details) if record.error_details else {}
                context = json.loads(record.context_data) if record.context_data else {}
                
                history.append({
                    "record_id": record.id,
                    "service": record.service,
                    "resource_id": record.resource_id,
                    "resource_type": record.resource_type,
                    "error_type": record.error_type,
                    "error_details": error_details,
                    "context": context,
                    "status": record.status,
                    "retry_count": record.retry_count,
                    "max_retries": record.max_retries,
                    "created_at": record.created_at.isoformat(),
                    "updated_at": record.updated_at.isoformat(),
                    "resolved_at": record.resolved_at.isoformat() if record.resolved_at else None,
                    "recovery_notes": record.recovery_notes
                })
            
            return history
            
        except Exception as e:
            logger.error(f"Error getting recovery history: {e}", exc_info=True)
            return []
    
    async def bulk_resolve_interventions(
        self, 
        record_ids: List[str], 
        resolution_notes: str, 
        resolved_by: str
    ) -> Dict[str, Any]:
        """
        Bulk resolve multiple manual interventions.
        
        Args:
            record_ids: List of failed upload record IDs
            resolution_notes: Notes for bulk resolution
            resolved_by: ID of person resolving
            
        Returns:
            Dict containing bulk resolution results
        """
        try:
            results = {
                "total_requested": len(record_ids),
                "successful": 0,
                "failed": 0,
                "details": []
            }
            
            for record_id in record_ids:
                try:
                    success = await self.error_handler.resolve_manual_intervention(
                        record_id, resolution_notes, resolved_by
                    )
                    
                    if success:
                        results["successful"] += 1
                        results["details"].append({
                            "record_id": record_id,
                            "status": "resolved",
                            "message": "Successfully resolved"
                        })
                    else:
                        results["failed"] += 1
                        results["details"].append({
                            "record_id": record_id,
                            "status": "failed",
                            "message": "Record not found or already resolved"
                        })
                        
                except Exception as e:
                    results["failed"] += 1
                    results["details"].append({
                        "record_id": record_id,
                        "status": "error",
                        "message": str(e)
                    })
            
            logger.info(f"Bulk resolution completed: {results['successful']}/{results['total_requested']} successful")
            return results
            
        except Exception as e:
            logger.error(f"Error in bulk resolve interventions: {e}", exc_info=True)
            return {
                "total_requested": len(record_ids),
                "successful": 0,
                "failed": len(record_ids),
                "error": str(e)
            }