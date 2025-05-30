# src/main.py (UPDATED)

from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging
import asyncio
from typing import List

from src.config.settings import settings
from src.config.database import init_db 
from src.config.event_bus import get_event_bus, close_event_bus

# --- IMPORT YOUR API ROUTERS HERE ---
from src.api.projects.controllers import router as projects_router # <--- NEW IMPORT
# from src.api.auth.controllers import router as auth_router


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

background_tasks: List[asyncio.Task] = []

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown events for the FastAPI application.
    """
    logger.info("Application starting up...")

    # 1. Initialize Database
    try:
        await init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise 

    # 2. Initialize Event Bus (will connect producer/client)
    try:
        event_bus = await get_event_bus()
        logger.info("Event Bus initialized and connected successfully.")

        # 3. Start SAGA Listeners (Example - you will create these later)
        # Add your actual listener startup logic here as you create them.
        # Example:
        # from src.listeners.project_events_listener import start_listening as start_project_listener
        # task = asyncio.create_task(start_project_listener(event_bus))
        # background_tasks.append(task)
        
    except Exception as e:
        logger.error(f"Failed to initialize Event Bus or start listeners: {e}")
        raise

    yield # Application is ready to serve requests

    # Shutdown events
    logger.info("Application shutting down...")
    for task in background_tasks:
        task.cancel() # Request tasks to cancel
        try:
            await task # Await cancellation to complete
        except asyncio.CancelledError:
            pass # Task was cancelled as expected

    await close_event_bus() # Close the active event bus connection
    logger.info("Application shutdown complete.")


app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    version="0.1.0",
    lifespan=lifespan # Attach the lifespan context manager
)

# --- INCLUDE YOUR API ROUTERS HERE ---
app.include_router(projects_router, prefix="/api/v1") # <--- NEW LINE
# app.include_router(auth_router, prefix="/api/v1/auth")


@app.get("/api/v1/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "ok", "app_name": settings.APP_NAME, "environment": settings.ENV}