from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.deps import CurrentUser
from app.db import DbSession
from app.schemas import LoginRequest, UserRead
from app.services.auth import authenticate

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
async def login(payload: LoginRequest, request: Request, db: DbSession) -> UserRead:
    user = await authenticate(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid username or password")
    request.session["user_id"] = str(user.id)
    return UserRead.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me")
async def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
