from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


MessageRole = Literal["system", "user", "assistant", "tool"]


@dataclass
class Message:
    id: str
    session_id: str
    user_id: str
    role: MessageRole
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None