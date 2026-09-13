"""Isolates all direct Stripe SDK calls behind small functions.

The router only ever calls these, never `stripe.*` directly -- that's what
lets tests monkeypatch `create_checkout_session` / `create_refund` instead
of needing real Stripe credentials or network access, and lets
`construct_webhook_event` fall back to trusting a plain JSON body when no
webhook secret is configured (local dev / tests), while still doing real
signature verification whenever `STRIPE_WEBHOOK_SECRET` is set.
"""

import json
from typing import Any

import stripe

from src.config import settings


def _configured_stripe():
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def create_checkout_session(
        *,
        order_id: int,
        line_items: list[dict[str, Any]],
        success_url: str,
        cancel_url: str,
) -> Any:
    client = _configured_stripe()
    return client.checkout.Session.create(
        mode="payment",
        client_reference_id=str(order_id),
        line_items=line_items,
        success_url=success_url,
        cancel_url=cancel_url,
    )


def construct_webhook_event(
        payload: bytes,
        sig_header: str | None
) -> dict:
    if not settings.STRIPE_WEBHOOK_SECRET:
        # No webhook secret configured (local dev / tests): trust the body
        # as-is instead of verifying a Stripe signature.
        return json.loads(payload)
    event = stripe.Webhook.construct_event(
        payload,
        sig_header,
        settings.STRIPE_WEBHOOK_SECRET
    )
    return event if isinstance(event, dict) else event.to_dict()


def create_refund(*, payment_intent_id: int) -> Any:
    client = _configured_stripe()
    return client.Refund.create(payment_intent=payment_intent_id)
