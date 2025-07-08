# src/api/events/controllers.py

import logging
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.config.database import get_db_session
from src.middleware.auth_middleware import AuthContext, require_auth
from src.middleware.permissions_middleware import require_resource_permission
from src.models.project_event import ProjectEvent, EventType, EventStatus

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/events",
    tags=["Events & Milestones"],
    redirect_slashes=False,
)


# --- Pydantic Models ---

class EventResponse(BaseModel):
    """Response model for project events"""
    id: str
    project_id: str
    deliverable_id: Optional[str]
    title: str
    description: Optional[str]
    event_type: str
    scheduled_date: datetime
    due_date: Optional[datetime]
    status: str
    is_critical: bool
    is_automated: bool
    assigned_to: Optional[str]
    created_by: str
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    days_until_event: int
    is_overdue: bool

    class Config:
        from_attributes = True


class CreateEventRequest(BaseModel):
    """Request model for creating events"""
    project_id: str = Field(..., description="Project ID")
    deliverable_id: Optional[str] = Field(None, description="Deliverable ID (optional)")
    title: str = Field(..., description="Event title")
    description: Optional[str] = Field(None, description="Event description")
    event_type: str = Field(..., description="Event type")
    scheduled_date: datetime = Field(..., description="Scheduled date")
    due_date: Optional[datetime] = Field(None, description="Due date")
    is_critical: bool = Field(False, description="Is critical event")
    assigned_to: Optional[str] = Field(None, description="Assigned user ID")


class UpdateEventRequest(BaseModel):
    """Request model for updating events"""
    title: Optional[str] = Field(None, description="Event title")
    description: Optional[str] = Field(None, description="Event description")
    scheduled_date: Optional[datetime] = Field(None, description="Scheduled date")
    due_date: Optional[datetime] = Field(None, description="Due date")
    status: Optional[str] = Field(None, description="Event status")
    is_critical: Optional[bool] = Field(None, description="Is critical event")
    assigned_to: Optional[str] = Field(None, description="Assigned user ID")


class UpcomingEventsResponse(BaseModel):
    """Response model for upcoming events"""
    events: List[EventResponse]
    total_count: int
    upcoming_count: int
    overdue_count: int


# --- Utility Functions ---

def event_to_response(event: ProjectEvent) -> EventResponse:
    """Convert ProjectEvent model to response"""
    return EventResponse(
        id=str(event.id),
        project_id=str(event.project_id),
        deliverable_id=str(event.deliverable_id) if event.deliverable_id else None,
        title=event.title,
        description=event.description,
        event_type=event.event_type.value,
        scheduled_date=event.scheduled_date,
        due_date=event.due_date,
        status=event.status.value,
        is_critical=event.is_critical,
        is_automated=event.is_automated,
        assigned_to=str(event.assigned_to) if event.assigned_to else None,
        created_by=str(event.created_by),
        created_at=event.created_at,
        updated_at=event.updated_at,
        completed_at=event.completed_at,
        days_until_event=event.days_until_event(),
        is_overdue=event.is_overdue()
    )


# --- API Endpoints ---

@router.get("/projects/{project_id}/upcoming", response_model=UpcomingEventsResponse)
async def get_upcoming_events(
    project_id: str,
    days_ahead: int = Query(30, description="Days ahead to look for events"),
    deliverable_id: Optional[str] = Query(None, description="Filter by deliverable"),
    event_types: Optional[List[str]] = Query(None, description="Filter by event types"),
    include_overdue: bool = Query(True, description="Include overdue events"),
    db_session: AsyncSession = Depends(get_db_session),
    auth_context: AuthContext = Depends(require_resource_permission("events", "read"))
):
    """
    Get upcoming events for a project.
    """
    try:
        logger.info(f"Getting upcoming events for project {project_id}")
        
        # Build query filters
        filters = [ProjectEvent.project_id == UUID(project_id)]
        
        if deliverable_id:
            filters.append(ProjectEvent.deliverable_id == UUID(deliverable_id))
        
        if event_types:
            type_filters = [ProjectEvent.event_type == EventType(et) for et in event_types]
            filters.append(or_(*type_filters))
        
        # Date range filters
        current_time = datetime.utcnow()
        future_date = current_time + timedelta(days=days_ahead)
        
        if include_overdue:
            # Include overdue and upcoming events
            date_filter = or_(
                and_(
                    ProjectEvent.scheduled_date < current_time,
                    ProjectEvent.status.in_([EventStatus.UPCOMING, EventStatus.IN_PROGRESS])
                ),
                and_(
                    ProjectEvent.scheduled_date >= current_time,
                    ProjectEvent.scheduled_date <= future_date
                )
            )
        else:
            # Only upcoming events
            date_filter = and_(
                ProjectEvent.scheduled_date >= current_time,
                ProjectEvent.scheduled_date <= future_date
            )
        
        filters.append(date_filter)
        filters.append(ProjectEvent.status != EventStatus.CANCELLED)
        
        # Execute query
        query = select(ProjectEvent).where(and_(*filters)).order_by(ProjectEvent.scheduled_date)
        result = await db_session.execute(query)
        events = result.scalars().all()
        
        # Convert to response models
        event_responses = [event_to_response(event) for event in events]
        
        # Calculate counts
        total_count = len(event_responses)
        upcoming_count = len([e for e in event_responses if not e.is_overdue])
        overdue_count = len([e for e in event_responses if e.is_overdue])
        
        logger.info(f"Found {total_count} events for project {project_id}")
        
        return UpcomingEventsResponse(
            events=event_responses,
            total_count=total_count,
            upcoming_count=upcoming_count,
            overdue_count=overdue_count
        )
        
    except Exception as e:
        logger.error(f"Error getting upcoming events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get upcoming events: {str(e)}"
        )


@router.get("/deliverables/{deliverable_id}/upcoming", response_model=List[EventResponse])
async def get_deliverable_upcoming_events(
    deliverable_id: str,
    days_ahead: int = Query(14, description="Days ahead to look for events"),
    db_session: AsyncSession = Depends(get_db_session),
    auth_context: AuthContext = Depends(require_resource_permission("events", "read"))
):
    """
    Get upcoming events for a specific deliverable.
    """
    try:
        logger.info(f"Getting upcoming events for deliverable {deliverable_id}")
        
        current_time = datetime.utcnow()
        future_date = current_time + timedelta(days=days_ahead)
        
        query = select(ProjectEvent).where(
            and_(
                ProjectEvent.deliverable_id == UUID(deliverable_id),
                ProjectEvent.scheduled_date >= current_time,
                ProjectEvent.scheduled_date <= future_date,
                ProjectEvent.status.in_([EventStatus.UPCOMING, EventStatus.IN_PROGRESS])
            )
        ).order_by(ProjectEvent.scheduled_date)
        
        result = await db_session.execute(query)
        events = result.scalars().all()
        
        event_responses = [event_to_response(event) for event in events]
        
        logger.info(f"Found {len(event_responses)} upcoming events for deliverable {deliverable_id}")
        return event_responses
        
    except Exception as e:
        logger.error(f"Error getting deliverable upcoming events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get deliverable upcoming events: {str(e)}"
        )


@router.post("/", response_model=EventResponse)
async def create_event(
    event_data: CreateEventRequest,
    db_session: AsyncSession = Depends(get_db_session),
    auth_context: AuthContext = Depends(require_resource_permission("events", "create"))
):
    """
    Create a new project event.
    """
    try:
        logger.info(f"Creating event: {event_data.title}")
        
        # Create new event
        new_event = ProjectEvent(
            project_id=UUID(event_data.project_id),
            deliverable_id=UUID(event_data.deliverable_id) if event_data.deliverable_id else None,
            title=event_data.title,
            description=event_data.description,
            event_type=EventType(event_data.event_type),
            scheduled_date=event_data.scheduled_date,
            due_date=event_data.due_date,
            is_critical=event_data.is_critical,
            assigned_to=UUID(event_data.assigned_to) if event_data.assigned_to else None,
            created_by=UUID(auth_context.user_id)
        )
        
        db_session.add(new_event)
        await db_session.commit()
        await db_session.refresh(new_event)
        
        logger.info(f"Created event {new_event.id}: {new_event.title}")
        return event_to_response(new_event)
        
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Error creating event: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create event: {str(e)}"
        )


@router.put("/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: str,
    event_data: UpdateEventRequest,
    db_session: AsyncSession = Depends(get_db_session),
    auth_context: AuthContext = Depends(require_resource_permission("events", "update"))
):
    """
    Update an existing event.
    """
    try:
        logger.info(f"Updating event {event_id}")
        
        # Get existing event
        query = select(ProjectEvent).where(ProjectEvent.id == UUID(event_id))
        result = await db_session.execute(query)
        event = result.scalar_one_or_none()
        
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found"
            )
        
        # Update fields
        if event_data.title is not None:
            event.title = event_data.title
        if event_data.description is not None:
            event.description = event_data.description
        if event_data.scheduled_date is not None:
            event.scheduled_date = event_data.scheduled_date
        if event_data.due_date is not None:
            event.due_date = event_data.due_date
        if event_data.status is not None:
            event.status = EventStatus(event_data.status)
        if event_data.is_critical is not None:
            event.is_critical = event_data.is_critical
        if event_data.assigned_to is not None:
            event.assigned_to = UUID(event_data.assigned_to)
        
        await db_session.commit()
        await db_session.refresh(event)
        
        logger.info(f"Updated event {event_id}")
        return event_to_response(event)
        
    except HTTPException:
        raise
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Error updating event: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update event: {str(e)}"
        )


@router.delete("/{event_id}")
async def delete_event(
    event_id: str,
    db_session: AsyncSession = Depends(get_db_session),
    auth_context: AuthContext = Depends(require_resource_permission("events", "delete"))
):
    """
    Delete an event.
    """
    try:
        logger.info(f"Deleting event {event_id}")
        
        # Get existing event
        query = select(ProjectEvent).where(ProjectEvent.id == UUID(event_id))
        result = await db_session.execute(query)
        event = result.scalar_one_or_none()
        
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found"
            )
        
        await db_session.delete(event)
        await db_session.commit()
        
        logger.info(f"Deleted event {event_id}")
        return {"message": f"Event {event_id} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Error deleting event: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete event: {str(e)}"
        ) 