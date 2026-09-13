import stripe
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from accounts.models import UserGroupEnum
from movies.models import Certification
from tests.test_cart.conftest import create_movie
from tests.test_movies.conftest import create_user_headers
from tests.test_payments.conftest import (
    create_pending_order,
    fake_checkout_session,
    webhook_event,
)


def _raise_stripe_error(**kwargs):
    raise stripe.error.StripeError("simulated Stripe outage")


# --- Checkout session creation --------------------


async def test_create_checkout_session(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
    monkeypatch,
):
    monkeypatch.setattr(
        "payments.stripe_client.create_checkout_session",
        fake_checkout_session,
    )
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "checkout"
    )
    _, headers = await create_user_headers(
        client, db_session, "checkout-user@example.com", strong_password
    )
    order_id = await create_pending_order(client, headers, movie_id)

    response = await client.post(
        f"/api/v1/payments/checkout/{order_id}", headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session_id"] == f"cs_test_{order_id}"
    assert "checkout.stripe.test" in body["checkout_url"]


async def test_checkout_session_for_others_order_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
    monkeypatch,
):
    monkeypatch.setattr(
        "payments.stripe_client.create_checkout_session",
        fake_checkout_session,
    )
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "notyours"
    )
    _, owner_headers = await create_user_headers(
        client, db_session, "checkout-owner@example.com", strong_password
    )
    _, stranger_headers = await create_user_headers(
        client, db_session, "checkout-stranger@example.com", strong_password
    )
    order_id = await create_pending_order(client, owner_headers, movie_id)

    response = await client.post(
        f"/api/v1/payments/checkout/{order_id}", headers=stranger_headers
    )
    assert response.status_code == 404


async def test_checkout_session_for_non_pending_order_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
    monkeypatch,
):
    monkeypatch.setattr(
        "payments.stripe_client.create_checkout_session",
        fake_checkout_session,
    )
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "notpending"
    )
    _, headers = await create_user_headers(
        client, db_session, "checkout-notpending@example.com", strong_password
    )
    order_id = await create_pending_order(client, headers, movie_id)
    await client.post(f"/api/v1/orders/{order_id}/cancel", headers=headers)

    response = await client.post(
        f"/api/v1/payments/checkout/{order_id}", headers=headers
    )
    assert response.status_code == 400


async def test_checkout_session_unknown_order_returns_404(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    _, headers = await create_user_headers(
        client, db_session, "checkout-404@example.com", strong_password
    )
    response = await client.post(
        "/api/v1/payments/checkout/999999", headers=headers
    )
    assert response.status_code == 404


async def test_checkout_session_stripe_error_returns_502(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
    monkeypatch,
):
    monkeypatch.setattr(
        "payments.stripe_client.create_checkout_session",
        _raise_stripe_error,
    )
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "stripedown"
    )
    _, headers = await create_user_headers(
        client, db_session, "checkout-stripedown@example.com", strong_password
    )
    order_id = await create_pending_order(client, headers, movie_id)

    response = await client.post(
        f"/api/v1/payments/checkout/{order_id}", headers=headers
    )
    assert response.status_code == 502


# --- Webhook --------------------------------


async def test_webhook_marks_order_paid_and_creates_payment(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "webhook"
    )
    _, headers = await create_user_headers(
        client, db_session, "webhook-user@example.com", strong_password
    )
    order_id = await create_pending_order(client, headers, movie_id)

    response = await client.post(
        "/api/v1/payments/webhook", json=webhook_event(order_id)
    )
    assert response.status_code == 200
    assert response.json() == {"received": True}

    order = await client.get(f"/api/v1/orders/{order_id}", headers=headers)
    assert order.json()["status"] == "paid"

    payments = await client.get("/api/v1/payments", headers=headers)
    assert payments.json()["total"] == 1
    payment = payments.json()["items"][0]
    assert payment["order_id"] == order_id
    assert payment["status"] == "successful"
    assert payment["external_payment_id"] == "pi_test_123"
    assert len(payment["items"]) == 1
    assert payment["items"][0]["movie_id"] == movie_id


async def test_webhook_is_idempotent_on_redelivery(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "redelivery"
    )
    _, headers = await create_user_headers(
        client, db_session, "redelivery-user@example.com", strong_password
    )
    order_id = await create_pending_order(client, headers, movie_id)

    event = webhook_event(order_id)
    first = await client.post("/api/v1/payments/webhook", json=event)
    second = await client.post("/api/v1/payments/webhook", json=event)
    assert first.status_code == 200
    assert second.status_code == 200

    payments = await client.get("/api/v1/payments", headers=headers)
    assert payments.json()["total"] == 1


async def test_webhook_for_unknown_order_is_a_graceful_noop(
    client: AsyncClient,
):
    response = await client.post(
        "/api/v1/payments/webhook", json=webhook_event(999999)
    )
    assert response.status_code == 200


async def test_webhook_with_invalid_payload_returns_400(client: AsyncClient):
    response = await client.post(
        "/api/v1/payments/webhook",
        content=b"not-json-at-all",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400


# --- History / detail permissions -------------------


async def test_payments_require_authentication(client: AsyncClient):
    response = await client.get("/api/v1/payments")
    assert response.status_code == 401


async def test_get_payment_detail_permissions(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "detailperm"
    )
    _, owner_headers = await create_user_headers(
        client, db_session, "payment-owner@example.com", strong_password
    )
    _, stranger_headers = await create_user_headers(
        client, db_session, "payment-stranger@example.com", strong_password
    )
    _, moderator_headers = await create_user_headers(
        client,
        db_session,
        "payment-moderator@example.com",
        strong_password,
        UserGroupEnum.MODERATOR,
    )
    order_id = await create_pending_order(client, owner_headers, movie_id)
    await client.post("/api/v1/payments/webhook", json=webhook_event(order_id))
    payment_id = (
        await client.get("/api/v1/payments", headers=owner_headers)
    ).json()["items"][0]["id"]

    own_view = await client.get(
        f"/api/v1/payments/{payment_id}", headers=owner_headers
    )
    assert own_view.status_code == 200

    forbidden = await client.get(
        f"/api/v1/payments/{payment_id}", headers=stranger_headers
    )
    assert forbidden.status_code == 403

    mod_view = await client.get(
        f"/api/v1/payments/{payment_id}", headers=moderator_headers
    )
    assert mod_view.status_code == 200

    missing = await client.get(
        "/api/v1/payments/999999", headers=owner_headers
    )
    assert missing.status_code == 404


# --- Refunds ------------------------------------


async def test_moderator_can_refund_payment(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
    monkeypatch,
):
    refund_calls = []
    monkeypatch.setattr(
        "payments.stripe_client.create_refund",
        lambda **kwargs: refund_calls.append(kwargs),
    )

    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "refund"
    )
    _, user_headers = await create_user_headers(
        client, db_session, "refund-user@example.com", strong_password
    )
    _, mod_headers = await create_user_headers(
        client,
        db_session,
        "refund-moderator@example.com",
        strong_password,
        UserGroupEnum.MODERATOR,
    )
    order_id = await create_pending_order(client, user_headers, movie_id)
    await client.post("/api/v1/payments/webhook", json=webhook_event(order_id))
    payment_id = (
        await client.get("/api/v1/payments", headers=user_headers)
    ).json()["items"][0]["id"]

    response = await client.post(
        f"/api/v1/payments/{payment_id}/refund", headers=mod_headers
    )
    assert response.status_code == 200
    assert len(refund_calls) == 1
    assert refund_calls[0]["payment_intent_id"] == "pi_test_123"

    payment = await client.get(
        f"/api/v1/payments/{payment_id}", headers=user_headers
    )
    assert payment.json()["status"] == "refunded"

    order = await client.get(
        f"/api/v1/orders/{order_id}", headers=user_headers
    )
    assert order.json()["status"] == "canceled"


async def test_cannot_refund_already_refunded_payment(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
    monkeypatch,
):
    monkeypatch.setattr(
        "payments.stripe_client.create_refund", lambda **kwargs: None
    )
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "doublerefund"
    )
    _, user_headers = await create_user_headers(
        client, db_session, "double-refund-user@example.com", strong_password
    )
    _, mod_headers = await create_user_headers(
        client,
        db_session,
        "double-refund-mod@example.com",
        strong_password,
        UserGroupEnum.MODERATOR,
    )
    order_id = await create_pending_order(client, user_headers, movie_id)
    await client.post("/api/v1/payments/webhook", json=webhook_event(order_id))
    payment_id = (
        await client.get("/api/v1/payments", headers=user_headers)
    ).json()["items"][0]["id"]

    await client.post(
        f"/api/v1/payments/{payment_id}/refund", headers=mod_headers
    )
    second = await client.post(
        f"/api/v1/payments/{payment_id}/refund", headers=mod_headers
    )
    assert second.status_code == 400


async def test_non_moderator_cannot_refund(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
):
    movie_id = await create_movie(
        client, db_session, strong_password, certification.id, "protectref"
    )
    _, user_headers = await create_user_headers(
        client, db_session, "protect-refund-user@example.com", strong_password
    )
    order_id = await create_pending_order(client, user_headers, movie_id)
    await client.post("/api/v1/payments/webhook", json=webhook_event(order_id))
    payment_id = (
        await client.get("/api/v1/payments", headers=user_headers)
    ).json()["items"][0]["id"]

    response = await client.post(
        f"/api/v1/payments/{payment_id}/refund", headers=user_headers
    )
    assert response.status_code == 403


# --- Admin listing ----------------------------------


async def test_admin_payment_listing_requires_moderator(
    client: AsyncClient, db_session: AsyncSession, strong_password: str
):
    _, headers = await create_user_headers(
        client, db_session, "not-a-payment-mod@example.com", strong_password
    )
    response = await client.get("/api/v1/payments/admin", headers=headers)
    assert response.status_code == 403


async def test_admin_payment_listing_filters_by_user_and_status(
    client: AsyncClient,
    db_session: AsyncSession,
    strong_password: str,
    certification: Certification,
    monkeypatch,
):
    monkeypatch.setattr(
        "payments.stripe_client.create_refund", lambda **kwargs: None
    )
    movie_a = await create_movie(
        client, db_session, strong_password, certification.id, "adminpayA"
    )
    movie_b = await create_movie(
        client, db_session, strong_password, certification.id, "adminpayB"
    )
    alice, alice_headers = await create_user_headers(
        client, db_session, "alice-payment@example.com", strong_password
    )
    _, bob_headers = await create_user_headers(
        client, db_session, "bob-payment@example.com", strong_password
    )
    _, mod_headers = await create_user_headers(
        client,
        db_session,
        "admin-payment-mod@example.com",
        strong_password,
        UserGroupEnum.MODERATOR,
    )

    alice_order = await create_pending_order(client, alice_headers, movie_a)
    await client.post(
        "/api/v1/payments/webhook", json=webhook_event(alice_order)
    )
    bob_order = await create_pending_order(client, bob_headers, movie_b)
    await client.post(
        "/api/v1/payments/webhook", json=webhook_event(bob_order, "pi_bob")
    )

    alice_payment_id = (
        await client.get("/api/v1/payments", headers=alice_headers)
    ).json()["items"][0]["id"]
    await client.post(
        f"/api/v1/payments/{alice_payment_id}/refund", headers=mod_headers
    )

    all_payments = await client.get(
        "/api/v1/payments/admin", headers=mod_headers
    )
    assert all_payments.json()["total"] >= 2

    by_user = await client.get(
        "/api/v1/payments/admin",
        params={"user_id": alice.id},
        headers=mod_headers,
    )
    assert by_user.json()["total"] == 1
    assert by_user.json()["items"][0]["user_id"] == alice.id

    by_status = await client.get(
        "/api/v1/payments/admin",
        params={"status_filter": "refunded"},
        headers=mod_headers,
    )
    assert all(
        item["status"] == "refunded" for item in by_status.json()["items"]
    )
    assert by_status.json()["total"] == 1
