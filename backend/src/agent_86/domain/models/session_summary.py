from dataclasses import dataclass, field
from datetime import datetime

from agent_86.domain.schemas.session_summary import ActionItem, ArtifactRef


@dataclass
class SessionSummary:
    id: str
    session_id: str
    user_id: str
    title: str
    date_range_start: datetime
    date_range_end: datetime
    one_line_summary: str
    topics: list[str] = field(default_factory=list)
    key_decisions: list[str] = field(default_factory=list)
    action_items: list[ActionItem] = field(default_factory=list)
    artifacts_generated: list[ArtifactRef] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    continuation_context: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None