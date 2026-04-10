"""Products: image_front, image_back, condition, created_by_user_id NOT NULL. Auctions: image_front, image_back NOT NULL.

Revision ID: 006
Revises: 005
Create Date: 2025-03-13 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Products: backfill NULLs then set NOT NULL
    op.execute(sa.text("UPDATE products SET condition = '' WHERE condition IS NULL"))
    op.execute(sa.text("UPDATE products SET image_front = '' WHERE image_front IS NULL"))
    op.execute(sa.text("UPDATE products SET image_back = '' WHERE image_back IS NULL"))
    # created_by_user_id: use sentinel UUID for legacy rows; new rows are always set by API
    op.execute(
        sa.text(
            "UPDATE products SET created_by_user_id = '00000000-0000-0000-0000-000000000000'::uuid WHERE created_by_user_id IS NULL"
        )
    )
    op.alter_column(
        "products",
        "image_front",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.alter_column(
        "products",
        "image_back",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.alter_column(
        "products",
        "condition",
        existing_type=sa.String(100),
        nullable=False,
        server_default=sa.text("''"),
    )
    op.alter_column(
        "products",
        "created_by_user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    # Auctions: backfill then NOT NULL
    op.execute(sa.text("UPDATE auctions SET image_front = '' WHERE image_front IS NULL"))
    op.execute(sa.text("UPDATE auctions SET image_back = '' WHERE image_back IS NULL"))
    op.alter_column(
        "auctions",
        "image_front",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.alter_column(
        "auctions",
        "image_back",
        existing_type=sa.Text(),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "auctions",
        "image_back",
        existing_type=sa.Text(),
        nullable=True,
    )
    op.alter_column(
        "auctions",
        "image_front",
        existing_type=sa.Text(),
        nullable=True,
    )
    op.alter_column(
        "products",
        "created_by_user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.alter_column(
        "products",
        "condition",
        existing_type=sa.String(100),
        nullable=True,
        server_default=None,
    )
    op.alter_column(
        "products",
        "image_back",
        existing_type=sa.Text(),
        nullable=True,
    )
    op.alter_column(
        "products",
        "image_front",
        existing_type=sa.Text(),
        nullable=True,
    )
