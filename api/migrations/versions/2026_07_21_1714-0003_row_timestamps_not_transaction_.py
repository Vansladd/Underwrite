"""row timestamps not transaction timestamps

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-21 17:14:36.034886

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# now() is the transaction timestamp, so rows written together tie. See DECISIONS D-011.
COLUMNS = (
    ("submissions", "created_at"),
    ("submissions", "updated_at"),
    ("extractions", "created_at"),
    ("enrichments", "created_at"),
    ("ratings", "created_at"),
    ("quotes", "created_at"),
)


def upgrade() -> None:
    for table, column in COLUMNS:
        op.execute(f"alter table {table} alter column {column} set default clock_timestamp()")


def downgrade() -> None:
    for table, column in COLUMNS:
        op.execute(f"alter table {table} alter column {column} set default now()")
