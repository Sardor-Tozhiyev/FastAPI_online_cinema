from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application configuration,
     populated from environment
      variables / .env"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # App
    APP_NAME: str = "Online Cinema"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = ("postgresql+asyncpg://"
                         "postgres:postgres@db:5432/online_cinema")

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-prod"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ACTIVATION_TOKEN_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS: int = 24

    # Redis / Celery
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"

    # Mail (SMTP) — used by the notifications service
    MAIL_FROM: str = "no-reply@online-cinema.local"
    MAIL_SERVER: str = "mailhog"
    MAIL_PORT: int = 1025
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""

    # MinIO / S3 (avatars, etc.)
    S3_ENDPOINT_URL: str = "http://minio:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET_NAME: str = "online-cinema"

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Frontend base URL, used to build activation / reset links
    FRONTEND_URL: str = "http://localhost:3000"


settings = Settings()
