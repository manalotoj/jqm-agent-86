from typing import Protocol

from agent_86.domain.models.session_summary import SessionSummary


class SessionSummaryRepository(Protocol):
    async def get_summary(
        self,
        user_id: str,
        session_id: str,
    ) -> SessionSummary | None: ...

    async def upsert_summary(
        self,
        summary: SessionSummary,
    ) -> SessionSummary: ...