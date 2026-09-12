import enum
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base
from src.movies.models import Movie


class OrderStatusEnum(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    CANCELED = "canceled"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    status: Mapped[OrderStatusEnum] = mapped_column(
        Enum(OrderStatusEnum),
        nullable=False,
        default=OrderStatusEnum.PENDING,
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"),
        nullable=False,
    )
    price_at_order: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    order: Mapped["Order"] = relationship(back_populates="items")
    movie: Mapped["Movie"] = relationship()
