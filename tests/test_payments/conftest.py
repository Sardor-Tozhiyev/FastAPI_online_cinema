import json
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

# Re-exported so pytest picks up shared fixtures/helpers for this directory.
from tests.test_cart.conftest import create_movie  # noqa: F401
from tests.test_movies.conftest import (  # noqa: F401
    certification,
    create_user_headers,
)
from tests.test_orders.conftest import add_to_cart  # noqa: F401


async def create_pending_order(
    client: AsyncClient, headers: dict[str, str], movie_id: int
) -> int:
    await add_to_cart(client, headers, movie_id)
    response = await client.post("/api/v1/orders", headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["order"]["id"]


def fake_checkout_session(**kwargs) -> SimpleNamespace:
    """Stand-in for `stripe.checkout.Session.create`'s return value."""
    order_id = kwargs["order_id"]
    return SimpleNamespace(
        id=f"cs_test_{order_id}",
        url=f"https://checkout.stripe.test/pay/cs_test_{order_id}",
    )


def webhook_event(order_id: int, payment_intent: str = "pi_test_123") -> dict:
    """Return a minimal checkout.session.completed event body."""
    return {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": str(order_id),
                "payment_intent": payment_intent,
            }
        },
    }


@pytest.fixture
def bypass_webhook_signature(monkeypatch):
    def construct_webhook_event(payload, sig_header):
        return json.loads(payload)

    monkeypatch.setattr(
        "payments.stripe_client.construct_webhook_event",
        construct_webhook_event,
    )
