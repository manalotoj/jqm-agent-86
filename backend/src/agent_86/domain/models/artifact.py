from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Artifact:
    id: str
    session_id: str
    user_id: str
    filename: str
    content_type: str
    size_bytes: int
    blob_name: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None