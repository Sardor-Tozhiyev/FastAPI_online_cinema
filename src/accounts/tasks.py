import asyncio
from datetime import timezone, datetime

from sqlalchemy import delete
from src.celery_app import celery_app

from src.accounts.models import ActivationToken, PasswordResetToken
from src.database import AsyncSessionLocal


async def _delete_expired(model) -> int:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        result = await session.execute(delete(model)
                                       .where(model.expires_at < now))
        await session.commit()
        return result.rowcount or 0


@celery_app.task(name="accounts.cleanup_expired_activation_tokens")
def cleanup_expired_activation_tokens() -> int:
    """Periodic task (celery-beat, hourly):
     purges expired ActivationToken rows."""
    return asyncio.run(_delete_expired(ActivationToken))


@celery_app.task(name="accounts.cleanup_expired_password_reset_tokens")
def cleanup_expired_password_reset_tokens() -> int:
    """Periodic task (celery-beat, hourly):
     purges expired PasswordResetToken rows."""
    return asyncio.run(_delete_expired(PasswordResetToken))
