"""add_postgis_hotspots_and_dimensions

Revision ID: c133643a9626
Revises: 6317c2563d0b
Create Date: 2025-11-20 11:12:49.569397

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c133643a9626'
down_revision: Union[str, Sequence[str], None] = '6317c2563d0b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Enable PostGIS extension
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    
    # Add geometry column to hotspots table for storing 3D points
    # Using SRID 0 for local 3D model coordinate system (not geographic)
    op.execute("""
        ALTER TABLE tbl_hotspots 
        ADD COLUMN position_3d geometry(PointZ, 0);
    """)
    
    # Create spatial index on the geometry column
    op.execute("""
        CREATE INDEX idx_hotspots_position_3d 
        ON tbl_hotspots USING GIST (position_3d);
    """)
    
    # Migrate existing pos_x, pos_y, pos_z data to geometry column
    # Note: We're using a simple coordinate system for 3D model space (-1 to 1 range)
    # PostGIS PointZ requires valid coordinates, so we'll use a local coordinate system
    op.execute("""
        UPDATE tbl_hotspots 
        SET position_3d = ST_SetSRID(ST_MakePoint(pos_x, pos_y, pos_z), 0)
        WHERE pos_x IS NOT NULL AND pos_y IS NOT NULL AND pos_z IS NOT NULL;
    """)
    
    # Add dimension columns to products table
    op.add_column('tbl_products', sa.Column('dimension_width', sa.Float(), nullable=True))
    op.add_column('tbl_products', sa.Column('dimension_height', sa.Float(), nullable=True))
    op.add_column('tbl_products', sa.Column('dimension_depth', sa.Float(), nullable=True))
    
    # Add comment to columns
    op.execute("COMMENT ON COLUMN tbl_products.dimension_width IS 'Width of the 3D model in meters'")
    op.execute("COMMENT ON COLUMN tbl_products.dimension_height IS 'Height of the 3D model in meters'")
    op.execute("COMMENT ON COLUMN tbl_products.dimension_depth IS 'Depth of the 3D model in meters'")
    op.execute("COMMENT ON COLUMN tbl_hotspots.position_3d IS '3D position of hotspot using PostGIS PointZ geometry'")


def downgrade() -> None:
    """Downgrade schema."""
    # Remove dimension columns from products
    op.drop_column('tbl_products', 'dimension_depth')
    op.drop_column('tbl_products', 'dimension_height')
    op.drop_column('tbl_products', 'dimension_width')
    
    # Drop spatial index
    op.execute("DROP INDEX IF EXISTS idx_hotspots_position_3d;")
    
    # Remove geometry column from hotspots
    op.drop_column('tbl_hotspots', 'position_3d')
    
    # Note: We don't drop the PostGIS extension as it might be used by other tables
    # If you want to drop it, uncomment the line below:
    # op.execute("DROP EXTENSION IF EXISTS postgis;")
