"""
Authentication configuration for ConvrseConnectBackend
Handles auth-service integration settings and JWT validation
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, validator


class AuthConfig(BaseSettings):
    """Authentication configuration settings"""
    
    # Auth Service Configuration
    auth_service_url: str = Field(
        default="http://localhost:8001",
        description="Base URL for the auth-service"
    )
    
    auth_service_token: str = Field(
        default="",
        description="Service-to-service authentication token"
    )
    
    auth_service_timeout: int = Field(
        default=30,
        description="Timeout for auth-service requests in seconds"
    )
    
    auth_service_max_retries: int = Field(
        default=3,
        description="Maximum retries for auth-service requests"
    )
    
    # JWT Configuration
    jwt_secret_key: str = Field(
        default="",
        description="Secret key for JWT token validation"
    )
    
    jwt_algorithm: str = Field(
        default="HS256",
        description="Algorithm for JWT token validation"
    )
    
    jwt_expiration_time: int = Field(
        default=3600,
        description="JWT token expiration time in seconds"
    )
    
    # Token Caching Configuration
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL for token caching"
    )
    
    token_cache_ttl: int = Field(
        default=300,
        description="Token cache TTL in seconds"
    )
    
    # Security Configuration
    auth_header_name: str = Field(
        default="Authorization",
        description="Header name for JWT token"
    )
    
    auth_header_prefix: str = Field(
        default="Bearer",
        description="Prefix for JWT token in header"
    )
    
    # Circuit Breaker Configuration
    circuit_breaker_failure_threshold: int = Field(
        default=5,
        description="Number of failures before opening circuit breaker"
    )
    
    circuit_breaker_recovery_timeout: int = Field(
        default=60,
        description="Circuit breaker recovery timeout in seconds"
    )
    
    # Rate Limiting
    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting"
    )
    
    rate_limit_requests_per_minute: int = Field(
        default=100,
        description="Requests per minute per user"
    )
    
    # Audit Logging
    audit_logging_enabled: bool = Field(
        default=True,
        description="Enable audit logging"
    )
    
    audit_log_sensitive_fields: bool = Field(
        default=False,
        description="Log sensitive fields in audit logs"
    )
    
    @validator('auth_service_url')
    def validate_auth_service_url(cls, v):
        if not v:
            raise ValueError("AUTH_SERVICE_URL must be set")
        if not v.startswith(('http://', 'https://')):
            raise ValueError("AUTH_SERVICE_URL must start with http:// or https://")
        return v.rstrip('/')
    
    @validator('jwt_secret_key')
    def validate_jwt_secret_key(cls, v):
        if not v:
            raise ValueError("JWT_SECRET_KEY must be set")
        if len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters long")
        return v
    
    @validator('auth_service_token')
    def validate_auth_service_token(cls, v):
        if not v:
            raise ValueError("AUTH_SERVICE_TOKEN must be set")
        return v
    
    class Config:
        env_prefix = "AUTH_"
        case_sensitive = False


class AuthConfigByEnvironment:
    """Environment-specific auth configurations"""
    
    @staticmethod
    def get_development_config() -> AuthConfig:
        """Development environment configuration"""
        return AuthConfig(
            auth_service_url="http://localhost:8001",
            auth_service_timeout=10,
            token_cache_ttl=60,  # Shorter cache for development
            rate_limit_requests_per_minute=1000,  # Higher limit for development
        )
    
    @staticmethod
    def get_staging_config() -> AuthConfig:
        """Staging environment configuration"""
        return AuthConfig(
            auth_service_timeout=20,
            token_cache_ttl=180,
            rate_limit_requests_per_minute=500,
        )
    
    @staticmethod
    def get_production_config() -> AuthConfig:
        """Production environment configuration"""
        return AuthConfig(
            auth_service_timeout=30,
            token_cache_ttl=300,
            rate_limit_requests_per_minute=100,
            circuit_breaker_failure_threshold=3,  # More sensitive in production
        )


# Global auth config instance
auth_config: Optional[AuthConfig] = None


def get_auth_config() -> AuthConfig:
    """Get the global auth configuration instance"""
    global auth_config
    
    if auth_config is None:
        env = os.getenv("ENV", "development").lower()
        
        if env == "development":
            auth_config = AuthConfigByEnvironment.get_development_config()
        elif env == "staging":
            auth_config = AuthConfigByEnvironment.get_staging_config()
        elif env == "production":
            auth_config = AuthConfigByEnvironment.get_production_config()
        else:
            # Default to development
            auth_config = AuthConfigByEnvironment.get_development_config()
    
    return auth_config


def reload_auth_config():
    """Reload auth configuration (useful for testing)"""
    global auth_config
    auth_config = None
    return get_auth_config()


# Auth endpoints configuration
class AuthEndpoints:
    """Auth service endpoint configurations"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
    
    @property
    def validate_token(self) -> str:
        return f"{self.base_url}/auth/validate"
    
    @property
    def get_user(self) -> str:
        return f"{self.base_url}/users/me"
    
    @property
    def get_user_businesses(self) -> str:
        return f"{self.base_url}/users/me/businesses"
    
    @property
    def check_permissions(self) -> str:
        return f"{self.base_url}/auth/permissions/check"
    
    @property
    def log_activity(self) -> str:
        return f"{self.base_url}/auth/activity"
    
    @property
    def health(self) -> str:
        return f"{self.base_url}/health"


def get_auth_endpoints() -> AuthEndpoints:
    """Get auth service endpoints"""
    config = get_auth_config()
    return AuthEndpoints(config.auth_service_url) 