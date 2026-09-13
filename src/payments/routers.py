import logging
from datetime import date, datetime, time, timezone
from math import ceil

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from accounts.dependencies import get_current_user, require_moderator
from accounts.models import User
from accounts.notifications import send_order_confirmation_email
from accounts.schemas import MessageResponse
from config import settings
from database import get_db
from movies.schemas import PaginatedResponse
from orders.models import Order, OrderItem, OrderStatusEnum
from payments import stripe_client
from payments.models import Payment, PaymentItem, PaymentStatusEnum
from payments.schemas import CheckoutSessionResponse, PaymentResponse

logger = logging.getLogger("online_cinema.payments")

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


async def _payment_payload(db: AsyncSession, payment: Payment) -> dict:
    result = await db.execute(
        select(PaymentItem)
        .options(
            selectinload(PaymentItem.order_item).selectinload(OrderItem.movie)
        )
        .where(PaymentItem.payment_id == payment.id)
    )
    items = list(result.scalars().all())
    return {
        "id": payment.id,
        "user_id": payment.user_id,
        "order_id": payment.order_id,
        "created_at": payment.created_at,
        "status": payment.status,
        "amount": payment.amount,
        "external_payment_id": payment.external_payment_id,
        "items": [
            {
                "movie_id": item.order_item.movie_id,
                "name": item.order_item.movie.name,
                "price_at_payment": item.price_at_payment,
            }
            for item in items
        ],
    }


# --- Checkout ----------------------------------------------------


@router.post(
    "/checkout/{order_id}",
    response_model=CheckoutSessionResponse,
    summary="Create a Stripe Checkout session for a pending order",
    description=(
        "Fails with 404 if the order doesn't exist or isn't yours, 400 if "
        "it isn't `pending`, and 502 if Stripe itself is unreachable or "
        "declines to create the session (try again or use a different "
        "payment method)."
    ),
)
async def create_checkout_session(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    order = await db.get(Order, order_id)
    if order is None or order.user_id != current_user.id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Order not found."
        )
    if order.status != OrderStatusEnum.PENDING:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Only pending orders can be paid for.",
        )

    items_result = await db.execute(
        select(OrderItem)
        .options(selectinload(OrderItem.movie))
        .where(OrderItem.order_id == order.id)
    )
    order_items = list(items_result.scalars().all())
    if not order_items:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Order has no items."
        )

    # Revalidate the total against the frozen per-item prices, in case of
    # any manual data drift since the order was created.
    order.total_amount = sum(item.price_at_order for item in order_items)
    await db.commit()

    line_items = [
        {
            "price_data": {
                "currency": "usd",
                "product_data": {"name": item.movie.name},
                "unit_amount": int(round(float(item.price_at_order) * 100)),
            },
            "quantity": 1,
        }
        for item in order_items
    ]

    try:
        session = stripe_client.create_checkout_session(
            order_id=order.id,
            line_items=line_items,
            success_url=(
                f"{settings.FRONTEND_URL}/payments/success"
                f"?order_id={order.id}"
            ),
            cancel_url=(
                f"{settings.FRONTEND_URL}/payments/cancel"
                f"?order_id={order.id}"
            ),
        )
    except stripe.StripeError as exc:
        logger.warning("Stripe checkout session creation failed: %s", exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=(
                "We couldn't reach the payment provider. Please try again "
                "or use a different payment method."
            ),
        ) from exc

    return {"checkout_url": session.url, "session_id": session.id}


# --- Webhook -------------------------------------------


@router.post(
    "/webhook",
    summary="Stripe webhook receiver",
    description=(
        "Verifies and processes Stripe events. Marks the corresponding "
        "order as paid and records a Payment on "
        "`checkout.session.completed`. Not meant to be called directly by "
        "clients."
    ),
)
async def stripe_webhook(
    request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe_client.construct_webhook_event(payload, sig_header)
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload."
        ) from exc

    if event.get("type") == "checkout.session.completed":
        await _handle_checkout_completed(db, event["data"]["object"])

    return {"received": True}


async def _handle_checkout_completed(db: AsyncSession, session: dict) -> None:
    order_id_raw = session.get("client_reference_id")
    if not order_id_raw:
        logger.warning("Webhook checkout session missing client_reference_id")
        return

    order = await db.get(Order, int(order_id_raw))
    if order is None:
        logger.warning("Webhook referenced unknown order id=%s", order_id_raw)
        return

    existing = await db.execute(
        select(Payment).where(Payment.order_id == order.id)
    )
    if existing.scalar_one_or_none() is not None:
        return  # already processed -- webhooks can be delivered more than once

    items_result = await db.execute(
        select(OrderItem).where(OrderItem.order_id == order.id)
    )
    order_items = list(items_result.scalars().all())

    payment = Payment(
        user_id=order.user_id,
        order_id=order.id,
        status=PaymentStatusEnum.SUCCESSFUL,
        amount=order.total_amount or 0,
        external_payment_id=session.get("payment_intent"),
    )
    db.add(payment)
    await db.flush()

    for order_item in order_items:
        db.add(
            PaymentItem(
                payment_id=payment.id,
                order_item_id=order_item.id,
                price_at_payment=order_item.price_at_order,
            )
        )

    order.status = OrderStatusEnum.PAID
    await db.commit()

    user = await db.get(User, order.user_id)
    if user is not None:
        send_order_confirmation_email(
            user.email, order.id, f"{float(payment.amount):.2f}"
        )


# --- History --------------------------------


@router.get(
    "",
    response_model=PaginatedResponse[PaymentResponse],
    summary="List the current user's payment history",
)
async def list_payments(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    total = (
        await db.execute(
            select(func.count(Payment.id)).where(
                Payment.user_id == current_user.id
            )
        )
    ).scalar_one()

    offset = (page - 1) * per_page
    result = await db.execute(
        select(Payment)
        .where(Payment.user_id == current_user.id)
        .order_by(Payment.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    payments = list(result.scalars().all())
    items = [await _payment_payload(db, p) for p in payments]

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": ceil(total / per_page) if per_page else 0,
    }


@router.get(
    "/admin",
    response_model=PaginatedResponse[PaymentResponse],
    summary="[Moderator] List all payments with filters",
)
async def list_all_payments(
    user_id: int | None = Query(default=None),
    status_filter: PaymentStatusEnum | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
) -> dict:
    filters: list[ColumnElement[bool]] = []
    if user_id is not None:
        filters.append(Payment.user_id == user_id)
    if status_filter is not None:
        filters.append(Payment.status == status_filter)
    if date_from is not None:
        filters.append(
            Payment.created_at
            >= datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        )
    if date_to is not None:
        filters.append(
            Payment.created_at
            <= datetime.combine(date_to, time.max, tzinfo=timezone.utc)
        )

    where_clause: ColumnElement[bool] = and_(*filters) if filters else true()

    total = (
        await db.execute(select(func.count(Payment.id)).where(where_clause))
    ).scalar_one()

    offset = (page - 1) * per_page
    result = await db.execute(
        select(Payment)
        .where(where_clause)
        .order_by(Payment.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    payments = list(result.scalars().all())
    items = [await _payment_payload(db, p) for p in payments]

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": ceil(total / per_page) if per_page else 0,
    }


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    summary="Get payment details (owner or moderator)",
)
async def get_payment(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    payment = await db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Payment not found."
        )
    is_owner = payment.user_id == current_user.id
    is_privileged = current_user.group.name in ("MODERATOR", "ADMIN")
    if not (is_owner or is_privileged):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this payment.",
        )
    return await _payment_payload(db, payment)


@router.post(
    "/{payment_id}/refund",
    response_model=MessageResponse,
    summary="[Moderator] Refund a successful payment",
    description=(
        "Refunds the charge via Stripe, marks the payment `refunded`, and "
        "cancels the associated order, per the rule that a paid order can "
        "only be canceled through a refund."
    ),
)
async def refund_payment(
    payment_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
) -> dict:
    payment = await db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Payment not found."
        )
    if payment.status != PaymentStatusEnum.SUCCESSFUL:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Payment is already {payment.status.value}.",
        )

    if payment.external_payment_id:
        try:
            stripe_client.create_refund(
                payment_intent_id=payment.external_payment_id
            )
        except stripe.StripeError as exc:
            logger.warning("Stripe refund failed: %s", exc)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                detail="We couldn't reach the payment provider"
                " to refund this charge.",
            ) from exc

    payment.status = PaymentStatusEnum.REFUNDED
    order = await db.get(Order, payment.order_id)
    if order is not None:
        order.status = OrderStatusEnum.CANCELED
    await db.commit()
    return {"message": "Payment refunded and order canceled."}
