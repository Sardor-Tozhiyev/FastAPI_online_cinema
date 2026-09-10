import enum
import uuid
from datetime import datetime, timezone, date, timedelta

from sqlalchemy import Enum, String, Boolean, DateTime, ForeignKey, Date, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config import settings
from src.database import Base


class UserGroupEnum(str, enum.Enum):
    USER = "USER"
    MODERATOR = "MODERATOR"
    ADMIN = "ADMIN"


class GenderEnum(str, enum.Enum):
    MAN = "MAN"
    WOMAN = "WOMAN"


class UserGroup(Base):
    __tablename__ = "user_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(
        Enum(UserGroupEnum), unique=True, nullable=False
    )

    users: Mapped[list["User"]] = relationship(back_populates="group")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    group_id: Mapped[int] = mapped_column(
        ForeignKey("user_groups.id"), nullable=False
    )

    group: Mapped["UserGroup"] = relationship(back_populates="users")
    profile: Mapped["UserProfile | None"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    activation_token: Mapped["ActivationToken | None"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    password_reset_token: Mapped["PasswordResetToken | None"] = mapped_column(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    refresh_token: Mapped["RefreshToken"] = mapped_column(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def has_role(self, *roles: UserGroupEnum) -> bool:
        return self.group.name in roles


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), unique=True, nullable=False
    )
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avatar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gender: Mapped[GenderEnum | None] = mapped_column(
        Enum(GenderEnum), nullable=True
    )
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    info: Mapped[str | None] = mapped_column(Text, nullable=True)


def _activation_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(
        hours=settings.ACTIVATION_TOKEN_EXPIRE_HOURS
    )


def _reset_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(
        hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS
    )


def _refresh_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )


class ActivationToken(Base):
    __tablename__ = "activation_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), unique=True, nullable=False
    )
    token: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        default=lambda: uuid.uuid4().hex,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_activation_expiry
    )
    user: Mapped["User"] = relationship(back_populates="activation_token")

    @property
    def is_expired(self) -> bool:
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > expires_at


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), unique=True, nullable=False
    )
    token: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        default=lambda: uuid.uuid4().hex,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_reset_expiry
    )
    user: Mapped["User"] = relationship(back_populates="password_reset_token")

    @property
    def is_expired(self) -> bool:
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > expires_at


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), unique=True, nullable=False
    )
    token: Mapped[str | None] = mapped_column(
        String(512),
        unique=True,
        nullable=False,
        default=lambda: uuid.uuid4().hex,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_refresh_expiry
    )
    user: Mapped["User"] = relationship(back_populates="refresh_token")

    @property
    def is_expired(self) -> bool:
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > expires_at
