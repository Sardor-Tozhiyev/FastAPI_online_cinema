from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class CartItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    movie_id: int
    name: str
    price: Decimal
    year: int
    genres: list[str] = []
    added_at: datetime

    @field_validator("price", mode="before")
    @classmethod
    def _coerce_price(cls, value: Any) -> Any:
        return float(value) if value is not None else value


class CartResponse(BaseModel):
    id: int
    user_id: int
    items: list[CartItemResponse]
    total_price: Decimal
    item_count: int


class CartSummaryResponse(BaseModel):
    """Lightweight cart view used in the moderator listing endpoint."""

    user_id: int
    item_count: int
    total_price: Decimal
    items: list[CartItemResponse]
