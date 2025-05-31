# src/config/database.py (FINAL UPDATE for Phase 5 Models)

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from src.config.settings import settings

# Base class for declarative models
Base = declarative_base()

# Create an async SQLAlchemy engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG, # Set to True to log all SQL statements for debugging
    pool_pre_ping=True # Ensures connections are healthy
)

# Async sessionmaker for database operations
AsyncSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False # Prevents objects from expiring after commit
)

async def get_db_session():
    """Dependency for FastAPI routes to get a database session."""
    async with AsyncSessionLocal() as session:
        yield session

async def init_db():
    """
    Initializes the database: creates tables for all models if they don't exist.
    Models MUST be imported here so SQLAlchemy knows about them.
    """
    # --- IMPORT ALL YOUR ORM MODELS HERE ---
    # This is crucial so SQLAlchemy's Base.metadata.create_all() knows about them.
    # Keep these imports INSIDE init_db to avoid circular imports at module level
    # if models also import Base from this file.

    from src.models.project import Project, ProjectStatus
    from src.models.saga_state import SagaState, SagaStatus, SagaType 
    from src.models.deliverable import Deliverable, DeliverableStatus, DeliverableType 
    from src.models.requirement import Requirement, RequirementStatus, RequirementType 
    from src.models.requirement_file import RequirementFile 
    from src.models.internal_task import InternalTask, TaskStatus, TaskType, Priority 
    from src.models.review_item import ReviewItem, ReviewItemType, ReviewStatus 
    from src.models.client_feedback import ClientFeedback, FeedbackType 
    from src.models.project_output import ProjectOutput 


    async with engine.begin() as conn:
        print("Initializing database...")
        # This will create tables for all models inherited from Base
        # that have been imported within this function.
        await conn.run_sync(Base.metadata.create_all)
        print("Database initialization complete.")