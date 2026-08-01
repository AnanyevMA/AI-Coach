from typing import AsyncGenerator, Optional
import os
import secrets
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Adaptive Coach v7.0 API"
    API_V1_STR: str = "/api/v1"

    # Security & JWT
    SECRET_KEY: str = Field(
        default_factory=lambda: os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # 152-FZ Encryption Secret (AES-256-GCM requiring 32 bytes / 256 bits)
    # Default is generated if not present, but for production should be set in environment
    AES_SECRET_KEY: str = Field(
        default_factory=lambda: os.getenv("AES_SECRET_KEY", secrets.token_hex(32))
    )
    COMPLIANCE_152_FZ_ENABLED: bool = True

    # Database Settings
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "ai_sport_db"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: Optional[str] = None

    # Redis Settings
    REDIS_URL: str = "redis://localhost:6379/0"

    # Telegram Integration
    TELEGRAM_BOT_TOKEN: Optional[str] = None

    # Sentry & Observability Integration
    ENVIRONMENT: str = Field(default_factory=lambda: os.getenv("ENVIRONMENT", "production"))
    SENTRY_DSN: Optional[str] = Field(default_factory=lambda: os.getenv("SENTRY_DSN", None))
    SENTRY_TRACES_SAMPLE_RATE: float = Field(default_factory=lambda: float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "1.0")))
    SENTRY_PROFILES_SAMPLE_RATE: float = Field(default_factory=lambda: float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "1.0")))

    # Google Gemini AI Integration
    GEMINI_API_KEY: Optional[str] = Field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY"))
    )
    GOOGLE_API_KEY: Optional[str] = Field(
        default_factory=lambda: os.getenv("GOOGLE_API_KEY", os.getenv("GEMINI_API_KEY"))
    )
    GEMINI_PRIMARY_MODEL: str = "gemini-1.5-flash"
    GEMINI_FALLBACK_MODEL: str = "gemini-1.5-pro"

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # DDoS & Token Exhaustion Rate Limiting Settings
    RATE_LIMITING_ENABLED: bool = True
    AI_COACH_RATE_LIMIT_PLAN: int = 5       # Max 5 plan generations per minute per user/IP
    AI_COACH_RATE_LIMIT_ANALYZE: int = 10   # Max 10 activity analyses per minute per user/IP
    TELEMETRY_RATE_LIMIT_RECORD: int = 60   # Max 60 telemetry records per minute per user/IP
    TELEMETRY_RATE_LIMIT_HRV: int = 15      # Max 15 HRV logs per minute per user/IP
    TELEMETRY_RATE_LIMIT_UPLOAD_FIT: int = 10 # Max 10 FIT uploads per minute per user/IP

    def get_masked_gemini_key(self) -> str:
        key = self.GEMINI_API_KEY or self.GOOGLE_API_KEY
        if not key:
            return "NOT_SET"
        if len(key) <= 8:
            return "****"
        return f"{key[:4]}...{key[-4:]}"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


settings = Settings()
