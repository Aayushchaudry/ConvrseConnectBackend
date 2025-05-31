"""
Project Lifecycle SAGA States.
Enum for SAGA states in the project lifecycle orchestration.
"""

import enum

class ProjectSagaState(enum.Enum):
    """
    Enum defining the possible states of a Project Lifecycle SAGA.
    These states represent the high-level phases of a project's lifecycle.
    """
    # Initial state when project is created
    PROJECT_CREATED = "project_created"
    
    # Information gathering phase
    INFO_GATHERING_INITIATED = "info_gathering_initiated"
    INFO_GATHERING_IN_PROGRESS = "info_gathering_in_progress"
    INFO_GATHERING_COMPLETED = "info_gathering_completed"
    
    # Planning and preparation phase
    PLANNING_INITIATED = "planning_initiated"
    PLANNING_IN_PROGRESS = "planning_in_progress"
    PLANNING_COMPLETED = "planning_completed"
    
    # Production coordination phase
    COORDINATING_DELIVERABLES = "coordinating_deliverables"
    DELIVERABLES_IN_PROGRESS = "deliverables_in_progress"
    
    # Review and feedback phase
    IN_REVIEW = "in_review"
    AWAITING_CLIENT_FEEDBACK = "awaiting_client_feedback"
    CLIENT_FEEDBACK_RECEIVED = "client_feedback_received"
    
    # Completion phase
    ALL_DELIVERABLES_DELIVERED = "all_deliverables_delivered"
    DELIVERY_PREPARATION = "delivery_preparation"
    PROJECT_DELIVERED = "project_delivered"
    PROJECT_COMPLETED = "project_completed"
    
    # Error states
    PROJECT_FAILED = "project_failed"
    PROJECT_CANCELLED = "project_cancelled"
    
    # Compensation states
    COMPENSATING = "compensating"
    COMPENSATION_COMPLETED = "compensation_completed" 