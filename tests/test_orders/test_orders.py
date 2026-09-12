from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.models import UserGroupEnum
from src.movies.models import Certification
from tests.test_orders.conftest import add_to_cart, mark_order_paid
from tests.test_cart.conftest import create_movie
from tests.test_movies.conftest import create_user_headers


# --- Placing orders ------------------------------------------------------------------


async def test_placing_order_with_empty_cart_returns_400(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    _, headers = await create_user_headers(
        client, db_session, "empty-order@example.com", strong_password
    )
    response = await client.post("/api/v1/orders", headers=headers)
    assert response.status_code == 400


async def test_place_order_creates_order_and_empties_cart(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "place"
    )
    _, headers = await create_user_headers(
        client, db_session, "order-placer@example.com", strong_password
    )
    await add_to_cart(client, headers, movie_id)

    response = await client.post("/api/v1/orders", headers=headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["excluded"] == []
    order = body["order"]
    assert order["status"] == "pending"
    assert len(order["items"]) == 1
    assert order["items"][0]["movie_id"] == movie_id
    assert order["total_amount"] == order["items"][0]["price_at_order"]

    cart = await client.get("/api/v1/cart", headers=headers)
    assert cart.json()["items"] == []


async def test_placing_order_excludes_already_purchased_movie(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "repurchase"
    )
    _, headers = await create_user_headers(
        client, db_session, "repurchaser@example.com", strong_password
    )

    await add_to_cart(client, headers, movie_id)
    first_order = await client.post("/api/v1/orders", headers=headers)
    order_id = first_order.json()["order"]["id"]
    await mark_order_paid(db_session, order_id)

    await add_to_cart(client, headers, movie_id)
    second = await client.post("/api/v1/orders", headers=headers)
    assert second.status_code == 400
    assert "already purchased" in second.json()["detail"].lower() or (
        "unavailable" in second.json()["detail"].lower()
    )


async def test_placing_order_excludes_movie_in_another_pending_order(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_a = await create_movie(
        client, db_session, strong_password, certification.id, "pendA"
    )
    movie_b = await create_movie(
        client, db_session, strong_password, certification.id, "pendB"
    )
    _, headers = await create_user_headers(
        client, db_session, "pending-orderer@example.com", strong_password
    )

    await add_to_cart(client, headers, movie_a)
    first = await client.post("/api/v1/orders", headers=headers)
    assert first.status_code == 201
    assert first.json()["order"]["status"] == "pending"

    # Same movie re-added to cart while the first order is still pending,
    # plus a brand new movie that should go through fine.
    await add_to_cart(client, headers, movie_a)
    await add_to_cart(client, headers, movie_b)

    second = await client.post("/api/v1/orders", headers=headers)
    assert second.status_code == 201, second.text
    body = second.json()
    assert len(body["excluded"]) == 1
    assert body["excluded"][0]["movie_id"] == movie_a
    assert len(body["order"]["items"]) == 1
    assert body["order"]["items"][0]["movie_id"] == movie_b


async def test_placing_order_with_only_excluded_movies_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "onlyexcl"
    )
    _, headers = await create_user_headers(
        client, db_session, "only-excluded@example.com", strong_password
    )

    await add_to_cart(client, headers, movie_id)
    first = await client.post("/api/v1/orders", headers=headers)
    assert first.status_code == 201

    await add_to_cart(client, headers, movie_id)
    second = await client.post("/api/v1/orders", headers=headers)
    assert second.status_code == 400


# --- Listing / detail ----------------------------------------------------------------


async def test_list_orders_and_status_filter(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_a = await create_movie(
        client, db_session, strong_password, certification.id, "listA"
    )
    movie_b = await create_movie(
        client, db_session, strong_password, certification.id, "listB"
    )
    _, headers = await create_user_headers(
        client, db_session, "order-lister@example.com", strong_password
    )

    await add_to_cart(client, headers, movie_a)
    order1 = await client.post("/api/v1/orders", headers=headers)
    await mark_order_paid(db_session, order1.json()["order"]["id"])

    await add_to_cart(client, headers, movie_b)
    await client.post("/api/v1/orders", headers=headers)

    all_orders = await client.get("/api/v1/orders", headers=headers)
    assert all_orders.json()["total"] == 2

    paid_only = await client.get(
        "/api/v1/orders", params={"status_filter": "paid"}, headers=headers
    )
    assert paid_only.json()["total"] == 1
    assert paid_only.json()["items"][0]["status"] == "paid"


async def test_get_order_detail_permissions(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "detail"
    )
    _, owner_headers = await create_user_headers(
        client, db_session, "order-owner@example.com", strong_password
    )
    _, stranger_headers = await create_user_headers(
        client, db_session, "order-stranger@example.com", strong_password
    )
    _, moderator_headers = await create_user_headers(
        client,
        db_session,
        "order-moderator@example.com",
        strong_password,
        UserGroupEnum.MODERATOR,
    )

    await add_to_cart(client, owner_headers, movie_id)
    created = await client.post("/api/v1/orders", headers=owner_headers)
    order_id = created.json()["order"]["id"]

    own_view = await client.get(
        f"/api/v1/orders/{order_id}", headers=owner_headers
    )
    assert own_view.status_code == 200

    forbidden = await client.get(
        f"/api/v1/orders/{order_id}", headers=stranger_headers
    )
    assert forbidden.status_code == 403

    mod_view = await client.get(
        f"/api/v1/orders/{order_id}", headers=moderator_headers
    )
    assert mod_view.status_code == 200

    missing = await client.get("/api/v1/orders/999999", headers=owner_headers)
    assert missing.status_code == 404


# --- Cancellation --------------------------------------------------------------------


async def test_owner_can_cancel_pending_order(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "cancel"
    )
    _, headers = await create_user_headers(
        client, db_session, "order-canceler@example.com", strong_password
    )
    await add_to_cart(client, headers, movie_id)
    created = await client.post("/api/v1/orders", headers=headers)
    order_id = created.json()["order"]["id"]

    response = await client.post(
        f"/api/v1/orders/{order_id}/cancel", headers=headers
    )
    assert response.status_code == 200

    detail = await client.get(f"/api/v1/orders/{order_id}", headers=headers)
    assert detail.json()["status"] == "canceled"


async def test_cannot_cancel_already_canceled_order(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "doublecancel"
    )
    _, headers = await create_user_headers(
        client, db_session, "double-canceler@example.com", strong_password
    )
    await add_to_cart(client, headers, movie_id)
    created = await client.post("/api/v1/orders", headers=headers)
    order_id = created.json()["order"]["id"]

    await client.post(f"/api/v1/orders/{order_id}/cancel", headers=headers)
    second = await client.post(
        f"/api/v1/orders/{order_id}/cancel", headers=headers
    )
    assert second.status_code == 400


async def test_cannot_cancel_paid_order(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "paidcancel"
    )
    _, headers = await create_user_headers(
        client, db_session, "paid-canceler@example.com", strong_password
    )
    await add_to_cart(client, headers, movie_id)
    created = await client.post("/api/v1/orders", headers=headers)
    order_id = created.json()["order"]["id"]
    await mark_order_paid(db_session, order_id)

    response = await client.post(
        f"/api/v1/orders/{order_id}/cancel", headers=headers
    )
    assert response.status_code == 400


async def test_non_owner_cannot_cancel_order(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "protectcancel"
    )
    _, owner_headers = await create_user_headers(
        client, db_session, "cancel-owner@example.com", strong_password
    )
    _, stranger_headers = await create_user_headers(
        client, db_session, "cancel-stranger@example.com", strong_password
    )
    await add_to_cart(client, owner_headers, movie_id)
    created = await client.post("/api/v1/orders", headers=owner_headers)
    order_id = created.json()["order"]["id"]

    response = await client.post(
        f"/api/v1/orders/{order_id}/cancel", headers=stranger_headers
    )
    assert response.status_code == 403


# --- Admin listing ---------------------------------------------------------------------


async def test_admin_listing_requires_moderator(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    _, headers = await create_user_headers(
        client, db_session, "not-a-mod@example.com", strong_password
    )
    response = await client.get("/api/v1/orders/admin", headers=headers)
    assert response.status_code == 403


async def test_admin_listing_filters_by_user_and_status(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_a = await create_movie(
        client, db_session, strong_password, certification.id, "adminA"
    )
    movie_b = await create_movie(
        client, db_session, strong_password, certification.id, "adminB"
    )
    alice, alice_headers = await create_user_headers(
        client, db_session, "alice-admin@example.com", strong_password
    )
    _, bob_headers = await create_user_headers(
        client, db_session, "bob-admin@example.com", strong_password
    )
    _, moderator_headers = await create_user_headers(
        client,
        db_session,
        "admin-listing-mod@example.com",
        strong_password,
        UserGroupEnum.MODERATOR,
    )

    await add_to_cart(client, alice_headers, movie_a)
    alice_order = await client.post("/api/v1/orders", headers=alice_headers)
    await mark_order_paid(db_session, alice_order.json()["order"]["id"])

    await add_to_cart(client, bob_headers, movie_b)
    await client.post("/api/v1/orders", headers=bob_headers)

    all_orders = await client.get(
        "/api/v1/orders/admin", headers=moderator_headers
    )
    assert all_orders.json()["total"] >= 2

    by_user = await client.get(
        "/api/v1/orders/admin",
        params={"user_id": alice.id},
        headers=moderator_headers,
    )
    assert by_user.json()["total"] == 1
    assert by_user.json()["items"][0]["user_id"] == alice.id

    by_status = await client.get(
        "/api/v1/orders/admin",
        params={"status_filter": "paid"},
        headers=moderator_headers,
    )
    assert all(item["status"] == "paid" for item in by_status.json()["items"])
