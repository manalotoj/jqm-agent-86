from collections.abc import Mapping
from typing import Any

import httpx
import jwt
from jwt import InvalidTokenError
from jwt.algorithms import RSAAlgorithm

from agent_86.auth.provider import TokenValidationError
from agent_86.core.config import Settings


class OpenIdMetadataFetcher:
    def __init__(self, config_url: str) -> None:
        self._config_url = config_url
        self._metadata: dict[str, Any] | None = None
        self._jwks: dict[str, Any] | None = None

    async def get_metadata(self) -> dict[str, Any]:
        if self._metadata is None:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(self._config_url)
                    response.raise_for_status()
                    self._metadata = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise TokenValidationError(
                    "Failed to load OpenID configuration"
                ) from exc

        return self._metadata

    async def get_jwks(self) -> dict[str, Any]:
        if self._jwks is None:
            metadata = await self.get_metadata()
            jwks_uri = metadata.get("jwks_uri")
            if not jwks_uri:
                raise TokenValidationError("OIDC metadata is missing jwks_uri")

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(jwks_uri)
                    response.raise_for_status()
                    self._jwks = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise TokenValidationError("Failed to load token signing keys") from exc

        return self._jwks


class EntraJwtTokenValidator:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._metadata_fetcher = OpenIdMetadataFetcher(
            settings.entra_openid_configuration_url
        )

    async def validate_token(self, token: str) -> Mapping[str, Any]:
        if not token:
            raise TokenValidationError("Missing access token")

        try:
            header = jwt.get_unverified_header(token)
        except InvalidTokenError as exc:
            raise TokenValidationError("Token header is invalid") from exc

        key_id = header.get("kid")
        if not key_id:
            raise TokenValidationError("Token header is missing kid")

        jwks = await self._metadata_fetcher.get_jwks()
        key = self._find_signing_key(jwks, key_id)

        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                audience=self._settings.entra_api_audience,
                issuer=self._settings.entra_issuer,
                options={"require": ["exp", "iat", "iss", "aud"]},
            )
        except InvalidTokenError as exc:
            raise TokenValidationError("Token validation failed") from exc

        return claims

    def _find_signing_key(self, jwks: dict[str, Any], key_id: str) -> Any:
        for jwk in jwks.get("keys", []):
            if jwk.get("kid") == key_id:
                return RSAAlgorithm.from_jwk(jwk)

        raise TokenValidationError("Signing key not found for token")