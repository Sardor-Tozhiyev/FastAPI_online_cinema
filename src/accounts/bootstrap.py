from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.models import UserGroup, UserGroupEnum


async def seed_user_groups(db: AsyncSession) -> None:
    """Ensures the USER / MODERATOR / ADMIN groups exist. Idempotent."""
    result = await db.execute(select(UserGroup.name))
    existing = {row for row in result.scalars().all()}
    for group in UserGroupEnum:
        if group not in existing:
            db.add(UserGroup(name=group))
    await db.commit()
