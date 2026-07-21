"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-21 14:05:01.259919

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# DROP TABLE does not drop the enum types the table used, so a downgrade that only drops
# tables leaves these behind and the next upgrade dies on "type already exists".
ENUM_TYPES = (
    "audit_actor",
    "audit_event_type",
    "company_status",
    "data_volume",
    "decision",
    "input_mode",
    "quote_status",
    "requested_limit",
    "sector",
    "submission_status",
)


def upgrade() -> None:
    op.create_table(
        "submissions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "received",
                "failed",
                "auto_approved",
                "referred",
                "declined",
                "quoted",
                name="submission_status",
            ),
            server_default=sa.text("'received'"),
            nullable=False,
        ),
        sa.Column(
            "input_mode", sa.Enum("form", "paste", "pdf_upload", name="input_mode"), nullable=False
        ),
        sa.Column("raw_input", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submissions")),
    )
    op.create_index(op.f("ix_submissions_status"), "submissions", ["status"], unique=False)
    op.create_table(
        "audit_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("submission_id", sa.UUID(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "submission_received",
                "extraction_completed",
                "extraction_failed",
                "enrichment_completed",
                "enrichment_failed",
                "rating_completed",
                "rating_failed",
                "submission_approved",
                "submission_declined",
                "quote_generated",
                "quote_render_failed",
                "quote_expired",
                "bordereau_exported",
                name="audit_event_type",
            ),
            nullable=False,
        ),
        sa.Column(
            "actor", sa.Enum("system", "ops", "applicant", name="audit_actor"), nullable=False
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_audit_events_submission_id"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        op.f("ix_audit_events_submission_id_occurred_at"),
        "audit_events",
        ["submission_id", "occurred_at"],
        unique=False,
    )
    op.create_table(
        "enrichments",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("submission_id", sa.UUID(), nullable=False),
        sa.Column("ch_found", sa.Boolean(), nullable=False),
        sa.Column("ch_company_number", sa.String(), nullable=True),
        sa.Column("ch_company_name", sa.String(), nullable=True),
        sa.Column(
            "ch_company_status",
            sa.Enum(
                "active",
                "dissolved",
                "liquidation",
                "receivership",
                "administration",
                "voluntary-arrangement",
                "converted-closed",
                "insolvency-proceedings",
                "registered",
                "removed",
                "closed",
                "open",
                name="company_status",
            ),
            nullable=True,
        ),
        sa.Column("ch_company_status_detail", sa.String(), nullable=True),
        sa.Column("ch_date_of_creation", sa.Date(), nullable=True),
        sa.Column("ch_name_match_score", sa.Float(), nullable=True),
        sa.Column(
            "sic_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "discrepancies",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("rate_limited", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_enrichments_submission_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrichments")),
        sa.UniqueConstraint("submission_id", name=op.f("uq_enrichments_submission_id")),
    )
    op.create_table(
        "extractions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("submission_id", sa.UUID(), nullable=False),
        sa.Column("company_name", sa.String(), nullable=True),
        sa.Column("company_number", sa.String(), nullable=True),
        sa.Column(
            "sector",
            sa.Enum(
                "saas",
                "fintech",
                "healthtech",
                "ecommerce",
                "ai_ml",
                "marketplace",
                "crypto",
                "other",
                name="sector",
            ),
            nullable=True,
        ),
        sa.Column("annual_revenue_pence", sa.BigInteger(), nullable=True),
        sa.Column("months_trading", sa.Integer(), nullable=True),
        sa.Column("prior_claims_count", sa.Integer(), nullable=True),
        sa.Column(
            "data_records_held",
            sa.Enum("under_10k", "10k_100k", "100k_1m", "over_1m", name="data_volume"),
            nullable=True,
        ),
        sa.Column(
            "requested_limit",
            sa.Enum("GBP_250K", "GBP_500K", "GBP_1M", "GBP_2M", name="requested_limit"),
            nullable=True,
        ),
        sa.Column("extraction_confidence", sa.Float(), nullable=False),
        sa.Column(
            "missing_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_extractions_submission_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extractions")),
        sa.UniqueConstraint("submission_id", name=op.f("uq_extractions_submission_id")),
    )
    op.create_table(
        "quotes",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("submission_id", sa.UUID(), nullable=False),
        sa.Column("quote_ref", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("issued", "expired", name="quote_status"),
            server_default=sa.text("'issued'"),
            nullable=False,
        ),
        sa.Column("limit_pence", sa.BigInteger(), nullable=False),
        sa.Column("excess_pence", sa.BigInteger(), nullable=False),
        sa.Column("gross_premium_pence", sa.BigInteger(), nullable=False),
        sa.Column("inception_date", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("pdf_s3_key", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_quotes_submission_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quotes")),
        sa.UniqueConstraint("quote_ref", name=op.f("uq_quotes_quote_ref")),
        sa.UniqueConstraint("submission_id", name=op.f("uq_quotes_submission_id")),
    )
    op.create_index(op.f("ix_quotes_status"), "quotes", ["status"], unique=False)
    op.create_index(op.f("ix_quotes_valid_until"), "quotes", ["valid_until"], unique=False)
    op.create_table(
        "ratings",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("submission_id", sa.UUID(), nullable=False),
        sa.Column("rating_version", sa.String(), nullable=False),
        sa.Column(
            "decision", sa.Enum("AUTO_APPROVE", "REFER", "DECLINE", name="decision"), nullable=False
        ),
        sa.Column("base_premium_pence", sa.BigInteger(), nullable=False),
        sa.Column("indicative_premium_pence", sa.BigInteger(), nullable=False),
        sa.Column("annual_premium_pence", sa.BigInteger(), nullable=True),
        sa.Column(
            "factors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "refer_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "decline_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(decision = 'DECLINE') = (annual_premium_pence IS NULL)",
            name=op.f("ck_ratings_declined_iff_no_annual_premium"),
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_ratings_submission_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ratings")),
        sa.UniqueConstraint("submission_id", name=op.f("uq_ratings_submission_id")),
    )
    op.create_index(op.f("ix_ratings_decision"), "ratings", ["decision"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ratings_decision"), table_name="ratings")
    op.drop_table("ratings")
    op.drop_index(op.f("ix_quotes_valid_until"), table_name="quotes")
    op.drop_index(op.f("ix_quotes_status"), table_name="quotes")
    op.drop_table("quotes")
    op.drop_table("extractions")
    op.drop_table("enrichments")
    op.drop_index(op.f("ix_audit_events_submission_id_occurred_at"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index(op.f("ix_submissions_status"), table_name="submissions")
    op.drop_table("submissions")

    for name in ENUM_TYPES:
        sa.Enum(name=name).drop(op.get_bind())
