# src/events/client_feedback_events.py

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
import uuid # For uuid.uuid4()
from typing import Optional, List, Dict, Any

# --- Base Event Definition ---
@dataclass
class BaseEvent:
    event_id: UUID
    timestamp: datetime
    event_type: str

    def __post_init__(self):
        if not hasattr(self, 'event_type') or self.event_type is None:
            self.event_type = self.__class__.__name__

# --- Client Feedback Specific Events ---

@dataclass
class ClientFeedbackSubmittedEvent(BaseEvent):
    """
    Event published when a client submits any type of feedback (accept, reject, comment, like)
    on a ReviewItem.
    Published by: Review Management Service
    Consumed by: Deliverable SAGA Orchestrator (core event for review cycle)
    """
    project_id: UUID
    deliverable_id: UUID
    review_item_id: UUID
    client_user_id: Optional[UUID] # User who gave feedback (if authenticated)
    feedback_type: str # e.g., 'accept', 'reject', 'comment', 'like' (string representation of FeedbackType enum)
    comment_text: Optional[str] = None
    timestamp_seconds: Optional[int] = None # For video/audio comments
    context_coordinates: Optional[Dict[str, Any]] = None # For image region comments

    def __init__(self, project_id: UUID, deliverable_id: UUID, review_item_id: UUID, client_user_id: Optional[UUID], feedback_type: str, comment_text: Optional[str] = None, timestamp_seconds: Optional[int] = None, context_coordinates: Optional[Dict[str, Any]] = None):
        super().__init__(event_id=uuid.uuid4(), timestamp=datetime.utcnow(), event_type="ClientFeedbackSubmittedEvent")
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.review_item_id = review_item_id
        self.client_user_id = client_user_id
        self.feedback_type = feedback_type
        self.comment_text = comment_text
        self.timestamp_seconds = timestamp_seconds
        self.context_coordinates = context_coordinates


@dataclass
class ReviewItemApprovedEvent(BaseEvent):
    """
    Event published (or internally derived by orchestrator) when a ReviewItem
    is explicitly approved by the client.
    Published by: Deliverable SAGA Orchestrator (after processing ClientFeedbackSubmittedEvent)
    Consumed by: Production Management Service (to proceed with next stage), Analytics/UI
    """
    project_id: UUID
    deliverable_id: UUID
    review_item_id: UUID
    approved_by_user_id: Optional[UUID] = None
    
    def __init__(self, project_id: UUID, deliverable_id: UUID, review_item_id: UUID, approved_by_user_id: Optional[UUID] = None):
        super().__init__(event_id=uuid.uuid4(), timestamp=datetime.utcnow(), event_type="ReviewItemApprovedEvent")
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.review_item_id = review_item_id
        self.approved_by_user_id = approved_by_user_id


@dataclass
class ReviewItemRejectedEvent(BaseEvent):
    """
    Event published (or internally derived by orchestrator) when a ReviewItem
    is explicitly rejected by the client.
    Published by: Deliverable SAGA Orchestrator
    Consumed by: Production Management Service (to trigger rework/compensation), Analytics/UI
    """
    project_id: UUID
    deliverable_id: UUID
    review_item_id: UUID
    rejected_by_user_id: Optional[UUID] = None
    reason: Optional[str] = None # Why it was rejected

    def __init__(self, project_id: UUID, deliverable_id: UUID, review_item_id: UUID, rejected_by_user_id: Optional[UUID] = None, reason: Optional[str] = None):
        super().__init__(event_id=uuid.uuid4(), timestamp=datetime.utcnow(), event_type="ReviewItemRejectedEvent")
        self.project_id = project_id
        self.deliverable_id = deliverable_id
        self.review_item_id = review_item_id
        self.rejected_by_user_id = rejected_by_user_id
        self.reason = reason