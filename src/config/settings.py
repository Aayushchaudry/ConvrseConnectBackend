# src/config/settings.py (UPDATED)

from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from typing import Optional
class Settings(BaseSettings):
    # Base application settings
    APP_NAME: str = "3D Project Portal Backend"
    ENV: str = "development" # development, staging, production
    DEBUG: bool = True

    # Database settings
    DATABASE_URL: str = "postgresql+asyncpg://ConvrseConnect:ConvrseConnect123@localhost:5433/project_db"

    # Event Bus general settings
    # Options: "kafka", "sqs_mock", "sqs" (when implemented)
    ACTIVE_EVENT_BUS: str = "kafka" # <---- NEW SETTING!

    # Kafka settings
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_CLIENT_ID: str = "project-portal-backend"
    KAFKA_CONSUMER_GROUP_ID: str = "project-portal-group"
    KAFKA_RETRIES: int = 5
    KAFKA_LINGER_MS: int = 10

    # AWS SQS settings (if you plan to use SQS)
    AWS_REGION: str = "ap-south-1" # e.g., your AWS region
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    # Add other SQS specific settings if needed, e.g., queue URLs mapping

    # SAGA specific settings
    SAGA_STATE_DB_TABLE: str = "saga_state"
    SAGA_RETRY_ATTEMPTS: int = 5
    SAGA_RETRY_DELAY_SECONDS: int = 5

    model_config = SettingsConfigDict(env_file=Path(__file__).parent.parent.parent / '.env', extra='ignore')

settings = Settings()