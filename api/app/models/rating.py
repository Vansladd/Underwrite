import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import Decision
from app.models.base import (
    Base,
    created_at,
    json_list,
    optional_pence,
    pence,
    pg_enum_by_name,
    uuid_pk,
)

if TYPE_CHECKING:
    from app.models.submission import Submission


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (
        # RATING_SPEC D3, enforced by Postgres rather than by remembering to branch.
        CheckConstraint(
            "(decision = 'DECLINE') = (annual_premium_pence IS NULL)",
            name="declined_iff_no_annual_premium",
        ),
    )

    id: Mapped[uuid_pk]
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"),
        unique=True,
    )

    rating_version: Mapped[str]
    decision: Mapped[Decision] = mapped_column(pg_enum_by_name(Decision, "decision"), index=True)
    base_premium_pence: Mapped[pence]
    indicative_premium_pence: Mapped[pence]
    annual_premium_pence: Mapped[optional_pence]

    # Multipliers and premiums are Decimal strings. See DECISIONS D-004.
    factors: Mapped[json_list]
    refer_reasons: Mapped[json_list]
    decline_reasons: Mapped[json_list]
    created_at: Mapped[created_at]

    submission: Mapped["Submission"] = relationship(back_populates="rating")
