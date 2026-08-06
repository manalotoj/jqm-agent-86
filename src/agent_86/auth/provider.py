from collections.abc import Mapping
from typing import Any, Protocol


class TokenValidationError(Exception):
    """Raised when a bearer token cannot be validated."""


class TokenValidator(Protocol):
    async def validate_token(self, token: str) -> Mapping[str, Any]: ...