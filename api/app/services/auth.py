from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User

_hasher = PasswordHasher()

# Verified against on a username miss so a wrong user and a wrong password cost the same time.
_DUMMY_HASH = _hasher.hash("dummy-password-for-constant-time-compare")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    # A mismatch (VerificationError) and a malformed/corrupt hash (InvalidHashError, a ValueError,
    # not an Argon2Error) both mean "not authenticated" — never a 500.
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


async def authenticate(session: AsyncSession, username: str, password: str) -> User | None:
    user = await session.scalar(select(User).where(User.username == username))
    if user is None:
        # Spend the same work as a real verify so a missing user is not timing-distinguishable.
        verify_password(_DUMMY_HASH, password)
        return None
    if not verify_password(user.password_hash, password):
        return None
    return user
