import uuid
from datetime import date, datetime
from enum import Enum as PyEnum
from typing import Annotated, Any

from sqlalchemy import BigInteger, Date, DateTime, Enum, MetaData, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, mapped_column

# An unnamed constraint cannot be referenced by a later ALTER. See DECISIONS D-005.
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
    """Stores member values; SQLAlchemy's default of names breaks `WHERE sector = 'saas'`."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


def pg_enum_by_name(enum_cls: type[PyEnum], name: str) -> Enum:
    """Stores member names, for the two IntEnums. See DECISIONS D-005."""
    return Enum(enum_cls, name=name, native_enum=True)


uuid_pk = Annotated[
    uuid.UUID,
    mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
]
created_at = Annotated[
    datetime,
    mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False),
]
# clock_timestamp(), not now(): now() ties every row written in one transaction.
event_at = Annotated[
    datetime,
    mapped_column(
        DateTime(timezone=True),
        server_default=text("clock_timestamp()"),
        nullable=False,
    ),
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
optional_long_text = Annotated[str | None, mapped_column(Text)]
# server_default too: seeds and data migrations insert outside the ORM.
json_list = Annotated[
    list[Any],
    mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb")),
]
json_object = Annotated[
    dict[str, Any],
    mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb")),
]
calendar_date = Annotated[date, mapped_column(Date)]
