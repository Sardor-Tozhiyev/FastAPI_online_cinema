from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from src.orders.models import OrderStatusEnum


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    movie_id: int
    name: str
    price_at_order: Decimal

    @field_validator("price_at_order", mode="before")
    @classmethod
    def _coerce_price(cls, value: Decimal) -> Decimal | None:
        return Decimal(str(value)) if value is not None else value


class OrderResponse(BaseModel):
    id: int
    user_id: int
    created_at: datetime
    status: OrderStatusEnum
    total_amount: Decimal | None
    items: list[OrderItemResponse]

    @field_validator("total_amount", mode="before")
    @classmethod
    def _coerce_total_amount(cls, value: Decimal) -> Decimal | None:
        return Decimal(str(value)) if value is not None else value


class ExcludeMovieResponse(BaseModel):
    movie_id: int
    name: str
    reason: str


class OrderCreateResponse(BaseModel):
    order: OrderResponse
    excluded: list[ExcludeMovieResponse] = []


class OrderListItemResponse(BaseModel):
    id: int
    created_at: datetime
    status: OrderStatusEnum
    total_amount: Decimal | None
    movie_count: int

    @field_validator("total_amount", mode="before")
    @classmethod
    def _coerce_total_amount(cls, value: Decimal) -> Decimal | None:
        return Decimal(str(value)) if value is not None else value
