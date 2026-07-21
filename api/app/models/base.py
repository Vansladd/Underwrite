import uuid
from datetime import date, datetime
from enum import Enum as PyEnum
from typing import Annotated, Any

from sqlalchemy import BigInteger, Date, DateTime, Enum, MetaData, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, mapped_column

# Alembic autogenerates unnamed constraints without this, and an unnamed constraint cannot
# be referenced by a later ALTER. Set before the first migration, not after.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def pg_enum(enum_cls: type[PyEnum], name: str) -> Enum:
    """A native Postgres enum storing member *values*.

    SQLAlchemy's default is to persist the member *name*, so `SAAS = "saas"` lands in the
    database as 'SAAS' and every `WHERE sector = 'saas'` quietly misses.
    """
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


def pg_enum_by_name(enum_cls: type[PyEnum], name: str) -> Enum:
    """A native Postgres enum storing member *names* — for the two IntEnums.

    `Decision` is deliberate: D7 requires 'DECLINE' on disk so that reordering the IntEnum
    cannot reinterpret history. `RequestedLimit`'s values are integers, which a Postgres
    enum cannot hold at all.
    """
    return Enum(enum_cls, name=name, native_enum=True)


uuid_pk = Annotated[
    uuid.UUID,
    mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
]
created_at = Annotated[
    datetime,
    mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False),
]
updated_at = Annotated[
    datetime,
    mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
]
pence = Annotated[int, mapped_column(BigInteger)]
optional_pence = Annotated[int | None, mapped_column(BigInteger)]
long_text = Annotated[str, mapped_column(Text)]
json_list = Annotated[list[Any], mapped_column(JSONB, default=list)]
json_object = Annotated[dict[str, Any], mapped_column(JSONB, default=dict)]
calendar_date = Annotated[date, mapped_column(Date)]
