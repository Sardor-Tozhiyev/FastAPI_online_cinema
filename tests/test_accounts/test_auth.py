from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.models import ActivationToken, RefreshToken, User


async def _register_and_activate(client: AsyncClient, db_session: AsyncSession, email: str, password: str):
    await client.post("/api/v1/accounts/register", json={"email": email, "password": password})
    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    token_result = await db_session.execute(
        select(ActivationToken).where(ActivationToken.user_id == user.id)
    )
    token = token_result.scalar_one()
    await client.post("/api/v1/accounts/activate", json={"email": email, "token": token.token})
    return user


async def test_login_with_inactive_account_returns_403(client: AsyncClient, strong_password: str):
    await client.post(
        "/api/v1/accounts/register",
        json={"email": "inactive@example.com", "password": strong_password},
    )
    response = await client.post(
        "/api/v1/accounts/login",
        json={"email": "inactive@example.com", "password": strong_password},
    )
    assert response.status_code == 403


async def test_login_success_returns_token_pair(client: AsyncClient, db_session: AsyncSession, strong_password: str):
    await _register_and_activate(client, db_session, "login@example.com", strong_password)

    response = await client.post(
        "/api/v1/accounts/login", json={"email": "login@example.com", "password": strong_password}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data and "refresh_token" in data


async def test_login_wrong_password_returns_401(client: AsyncClient, db_session: AsyncSession, strong_password: str):
    await _register_and_activate(client, db_session, "wrongpass@example.com", strong_password)
    response = await client.post(
        "/api/v1/accounts/login", json={"email": "wrongpass@example.com", "password": "WrongPass1!"}
    )
    assert response.status_code == 401


async def test_me_requires_valid_access_token(client: AsyncClient, db_session: AsyncSession, strong_password: str):
    await _register_and_activate(client, db_session, "me@example.com", strong_password)
    login_response = await client.post(
        "/api/v1/accounts/login", json={"email": "me@example.com", "password": strong_password}
    )
    access_token = login_response.json()["access_token"]

    unauthenticated = await client.get("/api/v1/accounts/me")
    assert unauthenticated.status_code == 401

    authenticated = await client.get(
        "/api/v1/accounts/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert authenticated.status_code == 200
    assert authenticated.json()["email"] == "me@example.com"


async def test_refresh_token_issues_new_access_token(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    await _register_and_activate(client, db_session, "refresh@example.com", strong_password)
    login_response = await client.post(
        "/api/v1/accounts/login", json={"email": "refresh@example.com", "password": strong_password}
    )
    refresh_token = login_response.json()["refresh_token"]

    response = await client.post("/api/v1/accounts/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    assert "access_token" in response.json()


async def test_logout_revokes_refresh_token(client: AsyncClient, db_session: AsyncSession, strong_password: str):
    await _register_and_activate(client, db_session, "logout@example.com", strong_password)
    login_response = await client.post(
        "/api/v1/accounts/login", json={"email": "logout@example.com", "password": strong_password}
    )
    refresh_token = login_response.json()["refresh_token"]

    logout_response = await client.post("/api/v1/accounts/logout", json={"refresh_token": refresh_token})
    assert logout_response.status_code == 200

    result = await db_session.execute(select(RefreshToken).where(RefreshToken.token == refresh_token))
    assert result.scalar_one_or_none() is None

    reuse_response = await client.post("/api/v1/accounts/refresh", json={"refresh_token": refresh_token})
    assert reuse_response.status_code == 401
