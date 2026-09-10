import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.models import ActivationToken, User


async def test_register_creates_inactive_user(client: AsyncClient, strong_password: str):
    response = await client.post(
        "/api/v1/accounts/register",
        json={"email": "user@example.com", "password": strong_password},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "user@example.com"
    assert data["is_active"] is False


async def test_register_duplicate_email_returns_409(client: AsyncClient, strong_password: str):
    payload = {"email": "dup@example.com", "password": strong_password}
    first = await client.post("/api/v1/accounts/register", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/v1/accounts/register", json=payload)
    assert second.status_code == 409


@pytest.mark.parametrize(
    "password",
    ["short1!", "nouppercase1!", "NOLOWERCASE1!", "NoDigitsHere!", "NoSpecialChar123"],
)
async def test_register_rejects_weak_passwords(client: AsyncClient, password: str):
    response = await client.post(
        "/api/v1/accounts/register", json={"email": "weak@example.com", "password": password}
    )
    assert response.status_code == 422


async def test_activate_account_success(client: AsyncClient, db_session: AsyncSession, strong_password: str):
    await client.post(
        "/api/v1/accounts/register",
        json={"email": "activate@example.com", "password": strong_password},
    )
    result = await db_session.execute(select(User).where(User.email == "activate@example.com"))
    user = result.scalar_one()
    token_result = await db_session.execute(
        select(ActivationToken).where(ActivationToken.user_id == user.id)
    )
    token = token_result.scalar_one()

    response = await client.post(
        "/api/v1/accounts/activate",
        json={"email": "activate@example.com", "token": token.token},
    )
    assert response.status_code == 200

    await db_session.refresh(user)
    assert user.is_active is True


async def test_activate_account_invalid_token_returns_400(client: AsyncClient, strong_password: str):
    await client.post(
        "/api/v1/accounts/register",
        json={"email": "badtoken@example.com", "password": strong_password},
    )
    response = await client.post(
        "/api/v1/accounts/activate",
        json={"email": "badtoken@example.com", "token": "not-the-real-token"},
    )
    assert response.status_code == 400


async def test_resend_activation_issues_new_token(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    await client.post(
        "/api/v1/accounts/register",
        json={"email": "resend@example.com", "password": strong_password},
    )
    result = await db_session.execute(select(User).where(User.email == "resend@example.com"))
    user = result.scalar_one()
    old_token_result = await db_session.execute(
        select(ActivationToken).where(ActivationToken.user_id == user.id)
    )
    old_token_value = old_token_result.scalar_one().token

    response = await client.post(
        "/api/v1/accounts/resend-activation", json={"email": "resend@example.com"}
    )
    assert response.status_code == 200

    new_token_result = await db_session.execute(
        select(ActivationToken).where(ActivationToken.user_id == user.id)
    )
    new_token = new_token_result.scalar_one()
    assert new_token.token != old_token_value


async def test_resend_activation_unknown_email_is_generic(client: AsyncClient):
    response = await client.post(
        "/api/v1/accounts/resend-activation", json={"email": "ghost@example.com"}
    )
    assert response.status_code == 200
