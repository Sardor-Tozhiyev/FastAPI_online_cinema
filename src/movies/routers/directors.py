from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.dependencies import require_moderator
from src.accounts.models import User
from src.accounts.schemas import MessageResponse
from src.database import get_db
from src.movies.models import Director
from src.movies.schemas import DirectorResponse, NamedEntityRequest


router = APIRouter(prefix="/api/v1/movies", tags=["directors"])


@router.get(
    "/directors",
    response_model=list[DirectorResponse],
    summary="List directors",
)
async def list_directors(
    db: AsyncSession = Depends(get_db),
) -> list[Director]:
    result = await db.execute(select(Director).order_by(Director.name))

    return list(result.scalars().all())


@router.post(
    "/directors",
    response_model=DirectorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[Moderator] Create a director",
)
async def create_director(
    payload: NamedEntityRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
) -> Director:
    existing = await db.execute(
        select(Director).where(Director.name == payload.name)
    )

    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Director already exists.",
        )

    director = Director(name=payload.name)

    db.add(director)
    await db.commit()
    await db.refresh(director)

    return director


@router.delete(
    "/directors/{director_id}",
    response_model=MessageResponse,
    summary="[Moderator] Delete a director",
)
async def delete_director(
    director_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
) -> dict:
    director = await db.get(Director, director_id)

    if director is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Director not found.",
        )

    await db.delete(director)
    await db.commit()

    return {"message": "Director deleted."}
