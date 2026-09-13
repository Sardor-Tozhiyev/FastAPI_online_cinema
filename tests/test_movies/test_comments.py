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
        json=movie_payload(certification_id, name=f"Movie {tag}"),
        headers=mod_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --- Creating / listing comments -----------------------------------------------------


async def test_create_top_level_comment(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "comment"
    )
    _, headers = await create_user_headers(
        client, db_session, "commenter@example.com", strong_password
    )

    response = await client.post(
        f"/api/v1/movies/{movie_id}/comments",
        json={"text": "Great movie!"},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["text"] == "Great movie!"
    assert body["parent_id"] is None
    assert body["replies"] == []
    assert body["likes_count"] == 0


async def test_comments_require_authentication(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "authreq"
    )
    response = await client.post(
        f"/api/v1/movies/{movie_id}/comments", json={"text": "Hi"}
    )
    assert response.status_code == 401


async def test_comments_on_unknown_movie_return_404(client: AsyncClient):
    listing = await client.get("/api/v1/movies/999999/comments")
    assert listing.status_code == 404


async def test_reply_nests_under_parent_comment(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "reply"
    )
    _, alice = await create_user_headers(
        client, db_session, "alice-reply@example.com", strong_password
    )
    _, bob = await create_user_headers(
        client, db_session, "bob-reply@example.com", strong_password
    )

    parent = await client.post(
        f"/api/v1/movies/{movie_id}/comments",
        json={"text": "What did everyone think?"},
        headers=alice,
    )
    parent_id = parent.json()["id"]

    reply = await client.post(
        f"/api/v1/movies/{movie_id}/comments",
        json={"text": "Loved it!", "parent_id": parent_id},
        headers=bob,
    )
    assert reply.status_code == 201
    assert reply.json()["parent_id"] == parent_id

    listing = await client.get(f"/api/v1/movies/{movie_id}/comments")
    assert listing.status_code == 200
    top_level = listing.json()
    assert len(top_level) == 1
    assert top_level[0]["id"] == parent_id
    assert len(top_level[0]["replies"]) == 1
    assert top_level[0]["replies"][0]["text"] == "Loved it!"


async def test_reply_to_nonexistent_parent_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "badparent"
    )
    _, headers = await create_user_headers(
        client, db_session, "badparent-user@example.com", strong_password
    )

    response = await client.post(
        f"/api/v1/movies/{movie_id}/comments",
        json={"text": "Reply to nothing", "parent_id": 999999},
        headers=headers,
    )
    assert response.status_code == 400


async def test_reply_to_comment_on_another_movie_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_a = await _create_movie(
        client, db_session, strong_password, certification.id, "movieA"
    )
    movie_b = await _create_movie(
        client, db_session, strong_password, certification.id, "movieB"
    )
    _, headers = await create_user_headers(
        client, db_session, "cross-movie@example.com", strong_password
    )

    comment_on_a = await client.post(
        f"/api/v1/movies/{movie_a}/comments",
        json={"text": "On movie A"},
        headers=headers,
    )
    parent_id = comment_on_a.json()["id"]

    response = await client.post(
        f"/api/v1/movies/{movie_b}/comments",
        json={"text": "Reply from movie B", "parent_id": parent_id},
        headers=headers,
    )
    assert response.status_code == 400


# --- Deleting comments -----------------------------------------------------------------


async def test_owner_can_delete_own_comment(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "owndelete"
    )
    _, headers = await create_user_headers(
        client, db_session, "owner@example.com", strong_password
    )
    created = await client.post(
        f"/api/v1/movies/{movie_id}/comments",
        json={"text": "Delete me"},
        headers=headers,
    )
    comment_id = created.json()["id"]

    response = await client.delete(
        f"/api/v1/movies/comments/{comment_id}", headers=headers
    )
    assert response.status_code == 200

    listing = await client.get(f"/api/v1/movies/{movie_id}/comments")
    assert listing.json() == []


async def test_other_user_cannot_delete_comment(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "protectdel"
    )
    _, owner = await create_user_headers(
        client, db_session, "owner2@example.com", strong_password
    )
    _, stranger = await create_user_headers(
        client, db_session, "stranger@example.com", strong_password
    )
    created = await client.post(
        f"/api/v1/movies/{movie_id}/comments",
        json={"text": "Mine"},
        headers=owner,
    )
    comment_id = created.json()["id"]

    response = await client.delete(
        f"/api/v1/movies/comments/{comment_id}", headers=stranger
    )
    assert response.status_code == 403


async def test_moderator_can_delete_others_comment(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "moddel"
    )
    _, owner = await create_user_headers(
        client, db_session, "owner3@example.com", strong_password
    )
    _, moderator = await create_user_headers(
        client,
        db_session,
        "moderator-del@example.com",
        strong_password,
        UserGroupEnum.MODERATOR,
    )
    created = await client.post(
        f"/api/v1/movies/{movie_id}/comments",
        json={"text": "Needs moderation"},
        headers=owner,
    )
    comment_id = created.json()["id"]

    response = await client.delete(
        f"/api/v1/movies/comments/{comment_id}", headers=moderator
    )
    assert response.status_code == 200


async def test_delete_unknown_comment_returns_404(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    _, headers = await create_user_headers(
        client, db_session, "delete-unknown@example.com", strong_password
    )
    response = await client.delete(
        "/api/v1/movies/comments/999999", headers=headers
    )
    assert response.status_code == 404


# --- Comment likes -----------------------------------------------------------------------


async def test_like_and_unlike_comment(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "commentlike"
    )
    _, owner = await create_user_headers(
        client, db_session, "comment-owner@example.com", strong_password
    )
    _, liker = await create_user_headers(
        client, db_session, "comment-liker@example.com", strong_password
    )
    created = await client.post(
        f"/api/v1/movies/{movie_id}/comments",
        json={"text": "Like this"},
        headers=owner,
    )
    comment_id = created.json()["id"]

    like = await client.post(
        f"/api/v1/movies/comments/{comment_id}/like", headers=liker
    )
    assert like.status_code == 200

    listing = await client.get(f"/api/v1/movies/{movie_id}/comments")
    assert listing.json()[0]["likes_count"] == 1

    unlike = await client.delete(
        f"/api/v1/movies/comments/{comment_id}/like", headers=liker
    )
    assert unlike.status_code == 200

    listing_after = await client.get(f"/api/v1/movies/{movie_id}/comments")
    assert listing_after.json()[0]["likes_count"] == 0


async def test_liking_a_comment_twice_is_idempotent(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "idempotentlike"
    )
    _, owner = await create_user_headers(
        client, db_session, "idempotent-owner@example.com", strong_password
    )
    _, liker = await create_user_headers(
        client, db_session, "idempotent-liker@example.com", strong_password
    )
    created = await client.post(
        f"/api/v1/movies/{movie_id}/comments",
        json={"text": "Like this too"},
        headers=owner,
    )
    comment_id = created.json()["id"]

    await client.post(
        f"/api/v1/movies/comments/{comment_id}/like", headers=liker
    )
    await client.post(
        f"/api/v1/movies/comments/{comment_id}/like", headers=liker
    )

    listing = await client.get(f"/api/v1/movies/{movie_id}/comments")
    assert listing.json()[0]["likes_count"] == 1


async def test_like_comment_requires_authentication(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await _create_movie(
        client, db_session, strong_password, certification.id, "likeauth"
    )
    _, owner = await create_user_headers(
        client, db_session, "likeauth-owner@example.com", strong_password
    )
    created = await client.post(
        f"/api/v1/movies/{movie_id}/comments",
        json={"text": "Needs auth to like"},
        headers=owner,
    )
    comment_id = created.json()["id"]

    response = await client.post(f"/api/v1/movies/comments/{comment_id}/like")
    assert response.status_code == 401
