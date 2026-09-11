from enum import Enum
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.accounts.dependencies import require_moderator
from src.accounts.models import User
from src.accounts.schemas import MessageResponse
from src.database import get_db
from src.movies.models import (
    Certification,
    Director,
    Genre,
    Movie,
    MovieDirector,
    MovieGenre,
    MovieRating,
    MovieReaction,
    MovieStar,
    Star,
)
from src.movies.schemas import (
    CertificationResponse,
    MovieCreateRequest,
    MovieDetailResponse,
    MovieListItemResponse,
    MovieUpdateRequest,
    NamedEntityRequest,
    PaginatedResponse,
)

router = APIRouter(prefix="/api/v1/movies", tags=["movies"])


# --- Sorting / pagination helpers ---------------------------------------------


class SortField(str, Enum):
    price = "price"
    year = "year"
    popularity = "popularity"
    imdb = "imdb"


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


def _paginate(page: int, per_page: int) -> tuple[int, int]:
    offset = (page - 1) * per_page
    return offset, per_page


async def _list_movies(
    db: AsyncSession,
    *,
    page: int,
    per_page: int,
    search: str | None = None,
    year: int | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    imdb_min: float | None = None,
    imdb_max: float | None = None,
    genre_id: int | None = None,
    sort_by: SortField | None = None,
    order: SortOrder = SortOrder.desc,
    movie_ids: list[int] | None = None,
) -> dict:
    """Shared catalog query used by the main listing, genre listing, and
    favorites listing (routers.genres / routers.interactions import this)."""

    base_query = select(Movie.id).distinct()
    filters = []

    if movie_ids is not None:
        filters.append(Movie.id.in_(movie_ids))
    if year is not None:
        filters.append(Movie.year == year)
    if year_from is not None:
        filters.append(Movie.year >= year_from)
    if year_to is not None:
        filters.append(Movie.year <= year_to)
    if imdb_min is not None:
        filters.append(Movie.imdb >= imdb_min)
    if imdb_max is not None:
        filters.append(Movie.imdb <= imdb_max)

    if genre_id is not None:
        base_query = base_query.join(
            MovieGenre, MovieGenre.movie_id == Movie.id
        ).where(MovieGenre.genre_id == genre_id)

    if search:
        pattern = f"%{search}%"
        base_query = (
            base_query.outerjoin(
                MovieDirector, MovieDirector.movie_id == Movie.id
            )
            .outerjoin(Director, Director.id == MovieDirector.director_id)
            .outerjoin(MovieStar, MovieStar.movie_id == Movie.id)
            .outerjoin(Star, Star.id == MovieStar.star_id)
            .where(
                or_(
                    Movie.name.ilike(pattern),
                    Movie.description.ilike(pattern),
                    Director.name.ilike(pattern),
                    Star.name.ilike(pattern),
                )
            )
        )

    if filters:
        base_query = base_query.where(and_(*filters))

    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    sort_column = {
        SortField.price: Movie.price,
        SortField.year: Movie.year,
        SortField.popularity: Movie.votes,
        SortField.imdb: Movie.imdb,
    }.get(sort_by or SortField.year, Movie.year)

    order_clause = (
        sort_column.asc() if order == SortOrder.asc else sort_column.desc()
    )

    offset, limit = _paginate(page, per_page)
    id_query = (
        base_query.order_by(order_clause, Movie.id.desc())
        .offset(offset)
        .limit(limit)
    )
    ordered_ids = [row[0] for row in (await db.execute(id_query)).all()]

    if not ordered_ids:
        movies: list[Movie] = []
    else:
        result = await db.execute(
            select(Movie)
            .options(selectinload(Movie.genres))
            .where(Movie.id.in_(ordered_ids))
        )
        by_id = {m.id: m for m in result.scalars().all()}
        movies = [by_id[mid] for mid in ordered_ids if mid in by_id]

    return {
        "items": movies,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": ceil(total / per_page) if per_page else 0,
    }


async def _get_movie_or_404(db: AsyncSession, movie_id: int) -> Movie:
    result = await db.execute(
        select(Movie)
        .options(
            selectinload(Movie.certification),
            selectinload(Movie.genres),
            selectinload(Movie.directors),
            selectinload(Movie.stars),
        )
        .where(Movie.id == movie_id)
    )
    movie = result.scalar_one_or_none()
    if movie is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Movie not found."
        )
    return movie


async def _movie_detail_payload(db: AsyncSession, movie: Movie) -> dict:
    likes_result = await db.execute(
        select(MovieReaction.is_like, func.count())
        .where(MovieReaction.movie_id == movie.id)
        .group_by(MovieReaction.is_like)
    )
    likes_count = 0
    dislikes_count = 0
    for is_like, count in likes_result.all():
        if is_like:
            likes_count = count
        else:
            dislikes_count = count

    rating_result = await db.execute(
        select(func.avg(MovieRating.rating), func.count(MovieRating.id)).where(
            MovieRating.movie_id == movie.id
        )
    )
    avg_rating, ratings_count = rating_result.one()

    return {
        "id": movie.id,
        "uuid": movie.uuid,
        "name": movie.name,
        "year": movie.year,
        "time": movie.time,
        "imdb": movie.imdb,
        "votes": movie.votes,
        "meta_score": movie.meta_score,
        "gross": movie.gross,
        "description": movie.description,
        "price": movie.price,
        "certification": movie.certification,
        "genres": movie.genres,
        "directors": movie.directors,
        "stars": movie.stars,
        "likes_count": likes_count,
        "dislikes_count": dislikes_count,
        "average_rating": (
            round(float(avg_rating), 2) if avg_rating is not None else None
        ),
        "ratings_count": ratings_count or 0,
    }


async def _resolve_related(
    db: AsyncSession, model, ids: list[int], label: str
) -> list:
    if not ids:
        return []
    result = await db.execute(select(model).where(model.id.in_(ids)))
    found = list(result.scalars().all())
    if len(found) != len(set(ids)):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"One or more {label} ids do not exist.",
        )
    return found


# --- Certifications ------------------------------------------------------------


@router.get(
    "/certifications",
    response_model=list[CertificationResponse],
    summary="List certifications",
)
async def list_certifications(
    db: AsyncSession = Depends(get_db),
) -> list[Certification]:
    result = await db.execute(
        select(Certification).order_by(Certification.name)
    )
    return list(result.scalars().all())


@router.post(
    "/certifications",
    response_model=CertificationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[Moderator] Create a certification",
)
async def create_certification(
    payload: NamedEntityRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
) -> Certification:
    existing = await db.execute(
        select(Certification).where(Certification.name == payload.name)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Certification already exists."
        )
    certification = Certification(name=payload.name)
    db.add(certification)
    await db.commit()
    await db.refresh(certification)
    return certification


# --- Movie catalog ---------------------------------------------------------------


@router.get(
    "",
    response_model=PaginatedResponse[MovieListItemResponse],
    summary="Browse the movie catalog",
    description=(
        "Paginated movie catalog with optional `search` (title, description, "
        "actor, director), filtering by `year`/`year_from`/`year_to`/"
        "`imdb_min`/`imdb_max`/`genre_id`, and sorting by `sort_by` "
        "(price, year, popularity, imdb) with `order` (asc/desc)."
    ),
)
async def list_movies(
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
    db: AsyncSession = Depends(get_db),
) -> dict:
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
    )


@router.get(
    "/{movie_id}",
    response_model=MovieDetailResponse,
    summary="Get full details of a single movie",
)
async def get_movie(
    movie_id: int, db: AsyncSession = Depends(get_db)
) -> dict:
    movie = await _get_movie_or_404(db, movie_id)
    return await _movie_detail_payload(db, movie)


@router.post(
    "",
    response_model=MovieDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[Moderator] Create a movie",
)
async def create_movie(
    payload: MovieCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
) -> dict:
    certification = await db.get(Certification, payload.certification_id)
    if certification is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Certification not found."
        )

    duplicate = await db.execute(
        select(Movie).where(
            Movie.name == payload.name,
            Movie.year == payload.year,
            Movie.time == payload.time,
        )
    )
    if duplicate.scalar_one_or_none() is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="A movie with this name, year and duration already exists.",
        )

    genres = await _resolve_related(db, Genre, payload.genre_ids, "genre")
    directors = await _resolve_related(
        db, Director, payload.director_ids, "director"
    )
    stars = await _resolve_related(db, Star, payload.star_ids, "star")

    movie = Movie(
        name=payload.name,
        year=payload.year,
        time=payload.time,
        imdb=payload.imdb,
        votes=payload.votes,
        meta_score=payload.meta_score,
        gross=payload.gross,
        description=payload.description,
        price=payload.price,
        certification=certification,
        genres=genres,
        directors=directors,
        stars=stars,
    )
    db.add(movie)
    await db.commit()
    await db.refresh(movie)
    movie = await _get_movie_or_404(db, movie.id)
    return await _movie_detail_payload(db, movie)


@router.put(
    "/{movie_id}",
    response_model=MovieDetailResponse,
    summary="[Moderator] Update a movie",
)
async def update_movie(
    movie_id: int,
    payload: MovieUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
) -> dict:
    movie = await _get_movie_or_404(db, movie_id)
    data = payload.model_dump(exclude_unset=True)

    if "certification_id" in data:
        certification = await db.get(
            Certification, data.pop("certification_id")
        )
        if certification is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="Certification not found."
            )
        movie.certification = certification

    if "genre_ids" in data:
        movie.genres = await _resolve_related(
            db, Genre, data.pop("genre_ids") or [], "genre"
        )
    if "director_ids" in data:
        movie.directors = await _resolve_related(
            db, Director, data.pop("director_ids") or [], "director"
        )
    if "star_ids" in data:
        movie.stars = await _resolve_related(
            db, Star, data.pop("star_ids") or [], "star"
        )

    for field, value in data.items():
        setattr(movie, field, value)

    await db.commit()
    movie = await _get_movie_or_404(db, movie_id)
    return await _movie_detail_payload(db, movie)


@router.delete(
    "/{movie_id}",
    response_model=MessageResponse,
    summary="[Moderator] Delete a movie",
    description=(
        "Deletes a movie, unless it has already been purchased by at least "
        "one user (enforced once the orders module tracks purchases)."
    ),
)
async def delete_movie(
    movie_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
) -> dict:
    movie = await db.get(Movie, movie_id)
    if movie is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Movie not found."
        )
    # movie with a paid order, and notify moderators of pending cart items.
    await db.delete(movie)
    await db.commit()
    return {"message": "Movie deleted."}
