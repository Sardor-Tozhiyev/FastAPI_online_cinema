from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.dependencies import require_moderator
from src.accounts.models import User
from src.accounts.schemas import MessageResponse
from src.database import get_db
from src.movies.models import Star
from src.movies.schemas import NamedEntityRequest, StarResponse


router = APIRouter(prefix="/api/v1/movies", tags=["stars"])


@router.get(
    "/stars",
    response_model=list[StarResponse],
    summary="List actors/stars",
)
async def list_stars(
    db: AsyncSession = Depends(get_db),
) -> list[Star]:
    result = await db.execute(
        select(Star).order_by(Star.name)
    )

    return list(result.scalars().all())


@router.post(
    "/stars",
    response_model=StarResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[Moderator] Create a star",
)
async def create_star(
    payload: NamedEntityRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
) -> Star:
    existing = await db.execute(
        select(Star).where(Star.name == payload.name)
    )

    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Star already exists.",
        )

    star = Star(name=payload.name)

    db.add(star)
    await db.commit()
    await db.refresh(star)

    return star


@router.delete(
    "/stars/{star_id}",
    response_model=MessageResponse,
    summary="[Moderator] Delete a star",
)
async def delete_star(
    star_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
) -> dict:
    star = await db.get(Star, star_id)

    if star is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Star not found.",
        )

    await db.delete(star)
    await db.commit()

    return {"message": "Star deleted."}
