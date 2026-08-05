"""
AI-QROS Backend Configuration
Phase 0: Project Foundation
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "AI-QROS"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-this-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # Database — Neon PostgreSQL
    DATABASE_URL: str = "postgresql+asyncpg://localhost/aiqros"
    DATABASE_URL_SYNC: str = "postgresql://localhost/aiqros"

    # Redis — Upstash
    REDIS_URL: str = "redis://localhost:6379"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # Upstox API
    UPSTOX_API_KEY: Optional[str] = None
    UPSTOX_API_SECRET: Optional[str] = None
    UPSTOX_REDIRECT_URI: str = "http://localhost:8000/auth/upstox/callback"
    UPSTOX_ACCESS_TOKEN: Optional[str] = None

    # OpenRouter API
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_FREE_MODEL: str = "meta-llama/llama-3.1-8b-instruct:free"

    # MLflow
    MLFLOW_TRACKING_URI: str = "http://localhost:5000"
    MLFLOW_EXPERIMENT_NAME: str = "aiqros-research"

    # CORS
    FRONTEND_URL: str = "http://localhost:3000"

    # Market Hours (IST)
    MARKET_OPEN_TIME: str = "09:15"
    MARKET_CLOSE_TIME: str = "15:30"
    MARKET_TIMEZONE: str = "Asia/Kolkata"

    # Angel One SmartAPI
    ANGEL_ONE_API_KEY: Optional[str] = None
    ANGEL_ONE_CLIENT_ID: Optional[str] = None
    ANGEL_ONE_PASSWORD: Optional[str] = None
    ANGEL_ONE_TOTP_SECRET: Optional[str] = None

    # Historical Data
    HISTORICAL_YEARS: int = 5

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
