from datetime import datetime
from typing import TypeVar, Generic, List, Any

from pydantic import BaseModel, Field, ConfigDict, field_validator

ItemT = TypeVar("ItemT")


class PaginatedResponse(BaseModel, Generic[ItemT]):
    items: List[ItemT]
    total: int
    page: int
    per_page: int
    pages: int


class NamedEntityRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class GenreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class GenreWithCountResponse(BaseModel):
    id: int
    name: str
    movie_count: int


class StarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class DirectorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class CertificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class MovieCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    year: int = Field(ge=1888)
    time: int = Field(gt=0, description="Duration in minutes")
    imdb: float = Field(ge=0, le=10)
    votes: int = Field(ge=0, default=0)
    meta_score: float | None = Field(default=None, ge=0, le=100)
    gross: float | None = Field(default=None, ge=0)
    description: str = Field(min_length=1)
    price: float = Field(ge=0)
    certification_id: int
    genre_ids: list[int] = Field(default_factory=list)
    director_ids: list[int] = Field(default_factory=list)
    star_ids: list[int] = Field(default_factory=list)


class MovieUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    year: int | None = Field(default=None, ge=1888)
    time: int | None = Field(default=None, gt=0)
    imdb: float | None = Field(default=None, ge=0, le=10)
    votes: int | None = Field(default=None, ge=0)
    meta_score: float | None = Field(default=None, ge=0, le=100)
    gross: float | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, min_length=1)
    price: float | None = Field(default=None, ge=0)
    certification_id: int | None = None
    genre_ids: list[int] | None = None
    director_ids: list[int] | None = None
    star_ids: list[int] | None = None


class MovieListItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    uuid: str
    name: str
    year: int
    time: int
    imdb: float
    votes: int
    meta_score: float | None
    gross: float | None
    description: str
    price: float
    certification: CertificationResponse
    genres: list[GenreResponse] = Field(default_factory=list)
    directors: list[DirectorResponse] = Field(default_factory=list)
    stars: list[StarResponse] = Field(default_factory=list)
    likes_count: int = 0
    dislikes_count: int = 0
    average_rating: float | None = None
    rating_count: int = 0

    @field_validator("price", mode="before")
    @classmethod
    def _coerce_price(cls, value: Any) -> Any:
        return float(value) if value is not None else value


class ReactionRequest(BaseModel):
    is_like: bool


class RatingRequest(BaseModel):
    rating: int = Field(ge=1, le=10)


class RatingResponse(BaseModel):
    movie_id: int
    average_rating: float | None
    rating_count: int
    user_rating: int | None


class CommentCreateRequest(BaseModel):
    text: str = Field(min_length=1)
    parent_id: int | None = None


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    movie_id: int
    user_id: int
    parent_id: int | None
    text: str
    created_at: datetime
    likes_count: int = 0
    replies: list["CommentResponse"] = Field(default_factory=list)


CommentResponse.model_rebuild()
