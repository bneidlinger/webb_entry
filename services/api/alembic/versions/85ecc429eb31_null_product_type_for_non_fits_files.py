"""null product_type for non-fits files

Revision ID: 85ecc429eb31
Revises: 7ed3b023ed62
Create Date: 2026-05-25 23:18:54.450755

Data-only fix. Pre-existing rows where MAST's JPG previews and CSV/ECSV catalogs
were misclassified with a science product_type (e.g. JPG thumbnails tagged as
i2d) get product_type=NULL. The classifier in app.clients.mast now only sets
product_type for FITS, so new ingests won't re-introduce these rows.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '85ecc429eb31'
down_revision: str | Sequence[str] | None = '7ed3b023ed62'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE data_products SET product_type = NULL "
        "WHERE file_extension IS NOT NULL AND file_extension != 'fits'"
    )


def downgrade() -> None:
    # Cannot reconstruct the original (incorrect) product_type values. No-op.
    pass
