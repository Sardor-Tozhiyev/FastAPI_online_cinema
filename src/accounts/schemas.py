from datetime import datetime

from pydantic import BaseModel, field_validator, EmailStr, ConfigDict

from src.accounts.models import UserGroupEnum
from src.accounts.security import (
    validate_password_complexity,
    PasswordComplexityError
)


class PasswordFieldMixin(BaseModel):
    password: str

    @field_validator("password")
    @classmethod
    def check_password_complexity(cls, value: str) -> str:
        try:
            validate_password_complexity(value)
        except PasswordComplexityError as exc:
            raise ValueError("; ".join(exc.errors)) from exc
        return value


class UserRegistrationRequest(PasswordFieldMixin):
    email: EmailStr


class UserRegistrationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    is_active: bool


class MessageResponse(BaseModel):
    message: str


class ActivationRequest(BaseModel):
    email: EmailStr
    token: str


class ResendActivationRequest(BaseModel):
    email: EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LogoutRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(PasswordFieldMixin):
    old_password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(PasswordFieldMixin):
    email: EmailStr
    token: str


class UserGroupUpdateRequest(BaseModel):
    group: UserGroupEnum


class UserDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    is_active: bool
    group: UserGroupEnum
    created_at: datetime

    @field_validator("group", mode="before")
    @classmethod
    def extract_group_name(cls, value: object) -> object:
        # Allows passing the ORM `UserGroup` relationship object directly.
        return getattr(value, "name", value)
