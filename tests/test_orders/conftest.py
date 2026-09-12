from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Re-exported so pytest picks up shared fixtures/helpers for this directory.
from tests.test_cart.conftest import create_movie  # noqa: F401
from tests.test_movies.conftest import (  # noqa: F401
    certification,
    create_user_headers,
)


async def add_to_cart(
    client: AsyncClient, headers: dict[str, str], movie_id: int
) -> None:
    response = await client.post(
        f"/api/v1/cart/items/{movie_id}", headers=headers
    )
    assert response.status_code == 201, response.text


async def mark_order_paid(db_session: AsyncSession, order_id: int) -> None:
    """Test-only shortcut: the real payments module isn't built yet, so
    this simulates a successful checkout by flipping the order's status
    directly in the DB."""
    from src.orders.models import Order, OrderStatusEnum

    order = (
        await db_session.execute(select(Order).where(Order.id == order_id))
    ).scalar_one()
    order.status = OrderStatusEnum.PAID
    await db_session.commit()
