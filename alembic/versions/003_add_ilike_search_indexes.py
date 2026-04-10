"""Add GIN trigram indexes for ILIKE search on auctions and products.

Enables pg_trgm and creates indexes so queries with ILIKE '%term%' can use
the index instead of full table scans.

Revision ID: 003
Revises: 002
Create Date: 2025-01-03 00:00:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute(
        "CREATE INDEX idx_auctions_title_trgm ON auctions USING gin (title gin_trgm_ops);"
    )
    op.execute(
        "CREATE INDEX idx_auctions_description_trgm ON auctions USING gin (description gin_trgm_ops);"
    )
    op.execute(
        "CREATE INDEX idx_products_name_trgm ON products USING gin (name gin_trgm_ops);"
    )
    op.execute(
        "CREATE INDEX idx_products_description_trgm ON products USING gin (description gin_trgm_ops);"
    )


def downgrade() -> None:
    op.drop_index("idx_products_description_trgm", table_name="products")
    op.drop_index("idx_products_name_trgm", table_name="products")
    op.drop_index("idx_auctions_description_trgm", table_name="auctions")
    op.drop_index("idx_auctions_title_trgm", table_name="auctions")
    # Do not DROP EXTENSION pg_trgm; other objects or DB might depend on it
