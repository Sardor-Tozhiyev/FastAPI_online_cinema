from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.accounts.dependencies import get_current_user, require_moderator
from src.accounts.models import User
from src.accounts.schemas import MessageResponse
from src.cart.models import Cart, CartItem
from src.cart.schemas import CartResponse, CartSummaryResponse
from src.database import get_db
from src.movies.models import Movie

router = APIRouter(prefix="/api/v1/cart", tags=["cart"])


async def _get_or_create_cart(db: AsyncSession, user_id: int) -> Cart:
    result = await db.execute(select(Cart).where(Cart.user_id == user_id))
    cart = result.scalar_one_or_none()
    if cart is not None:
        return cart

    cart = Cart(user_id=user_id)
    db.add(cart)
    await db.commit()
    await db.refresh(cart)
    return cart


async def _cart_items_payload(db: AsyncSession, cart_id: int) -> list[dict]:
    result = await db.execute(
        select(CartItem)
        .options(selectinload(CartItem.movie).selectinload(Movie.genres))
        .where(CartItem.cart_id == cart_id)
        .order_by(CartItem.added_at.desc())
    )
    items = list(result.scalars().all())
    return [
        {
            "id": item.id,
            "movie_id": item.movie.id,
            "name": item.movie.name,
            "price": item.movie.price,
            "year": item.movie.year,
            "genres": [g.name for g in item.movie.genres],
            "added_at": item.added_at,
        }
        for item in items
    ]


def _summarize(items: list[dict]) -> tuple[float, int]:
    total = sum(
        (item["price"] for item in items),
        Decimal("0.00"),
    )
    return float(total), len(items)


@router.get(
    "", response_model=CartResponse, summary="View the current user's cart"
)
async def get_cart(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cart = await _get_or_create_cart(db, current_user.id)
    items = await _cart_items_payload(db, cart.id)
    total_price, item_count = _summarize(items)
    return {
        "id": cart.id,
        "user_id": cart.user_id,
        "items": items,
        "total_price": total_price,
        "item_count": item_count,
    }


@router.post(
    "/items/{movie_id}/",
    response_model=CartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a movie to the cart",
    description=(
        "Fails with 404 if the movie doesn't exist and 409 if it is "
        "already in the cart. Checking that the movie hasn't already "
        "been purchased will be enforced once the orders module tracks "
        "purchases."
    ),
)
async def add_to_cart(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    movie = await db.get(Movie, movie_id)
    if movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie not found.",
        )
    cart = await _get_or_create_cart(db, current_user.id)
    existing = await db.execute(
        select(CartItem).where(
            CartItem.cart_id == cart.id,
            CartItem.movie_id == movie.id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This movie is already in your cart.",
        )

    db.add(CartItem(cart_id=cart.id, movie_id=movie.id))
    await db.commit()

    items = await _cart_items_payload(db, cart.id)
    total_price, item_count = _summarize(items)
    return {
        "id": cart.id,
        "user_id": cart.user_id,
        "items": items,
        "total_price": total_price,
        "item_count": item_count,
    }


@router.delete(
    "/items/{movie_id}/",
    response_model=MessageResponse,
    summary="Remove a movie from the cart",
)
async def remove_from_cart(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cart = await _get_or_create_cart(db, current_user.id)
    await db.execute(
        delete(CartItem).where(
            CartItem.cart_id == cart.id,
            CartItem.movie_id == movie_id,
        )
    )
    await db.commit()
    return {"message": "Movie removed from cart."}


@router.delete(
    "",
    response_model=MessageResponse,
    summary="Clear the entire cart",
)
async def clear_cart(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cart = await _get_or_create_cart(db, current_user.id)
    await db.execute(
        delete(CartItem).where(
            CartItem.cart_id == cart.id,
        )
    )
    await db.commit()
    return {"message": "Cart cleared."}


@router.get(
    "/users/{user_id}/",
    response_model=CartSummaryResponse,
    summary="[Moderator] View another user's cart",
)
async def get_user_cart(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
) -> dict:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    result = await db.execute(
        select(Cart).where(
            Cart.user_id == user.id,
        )
    )
    cart = result.scalar_one_or_none()
    items = await _cart_items_payload(db, cart.id) if cart else []
    total_price, item_count = _summarize(items)
    return {
        "user_id": user.id,
        "item_count": item_count,
        "total_price": total_price,
        "items": items,
    }
