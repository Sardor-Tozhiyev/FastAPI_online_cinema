"""add_order

Revision ID: 6ec148d1ad23
Revises: c34765f1b345
Create Date: 2026-09-13 13:11:20.705673

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6ec148d1ad23"
down_revision: Union[str, Sequence[str], None] = "c34765f1b345"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "PAID",
                "CANCELED",
                name="orderstatusenum",
            ),
            nullable=False,
        ),
        sa.Column(
            "total_amount",
            sa.Numeric(precision=10, scale=2),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("movie_id", sa.Integer(), nullable=False),
        sa.Column(
            "price_at_order",
            sa.Numeric(precision=10, scale=2),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["movie_id"],
            ["movies.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("order_items")
    op.drop_table("orders")
    sa.Enum(
        "PENDING",
        "PAID",
        "CANCELED",
        name="orderstatusenum",
    ).drop(op.get_bind(), checkfirst=True)
