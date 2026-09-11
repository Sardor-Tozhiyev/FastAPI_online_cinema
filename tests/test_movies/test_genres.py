from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.models import UserGroupEnum
from src.movies.models import Certification
from tests.test_movies.conftest import create_user_headers, movie_payload


async def test_list_genres_empty(client: AsyncClient):
    response = await client.get("/api/v1/movies/genres")
    assert response.status_code == 200
    assert response.json() == []


async def test_moderator_can_create_genre(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    _, headers = await create_user_headers(
        client,
        db_session,
        "mod-genre@example.com",
        strong_password,
        UserGroupEnum.MODERATOR,
    )

    response = await client.post(
        "/api/v1/movies/genres", json={"name": "Sci-Fi"}, headers=headers
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Sci-Fi"

    listing = await client.get("/api/v1/movies/genres")
    assert listing.json() == [
        {"id": response.json()["id"], "name": "Sci-Fi", "movie_count": 0}
    ]


async def test_regular_user_cannot_create_genre(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    _, headers = await create_user_headers(
        client, db_session, "plain-genre@example.com", strong_password
    )
    response = await client.post(
        "/api/v1/movies/genres", json={"name": "Horror"}, headers=headers
    )
    assert response.status_code == 403


async def test_duplicate_genre_name_returns_409(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    _, headers = await create_user_headers(
        client,
        db_session,
        "mod-dup-genre@example.com",
        strong_password,
        UserGroupEnum.MODERATOR,
    )
    payload = {"name": "Drama"}
    first = await client.post(
        "/api/v1/movies/genres", json=payload, headers=headers
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/movies/genres", json=payload, headers=headers
    )
    assert second.status_code == 409


async def test_moderator_can_rename_and_delete_genre(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    _, headers = await create_user_headers(
        client,
        db_session,
        "mod-rename-genre@example.com",
        strong_password,
        UserGroupEnum.MODERATOR,
    )
    created = await client.post(
        "/api/v1/movies/genres", json={"name": "Old Name"}, headers=headers
    )
    genre_id = created.json()["id"]

    renamed = await client.put(
        f"/api/v1/movies/genres/{genre_id}",
        json={"name": "New Name"},
        headers=headers,
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "New Name"

    deleted = await client.delete(
        f"/api/v1/movies/genres/{genre_id}", headers=headers
    )
    assert deleted.status_code == 200

    missing = await client.put(
        f"/api/v1/movies/genres/{genre_id}",
        json={"name": "Whatever"},
        headers=headers,
    )
    assert missing.status_code == 404


async def test_movies_by_genre_returns_only_matching_movies(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    _, headers = await create_user_headers(
        client,
        db_session,
        "mod-genre-movies@example.com",
        strong_password,
        UserGroupEnum.MODERATOR,
    )
    cert = Certification(name="R")
    db_session.add(cert)
    await db_session.commit()
    await db_session.refresh(cert)

    action = await client.post(
        "/api/v1/movies/genres", json={"name": "Action-2"}, headers=headers
    )
    comedy = await client.post(
        "/api/v1/movies/genres", json={"name": "Comedy-2"}, headers=headers
    )
    action_id = action.json()["id"]
    comedy_id = comedy.json()["id"]

    await client.post(
        "/api/v1/movies",
        json=movie_payload(
            cert.id, name="Action Movie", genre_ids=[action_id]
        ),
        headers=headers,
    )
    await client.post(
        "/api/v1/movies",
        json=movie_payload(
            cert.id, name="Comedy Movie", year=2022, genre_ids=[comedy_id]
        ),
        headers=headers,
    )

    response = await client.get(f"/api/v1/movies/genres/{action_id}/movies")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Action Movie"


async def test_movies_by_unknown_genre_returns_404(client: AsyncClient):
    response = await client.get("/api/v1/movies/genres/999/movies")
    assert response.status_code == 404
