# src/services/file_upload_integration_service.py

import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID
import asyncio
import aiohttp
from datetime import datetime
import mimetypes
import os

from fastapi import UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from pydantic import BaseModel, Field

from src.models.requirement import Requirement
from src.models.requirement_file import RequirementFile
from src.models.review_item import ReviewItem, ReviewItemType
from src.models.internal_task import InternalTask
from src.models.deliverable import Deliverable
from src.models.project import Project
from src.models.file_version import FileVersion, VersionType

logger = logging.getLogger(__name__)


class FileUploadContext(str, Enum):
    """Enum for different file upload contexts"""
    REQUIREMENT = "requirement"
    REVIEW_ITEM = "review_item"


class ValidationResult(BaseModel):
    """Result of file validation"""
    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class FileUploadError(Exception):
    """Custom exception for file upload errors"""
    def __init__(self, service: str, error_type: str, details: dict):
        self.service = service
        self.error_type = error_type
        self.details = details
        super().__init__(f"{service} error ({error_type}): {details}")


class RequirementFileMetadata(BaseModel):
    """Metadata for requirement file uploads"""
    requirement_id: UUID
    uploaded_by: Optional[UUID] = None
    file_description: Optional[str] = None


class ReviewItemFileMetadata(BaseModel):
    """Metadata for review item file uploads"""
    task_id: UUID
    review_item_type: str
    sequence_number: Optional[int] = None
    review_round: int = 1
    description: Optional[str] = None


class FileUploadResult(BaseModel):
    """Result of file upload operation"""
    platform_file_ids: List[UUID]
    uploaded_files: List[Dict[str, Any]]
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class FileUploadIntegrationService:
    """
    Enhanced centralized service for handling file uploads across different contexts.
    Integrates with platform-service for file storage and manages file references
    in both requirement and review item contexts with comprehensive error handling,
    retry mechanisms, and dual context support.
    """

    def __init__(self, db_session: AsyncSession, platform_service_url: str = None):
        """
        Initialize the FileUploadIntegrationService.
        
        Args:
            db_session: Database session for local operations
            platform_service_url: URL of the platform-service for file operations
        """
        self.db_session = db_session
        self.platform_service_url = platform_service_url or "http://platform-service:8000"
        
        # Enhanced retry configuration
        self.max_retries = 3
        self.retry_delay_base = 1.0  # Base delay in seconds
        self.retry_backoff_factor = 2.0  # Exponential backoff multiplier
        self.connection_timeout = 30.0  # Connection timeout in seconds
        self.read_timeout = 300.0  # Read timeout for large files (5 minutes)
        
        # File type configurations with MIME type validation
        self.requirement_allowed_types = {
            'pdf', 'doc', 'docx', 'txt', 'rtf',
            'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'webp', 'svg',
            'cad', 'dwg', 'step', 'iges', 'obj', 'fbx', '3ds', 'max', 'blend',
            'xls', 'xlsx', 'csv', 'ods',
            'zip', 'rar', '7z', 'tar', 'gz'
        }
        
        self.review_item_allowed_types = {
            'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'webp', 'svg',
            'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm', 'mkv', 'ogv',
            'mp3', 'wav', 'ogg', 'aac', 'flac',
            'pdf', 'doc', 'docx', 'ppt', 'pptx', 'txt', 'rtf',
            'zip', 'rar', '7z'
        }
        
        # MIME type mappings for additional validation
        self.mime_type_mappings = {
            'pdf': 'application/pdf',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'gif': 'image/gif',
            'mp4': 'video/mp4',
            'avi': 'video/x-msvideo',
            'mov': 'video/quicktime'
        }
        
        # File size limits (in bytes)
        self.max_file_size = 100 * 1024 * 1024  # 100MB
        self.max_total_size = 500 * 1024 * 1024  # 500MB per upload batch
        
        # Security configurations
        self.dangerous_extensions = {'exe', 'bat', 'sh', 'cmd', 'scr', 'vbs', 'js', 'jar'}
        self.max_filename_length = 255

    async def upload_requirement_files(
        self, 
        requirement_id: UUID, 
        files: List[UploadFile],
        metadata: RequirementFileMetadata
    ) -> FileUploadResult:
        """
        Upload files for a requirement with proper validation and storage.
        
        Args:
            requirement_id: ID of the requirement
            files: List of files to upload
            metadata: Additional metadata for the upload
            
        Returns:
            FileUploadResult: Result containing platform file IDs and status
        """
        logger.info(f"Starting requirement file upload for requirement {requirement_id}")
        
        try:
            # Validate requirement exists
            requirement = await self._get_requirement_by_id(requirement_id)
            if not requirement:
                raise FileUploadError(
                    "RequirementService", 
                    "NOT_FOUND", 
                    {"requirement_id": str(requirement_id)}
                )
            
            # Validate files
            validation_result = await self.validate_file_types(files, FileUploadContext.REQUIREMENT)
            if not validation_result.is_valid:
                raise FileUploadError(
                    "RequirementService",
                    "VALIDATION_ERROR",
                    {"errors": validation_result.errors}
                )
            
            # Upload files to platform-service
            platform_file_ids = await self._upload_to_platform_service(
                files, 
                context="requirement",
                context_id=str(requirement_id)
            )
            
            # Create requirement file records
            uploaded_files = []
            for i, (file, platform_file_id) in enumerate(zip(files, platform_file_ids)):
                requirement_file = RequirementFile(
                    requirement_id=requirement_id,
                    platform_file_id=platform_file_id,
                    file_name=file.filename,
                    file_type=self._get_file_extension(file.filename),
                    file_size=file.size if hasattr(file, 'size') else 0,
                    uploaded_by=metadata.uploaded_by,
                    upload_timestamp=datetime.utcnow(),
                    is_active=True
                )
                
                self.db_session.add(requirement_file)
                uploaded_files.append({
                    "file_name": file.filename,
                    "platform_file_id": str(platform_file_id),
                    "file_type": requirement_file.file_type,
                    "file_size": requirement_file.file_size
                })
            
            await self.db_session.commit()
            
            logger.info(f"Successfully uploaded {len(files)} files for requirement {requirement_id}")
            
            return FileUploadResult(
                platform_file_ids=platform_file_ids,
                uploaded_files=uploaded_files,
                warnings=validation_result.warnings
            )
            
        except FileUploadError:
            await self.db_session.rollback()
            raise
        except Exception as e:
            await self.db_session.rollback()
            logger.error(f"Error uploading requirement files: {e}", exc_info=True)
            raise FileUploadError(
                "RequirementService",
                "UPLOAD_ERROR",
                {"error": str(e), "requirement_id": str(requirement_id)}
            )

    async def upload_review_item_files(
        self, 
        task_id: UUID, 
        files: List[UploadFile],
        metadata: ReviewItemFileMetadata
    ) -> FileUploadResult:
        """
        Upload files for review items with automatic review item creation.
        
        Args:
            task_id: ID of the task being completed
            files: List of files to upload
            metadata: Additional metadata for the upload
            
        Returns:
            FileUploadResult: Result containing platform file IDs and status
        """
        logger.info(f"Starting review item file upload for task {task_id}")
        
        try:
            # Validate task exists and get context
            task = await self._get_task_by_id(task_id)
            if not task:
                raise FileUploadError(
                    "ReviewItemService", 
                    "NOT_FOUND", 
                    {"task_id": str(task_id)}
                )
            
            # Validate files
            validation_result = await self.validate_file_types(files, FileUploadContext.REVIEW_ITEM)
            if not validation_result.is_valid:
                raise FileUploadError(
                    "ReviewItemService",
                    "VALIDATION_ERROR",
                    {"errors": validation_result.errors}
                )
            
            # Upload files to platform-service
            platform_file_ids = await self._upload_to_platform_service(
                files, 
                context="review_item",
                context_id=str(task_id)
            )
            
            # Create review items for each file
            uploaded_files = []
            for i, (file, platform_file_id) in enumerate(zip(files, platform_file_ids)):
                sequence_number = metadata.sequence_number or (i + 1)
                
                review_item = ReviewItem(
                    project_id=task.project_id,
                    deliverable_id=task.deliverable_id,
                    source_internal_task_id=task_id,
                    item_type=metadata.review_item_type,
                    platform_file_id=platform_file_id,
                    description=metadata.description or f"Review for {file.filename}",
                    sequence_number=sequence_number,
                    review_round=metadata.review_round,
                    presented_at=datetime.utcnow()
                )
                
                self.db_session.add(review_item)
                uploaded_files.append({
                    "file_name": file.filename,
                    "platform_file_id": str(platform_file_id),
                    "review_item_id": str(review_item.id),
                    "sequence_number": sequence_number
                })
            
            await self.db_session.commit()
            
            logger.info(f"Successfully uploaded {len(files)} files and created review items for task {task_id}")
            
            return FileUploadResult(
                platform_file_ids=platform_file_ids,
                uploaded_files=uploaded_files,
                warnings=validation_result.warnings
            )
            
        except FileUploadError:
            await self.db_session.rollback()
            raise
        except Exception as e:
            await self.db_session.rollback()
            logger.error(f"Error uploading review item files: {e}", exc_info=True)
            raise FileUploadError(
                "ReviewItemService",
                "UPLOAD_ERROR",
                {"error": str(e), "task_id": str(task_id)}
            )

    async def validate_file_types(
        self, 
        files: List[UploadFile], 
        context: FileUploadContext
    ) -> ValidationResult:
        """
        Enhanced file validation with security checks and MIME type validation.
        
        Args:
            files: List of files to validate
            context: Upload context (requirement or review_item)
            
        Returns:
            ValidationResult: Validation result with errors and warnings
        """
        errors = []
        warnings = []
        
        if not files:
            errors.append("No files provided for upload")
            return ValidationResult(is_valid=False, errors=errors)
        
        # Get allowed types for context
        allowed_types = (
            self.requirement_allowed_types 
            if context == FileUploadContext.REQUIREMENT 
            else self.review_item_allowed_types
        )
        
        total_size = 0
        filenames_seen = set()
        
        for file in files:
            # Validate filename
            if not file.filename or len(file.filename) > self.max_filename_length:
                errors.append(f"Invalid filename or filename too long: {file.filename}")
                continue
            
            # Check for duplicate filenames
            if file.filename in filenames_seen:
                errors.append(f"Duplicate filename detected: {file.filename}")
                continue
            filenames_seen.add(file.filename)
            
            # Check file extension
            file_ext = self._get_file_extension(file.filename)
            if not file_ext:
                errors.append(f"File must have an extension: {file.filename}")
                continue
                
            if file_ext not in allowed_types:
                errors.append(
                    f"File type '{file_ext}' not allowed for {context.value} uploads. "
                    f"Allowed types: {', '.join(sorted(allowed_types))}"
                )
                continue
            
            # Security check for dangerous extensions
            if file_ext in self.dangerous_extensions:
                errors.append(f"Dangerous file type not allowed: {file.filename}")
                continue
            
            # Check file size
            file_size = getattr(file, 'size', 0)
            if file_size == 0:
                warnings.append(f"Empty file detected: {file.filename}")
            elif file_size > self.max_file_size:
                errors.append(
                    f"File '{file.filename}' exceeds maximum size limit "
                    f"({self.max_file_size / (1024*1024):.1f}MB)"
                )
            
            total_size += file_size
            
            # MIME type validation (if available)
            content_type = getattr(file, 'content_type', None)
            if content_type and file_ext in self.mime_type_mappings:
                expected_mime = self.mime_type_mappings[file_ext]
                if content_type != expected_mime:
                    warnings.append(
                        f"MIME type mismatch for {file.filename}: "
                        f"expected {expected_mime}, got {content_type}"
                    )
            
            # Additional security checks
            if self._contains_suspicious_patterns(file.filename):
                warnings.append(f"Suspicious filename pattern detected: {file.filename}")
        
        # Check total upload size
        if total_size > self.max_total_size:
            errors.append(
                f"Total upload size exceeds limit "
                f"({self.max_total_size / (1024*1024):.1f}MB)"
            )
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    async def _upload_to_platform_service(
        self, 
        files: List[UploadFile], 
        context: str,
        context_id: str
    ) -> List[UUID]:
        """
        Upload files to platform-service with enhanced error handling and retry mechanisms.
        
        Args:
            files: List of files to upload
            context: Upload context string
            context_id: Context-specific ID
            
        Returns:
            List[UUID]: List of platform file IDs
        """
        platform_file_ids = []
        
        # Configure session with timeouts and connection limits
        timeout = aiohttp.ClientTimeout(
            total=self.connection_timeout + self.read_timeout,
            connect=self.connection_timeout,
            sock_read=self.read_timeout
        )
        
        connector = aiohttp.TCPConnector(
            limit=10,  # Maximum number of connections
            limit_per_host=5,  # Maximum connections per host
            ttl_dns_cache=300,  # DNS cache TTL
            use_dns_cache=True
        )
        
        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector
        ) as session:
            
            # Upload files with retry mechanism
            for file in files:
                platform_file_id = await self._upload_single_file_with_retry(
                    session, file, context, context_id
                )
                platform_file_ids.append(platform_file_id)
        
        return platform_file_ids

    async def _upload_single_file_with_retry(
        self,
        session: aiohttp.ClientSession,
        file: UploadFile,
        context: str,
        context_id: str
    ) -> UUID:
        """
        Upload a single file with retry mechanism and exponential backoff.
        
        Args:
            session: aiohttp session
            file: File to upload
            context: Upload context
            context_id: Context-specific ID
            
        Returns:
            UUID: Platform file ID
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                # Reset file pointer for each attempt
                await file.seek(0)
                
                # Read file content
                file_content = await file.read()
                
                # Prepare form data
                data = aiohttp.FormData()
                data.add_field('file', file_content, filename=file.filename)
                data.add_field('context', context)
                data.add_field('context_id', context_id)
                
                # Add additional metadata
                if hasattr(file, 'content_type') and file.content_type:
                    data.add_field('content_type', file.content_type)
                if hasattr(file, 'size') and file.size:
                    data.add_field('file_size', str(file.size))
                
                # Upload to platform-service
                upload_url = f"{self.platform_service_url}/api/v1/files/upload"
                
                async with session.post(upload_url, data=data) as response:
                    if response.status == 201:
                        result = await response.json()
                        logger.info(f"Successfully uploaded file {file.filename} to platform-service")
                        return UUID(result['file_id'])
                    else:
                        error_text = await response.text()
                        error = FileUploadError(
                            "PlatformService",
                            "UPLOAD_FAILED",
                            {
                                "status": response.status,
                                "error": error_text,
                                "filename": file.filename,
                                "attempt": attempt + 1
                            }
                        )
                        
                        # Don't retry for certain error types
                        if response.status in [400, 401, 403, 413, 415]:
                            raise error
                        
                        last_error = error
                        
            except aiohttp.ClientError as e:
                last_error = FileUploadError(
                    "PlatformService",
                    "CONNECTION_ERROR",
                    {
                        "error": str(e), 
                        "filename": file.filename,
                        "attempt": attempt + 1
                    }
                )
            except Exception as e:
                last_error = FileUploadError(
                    "PlatformService",
                    "UNEXPECTED_ERROR",
                    {
                        "error": str(e), 
                        "filename": file.filename,
                        "attempt": attempt + 1
                    }
                )
            
            # Wait before retry (exponential backoff)
            if attempt < self.max_retries - 1:
                delay = self.retry_delay_base * (self.retry_backoff_factor ** attempt)
                logger.warning(
                    f"Upload attempt {attempt + 1} failed for {file.filename}, "
                    f"retrying in {delay}s: {last_error}"
                )
                await asyncio.sleep(delay)
        
        # All retries failed
        logger.error(f"All {self.max_retries} upload attempts failed for {file.filename}")
        raise last_error

    async def _get_requirement_by_id(self, requirement_id: UUID) -> Optional[Requirement]:
        """Get requirement by ID"""
        result = await self.db_session.execute(
            select(Requirement).filter(Requirement.id == requirement_id)
        )
        return result.scalar_one_or_none()

    async def _get_task_by_id(self, task_id: UUID) -> Optional[InternalTask]:
        """Get internal task by ID"""
        result = await self.db_session.execute(
            select(InternalTask).filter(InternalTask.id == task_id)
        )
        return result.scalar_one_or_none()

    def _get_file_extension(self, filename: str) -> str:
        """Extract file extension from filename"""
        if not filename or '.' not in filename:
            return ''
        return filename.split('.')[-1].lower()

    def _contains_suspicious_patterns(self, filename: str) -> bool:
        """
        Check if filename contains suspicious patterns that might indicate malicious intent.
        
        Args:
            filename: The filename to check
            
        Returns:
            bool: True if suspicious patterns are found
        """
        suspicious_patterns = [
            '..',  # Directory traversal
            '/',   # Path separator
            '\\',  # Windows path separator
            '<',   # HTML/XML tags
            '>',   # HTML/XML tags
            '|',   # Pipe character
            ':',   # Colon (Windows drive separator)
            '*',   # Wildcard
            '?',   # Wildcard
            '"',   # Quote character
            '\x00', # Null byte
        ]
        
        filename_lower = filename.lower()
        
        # Check for suspicious patterns
        for pattern in suspicious_patterns:
            if pattern in filename:
                return True
        
        # Check for suspicious keywords
        suspicious_keywords = ['script', 'exec', 'cmd', 'powershell', 'bash']
        for keyword in suspicious_keywords:
            if keyword in filename_lower:
                return True
        
        return False

    async def get_file_upload_statistics(
        self,
        context: Optional[FileUploadContext] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get statistics about file uploads for monitoring and analysis.
        
        Args:
            context: Optional context filter
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            Dict containing upload statistics
        """
        logger.info("Getting file upload statistics")
        
        try:
            stats = {
                "total_uploads": 0,
                "successful_uploads": 0,
                "failed_uploads": 0,
                "total_file_size": 0,
                "average_file_size": 0,
                "file_type_distribution": {},
                "context_distribution": {}
            }
            
            # Get requirement file statistics
            if not context or context == FileUploadContext.REQUIREMENT:
                req_filters = []
                if start_date:
                    req_filters.append(RequirementFile.created_at >= start_date)
                if end_date:
                    req_filters.append(RequirementFile.created_at <= end_date)
                
                req_result = await self.db_session.execute(
                    select(RequirementFile).filter(and_(*req_filters) if req_filters else True)
                )
                req_files = req_result.scalars().all()
                
                req_count = len(req_files)
                req_size = sum(getattr(f, 'file_size', 0) for f in req_files)
                
                stats["context_distribution"]["requirement"] = {
                    "count": req_count,
                    "total_size": req_size
                }
                
                # File type distribution for requirements
                for file in req_files:
                    file_type = getattr(file, 'file_type', 'unknown')
                    if file_type not in stats["file_type_distribution"]:
                        stats["file_type_distribution"][file_type] = 0
                    stats["file_type_distribution"][file_type] += 1
            
            # Get review item statistics
            if not context or context == FileUploadContext.REVIEW_ITEM:
                review_filters = []
                if start_date:
                    review_filters.append(ReviewItem.created_at >= start_date)
                if end_date:
                    review_filters.append(ReviewItem.created_at <= end_date)
                
                review_result = await self.db_session.execute(
                    select(ReviewItem).filter(
                        and_(
                            ReviewItem.platform_file_id.isnot(None),
                            *review_filters
                        ) if review_filters else ReviewItem.platform_file_id.isnot(None)
                    )
                )
                review_items = review_result.scalars().all()
                
                review_count = len(review_items)
                
                stats["context_distribution"]["review_item"] = {
                    "count": review_count,
                    "total_size": 0  # Size not tracked in review items currently
                }
            
            # Calculate totals
            total_files = sum(
                ctx_stats["count"] 
                for ctx_stats in stats["context_distribution"].values()
            )
            total_size = sum(
                ctx_stats["total_size"] 
                for ctx_stats in stats["context_distribution"].values()
            )
            
            stats["total_uploads"] = total_files
            stats["successful_uploads"] = total_files  # Assuming all in DB are successful
            stats["total_file_size"] = total_size
            stats["average_file_size"] = total_size / total_files if total_files > 0 else 0
            
            logger.info(f"File upload statistics: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error getting file upload statistics: {e}", exc_info=True)
            raise

    async def upload_file_version(
        self,
        original_file_id: UUID,
        new_file: UploadFile,
        metadata: Dict[str, Any]
    ) -> FileUploadResult:
        """
        Upload a new version of an existing file.
        
        Args:
            original_file_id: ID of the original file
            new_file: New file version to upload
            metadata: Additional metadata for the upload
            
        Returns:
            FileUploadResult: Result containing platform file ID and status
        """
        logger.info(f"Uploading new version for file {original_file_id}")
        
        try:
            # Validate file
            validation_result = await self.validate_file_types([new_file], FileUploadContext.REVIEW_ITEM)
            if not validation_result.is_valid:
                raise FileUploadError(
                    "FileVersionService",
                    "VALIDATION_ERROR",
                    {"errors": validation_result.errors}
                )
            
            # Upload file to platform-service
            platform_file_ids = await self._upload_to_platform_service(
                [new_file], 
                context="file_version",
                context_id=str(original_file_id)
            )
            
            # Create file metadata
            file_metadata = [{
                "file_name": new_file.filename,
                "file_type": self._get_file_extension(new_file.filename),
                "file_size": new_file.size if hasattr(new_file, 'size') else 0,
                "original_file_id": str(original_file_id)
            }]
            
            logger.info(f"Successfully uploaded new version for file {original_file_id}")
            
            return FileUploadResult(
                success=True,
                platform_file_ids=platform_file_ids,
                file_metadata=file_metadata,
                warnings=validation_result.warnings
            )
            
        except FileUploadError:
            raise
        except Exception as e:
            logger.error(f"Error uploading file version: {e}", exc_info=True)
            raise FileUploadError(
                "FileVersionService",
                "UPLOAD_ERROR",
                {"error": str(e), "original_file_id": str(original_file_id)}
            )
    
    async def cleanup_orphaned_files(self) -> Dict[str, int]:
        """
        Clean up orphaned file references that may exist due to failed operations.
        
        Returns:
            Dict containing cleanup statistics
        """
        logger.info("Starting orphaned file cleanup")
        
        try:
            cleanup_stats = {
                "orphaned_requirement_files": 0,
                "orphaned_file_versions": 0,
                "total_cleaned": 0
            }
            
            # Find requirement files with no corresponding requirement
            orphaned_req_files = await self.db_session.execute(
                select(RequirementFile)
                .outerjoin(Requirement, RequirementFile.requirement_id == Requirement.id)
                .filter(Requirement.id.is_(None))
            )
            
            for orphaned_file in orphaned_req_files.scalars():
                logger.warning(f"Found orphaned requirement file: {orphaned_file.id}")
                # Mark as inactive instead of deleting for audit purposes
                orphaned_file.is_active = False
                cleanup_stats["orphaned_requirement_files"] += 1
            
            # Find file versions with no corresponding files
            # This would require checking against platform-service, which is complex
            # For now, we'll just mark inactive file versions as candidates for cleanup
            inactive_versions = await self.db_session.execute(
                select(FileVersion).filter(FileVersion.is_active == False)
            )
            
            cleanup_stats["orphaned_file_versions"] = len(inactive_versions.scalars().all())
            cleanup_stats["total_cleaned"] = (
                cleanup_stats["orphaned_requirement_files"] + 
                cleanup_stats["orphaned_file_versions"]
            )
            
            await self.db_session.commit()
            
            logger.info(f"Cleanup completed: {cleanup_stats}")
            return cleanup_stats
            
        except Exception as e:
            await self.db_session.rollback()
            logger.error(f"Error during file cleanup: {e}", exc_info=True)
            raise


class FileUploadErrorHandler:
    """
    Handler for file upload errors with retry mechanisms and recovery strategies.
    """

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def handle_requirement_upload_error(
        self, 
        error: FileUploadError, 
        requirement_id: UUID
    ) -> Dict[str, Any]:
        """
        Handle requirement file upload errors with appropriate recovery.
        
        Args:
            error: The file upload error
            requirement_id: ID of the requirement
            
        Returns:
            Dict containing error response and recovery suggestions
        """
        logger.error(f"Requirement upload error for {requirement_id}: {error}")
        
        error_response = {
            "error_type": error.error_type,
            "service": error.service,
            "details": error.details,
            "requirement_id": str(requirement_id),
            "recovery_suggestions": []
        }
        
        if error.error_type == "VALIDATION_ERROR":
            error_response["recovery_suggestions"] = [
                "Check file types and sizes",
                "Remove invalid files and retry",
                "Contact support if file types should be allowed"
            ]
        elif error.error_type == "CONNECTION_ERROR":
            error_response["recovery_suggestions"] = [
                "Check network connection",
                "Retry upload after a few minutes",
                "Contact system administrator if problem persists"
            ]
        elif error.error_type == "UPLOAD_FAILED":
            error_response["recovery_suggestions"] = [
                "Retry upload with smaller files",
                "Check file integrity",
                "Contact support if problem persists"
            ]
        
        return error_response

    async def handle_review_item_upload_error(
        self, 
        error: FileUploadError, 
        task_id: UUID
    ) -> Dict[str, Any]:
        """
        Handle review item file upload errors with appropriate recovery.
        
        Args:
            error: The file upload error
            task_id: ID of the task
            
        Returns:
            Dict containing error response and recovery suggestions
        """
        logger.error(f"Review item upload error for task {task_id}: {error}")
        
        error_response = {
            "error_type": error.error_type,
            "service": error.service,
            "details": error.details,
            "task_id": str(task_id),
            "recovery_suggestions": []
        }
        
        if error.error_type == "VALIDATION_ERROR":
            error_response["recovery_suggestions"] = [
                "Check file types (images, videos, documents allowed)",
                "Reduce file sizes if too large",
                "Remove invalid files and retry"
            ]
        elif error.error_type == "CONNECTION_ERROR":
            error_response["recovery_suggestions"] = [
                "Check network connection",
                "Retry upload after a few minutes",
                "Save work and try again later"
            ]
        elif error.error_type == "UPLOAD_FAILED":
            error_response["recovery_suggestions"] = [
                "Retry upload with individual files",
                "Check file integrity",
                "Use alternative file formats if available"
            ]
        
        return error_response

    async def retry_failed_upload(
        self, 
        upload_function,
        *args,
        **kwargs
    ) -> Any:
        """
        Retry a failed upload with exponential backoff.
        
        Args:
            upload_function: The upload function to retry
            *args: Arguments for the upload function
            **kwargs: Keyword arguments for the upload function
            
        Returns:
            Result of successful upload
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                return await upload_function(*args, **kwargs)
            except FileUploadError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"Upload attempt {attempt + 1} failed, retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All {self.max_retries} upload attempts failed")
        
        raise last_error

    async def handle_platform_service_error(
        self,
        error: FileUploadError,
        context: str
    ) -> Dict[str, Any]:
        """
        Handle platform service specific errors with appropriate recovery strategies.
        
        Args:
            error: The file upload error from platform service
            context: The upload context (requirement or review_item)
            
        Returns:
            Dict containing error response and recovery suggestions
        """
        logger.error(f"Platform service error in {context} context: {error}")
        
        error_response = {
            "error_type": error.error_type,
            "service": error.service,
            "context": context,
            "details": error.details,
            "recovery_suggestions": []
        }
        
        if error.error_type == "CONNECTION_ERROR":
            error_response["recovery_suggestions"] = [
                "Platform service may be temporarily unavailable",
                "Check network connectivity",
                "Retry upload after a few minutes",
                "Contact system administrator if problem persists"
            ]
        elif error.error_type == "UPLOAD_FAILED":
            status_code = error.details.get("status", 0)
            if status_code == 413:  # Payload too large
                error_response["recovery_suggestions"] = [
                    "File size exceeds platform service limits",
                    "Try uploading smaller files",
                    "Compress files if possible",
                    "Contact administrator to increase limits"
                ]
            elif status_code == 415:  # Unsupported media type
                error_response["recovery_suggestions"] = [
                    "File type not supported by platform service",
                    "Convert file to supported format",
                    "Check file extension and content type",
                    "Contact support for format requirements"
                ]
            elif status_code >= 500:  # Server error
                error_response["recovery_suggestions"] = [
                    "Platform service experiencing internal errors",
                    "Retry upload after a few minutes",
                    "Contact system administrator",
                    "Check service status page"
                ]
            else:
                error_response["recovery_suggestions"] = [
                    "Upload failed due to platform service error",
                    "Check file integrity and format",
                    "Retry upload",
                    "Contact support if problem persists"
                ]
        
        return error_response

    async def retry_failed_upload(
        self, 
        upload_function,
        *args,
        **kwargs
    ) -> Any:
        """
        Retry a failed upload with exponential backoff.
        
        Args:
            upload_function: The upload function to retry
            *args: Arguments for the upload function
            **kwargs: Keyword arguments for the upload function
            
        Returns:
            Result of successful upload
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                return await upload_function(*args, **kwargs)
            except FileUploadError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"Upload attempt {attempt + 1} failed, retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All {self.max_retries} upload attempts failed")
        
        raise last_error

    async def handle_platform_service_error(
        self,
        error: FileUploadError,
        context: str
    ) -> Dict[str, Any]:
        """
        Handle platform service specific errors with appropriate recovery strategies.
        
        Args:
            error: The file upload error from platform service
            context: The upload context (requirement or review_item)
            
        Returns:
            Dict containing error response and recovery suggestions
        """
        logger.error(f"Platform service error in {context} context: {error}")
        
        error_response = {
            "error_type": error.error_type,
            "service": error.service,
            "context": context,
            "details": error.details,
            "recovery_suggestions": []
        }
        
        if error.error_type == "CONNECTION_ERROR":
            error_response["recovery_suggestions"] = [
                "Platform service may be temporarily unavailable",
                "Check network connectivity",
                "Retry upload after a few minutes",
                "Contact system administrator if problem persists"
            ]
        elif error.error_type == "UPLOAD_FAILED":
            status_code = error.details.get("status", 0)
            if status_code == 413:  # Payload too large
                error_response["recovery_suggestions"] = [
                    "File size exceeds platform service limits",
                    "Try uploading smaller files",
                    "Compress files if possible",
                    "Contact administrator to increase limits"
                ]
            elif status_code == 415:  # Unsupported media type
                error_response["recovery_suggestions"] = [
                    "File type not supported by platform service",
                    "Convert file to supported format",
                    "Check file extension and content type",
                    "Contact support for format requirements"
                ]
            elif status_code >= 500:  # Server error
                error_response["recovery_suggestions"] = [
                    "Platform service experiencing internal errors",
                    "Retry upload after a few minutes",
                    "Contact system administrator",
                    "Check service status page"
                ]
            else:
                error_response["recovery_suggestions"] = [
                    "Upload failed due to platform service error",
                    "Check file integrity and format",
                    "Retry upload",
                    "Contact support if problem persists"
                ]
        elif error.error_type == "UNEXPECTED_ERROR":
            error_response["recovery_suggestions"] = [
                "An unexpected error occurred during upload",
                "Check file integrity and format",
                "Retry upload with a different file",
                "Contact support with error details"
            ]
        
        return error_response

    async def check_platform_service_health(self) -> Dict[str, Any]:
        """
        Check the health status of the platform service.
        
        Returns:
            Dict containing health status information
        """
        try:
            timeout = aiohttp.ClientTimeout(total=10.0)  # Short timeout for health check
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                health_url = f"{self.platform_service_url}/health"
                
                async with session.get(health_url) as response:
                    if response.status == 200:
                        result = await response.json()
                        return {
                            "status": "healthy",
                            "response_time_ms": response.headers.get("X-Response-Time", "unknown"),
                            "details": result
                        }
                    else:
                        return {
                            "status": "unhealthy",
                            "status_code": response.status,
                            "error": await response.text()
                        }
                        
        except aiohttp.ClientError as e:
            return {
                "status": "unreachable",
                "error": str(e)
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    async def get_upload_queue_status(self) -> Dict[str, Any]:
        """
        Get status of any queued or failed uploads for monitoring.
        
        Returns:
            Dict containing queue status information
        """
        # This would typically integrate with a job queue system
        # For now, return basic status
        return {
            "queued_uploads": 0,
            "failed_uploads": 0,
            "retry_queue_size": 0,
            "last_successful_upload": None,
            "last_failed_upload": None
        }