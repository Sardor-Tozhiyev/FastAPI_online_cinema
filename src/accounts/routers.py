from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.accounts.dependencies import get_current_user, require_admin
from src.accounts.models import (
    ActivationToken,
    PasswordResetToken,
    RefreshToken,
    User,
    UserGroup,
    UserGroupEnum,
)
from src.accounts.notifications import (
    send_activation_email,
    send_password_reset_email,
)
from src.accounts.schemas import (
    AccessTokenResponse,
    ActivationRequest,
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RefreshTokenRequest,
    ResendActivationRequest,
    TokenPairResponse,
    UserDetailResponse,
    UserGroupUpdateRequest,
    UserRegistrationRequest,
    UserRegistrationResponse,
)
from src.accounts.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from src.database import get_db

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


async def _get_user_by_email(
    db: AsyncSession,
    email: str,
) -> User | None:
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.group),
            selectinload(User.activation_token),
            selectinload(User.password_reset_token),
        )
        .where(User.email == email)
    )
    return result.scalar_one_or_none()


@router.post(
    "/register",
    response_model=UserRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description=(
        "Creates a new inactive user"
        " in the default `USER` group and issues an "
        "`ActivationToken` valid for 24 hours."
        " An activation email containing a "
        "link with the token is sent to the provided address."
        " Fails with 409 if "
        "the email is already registered."
    ),
)
async def register(
    payload: UserRegistrationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> User:
    existing = await _get_user_by_email(db, payload.email)
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )

    group_result = await db.execute(
        select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
    )
    user_group = group_result.scalar_one_or_none()

    if user_group is None:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Default user group is not configured.",
        )

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        group=user_group,
    )
    db.add(user)
    await db.flush()

    token = ActivationToken(user_id=user.id)
    db.add(token)
    await db.commit()
    await db.refresh(user)

    background_tasks.add_task(
        send_activation_email,
        user.email,
        token.token,
    )
    return user


@router.post(
    "/activate",
    response_model=MessageResponse,
    summary="Activate a user account",
    description=(
        "Activates an account given the `email`"
        " and the `token` sent by email. "
        "The token must exist and not be expired (24h TTL from issuance); "
        "otherwise a 400 is returned. On success the token is deleted and the "
        "account's `is_active` flag becomes `true`."
    ),
)
async def activate_account(
    payload: ActivationRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _get_user_by_email(db, payload.email)

    if (
        user is None
        or user.activation_token is None
        or user.activation_token.token != payload.token
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Invalid activation token.",
        )

    if user.activation_token.is_expired:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                "Activation token has expired. Request a new one via "
                "/resend-activation."
            ),
        )

    user.is_active = True
    await db.delete(user.activation_token)
    await db.commit()

    return {"message": "Account activated successfully."}


@router.post(
    "/resend-activation",
    response_model=MessageResponse,
    summary="Resend the activation email",
    description=(
        "Issues a brand-new activation token "
        "(replacing any previous one) "
        "valid for another 24 hours and re-sends the activation email."
        " Returns 200 even if the account is already active,"
        " to avoid leaking account "
        "existence/state to callers,"
        " except that already-active accounts are "
        "told so explicitly."
    ),
)
async def resend_activation(
    payload: ResendActivationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _get_user_by_email(db, payload.email)

    if user is None:
        # Do not reveal whether the email is registered.
        return {
            "message": (
                "If the account exists and is inactive, a new activation "
                "email was sent."
            )
        }

    if user.is_active:
        return {"message": "This account is already activated."}

    if user.activation_token is not None:
        await db.delete(user.activation_token)
        await db.flush()

    token = ActivationToken(user_id=user.id)
    db.add(token)
    await db.commit()

    background_tasks.add_task(
        send_activation_email,
        user.email,
        token.token,
    )

    return {
        "message": (
            "If the account exists and is inactive, a new activation "
            "email was sent."
        )
    }


@router.post(
    "/login",
    response_model=TokenPairResponse,
    summary="Log in and obtain a JWT access/refresh token pair",
    description=(
        "Validates `email`/`password` for an **active** user and returns a "
        "short-lived `access_token` plus a longer-lived `refresh_token`. The "
        "refresh token is persisted server-side so it can be revoked on "
        "logout."
    ),
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _get_user_by_email(db, payload.email)

    if user is None or not verify_password(
        payload.password,
        user.hashed_password,
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Account is not activated.",
        )

    access_token = create_access_token(user.id)
    refresh_token_value = create_refresh_token(user.id)

    result = await db.execute(
        select(RefreshToken).where(RefreshToken.user_id == user.id)
    )
    stored_token = result.scalar_one_or_none()

    if stored_token is not None:
        stored_token.token = refresh_token_value
    else:
        db.add(
            RefreshToken(
                user_id=user.id,
                token=refresh_token_value,
            )
        )

    await db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token_value,
    }


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    summary="Exchange a refresh token for a new access token",
    description=(
        "Accepts a previously issued, non-revoked `refresh_token` and, if it "
        "is still valid, returns a brand-new short-lived `access_token`. "
        "Returns 401 if the refresh token is unknown, expired, or was already "
        "revoked via /logout."
    ),
)
async def refresh_access_token(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == payload.refresh_token)
    )
    stored_token = result.scalar_one_or_none()

    if stored_token is None or stored_token.is_expired:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

    try:
        decoded = decode_token(payload.refresh_token)

        if decoded.get("type") != "refresh":
            raise ValueError("wrong token type")

    except Exception as exc:  # noqa: BLE001
        # Normalize any decode failure to 401.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        ) from exc

    return {
        "access_token": create_access_token(stored_token.user_id),
    }


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Log out and revoke a refresh token",
    description=(
        "Deletes the given `refresh_token` server-side so it can no longer "
        "be used to mint new access tokens, effectively ending the session "
        "on that device."
    ),
)
async def logout(
    payload: LogoutRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == payload.refresh_token)
    )
    stored_token = result.scalar_one_or_none()

    if stored_token is not None:
        await db.delete(stored_token)
        await db.commit()

    return {"message": "Logged out successfully."}


@router.post(
    "/change-password",
    response_model=MessageResponse,
    summary="Change password (requires knowing the current password)",
    description=(
        "For an authenticated user: verifies `old_password` against the "
        "stored hash, then validates `password` against the complexity "
        "policy (min 8 chars, upper/lower/digit/special) and updates the "
        "stored hash. Requires a valid `access_token`."
    ),
)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not verify_password(
        payload.old_password,
        current_user.hashed_password,
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Old password is incorrect.",
        )

    current_user.hashed_password = hash_password(payload.password)
    db.add(current_user)
    await db.commit()

    return {"message": "Password changed successfully."}


@router.post(
    "/password-reset/request",
    response_model=MessageResponse,
    summary="Request a password reset link",
    description=(
        "For a registered, active `email`, issues a `PasswordResetToken` and "
        "emails a reset link. Always returns a generic 200 message regardless "
        "of whether the email exists, to avoid account enumeration."
    ),
)
async def request_password_reset(
    payload: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    generic_message = {
        "message": "If the account exists, a password reset email was sent."
    }

    user = await _get_user_by_email(db, payload.email)

    if user is None or not user.is_active:
        return generic_message

    if user.password_reset_token is not None:
        await db.delete(user.password_reset_token)
        await db.flush()

    token = PasswordResetToken(user_id=user.id)
    db.add(token)
    await db.commit()

    if token.token is None:
        raise ValueError("Password reset token was not generated")

    background_tasks.add_task(
        send_password_reset_email,
        user.email,
        token.token,
    )

    return generic_message


@router.post(
    "/password-reset/confirm",
    response_model=MessageResponse,
    summary="Set a new password using a reset token",
    description=(
        "Given `email`, the `token` received by email, and a new `password` "
        "(validated against the complexity policy), sets the new password "
        "**without** requiring the old one. The token is single-use and "
        "deleted on success; expired/invalid tokens return 400."
    ),
)
async def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _get_user_by_email(db, payload.email)

    if (
        user is None
        or user.password_reset_token is None
        or user.password_reset_token.token != payload.token
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Invalid password reset token.",
        )

    if user.password_reset_token.is_expired:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Password reset token has expired.",
        )

    user.hashed_password = hash_password(payload.password)
    await db.delete(user.password_reset_token)
    await db.commit()

    return {"message": "Password has been reset successfully."}


@router.get(
    "/me",
    response_model=UserDetailResponse,
    summary="Get the current authenticated user's profile",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user


# --- Admin-only user management ---------------------------------------------


@router.patch(
    "/users/{user_id}/group",
    response_model=UserDetailResponse,
    summary="[Admin] Change a user's group",
    description=(
        "Reassigns the target user to `USER`, `MODERATOR`, or `ADMIN`. "
        "Admin-only."
    ),
)
async def change_user_group(
    user_id: int,
    payload: UserGroupUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> User:
    result = await db.execute(
        select(User)
        .options(selectinload(User.group))
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    group_result = await db.execute(
        select(UserGroup).where(UserGroup.name == payload.group)
    )
    group = group_result.scalar_one_or_none()

    if group is None:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Target group not configured.",
        )

    user.group = group
    await db.commit()
    await db.refresh(user, attribute_names=["group"])

    return user


@router.post(
    "/users/{user_id}/activate",
    response_model=MessageResponse,
    summary="[Admin] Manually activate a user account",
    description=(
        "Marks the target user as active and removes any pending activation "
        "token. Admin-only."
    ),
)
async def manually_activate_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    result = await db.execute(
        select(User)
        .options(selectinload(User.activation_token))
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    user.is_active = True

    if user.activation_token is not None:
        await db.delete(user.activation_token)

    await db.commit()

    return {"message": "User activated successfully."}
