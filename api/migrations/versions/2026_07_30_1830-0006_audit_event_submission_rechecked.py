"""audit event submission_rechecked

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-30 18:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUM = "audit_event_type"
VALUE = "submission_rechecked"


def upgrade() -> None:
    # ADD VALUE cannot run inside a transaction block before PG 12, and alembic wraps everything
    # in one; IF NOT EXISTS also makes a re-run safe. After the declined value, to match the enum.
    op.execute(f"alter type {ENUM} add value if not exists '{VALUE}' after 'submission_declined'")


def downgrade() -> None:
    # Postgres cannot drop a value from an enum, so the type is rebuilt without it. Any row still
    # carrying the value would fail the cast — deliberately, because dropping the audit rows that
    # record a recheck is not something a schema migration gets to decide. See D-010.
    op.execute(f"alter type {ENUM} rename to {ENUM}_old")
    op.execute(
        f"create type {ENUM} as enum ("
        "'submission_received','extraction_completed','extraction_failed',"
        "'enrichment_completed','enrichment_failed','rating_completed','rating_failed',"
        "'submission_approved','submission_declined','quote_generated','quote_render_failed',"
        "'quote_expired','bordereau_exported')"
    )
    op.execute(
        "alter table audit_events alter column event_type"
        f" type {ENUM} using event_type::text::{ENUM}"
    )
    op.execute(f"drop type {ENUM}_old")
