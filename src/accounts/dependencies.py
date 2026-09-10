from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, status, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import selectinload

from src.accounts.models import User, UserGroupEnum
from src.accounts.security import decode_token
from src.database import get_db

# tokenUrl is documentation-only;
# actual login endpoint accepts JSON, not form data.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/accounts/login",
    auto_error=False
)


async def get_current_user(
        token: str | None = Depends(oauth2_scheme),
        db: AsyncSession = Depends(get_db)
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_error

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise credentials_error
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError) as exc:
        raise credentials_error from exc

    result = await db.execute(
        select(User).options(selectinload(User.group))
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_error
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not activated"
        )
    return user


def require_roles(*roles: UserGroupEnum):
    """Dependency factory: returns 403
     unless current user's group is one of `roles`."""

    async def _checker(user: User = Depends(get_current_user)) -> User:
        if user.group.name not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return user

    return _checker


require_moderator = require_roles(UserGroupEnum.MODERATOR, UserGroupEnum.ADMIN)
require_admin = require_roles(UserGroupEnum.ADMIN)
