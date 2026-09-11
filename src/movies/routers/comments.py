from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.accounts.dependencies import get_current_user
from src.accounts.models import User
from src.accounts.schemas import MessageResponse
from src.database import get_db
from src.movies.models import (
    Comment,
    CommentLike,
    Movie,
)
from src.movies.notifications import (
    send_comment_like_email,
    send_comment_reply_email,
)
from src.movies.routers.movies import _get_movie_or_404
from src.movies.schemas import (
    CommentCreateRequest,
    CommentResponse,
)


router = APIRouter(prefix="/api/v1/movies", tags=["comments"])


def _comment_to_response(
    comment: Comment,
    likes_by_id: dict[int, int],
) -> dict:
    return {
        "id": comment.id,
        "movie_id": comment.movie_id,
        "user_id": comment.user_id,
        "parent_id": comment.parent_id,
        "text": comment.text,
        "created_at": comment.created_at,
        "likes_count": likes_by_id.get(comment.id, 0),
        "replies": [
            _comment_to_response(reply, likes_by_id)
            for reply in sorted(
                comment.replies,
                key=lambda item: item.created_at,
            )
        ],
    }


@router.get(
    "/{movie_id}/comments",
    response_model=list[CommentResponse],
    summary="List top-level comments with nested replies",
)
async def list_comments(
    movie_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await _get_movie_or_404(db, movie_id)

    result = await db.execute(
        select(Comment)
        .options(selectinload(Comment.replies))
        .where(
            Comment.movie_id == movie_id,
            Comment.parent_id.is_(None),
        )
        .order_by(Comment.created_at.desc())
    )

    top_level = list(result.scalars().all())

    likes_result = await db.execute(
        select(
            CommentLike.comment_id,
            func.count(),
        )
        .join(
            Comment,
            Comment.id == CommentLike.comment_id,
        )
        .where(Comment.movie_id == movie_id)
        .group_by(CommentLike.comment_id)
    )

    likes_by_id = {
        comment_id: count
        for comment_id, count in likes_result.all()
    }

    return [
        _comment_to_response(comment, likes_by_id)
        for comment in top_level
    ]


@router.post(
    "/{movie_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Post a comment on a movie",
)
async def create_comment(
    movie_id: int,
    payload: CommentCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    movie = await _get_movie_or_404(db, movie_id)

    parent: Comment | None = None

    if payload.parent_id is not None:
        parent = await db.get(
            Comment,
            payload.parent_id,
        )

        if parent is None or parent.movie_id != movie_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Parent comment not found on this movie.",
            )

    comment = Comment(
        movie_id=movie_id,
        user_id=current_user.id,
        parent_id=payload.parent_id,
        text=payload.text,
    )

    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    if parent is not None and parent.user_id != current_user.id:
        parent_author = await db.get(
            User,
            parent.user_id,
        )

        if parent_author is not None:
            send_comment_reply_email(
                parent_author.email,
                movie.name,
                payload.text,
            )

    return _comment_to_response(comment, {})


@router.delete(
    "/comments/{comment_id}",
    response_model=MessageResponse,
    summary="Delete a comment",
)
async def delete_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    comment = await db.get(
        Comment,
        comment_id,
    )

    if comment is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Comment not found.",
        )

    is_owner = comment.user_id == current_user.id
    is_privileged = current_user.group.name in {
        "MODERATOR",
        "ADMIN",
    }

    if not (is_owner or is_privileged):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this comment.",
        )

    await db.delete(comment)
    await db.commit()

    return {"message": "Comment deleted."}


@router.post(
    "/comments/{comment_id}/like",
    response_model=MessageResponse,
    summary="Like a comment",
)
async def like_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    comment = await db.get(
        Comment,
        comment_id,
    )

    if comment is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Comment not found.",
        )

    existing = await db.execute(
        select(CommentLike).where(
            CommentLike.comment_id == comment_id,
            CommentLike.user_id == current_user.id,
        )
    )

    if existing.scalar_one_or_none() is None:
        db.add(
            CommentLike(
                comment_id=comment_id,
                user_id=current_user.id,
            )
        )

        await db.commit()

        if comment.user_id != current_user.id:
            author = await db.get(
                User,
                comment.user_id,
            )

            movie = await db.get(
                Movie,
                comment.movie_id,
            )

            if author is not None and movie is not None:
                send_comment_like_email(
                    author.email,
                    movie.name,
                )

    return {"message": "Comment liked."}


@router.delete(
    "/comments/{comment_id}/like",
    response_model=MessageResponse,
    summary="Remove your like from a comment",
)
async def unlike_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await db.execute(
        delete(CommentLike).where(
            CommentLike.comment_id == comment_id,
            CommentLike.user_id == current_user.id,
        )
    )

    await db.commit()

    return {"message": "Comment like removed."}
