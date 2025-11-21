"""add hotspot type table and column

Revision ID: 97c7878c3123
Revises: c133643a9626
Create Date: 2025-11-20 07:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "97c7878c3123"
down_revision: Union[str, Sequence[str], None] = "c133643a9626"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create hotspot type table and link hotspots."""
    op.create_table(
        "tbl_hotspot_type",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("isactive", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_date",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_date", sa.TIMESTAMP(timezone=True)),
    )

    op.add_column(
        "tbl_hotspots",
        sa.Column("hotspot_type", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_hotspots_hotspot_type",
        "tbl_hotspots",
        "tbl_hotspot_type",
        ["hotspot_type"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Drop hotspot type table/column."""
    op.drop_constraint("fk_hotspots_hotspot_type", "tbl_hotspots", type_="foreignkey")
    op.drop_column("tbl_hotspots", "hotspot_type")
    op.drop_table("tbl_hotspot_type")

