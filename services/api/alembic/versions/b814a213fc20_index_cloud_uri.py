"""Index cloud URIs for bounded S3 reconciliation.

Revision ID: b814a213fc20
Revises: 719f12cac17a
"""
from alembic import op

revision = "b814a213fc20"
down_revision = "719f12cac17a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_data_products_cloud_uri", "data_products", ["cloud_uri"])


def downgrade() -> None:
    op.drop_index("ix_data_products_cloud_uri", table_name="data_products")
