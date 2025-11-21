"""drop dimension columns from products

Revision ID: d8b6b3c4d9f1
Revises: 97c7878c3123
Create Date: 2025-11-20 07:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d8b6b3c4d9f1"
down_revision: Union[str, Sequence[str], None] = "97c7878c3123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE tbl_products DROP COLUMN IF EXISTS dimension_width")
    op.execute("ALTER TABLE tbl_products DROP COLUMN IF EXISTS dimension_height")
    op.execute("ALTER TABLE tbl_products DROP COLUMN IF EXISTS dimension_depth")


def downgrade() -> None:
    op.add_column("tbl_products", sa.Column("dimension_width", sa.Float(), nullable=True))
    op.add_column("tbl_products", sa.Column("dimension_height", sa.Float(), nullable=True))
    op.add_column("tbl_products", sa.Column("dimension_depth", sa.Float(), nullable=True))
