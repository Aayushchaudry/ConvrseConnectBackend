# src/config/database.py (SIMPLIFIED & CORRECTED)

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from src.config.settings import settings

# Base class for declarative models
# All your ORM models should inherit from this Base
Base = declarative_base()

# Create an async SQLAlchemy engine
# This engine is the primary interface to your database connection.
engine = create_async_engine(
    settings.DATABASE_URL, # Ensure this is 'postgresql+asyncpg://'
    echo=settings.DEBUG,   # Logs SQL statements if True (useful for debugging)
    pool_pre_ping=True     # Ensures connections in the pool are healthy
)

# Async sessionmaker for database operations
# This is what your services and orchestrators will use to get a database session.
AsyncSessionLocal = async_sessionmaker(
    autocommit=False,       # Don't auto-commit transactions
    autoflush=False,        # Don't autoflush (write changes) automatically
    bind=engine,            # Bind this sessionmaker to our async engine
    class_=AsyncSession,    # Use the async session class
    expire_on_commit=False  # Prevents ORM objects from expiring after commit (can simplify certain patterns)
)

async def get_db_session():
    """
    Dependency function for FastAPI routes to get an asynchronous database session.
    It yields a session, ensuring it's properly closed after the request.
    """
    async with AsyncSessionLocal() as session:
        yield session

async def init_db():
    """
    Initializes the database schema.
    Creates all tables defined in your models if they don't already exist.
    
    IMPORTANT: Import all models here (inside the function) to avoid circular imports.
    """
    # Import models here to avoid circular imports
    from src.models.project import Project, ProjectStatus
    from src.models.saga_state import SagaState, SagaStatus, SagaType
    # Add more model imports as you create them
    
    async with engine.begin() as conn:
        print("Initializing database...")
        # This command creates tables for all ORM models that inherit from `Base`
        # and have been imported into this function.
        await conn.run_sync(Base.metadata.create_all)
        print("Database initialization complete.")