import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    String,
    ForeignKey,
    UniqueConstraint,
    Integer,
    Text,
    Numeric,
    Boolean,
    DateTime,
)
from sqlalchemy.dialects.postgresql.base import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    movies: Mapped[list["Movie"]] = relationship(
        secondary="movie_genres", back_populates="genres"
    )


class Star(Base):
    __tablename__ = "stars"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    movies: Mapped[list["Movie"]] = relationship(
        secondary="movie_stars", back_populates="stars"
    )


class Director(Base):
    __tablename__ = "directors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    movies: Mapped[list["Movie"]] = relationship(
        secondary="movie_directors", back_populates="directors"
    )


class Certification(Base):
    __tablename__ = "certifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    movies: Mapped[list["Movie"]] = relationship(
        back_populates="certification"
    )


class MovieGenre(Base):
    __tablename__ = "movie_genres"

    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True
    )
    genre_id: Mapped[int] = mapped_column(
        ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True
    )


class MovieDirector(Base):
    __tablename__ = "movie_directors"

    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True
    )
    director_id: Mapped[int] = mapped_column(
        ForeignKey("directors.id", ondelete="CASCADE"), primary_key=True
    )


class MovieStar(Base):
    __tablename__ = "movie_stars"

    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True
    )
    star_id: Mapped[int] = mapped_column(
        ForeignKey("stars.id", ondelete="CASCADE"), primary_key=True
    )


class Movie(Base):
    __tablename__ = "movies"
    __table_args__ = (
        UniqueConstraint(
            "name", "year", "time", name="uq_movies_name_year_time"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(
        UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        unique=True,
        nullable=False,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    time: Mapped[int] = mapped_column(Integer, nullable=False)
    imdb: Mapped[float] = mapped_column(nullable=False)
    votes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    meta_score: Mapped[float | None] = mapped_column(nullable=True)
    gross: Mapped[float | None] = mapped_column(nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    certification_id: Mapped[int] = mapped_column(
        ForeignKey("certifications.id"), nullable=False
    )
    certification: Mapped["Certification"] = relationship(
        back_populates="movies",
    )
    genres: Mapped[list["Genre"]] = relationship(
        secondary="movie_genres",
        back_populates="movies",
    )
    directors: Mapped[list["Director"]] = relationship(
        secondary="movie_directors",
        back_populates="movies",
    )
    stars: Mapped[list["Star"]] = relationship(
        secondary="movie_stars",
        back_populates="movies",
    )
    reactions: Mapped[list["MovieReaction"]] = relationship(
        back_populates="movie",
        cascade="all, delete-orphan",
    )
    ratings: Mapped[list["MovieRating"]] = relationship(
        back_populates="movie",
        cascade="all, delete-orphan",
    )
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="movie",
        cascade="all, delete-orphan",
    )
    favorited_by: Mapped[list["Favorite"]] = relationship(
        back_populates="movie",
        cascade="all, delete-orphan",
    )


class MovieReaction(Base):
    """A user's like or dislike on a movie. One reaction per user/movie."""

    __tablename__ = "movie_reactions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "movie_id", name="uq_movie_reactions_user_movie"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), nullable=False
    )
    is_like: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    movie: Mapped["Movie"] = relationship(back_populates="reactions")


class MovieRating(Base):
    """A user's 1-10 rating for a movie. One rating per user/movie."""

    __tablename__ = "movie_ratings"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "movie_id", name="uq_movie_ratings_user_movie"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[float] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    movie: Mapped["Movie"] = relationship(back_populates="ratings")


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "movie_id", name="uq_favorites_user_movie"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    movie: Mapped["Movie"] = relationship(back_populates="favorited_by")


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[int] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    movie: Mapped["Movie"] = relationship(back_populates="comments")
    parent: Mapped["Comment | None"] = relationship(
        remote_side="Comment.id",
        back_populates="replies",
    )
    replies: Mapped[list["Comment"]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    likes: Mapped[list["CommentLike"]] = relationship(
        back_populates="comment",
        cascade="all, delete-orphan",
    )


class CommentLike(Base):
    __tablename__ = "comment_likes"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "comment_id", name="uq_comment_likes_user_comment"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    comment_id: Mapped[int] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    comment: Mapped["Comment"] = relationship(back_populates="likes")
