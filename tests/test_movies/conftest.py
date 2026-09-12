import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.models import (
    ActivationToken,
    User,
    UserGroup,
    UserGroupEnum,
)
from src.movies.models import Certification, Director, Genre, Star


async def register_and_activate(
    client: AsyncClient,
    db_session: AsyncSession,
    email: str,
    password: str,
    group: UserGroupEnum = UserGroupEnum.USER,
) -> User:
    """Registers, activates, and (optionally) promotes a user.

    Uses `client` (its own request-scoped DB session, see conftest.py's
    `client` fixture) to hit the API, then `db_session` to peek at
    server-generated data (activation tokens, user groups). Because these
    are two *different* AsyncSession objects sharing one SQLite
    connection, `db_session`'s identity map can go stale when a row's
    primary key gets reused (e.g. after the API deletes a consumed
    ActivationToken and SQLite recycles that rowid for the next one) --
    `populate_existing=True` forces those two queries to overwrite any
    stale cached object for that PK with the fresh row, without expiring
    unrelated objects (e.g. fixture-created rows) that other tests still
    hold references to.
    """
    await client.post(
        "/api/v1/accounts/register",
        json={"email": email, "password": password},
    )

    result = await db_session.execute(
        select(User)
        .where(User.email == email)
        .execution_options(populate_existing=True)
    )
    user = result.scalar_one()
    token_result = await db_session.execute(
        select(ActivationToken)
        .where(ActivationToken.user_id == user.id)
        .execution_options(populate_existing=True)
    )
    token = token_result.scalar_one()
    await client.post(
        "/api/v1/accounts/activate",
        json={"email": email, "token": token.token},
    )

    if group != UserGroupEnum.USER:
        group_result = await db_session.execute(
            select(UserGroup).where(UserGroup.name == group)
        )
        user.group = group_result.scalar_one()
        await db_session.commit()
        await db_session.refresh(user)

    return user


async def auth_headers(
    client: AsyncClient, email: str, password: str
) -> dict[str, str]:
    login = await client.post(
        "/api/v1/accounts/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def create_user_headers(
    client: AsyncClient,
    db_session: AsyncSession,
    email: str,
    password: str,
    group: UserGroupEnum = UserGroupEnum.USER,
) -> tuple[User, dict[str, str]]:
    user = await register_and_activate(
        client, db_session, email, password, group
    )
    headers = await auth_headers(client, email, password)
    return user, headers


@pytest_asyncio.fixture
async def certification(db_session: AsyncSession) -> Certification:
    cert = Certification(name="PG-13")
    db_session.add(cert)
    await db_session.commit()
    await db_session.refresh(cert)
    return cert


@pytest_asyncio.fixture
async def genre(db_session: AsyncSession) -> Genre:
    g = Genre(name="Action")
    db_session.add(g)
    await db_session.commit()
    await db_session.refresh(g)
    return g


@pytest_asyncio.fixture
async def director(db_session: AsyncSession) -> Director:
    d = Director(name="Christopher Nolan")
    db_session.add(d)
    await db_session.commit()
    await db_session.refresh(d)
    return d


@pytest_asyncio.fixture
async def star(db_session: AsyncSession) -> Star:
    s = Star(name="Cillian Murphy")
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


def movie_payload(
    certification_id: int,
    *,
    name: str = "Oppenheimer",
    year: int = 2023,
    time: int = 180,
    imdb: float = 8.5,
    price: float = 9.99,
    genre_ids: list[int] | None = None,
    director_ids: list[int] | None = None,
    star_ids: list[int] | None = None,
) -> dict:
    return {
        "name": name,
        "year": year,
        "time": time,
        "imdb": imdb,
        "votes": 1000,
        "description": "A biographical thriller.",
        "price": price,
        "certification_id": certification_id,
        "genre_ids": genre_ids or [],
        "director_ids": director_ids or [],
        "star_ids": star_ids or [],
    }
