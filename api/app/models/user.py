from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, uuid_pk, written_at


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid_pk]
    username: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    display_name: Mapped[str]
    created_at: Mapped[written_at]
