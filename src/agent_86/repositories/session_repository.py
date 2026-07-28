from typing import Protocol

from agent_86.domain.models.session import Session
from agent_86.domain.schemas.session import CreateSessionRequest


class SessionRepository(Protocol):
    async def create_session(
        self,
        user_id: str,
        request: CreateSessionRequest,
    ) -> Session: ...

    async def get_session(
        self,
        session_id: str,
    ) -> Session | None: ...

    async def list_sessions(
        self,
        user_id: str,
    ) -> list[Session]: ...