import enum
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import ForeignKey, DateTime, Enum, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class PaymentStatusEnum(enum.Enum):
    SUCCESSFUL = "SUCCESSFUL"
    CANCELED = "CANCELED"
    REFUNDED = "REFUNDED"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    status: Mapped[PaymentStatusEnum] = mapped_column(
        Enum(PaymentStatusEnum),
        nullable=False,
        default=PaymentStatusEnum.SUCCESSFUL,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    external_payment_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    items: Mapped[list["PaymentItem"]] = relationship(
        back_populates="payment",
        cascade="all, delete-orphan",
    )


class PaymentItem(Base):
    __tablename__ = "payment_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False
    )
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id", ondelete="CASCADE"),
        nullable=False
    )
    price_at_payment: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    payment: Mapped["Payment"] = relationship(back_populates="items")
    order_item: Mapped["OrderItem"] = relationship()
