from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.models import UserGroupEnum
from src.movies.models import Certification
from tests.test_movies.conftest import create_user_headers, movie_payload


async def _create_movie(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification_id: int,
    tag: str,
    **overrides,
) -> int:
    _, mod_headers = await create_user_headers(
        client,
        db_session,
        f"mod-{tag}@example.com",
        strong_password,
        UserGroupEnum.MODERATOR,
    )
    response = await client.post(
        "/api/v1/movies",
        json=movie_payload(certification_id, name=f"Movie {tag}", **overrides),
        headers=mod_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --- Reactions -----------------------------------------------------------------------


async def test_like_and_dislike_counts_reflected_in_detail(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "react"
    )
    _, alice = await create_user_headers(
        client, db_session, "alice-react@example.com", strong_password
    )
    _, bob = await create_user_headers(
        client, db_session, "bob-react@example.com", strong_password
    )

    like = await client.put(
        f"/api/v1/movies/{movie_id}/reaction",
        json={"is_like": True},
        headers=alice,
    )
    assert like.status_code == 200
    dislike = await client.put(
        f"/api/v1/movies/{movie_id}/reaction",
        json={"is_like": False},
        headers=bob,
    )
    assert dislike.status_code == 200

    detail = await client.get(f"/api/v1/movies/{movie_id}")
    assert detail.json()["likes_count"] == 1
    assert detail.json()["dislikes_count"] == 1


async def test_reaction_upsert_switches_like_to_dislike(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "switch"
    )
    _, headers = await create_user_headers(
        client, db_session, "switcher@example.com", strong_password
    )

    await client.put(
        f"/api/v1/movies/{movie_id}/reaction",
        json={"is_like": True},
        headers=headers,
    )
    await client.put(
        f"/api/v1/movies/{movie_id}/reaction",
        json={"is_like": False},
        headers=headers,
    )

    detail = await client.get(f"/api/v1/movies/{movie_id}")
    assert detail.json()["likes_count"] == 0
    assert detail.json()["dislikes_count"] == 1


async def test_remove_reaction(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "remove"
    )
    _, headers = await create_user_headers(
        client, db_session, "remover@example.com", strong_password
    )

    await client.put(
        f"/api/v1/movies/{movie_id}/reaction",
        json={"is_like": True},
        headers=headers,
    )
    removed = await client.delete(
        f"/api/v1/movies/{movie_id}/reaction", headers=headers
    )
    assert removed.status_code == 200

    detail = await client.get(f"/api/v1/movies/{movie_id}")
    assert detail.json()["likes_count"] == 0


async def test_reaction_requires_authentication(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "auth"
    )
    response = await client.put(
        f"/api/v1/movies/{movie_id}/reaction", json={"is_like": True}
    )
    assert response.status_code == 401


# --- Ratings ------------------------------------------------------------------------


async def test_rate_movie_computes_average(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "rate"
    )
    _, alice = await create_user_headers(
        client, db_session, "alice-rate@example.com", strong_password
    )
    _, bob = await create_user_headers(
        client, db_session, "bob-rate@example.com", strong_password
    )

    first = await client.put(
        f"/api/v1/movies/{movie_id}/rating",
        json={"rating": 8},
        headers=alice,
    )
    assert first.status_code == 200
    assert first.json()["average_rating"] == 8.0

    second = await client.put(
        f"/api/v1/movies/{movie_id}/rating",
        json={"rating": 4},
        headers=bob,
    )
    assert second.json()["average_rating"] == 6.0
    assert second.json()["ratings_count"] == 2


async def test_rate_movie_upsert_replaces_previous_rating(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "reRate"
    )
    _, headers = await create_user_headers(
        client, db_session, "rerater@example.com", strong_password
    )

    await client.put(
        f"/api/v1/movies/{movie_id}/rating",
        json={"rating": 10},
        headers=headers,
    )
    response = await client.put(
        f"/api/v1/movies/{movie_id}/rating",
        json={"rating": 2},
        headers=headers,
    )
    assert response.json()["average_rating"] == 2.0
    assert response.json()["ratings_count"] == 1


async def test_rate_movie_rejects_out_of_range_values(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "badrate"
    )
    _, headers = await create_user_headers(
        client, db_session, "badrater@example.com", strong_password
    )

    too_high = await client.put(
        f"/api/v1/movies/{movie_id}/rating",
        json={"rating": 11},
        headers=headers,
    )
    assert too_high.status_code == 422

    too_low = await client.put(
        f"/api/v1/movies/{movie_id}/rating",
        json={"rating": 0},
        headers=headers,
    )
    assert too_low.status_code == 422


# --- Favorites -----------------------------------------------------------------------


async def test_add_list_and_remove_favorite(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "fav"
    )
    other_movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "notfav"
    )
    _, headers = await create_user_headers(
        client, db_session, "favoriter@example.com", strong_password
    )

    add = await client.post(
        f"/api/v1/movies/{movie_id}/favorite", headers=headers
    )
    assert add.status_code == 200

    listing = await client.get("/api/v1/movies/favorites", headers=headers)
    assert listing.status_code == 200
    ids = {m["id"] for m in listing.json()["items"]}
    assert ids == {movie_id}
    assert other_movie_id not in ids

    remove = await client.delete(
        f"/api/v1/movies/{movie_id}/favorite", headers=headers
    )
    assert remove.status_code == 200

    empty_listing = await client.get(
        "/api/v1/movies/favorites", headers=headers
    )
    assert empty_listing.json()["items"] == []
    assert empty_listing.json()["total"] == 0


async def test_adding_same_favorite_twice_is_idempotent(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "idempotent"
    )
    _, headers = await create_user_headers(
        client, db_session, "idempotent-fav@example.com", strong_password
    )

    first = await client.post(
        f"/api/v1/movies/{movie_id}/favorite", headers=headers
    )
    second = await client.post(
        f"/api/v1/movies/{movie_id}/favorite", headers=headers
    )
    assert first.status_code == 200
    assert second.status_code == 200

    listing = await client.get("/api/v1/movies/favorites", headers=headers)
    assert listing.json()["total"] == 1


async def test_favorites_require_authentication(client: AsyncClient):
    response = await client.get("/api/v1/movies/favorites")
    assert response.status_code == 401


async def test_favorites_are_scoped_per_user(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "scoped"
    )
    _, alice = await create_user_headers(
        client, db_session, "alice-fav@example.com", strong_password
    )
    _, bob = await create_user_headers(
        client, db_session, "bob-fav@example.com", strong_password
    )

    await client.post(f"/api/v1/movies/{movie_id}/favorite", headers=alice)

    alice_list = await client.get("/api/v1/movies/favorites", headers=alice)
    bob_list = await client.get("/api/v1/movies/favorites", headers=bob)

    assert alice_list.json()["total"] == 1
    assert bob_list.json()["total"] == 0
