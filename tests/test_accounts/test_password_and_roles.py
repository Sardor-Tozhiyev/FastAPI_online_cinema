from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.models import (
    ActivationToken,
    PasswordResetToken,
    User,
    UserGroup,
    UserGroupEnum
)


async def _register_and_activate(
        client: AsyncClient,
        db_session: AsyncSession,
        email: str,
        password: str
):
    await client.post(
        "/api/v1/accounts/register",
        json={
            "email": email,
            "password": password
        }
    )
    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    token_result = await db_session.execute(
        select(ActivationToken).where(ActivationToken.user_id == user.id)
    )
    token = token_result.scalar_one()
    await client.post(
        "/api/v1/accounts/activate",
        json={
            "email": email,
            "token": token.token
        }
    )
    return user


async def test_change_password_requires_correct_old_password(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    await _register_and_activate(
        client,
        db_session,
        "changepw@example.com",
        strong_password
    )
    login = await client.post(
        "/api/v1/accounts/login",
        json={
            "email": "changepw@example.com",
            "password": strong_password
        }
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    wrong = await client.post(
        "/api/v1/accounts/change-password",
        json={"old_password": "WrongOld1!", "password": "NewStrong1!"},
        headers=headers,
    )
    assert wrong.status_code == 400

    correct = await client.post(
        "/api/v1/accounts/change-password",
        json={"old_password": strong_password, "password": "NewStrong1!"},
        headers=headers,
    )
    assert correct.status_code == 200

    # old password no longer works, new one does
    old_login = await client.post(
        "/api/v1/accounts/login",
        json={
            "email": "changepw@example.com",
            "password": strong_password
        }
    )
    assert old_login.status_code == 401
    new_login = await client.post(
        "/api/v1/accounts/login",
        json={
            "email": "changepw@example.com",
            "password": "NewStrong1!"
        }
    )
    assert new_login.status_code == 200


async def test_password_reset_flow(
        client: AsyncClient,
        db_session: AsyncSession,
        strong_password: str
):
    await _register_and_activate(
        client, db_session,
        "forgot@example.com",
        strong_password
    )

    request_response = await client.post(
        "/api/v1/accounts/password-reset/request",
        json={"email": "forgot@example.com"}
    )
    assert request_response.status_code == 200

    result = await db_session.execute(
        select(User)
        .where(User.email == "forgot@example.com")
    )
    user = result.scalar_one()
    token_result = await db_session.execute(
        select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    )
    token = token_result.scalar_one()

    confirm_response = await client.post(
        "/api/v1/accounts/password-reset/confirm",
        json={
            "email": "forgot@example.com",
            "token": token.token, "password": "BrandNew1!"
        },
    )
    assert confirm_response.status_code == 200

    login_response = await client.post(
        "/api/v1/accounts/login",
        json={
            "email": "forgot@example.com",
            "password": "BrandNew1!"
        }
    )
    assert login_response.status_code == 200


async def test_password_reset_request_for_unknown_email_is_generic(
        client: AsyncClient
):
    response = await client.post(
        "/api/v1/accounts/password-reset/request",
        json={"email": "nope@example.com"}
    )
    assert response.status_code == 200


async def test_non_admin_cannot_change_user_group(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    target = await _register_and_activate(
        client,
        db_session,
        "target@example.com",
        strong_password
    )
    await _register_and_activate(
        client,
        db_session,
        "actor@example.com",
        strong_password,
    )

    login = await client.post(
        "/api/v1/accounts/login",
        json={
            "email": "actor@example.com",
            "password": strong_password,
        },
    )

    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.patch(
        f"/api/v1/accounts/users/{target.id}/group",
        json={"group": "ADMIN"},
        headers=headers,
    )
    assert response.status_code == 403


async def test_admin_can_change_user_group_and_activate(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    target = await _register_and_activate(
        client,
        db_session,
        "promote@example.com",
        strong_password
    )
    admin_user = await _register_and_activate(
        client,
        db_session,
        "admin@example.com",
        strong_password
    )

    admin_group_result = await db_session.execute(
        select(UserGroup).where(UserGroup.name == UserGroupEnum.ADMIN)
    )
    admin_group = admin_group_result.scalar_one()
    admin_user.group = admin_group
    await db_session.commit()

    login = await client.post(
        "/api/v1/accounts/login",
        json={
            "email": "admin@example.com",
            "password": strong_password
        }
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.patch(
        f"/api/v1/accounts/users/{target.id}/group",
        json={"group": "MODERATOR"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["group"] == "MODERATOR"
