from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.dependencies import require_moderator
from src.accounts.models import User
from src.accounts.schemas import MessageResponse
from src.database import get_db
from src.movies.models import Genre, MovieGenre
from src.movies.routers.movies import _list_movies
from src.movies.schemas import (
    GenreResponse,
    GenreWithCountResponse,
    MovieListItemResponse,
    NamedEntityRequest,
    PaginatedResponse,
)

router = APIRouter(prefix="/api/v1/movies/genres", tags=["genres"])


@router.get(
    "",
    response_model=list[GenreWithCountResponse],
    summary="List genres with the number of movies in each",
)
async def list_genres(db: AsyncSession = Depends(get_db)) -> list[dict]:
    result = await db.execute(
        select(Genre.id, Genre.name, func.count(MovieGenre.movie_id))
        .outerjoin(MovieGenre, MovieGenre.genre_id == Genre.id)
        .group_by(Genre.id)
        .order_by(Genre.name)
    )
    return [
        {"id": gid, "name": name, "movie_count": count}
        for gid, name, count in result.all()
    ]


@router.post(
    "",
    response_model=GenreResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[Moderator] Create a genre",
)
async def create_genre(
    payload: NamedEntityRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
) -> Genre:
    existing = await db.execute(
        select(Genre).where(Genre.name == payload.name)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Genre already exists."
        )
    genre = Genre(name=payload.name)
    db.add(genre)
    await db.commit()
    await db.refresh(genre)
    return genre


@router.put(
    "/{genre_id}",
    response_model=GenreResponse,
    summary="[Moderator] Rename a genre",
)
async def update_genre(
    genre_id: int,
    payload: NamedEntityRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
) -> Genre:
    genre = await db.get(Genre, genre_id)
    if genre is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Genre not found."
        )
    genre.name = payload.name
    await db.commit()
    await db.refresh(genre)
    return genre


@router.delete(
    "/{genre_id}",
    response_model=MessageResponse,
    summary="[Moderator] Delete a genre",
)
async def delete_genre(
    genre_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
) -> dict:
    genre = await db.get(Genre, genre_id)
    if genre is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Genre not found."
        )
    await db.delete(genre)
    await db.commit()
    return {"message": "Genre deleted."}


@router.get(
    "/{genre_id}/movies",
    response_model=PaginatedResponse[MovieListItemResponse],
    summary="List all movies belonging to a genre",
)
async def list_movies_by_genre(
    genre_id: int,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict:
    genre = await db.get(Genre, genre_id)
    if genre is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Genre not found."
        )
    return await _list_movies(
        db, page=page, per_page=per_page, genre_id=genre_id
    )
