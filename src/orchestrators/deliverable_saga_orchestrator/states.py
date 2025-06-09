# src/orchestrators/deliverable_saga_orchestrator/states.py

import enum


class DeliverableSagaState(enum.Enum):
    """
    Defines the states for the Deliverable Production & Approval SAGA.
    These states represent the progression of an individual deliverable's lifecycle.
    """

    # Initial state when the Deliverable SAGA is initiated by Project Orchestrator
    INITIATED = "initiated"

    # Information Gathering Phase (managed by Information Gathering Service)
    INFO_GATHERING_STARTED = "info_gathering_started"
    INFO_GATHERING_COMPLETED = "info_gathering_completed"

    # Production Phases (managed by Production Management Service)
    MODELING_PENDING = "modeling_pending"
    MODELING_COMPLETED = "modeling_completed"
    TEXTURING_PENDING = "texturing_pending"
    TEXTURING_COMPLETED = "texturing_completed"
    RENDERING_PENDING = "rendering_pending"
    RENDERING_COMPLETED = "rendering_completed"
    COMPOSITING_PENDING = "compositing_pending"
    COMPOSITING_COMPLETED = "compositing_completed"

    # Client Review Phases (managed by Review Management Service)
    AWAITING_FIRST_DRAFT_REVIEW = "awaiting_first_draft_review"
    AWAITING_REVISION_REVIEW = "awaiting_revision_review"
    CLIENT_REVIEW_ACCEPTED = (
        "client_review_accepted"  # A stage is accepted, not final deliverable
    )

    # Rework/Compensation Phases
    REVISIONS_IN_PROGRESS = "revisions_in_progress"
    COMPENSATION_INITIATED = (
        "compensation_initiated"  # If a deeper rollback/undo is needed
    )

    # Delivery Phases (managed by Delivery Service)
    READY_FOR_FINAL_DELIVERY = "ready_for_final_delivery"
    DELIVERED = "delivered"

    # Failure/Cancellation States
    FAILED = "failed"  # This deliverable SAGA failed unrecoverably
    CANCELED = "canceled"  # This deliverable SAGA was canceled
