"""
SagaState table structure definition.
Defines the SagaState ORM model for SAGA orchestrator state management.
"""

# TODO: Import ORM base class and field types
# TODO: Define SagaState model with fields like:
#   - id, saga_id, saga_type, current_state
#   - project_id, deliverable_id (foreign keys)
#   - started_at, updated_at, completed_at
#   - context_data (JSON field for saga context)
#   - error_message, retry_count
# TODO: Define relationships with Project and Deliverable models
# TODO: Add methods for state transitions and error handling 