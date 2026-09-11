from fastapi import APIRouter, Depends
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.dependencies import get_current_user
from src.accounts.models import User
from src.accounts.schemas import MessageResponse
from src.database import get_db
from src.movies.models import (
    Favorite,
    MovieRating,
    MovieReaction,
)
from src.movies.routers.movies import (
    _get_movie_or_404,
    _list_movies,
    SortField,
    SortOrder,
)
from src.movies.schemas import (
    MovieListItemResponse,
    PaginatedResponse,
    RatingRequest,
    RatingResponse,
    ReactionRequest,
)


router = APIRouter(prefix="/api/v1/movies", tags=["interactions"])


@router.get(
    "/favorites",
    response_model=PaginatedResponse[MovieListItemResponse],
    summary="List the current user's favorite movies",
)
async def list_favorites(
    page: int = 1,
    per_page: int = 20,
    search: str | None = None,
    year: int | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    imdb_min: float | None = None,
    imdb_max: float | None = None,
    genre_id: int | None = None,
    sort_by: SortField | None = None,
    order: SortOrder = SortOrder.desc,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    favorite_result = await db.execute(
        select(Favorite.movie_id).where(Favorite.user_id == current_user.id)
    )

    favorite_ids = [row[0] for row in favorite_result.all()]

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

    aggregation = await db.execute(
        select(
            func.avg(MovieRating.rating),
            func.count(MovieRating.id),
        ).where(MovieRating.movie_id == movie_id)
    )

    avg_rating, count = aggregation.one()

    return {
        "movie_id": movie_id,
        "average_rating": (
            round(float(avg_rating), 2) if avg_rating is not None else None
        ),
        "ratings_count": count or 0,
        "user_rating": payload.rating,
    }


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

    result = await db.execute(
        select(Favorite).where(
            Favorite.movie_id == movie_id,
            Favorite.user_id == current_user.id,
        )
    )

    if result.scalar_one_or_none() is None:
        db.add(
            Favorite(
                movie_id=movie_id,
                user_id=current_user.id,
            )
        )

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
