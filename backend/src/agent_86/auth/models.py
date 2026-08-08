from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    claims: dict[str, Any]
    access_token: str