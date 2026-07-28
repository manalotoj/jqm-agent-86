from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Session:
    id: str
    user_id: str
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None