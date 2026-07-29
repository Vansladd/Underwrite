"""enrichment lookup_error

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-29 11:17:55.826737

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable with no backfill: a row written before this cannot say why it found nothing, and
    # inventing a cause for it would be worse than leaving it unknown.
    op.add_column("enrichments", sa.Column("lookup_error", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("enrichments", "lookup_error")
