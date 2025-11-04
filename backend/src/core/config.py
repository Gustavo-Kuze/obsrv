"""
Application configuration using Pydantic Settings.
"""

from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    # Application
    ENVIRONMENT: str = Field(default="development", description="Environment name")
    DEBUG: bool = Field(default=False, description="Debug mode")
    SECRET_KEY: str = Field(..., description="Secret key for signing tokens")

    # Server
    HOST: str = Field(default="0.0.0.0", description="Server host")
    PORT: int = Field(default=8000, description="Server port")

    # Database (Neon PostgreSQL)
    DATABASE_URL: str = Field(..., description="PostgreSQL connection string")

    # Inngest
    INNGEST_EVENT_KEY: str = Field(..., description="Inngest event key")
    INNGEST_SIGNING_KEY: str = Field(..., description="Inngest signing key")
    INNGEST_APP_ID: str = Field(default="obsrv-api", description="Inngest app ID")

    # Security
    API_KEY_LENGTH: int = Field(default=32, description="API key length in bytes")
    BCRYPT_ROUNDS: int = Field(default=12, description="Bcrypt work factor")

    # CORS
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:8000",
        description="Allowed CORS origins (comma-separated)",
    )

    # Crawling
    DEFAULT_CRAWL_TIMEOUT: int = Field(default=30, description="Default crawl timeout (seconds)")
    MAX_CONCURRENT_CRAWLS: int = Field(default=5, description="Max concurrent crawls")
    CRAWL_RATE_LIMIT_PER_DOMAIN: int = Field(
        default=10, description="Max requests per domain per minute"
    )
    CRAWL_RETRY_ATTEMPTS: int = Field(default=3, description="Max retry attempts for failed crawls")
    CRAWL_RETRY_BACKOFF_BASE: int = Field(
        default=60, description="Base backoff time for retries (seconds)"
    )

    # Webhooks
    WEBHOOK_TIMEOUT: int = Field(default=10, description="Webhook delivery timeout (seconds)")
    WEBHOOK_MAX_RETRIES: int = Field(default=3, description="Max webhook delivery retries")
    WEBHOOK_RETRY_BACKOFF_BASE: int = Field(
        default=300, description="Base backoff time for webhook retries (seconds)"
    )
    WEBHOOK_SIGNATURE_TOLERANCE_SECONDS: int = Field(
        default=300, description="Webhook signature timestamp tolerance (seconds)"
    )

    # Data Retention
    DEFAULT_RETENTION_DAYS: int = Field(default=90, description="Default data retention (days)")
    MAX_RETENTION_DAYS: int = Field(default=365, description="Maximum data retention (days)")

    # Pagination
    DEFAULT_PAGE_SIZE: int = Field(default=50, description="Default page size")
    MAX_PAGE_SIZE: int = Field(default=500, description="Maximum page size")

    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_FORMAT: str = Field(default="json", description="Log format (json or text)")

    # Rate Limiting
    RATE_LIMIT_PER_API_KEY_PER_HOUR: int = Field(
        default=1000, description="Rate limit per API key per hour"
    )
    RATE_LIMIT_PER_DOMAIN_PER_MINUTE: int = Field(
        default=10, description="Rate limit per domain per minute"
    )

    # Health Check
    HEALTH_CHECK_TIMEOUT: int = Field(default=5, description="Health check timeout (seconds)")

    @field_validator("CORS_ORIGINS")
    @classmethod
    def parse_cors_origins(cls, v: str) -> List[str]:
        """Parse comma-separated CORS origins into list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        return v_upper

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENVIRONMENT.lower() == "development"


# Global settings instance
settings = Settings()
