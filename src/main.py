# src/main.py

from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging
import asyncio
from typing import List

from src.config.settings import settings
from src.config.database import init_db 
from src.config.event_bus import get_event_bus, close_event_bus

# --- IMPORT YOUR API ROUTERS ---
from src.api.projects.controllers import router as projects_router
from src.api.deliverables.controllers import router as deliverables_router
from src.api.review_items.controllers import router as review_items_router
from src.api.internal_tasks.controllers import router as internal_tasks_router  # <--- NEW IMPORT
from src.api.project_outputs.controllers import router as project_outputs_router  # <--- NEW IMPORT
from src.api.debug_controller import router as debug_router  # <--- DEBUG IMPORT

# --- IMPORT YOUR LISTENERS ---
from src.listeners.project_events_listener import start_listening as start_project_events_listener
from src.listeners.info_gathering_listener import start_listening as start_info_gathering_listener
from src.listeners.deliverable_events_listener import start_listening as start_deliverable_events_listener
from src.listeners.production_management_listener import start_listening as start_production_management_listener
from src.listeners.review_management_listener import start_listening as start_review_management_listener
from src.listeners.client_feedback_listener import start_listening as start_client_feedback_listener
from src.listeners.delivery_listener import start_listening as start_delivery_listener # <--- NEW IMPORT


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

    # 2. Initialize Event Bus
    try:
        event_bus = await get_event_bus()
        logger.info("Event Bus initialized and connected successfully.")

        # 3. Start SAGA Listeners
        # Project Events Listener
        project_listener_task = asyncio.create_task(start_project_events_listener(event_bus))
        background_tasks.append(project_listener_task)
        logger.info("Project Events Listener started in background.")
        
        # Information Gathering Listener
        info_gathering_listener_task = asyncio.create_task(start_info_gathering_listener(event_bus))
        background_tasks.append(info_gathering_listener_task)
        logger.info("Information Gathering Listener started in background.")

        # Deliverable Events Listener
        deliverable_events_listener_task = asyncio.create_task(start_deliverable_events_listener(event_bus))
        background_tasks.append(deliverable_events_listener_task)
        logger.info("Deliverable Events Listener started in background.")

        # Production Management Listener
        production_management_listener_task = asyncio.create_task(start_production_management_listener(event_bus))
        background_tasks.append(production_management_listener_task)
        logger.info("Production Management Listener started in background.")

        # Review Management Listener
        review_management_listener_task = asyncio.create_task(start_review_management_listener(event_bus))
        background_tasks.append(review_management_listener_task)
        logger.info("Review Management Listener started in background.")

        # Client Feedback Listener
        client_feedback_listener_task = asyncio.create_task(start_client_feedback_listener(event_bus))
        background_tasks.append(client_feedback_listener_task)
        logger.info("Client Feedback Listener started in background.")

        # Delivery Listener # <--- NEW LISTENER STARTUP
        delivery_listener_task = asyncio.create_task(start_delivery_listener(event_bus))
        background_tasks.append(delivery_listener_task)
        logger.info("Delivery Listener started in background.")
        
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
app.include_router(projects_router, prefix="/api/v1")
app.include_router(deliverables_router, prefix="/api/v1")
app.include_router(review_items_router, prefix="/api/v1")
app.include_router(internal_tasks_router, prefix="/api/v1")
app.include_router(project_outputs_router, prefix="/api/v1")
app.include_router(debug_router, prefix="/api/v1")  # <--- ADD DEBUG ROUTER


@app.get("/api/v1/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "ok", "app_name": settings.APP_NAME, "environment": settings.ENV}