from datetime import date, datetime, time, timezone
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from src.accounts.dependencies import get_current_user, require_moderator
from src.accounts.models import User
from src.accounts.schemas import MessageResponse
from src.cart.models import Cart, CartItem
from src.database import get_db
from src.movies.schemas import PaginatedResponse
from src.orders.models import Order, OrderItem, OrderStatusEnum
from src.orders.schemas import (
    OrderCreateResponse,
    OrderListItemResponse,
    OrderResponse,
)


router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


async def _order_payload(
    db: AsyncSession,
    order: Order,
) -> dict:
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items).selectinload(OrderItem.movie))
        .where(Order.id == order.id)
    )
    order = result.scalar_one()

    return {
        "id": order.id,
        "user_id": order.user_id,
        "created_at": order.created_at,
        "status": order.status,
        "total_amount": order.total_amount,
        "items": [
            {
                "movie_id": item.movie.id,
                "name": item.movie.name,
                "price_at_order": item.price_at_order,
            }
            for item in order.items
        ],
    }


async def _get_order_or_404(
    db: AsyncSession,
    order_id: int,
) -> Order:
    order = await db.get(Order, order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found.",
        )
    return order


def _ensure_can_view(
    order: Order,
    user: User,
) -> None:
    is_owner = order.user_id == user.id
    is_privileged = user.group.name in ("MODERATOR", "ADMIN")
    if not (is_owner or is_privileged):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this order.",
        )


@router.post(
    "",
    response_model=OrderCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Place an order from the current cart",
    description=(
        "Creates a `pending` order from every movie currently in the "
        "user's cart, snapshotting each movie's current price. Movies "
        "already purchased (in a `paid` order) or already sitting in "
        "another `pending` order for this user are excluded and reported "
        "back rather than blocking the whole order. Fails with 400 if the "
        "cart is empty or if every movie in it had to be excluded. "
        "Successfully ordered movies are removed from the cart; excluded "
        "ones are left in place. Redirecting to a payment gateway and "
        "marking the order `paid` happens in the payments module."
    ),
)
async def create_order(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cart_result = await db.execute(
        select(Cart).where(Cart.user_id == current_user.id)
    )
    cart = cart_result.scalar_one_or_none()
    cart_items: list[CartItem] = []
    if cart is not None:
        items_result = await db.execute(
            select(CartItem)
            .options(selectinload(CartItem.movie))
            .where(CartItem.cart_id == cart.id)
        )
        cart_items = list(items_result.scalars().all())

    if not cart_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your cart is empty.",
        )
    movie_ids = [item.movie_id for item in cart_items]

    purchased_result = await db.execute(
        select(OrderItem.movie_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.user_id == current_user.id,
            Order.status == OrderStatusEnum.PAID,
            OrderItem.movie_id.in_(movie_ids),
        )
    )
    already_purchased = set(purchased_result.scalars().all())

    pending_result = await db.execute(
        select(OrderItem.movie_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.user_id == current_user.id,
            Order.status == OrderStatusEnum.PENDING,
            OrderItem.movie_id.in_(movie_ids),
        )
    )
    already_pending = set(pending_result.scalars().all())

    excluded: list[dict] = []
    orderable_items: list[CartItem] = []
    for item in cart_items:
        if item.movie_id in already_purchased:
            excluded.append(
                {
                    "movie_id": item.movie_id,
                    "name": item.movie.name,
                    "reason": "Already purchased.",
                }
            )
        elif item.movie_id in already_pending:
            excluded.append(
                {
                    "movie_id": item.movie_id,
                    "name": item.movie.name,
                    "reason": "Already in another pending order.",
                }
            )
        else:
            orderable_items.append(item)

    if not orderable_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Every movie in your cart is unavailable for purchase "
                "(already purchased or already pending)."
            ),
        )
    total_amount = sum(item.movie.price for item in orderable_items)
    order = Order(
        user_id=current_user.id,
        status=OrderStatusEnum.PENDING,
        total_amount=total_amount,
    )
    db.add(order)
    await db.flush()

    for item in orderable_items:
        db.add(
            OrderItem(
                order_id=order.id,
                movie_id=item.movie_id,
                price_at_order=item.movie.price,
            )
        )
        await db.delete(item)

    await db.commit()

    payload = await _order_payload(db, order)
    return {"order": payload, "excluded": excluded}


@router.get(
    "",
    response_model=PaginatedResponse[OrderListItemResponse],
    summary="List the current user's orders",
)
async def list_orders(
    status_filter: OrderStatusEnum | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    filters = [Order.user_id == current_user.id]
    if status_filter is not None:
        filters.append(Order.status == status_filter)

    total = (
        await db.execute(select(func.count(Order.id)).where(and_(*filters)))
    ).scalar_one()

    offset = (page - 1) * per_page
    result = await db.execute(
        select(Order)
        .where(and_(*filters))
        .order_by(Order.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    orders = list(result.scalars().all())

    counts_result = await db.execute(
        select(OrderItem.order_id, func.count(OrderItem.order_id))
        .where(OrderItem.order_id.in_([o.id for o in orders]))
        .order_by(OrderItem.order_id)
    )
    counts_by_id = {oid: c for oid, c in counts_result.all()}

    items = [
        {
            "id": o.id,
            "created_at": o.created_at,
            "status": o.status,
            "total_amount": o.total_amount,
            "movie_count": counts_by_id.get(o.id, 0),
        }
        for o in orders
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": ceil(total / per_page) if per_page else 0,
    }


@router.get(
    "/admin",
    response_model=PaginatedResponse[OrderResponse],
    summary="[Moderator] List all orders with filter",
)
async def list_all_orders(
    user_id: int,
    status_filter: OrderStatusEnum | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
) -> dict:
    filters: list[ColumnElement[bool]] = []
    if user_id is not None:
        filters.append(Order.user_id == user_id)
    if status_filter is not None:
        filters.append(Order.status == status_filter)
    if date_from is not None:
        filters.append(
            Order.created_at
            >= datetime.combine(date_from, time.max, tzinfo=timezone.utc)
        )
    if date_to is not None:
        filters.append(
            Order.created_at
            <= datetime.combine(date_to, time.max, tzinfo=timezone.utc)
        )

    where_clause = and_(*filters)

    total = (
        await db.execute(select(func.count(Order.id)).where(where_clause))
    ).scalar_one()

    offset = (page - 1) * per_page
    result = await db.execute(
        select(Order)
        .where(where_clause)
        .order_by(Order.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    orders = list(result.scalars().all())
    items = [await _order_payload(db, o) for o in orders]

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": ceil(total / per_page) if per_page else 0,
    }


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    summary="Get order details (owner or moderator)",
)
async def get_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    order = await _get_order_or_404(db, order_id)
    _ensure_can_view(order, current_user)
    return await _order_payload(db, order)


@router.post(
    "/{order_id}/cancel",
    response_model=MessageResponse,
    summary="Cancel a pending order",
    description=(
        "Only the order's owner may cancel it, and only while it is still "
        "`pending`. Paid orders must go through a refund request instead "
        "(handled by the payments module)."
    ),
)
async def cancel_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    order = await _get_order_or_404(db, order_id)
    if order.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to cancel this order.",
        )
    if order.status == OrderStatusEnum.PAID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Paid orders can only be canceled via a refund request.",
        )
    if order.status == OrderStatusEnum.CANCELED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order is already canceled.",
        )
    order.status = OrderStatusEnum.CANCELED
    await db.commit()
    return {"message": "Order canceled."}
