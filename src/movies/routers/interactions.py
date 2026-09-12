from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.dependencies import get_current_user
from src.accounts.models import User
from src.accounts.schemas import MessageResponse
from src.database import get_db
from src.movies.models import Favorite, MovieRating, MovieReaction
from src.movies.routers.movies import (
    SortField,
    SortOrder,
    _get_movie_or_404,
    _list_movies,
)
from src.movies.schemas import (
    MovieListItemResponse,
    PaginatedResponse,
    RatingRequest,
    RatingResponse,
    ReactionRequest,
)

router = APIRouter(prefix="/api/v1/movies", tags=["movie interactions"])


# --- Favorites (listing) -------------------------------------------------
# NOTE: this literal route ("/favorites") must be registered before
# routers.movies' "/{movie_id}" route or the latter will shadow it. See
# the include order in src/movies/routers/__init__.py.


@router.get(
    "/favorites",
    response_model=PaginatedResponse[MovieListItemResponse],
    summary="List the current user's favorite movies",
    description=(
        "Supports the same `search`/filter/`sort_by` parameters as the main "
        "catalog, scoped to the current user's favorites."
    ),
)
async def list_favorites(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    year: int | None = Query(default=None),
    year_from: int | None = Query(default=None),
    year_to: int | None = Query(default=None),
    imdb_min: float | None = Query(default=None, ge=0, le=10),
    imdb_max: float | None = Query(default=None, ge=0, le=10),
    genre_id: int | None = Query(default=None),
    sort_by: SortField | None = Query(default=None),
    order: SortOrder = Query(default=SortOrder.desc),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    fav_result = await db.execute(
        select(Favorite.movie_id).where(Favorite.user_id == current_user.id)
    )
    favorite_ids = [row[0] for row in fav_result.all()]
    if not favorite_ids:
        return {
            "items": [],
            "total": 0,
            "page": page,
            "per_page": per_page,
            "pages": 0,
        }
    return await _list_movies(
        db,
        page=page,
        per_page=per_page,
        search=search,
        year=year,
        year_from=year_from,
        year_to=year_to,
        imdb_min=imdb_min,
        imdb_max=imdb_max,
        genre_id=genre_id,
        sort_by=sort_by,
        order=order,
        movie_ids=favorite_ids,
    )


@router.post(
    "/{movie_id}/favorite",
    response_model=MessageResponse,
    summary="Add a movie to favorites",
)
async def add_favorite(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_movie_or_404(db, movie_id)
    existing = await db.execute(
        select(Favorite).where(
            Favorite.movie_id == movie_id,
            Favorite.user_id == current_user.id,
        )
    )
    if existing.scalar_one_or_none() is None:
        db.add(Favorite(movie_id=movie_id, user_id=current_user.id))
        await db.commit()
    return {"message": "Movie added to favorites."}


@router.delete(
    "/{movie_id}/favorite",
    response_model=MessageResponse,
    summary="Remove a movie from favorites",
)
async def remove_favorite(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await db.execute(
        delete(Favorite).where(
            Favorite.movie_id == movie_id,
            Favorite.user_id == current_user.id,
        )
    )
    await db.commit()
    return {"message": "Movie removed from favorites."}


# --- Reactions (like / dislike) -------------------------------------------


@router.put(
    "/{movie_id}/reaction",
    response_model=MessageResponse,
    summary="Like or dislike a movie",
)
async def set_reaction(
    movie_id: int,
    payload: ReactionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_movie_or_404(db, movie_id)

    result = await db.execute(
        select(MovieReaction).where(
            MovieReaction.movie_id == movie_id,
            MovieReaction.user_id == current_user.id,
        )
    )
    reaction = result.scalar_one_or_none()
    if reaction is not None:
        reaction.is_like = payload.is_like
    else:
        db.add(
            MovieReaction(
                movie_id=movie_id,
                user_id=current_user.id,
                is_like=payload.is_like,
            )
        )
    await db.commit()
    return {"message": "Reaction saved."}


@router.delete(
    "/{movie_id}/reaction",
    response_model=MessageResponse,
    summary="Remove your like/dislike from a movie",
)
async def remove_reaction(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await db.execute(
        delete(MovieReaction).where(
            MovieReaction.movie_id == movie_id,
            MovieReaction.user_id == current_user.id,
        )
    )
    await db.commit()
    return {"message": "Reaction removed."}


# --- Ratings ----------------------------------------------------------------


@router.put(
    "/{movie_id}/rating",
    response_model=RatingResponse,
    summary="Rate a movie on a 10-point scale",
)
async def rate_movie(
    movie_id: int,
    payload: RatingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_movie_or_404(db, movie_id)

    result = await db.execute(
        select(MovieRating).where(
            MovieRating.movie_id == movie_id,
            MovieRating.user_id == current_user.id,
        )
    )
    rating = result.scalar_one_or_none()
    if rating is not None:
        rating.rating = payload.rating
    else:
        db.add(
            MovieRating(
                movie_id=movie_id,
                user_id=current_user.id,
                rating=payload.rating,
            )
        )
    await db.commit()

    agg = await db.execute(
        select(func.avg(MovieRating.rating), func.count(MovieRating.id)).where(
            MovieRating.movie_id == movie_id
        )
    )
    avg_rating, count = agg.one()
    return {
        "movie_id": movie_id,
        "average_rating": (
            round(float(avg_rating), 2) if avg_rating is not None else None
        ),
        "ratings_count": count or 0,
        "user_rating": payload.rating,
    }
