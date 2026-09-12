from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.models import UserGroupEnum
from src.movies.models import Certification
from tests.test_cart.conftest import create_movie
from tests.test_movies.conftest import create_user_headers


async def test_empty_cart_is_created_on_first_view(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    _, headers = await create_user_headers(
        client, db_session, "empty-cart@example.com", strong_password
    )
    response = await client.get("/api/v1/cart", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total_price"] == 0
    assert body["item_count"] == 0


async def test_cart_requires_authentication(client: AsyncClient):
    response = await client.get("/api/v1/cart")
    assert response.status_code == 401


async def test_add_movie_to_cart(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "add"
    )
    _, headers = await create_user_headers(
        client, db_session, "cart-adder@example.com", strong_password
    )

    response = await client.post(
        f"/api/v1/cart/items/{movie_id}", headers=headers
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["item_count"] == 1
    assert body["items"][0]["movie_id"] == movie_id
    assert body["items"][0]["name"] == "Movie add"
    assert body["total_price"] == body["items"][0]["price"]


async def test_add_unknown_movie_returns_404(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    _, headers = await create_user_headers(
        client, db_session, "cart-404@example.com", strong_password
    )
    response = await client.post(
        "/api/v1/cart/items/999999", headers=headers
    )
    assert response.status_code == 404


async def test_adding_same_movie_twice_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "dup"
    )
    _, headers = await create_user_headers(
        client, db_session, "cart-dup@example.com", strong_password
    )

    first = await client.post(
        f"/api/v1/cart/items/{movie_id}", headers=headers
    )
    assert first.status_code == 201
    second = await client.post(
        f"/api/v1/cart/items/{movie_id}", headers=headers
    )
    assert second.status_code == 409


async def test_remove_movie_from_cart(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "remove"
    )
    _, headers = await create_user_headers(
        client, db_session, "cart-remover@example.com", strong_password
    )

    await client.post(f"/api/v1/cart/items/{movie_id}", headers=headers)
    response = await client.delete(
        f"/api/v1/cart/items/{movie_id}", headers=headers
    )
    assert response.status_code == 200

    cart = await client.get("/api/v1/cart", headers=headers)
    assert cart.json()["items"] == []


async def test_removing_movie_not_in_cart_is_idempotent(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    _, headers = await create_user_headers(
        client, db_session, "cart-remove-noop@example.com", strong_password
    )
    response = await client.delete(
        "/api/v1/cart/items/999999", headers=headers
    )
    assert response.status_code == 200


async def test_clear_cart(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_a = await create_movie(
        client, db_session, strong_password, certification.id, "clearA"
    )
    movie_b = await create_movie(
        client, db_session, strong_password, certification.id, "clearB"
    )
    _, headers = await create_user_headers(
        client, db_session, "cart-clearer@example.com", strong_password
    )

    await client.post(f"/api/v1/cart/items/{movie_a}", headers=headers)
    await client.post(f"/api/v1/cart/items/{movie_b}", headers=headers)

    response = await client.delete("/api/v1/cart", headers=headers)
    assert response.status_code == 200

    cart = await client.get("/api/v1/cart", headers=headers)
    assert cart.json()["items"] == []
    assert cart.json()["total_price"] == 0


async def test_cart_is_scoped_per_user(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "scoped"
    )
    _, alice = await create_user_headers(
        client, db_session, "alice-cart@example.com", strong_password
    )
    _, bob = await create_user_headers(
        client, db_session, "bob-cart@example.com", strong_password
    )

    await client.post(f"/api/v1/cart/items/{movie_id}", headers=alice)

    alice_cart = await client.get("/api/v1/cart", headers=alice)
    bob_cart = await client.get("/api/v1/cart", headers=bob)

    assert alice_cart.json()["item_count"] == 1
    assert bob_cart.json()["item_count"] == 0


# --- Moderator visibility -----------------------------------------------------------


async def test_moderator_can_view_another_users_cart(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "modview"
    )
    alice, alice_headers = await create_user_headers(
        client, db_session, "alice-modview@example.com", strong_password
    )
    _, moderator_headers = await create_user_headers(
        client,
        db_session,
        "moderator-cartview@example.com",
        strong_password,
        UserGroupEnum.MODERATOR,
    )

    await client.post(f"/api/v1/cart/items/{movie_id}", headers=alice_headers)

    response = await client.get(
        f"/api/v1/cart/users/{alice.id}", headers=moderator_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == alice.id
    assert body["item_count"] == 1


async def test_regular_user_cannot_view_another_users_cart(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    alice, _ = await create_user_headers(
        client, db_session, "alice-protected@example.com", strong_password
    )
    _, bob_headers = await create_user_headers(
        client, db_session, "bob-protected@example.com", strong_password
    )

    response = await client.get(
        f"/api/v1/cart/users/{alice.id}", headers=bob_headers
    )
    assert response.status_code == 403


async def test_moderator_view_of_unknown_user_returns_404(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    _, moderator_headers = await create_user_headers(
        client,
        db_session,
        "moderator-404@example.com",
        strong_password,
        UserGroupEnum.MODERATOR,
    )
    response = await client.get(
        "/api/v1/cart/users/999999", headers=moderator_headers
    )
    assert response.status_code == 404


# --- Delete-movie cart guard ---------------------------------------------------------


async def test_deleting_a_movie_in_a_cart_is_blocked_without_force(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "guarded"
    )
    _, mod_headers = await create_user_headers(
        client,
        db_session,
        "moderator-guard@example.com",
        strong_password,
        UserGroupEnum.MODERATOR,
    )
    _, user_headers = await create_user_headers(
        client, db_session, "cart-guard-user@example.com", strong_password
    )
    await client.post(f"/api/v1/cart/items/{movie_id}", headers=user_headers)

    blocked = await client.delete(
        f"/api/v1/movies/{movie_id}", headers=mod_headers
    )
    assert blocked.status_code == 409

    forced = await client.delete(
        f"/api/v1/movies/{movie_id}",
        params={"force": "true"},
        headers=mod_headers,
    )
    assert forced.status_code == 200


async def test_deleting_a_movie_not_in_any_cart_succeeds(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "unguarded"
    )
    _, mod_headers = await create_user_headers(
        client,
        db_session,
        "moderator-unguarded@example.com",
        strong_password,
        UserGroupEnum.MODERATOR,
    )

    response = await client.delete(
        f"/api/v1/movies/{movie_id}", headers=mod_headers
    )
    assert response.status_code == 200
