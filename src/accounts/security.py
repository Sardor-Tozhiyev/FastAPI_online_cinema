import re
from datetime import timedelta, timezone, datetime
from typing import Literal, Any

from jose import jwt, JWTError
from passlib.context import CryptContext

from src.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

PASSWORD_RULES = (
    (re.compile(r".{8,}"), "Password must be at least 8 characters long."),
    (
        re.compile(r"[A-Z]"),
        "Password must contain at least one uppercase letter.",
    ),
    (
        re.compile(r"[a-z]"),
        "Password must contain at least one lowercase letter.",
    ),
    (re.compile(r"\d"), "Password must be at least on digit."),
    (
        re.compile(r"[^\w\s]"),
        "Password must contain at least one special character.",
    ),
)


class PasswordComplexityError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(";".join(errors))


def validate_password_complexity(password: str) -> None:
    errors = [
        message
        for pattern, message in PASSWORD_RULES
        if not pattern.match(password)
    ]
    if errors:
        raise PasswordComplexityError(errors)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def _create_token(
    subject: str,
    expires_delta: timedelta,
    token_type: Literal["access", "refresh"],
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def create_access_token(user_id: int) -> str:
    return _create_token(
        str(user_id),
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "access",
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        str(user_id),
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "refresh",
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises jose.JWTError if invalid/expired."""
    return jwt.decode(
        token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )


__all__ = [
    "hash_password",
    "verify_password",
    "validate_password_complexity",
    "PasswordComplexityError",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "JWTError",
]
