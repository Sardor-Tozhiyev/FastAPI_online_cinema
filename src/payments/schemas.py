from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from payments.models import PaymentStatusEnum


class CheckoutSessionResponse(BaseModel):
    checkout_url: str
    session_id: str


class PaymentItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    movie_id: int
    name: str
    price_at_payment: float

    @field_validator("price_at_payment", mode="before")
    @classmethod
    def _coerce_price_at_payment(cls, value: Any) -> Any:
        return float(str(value)) if value is not None else value


class PaymentResponse(BaseModel):
    id: int
    user_id: int
    order_id: int
    created_at: datetime
    status: PaymentStatusEnum
    amount: float
    external_payment_id: str | None
    items: list[PaymentItemResponse]

    @field_validator("amount", mode="before")
    @classmethod
    def _coerce_amount(cls, value: Any) -> Any:
        return float(str(value)) if value is not None else value
