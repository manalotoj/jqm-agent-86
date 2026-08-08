from collections.abc import Mapping
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status

from backend.src.agent_86.auth.jwt_validator import EntraJwtTokenValidator
from backend.src.agent_86.auth.models import AuthenticatedUser
from backend.src.agent_86.auth.provider import TokenValidationError, TokenValidator
from backend.src.agent_86.core.config import get_settings


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token


def _resolve_user_id(claims: Mapping[str, Any]) -> str:
    user_id = claims.get("oid") or claims.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing oid/sub claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return str(user_id)


@lru_cache(maxsize=1)
def get_token_validator() -> TokenValidator:
    return EntraJwtTokenValidator(get_settings())


async def get_authenticated_user(
    authorization: Annotated[str | None, Header()] = None,
    token_validator: TokenValidator = Depends(get_token_validator),
) -> AuthenticatedUser:
    token = _extract_bearer_token(authorization)

    try:
        claims = await token_validator.validate_token(token)
    except TokenValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc) or "Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return AuthenticatedUser(
        user_id=_resolve_user_id(claims),
        claims=dict(claims),
        access_token=token,
    )