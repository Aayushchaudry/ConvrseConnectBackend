# src/config/database.py (FINAL UPDATE for Phase 5 Models)

import re

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from src.config.settings import settings

# Base class for declarative models
Base = declarative_base()


def get_schema_from_url(url: str) -> tuple[str, str]:
    """Extract schema from database URL and return clean URL and schema name"""
    schema_match = re.search(r"[?&]schema=([^&]+)", url)
    if schema_match:
        schema = schema_match.group(1)
        clean_url = re.sub(r"[?&]schema=[^&]+", "", url)
        # Remove trailing ? or & if they exist
        clean_url = re.sub(r"[?&]$", "", clean_url)
        return clean_url, schema
    return url, "public"


database_url, schema_name = get_schema_from_url(settings.DATABASE_URL)

# Create an async SQLAlchemy engine
engine = create_async_engine(
    database_url,
    echo=settings.DEBUG,  # Set to True to log all SQL statements for debugging
    pool_pre_ping=True,  # Ensures connections are healthy
    pool_size=10,  # Increase pool size
    max_overflow=20,  # Allow overflow connections
    pool_recycle=3600,  # Recycle connections every hour
    pool_timeout=30,  # Timeout for getting connection from pool
    connect_args={
        "server_settings": {"search_path": schema_name},
        "command_timeout": 30,  # 30 second timeout for commands
    },
)

# Async sessionmaker for database operations
AsyncSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,  # Don't auto-flush to prevent unnecessary queries
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Prevents objects from expiring after commit
)


async def get_db_session():
    """Dependency for FastAPI routes to get a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            # Only commit if there were no exceptions
            await session.commit()
        except Exception:
            # Rollback on any exception
            await session.rollback()
            raise
        finally:
            # Session is automatically closed by context manager
            pass


async def init_db():
    """
    Initializes the database: creates tables for all models if they don't exist.
    Models MUST be imported here so SQLAlchemy knows about them.
    """
    # --- IMPORT ALL YOUR ORM MODELS HERE ---
    # This is crucial so SQLAlchemy's Base.metadata.create_all() knows about them.
    # Keep these imports INSIDE init_db to avoid circular imports at module level
    # if models also import Base from this file.

    from src.models.client_feedback import ClientFeedback, FeedbackType
    from src.models.deliverable import Deliverable, DeliverableStatus, DeliverableType
    from src.models.internal_task import InternalTask, Priority, TaskStatus, TaskType
    from src.models.project import Project, ProjectStatus
    from src.models.project_output import ProjectOutput
    from src.models.requirement import Requirement, RequirementStatus, RequirementType
    from src.models.requirement_file import RequirementFile
    from src.models.review_item import ReviewItem, ReviewItemType, ReviewStatus
    from src.models.saga_state import SagaState, SagaStatus, SagaType

    async with engine.begin() as conn:
        print("Initializing database...")
        # This will create tables for all models inherited from Base
        # that have been imported within this function.
        await conn.run_sync(Base.metadata.create_all)
        print("Database initialization complete.")
