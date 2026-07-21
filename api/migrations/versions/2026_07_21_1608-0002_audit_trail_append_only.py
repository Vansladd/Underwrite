"""audit trail append only

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-21 16:08:35.627590

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A trigger fires for superusers and raw SQL; a REVOKE does not. See DECISIONS D-010.
CREATE_FUNCTION = """
create or replace function refuse_audit_mutation() returns trigger as $$
begin
    raise exception 'audit_events is append-only (attempted %)', tg_op
        using errcode = 'restrict_violation';
end;
$$ language plpgsql
"""

CREATE_ROW_TRIGGER = """
create trigger audit_events_append_only
before update or delete on audit_events
for each row execute function refuse_audit_mutation()
"""

# Row triggers do not fire for TRUNCATE, which empties the table and reports success.
CREATE_TRUNCATE_TRIGGER = """
create trigger audit_events_no_truncate
before truncate on audit_events
for each statement execute function refuse_audit_mutation()
"""


def upgrade() -> None:
    op.execute(CREATE_FUNCTION)
    op.execute(CREATE_ROW_TRIGGER)
    op.execute(CREATE_TRUNCATE_TRIGGER)


def downgrade() -> None:
    op.execute("drop trigger if exists audit_events_no_truncate on audit_events")
    op.execute("drop trigger if exists audit_events_append_only on audit_events")
    op.execute("drop function if exists refuse_audit_mutation()")
