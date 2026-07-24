import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.db import DbSession
from app.models import User
from app.services.companies_house import CompaniesHouseClient
from app.services.extraction import AnthropicExtractor
from app.services.pdf import PdfRenderer

UNAUTHENTICATED = HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")


async def get_current_user(request: Request, db: DbSession) -> User:
    raw = request.session.get("user_id")
    if raw is None:
        raise UNAUTHENTICATED
    try:
        user_id = uuid.UUID(raw)
    except (ValueError, TypeError):
        request.session.clear()
        raise UNAUTHENTICATED from None
    user = await db.get(User, user_id)
    if user is None:
        # The session outlived the user (deleted, or the signing secret rotated).
        request.session.clear()
        raise UNAUTHENTICATED
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_extractor(request: Request) -> AnthropicExtractor:
    return request.app.state.extractor


def get_ch_client(request: Request) -> CompaniesHouseClient:
    return request.app.state.ch_client


def get_renderer(request: Request) -> PdfRenderer:
    return request.app.state.renderer


ExtractorDep = Annotated[AnthropicExtractor, Depends(get_extractor)]
ChClientDep = Annotated[CompaniesHouseClient, Depends(get_ch_client)]
RendererDep = Annotated[PdfRenderer, Depends(get_renderer)]
