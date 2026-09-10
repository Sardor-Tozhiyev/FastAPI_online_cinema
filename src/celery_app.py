from celery import Celery
from celery.schedules import crontab

from src.config import settings

celery_app = Celery(
    "online_cinema",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["src.accounts.tasks"],
)

celery_app.conf.timezone = "UTC"

celery_app.conf.beat_schedule = {
    "cleanup-expired-activation-tokens": {
        "task": "accounts.cleanup_expired_activation_tokens",
        "schedule": crontab(minute=0),  # hourly
    },
    "cleanup-expired-password-reset-tokens": {
        "task": "accounts.cleanup_expired_password_reset_tokens",
        "schedule": crontab(minute=0),  # hourly
    },
}
