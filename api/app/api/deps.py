import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import SettingsDep
from app.services.companies_house import CompaniesHouseClient
from app.services.extraction import AnthropicExtractor

OPS_USERNAME = "ops"
UNAUTHORISED = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    "ops credentials required",
    headers={"WWW-Authenticate": "Basic"},
)

basic = HTTPBasic(auto_error=False)


def matches(supplied: str, expected: str) -> bool:
    # Bytes, not str: compare_digest raises TypeError on non-ASCII, turning a 401 into a 500.
    return secrets.compare_digest(supplied.encode(), expected.encode())


async def require_ops(
    settings: SettingsDep,
    credentials: Annotated[HTTPBasicCredentials | None, Depends(basic)] = None,
) -> str:
    if credentials is None:
        raise UNAUTHORISED

    # Both compared before combining: `and` short-circuits, restoring the timing signal.
    user_ok = matches(credentials.username, OPS_USERNAME)
    password_ok = matches(credentials.password, settings.ops_password)
    if not (user_ok and password_ok):
        raise UNAUTHORISED

    return credentials.username


OpsUser = Annotated[str, Depends(require_ops)]


def get_extractor(request: Request) -> AnthropicExtractor:
    return request.app.state.extractor


def get_ch_client(request: Request) -> CompaniesHouseClient:
    return request.app.state.ch_client


ExtractorDep = Annotated[AnthropicExtractor, Depends(get_extractor)]
ChClientDep = Annotated[CompaniesHouseClient, Depends(get_ch_client)]
