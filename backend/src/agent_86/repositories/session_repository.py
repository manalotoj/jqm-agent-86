from typing import Protocol

from backend.src.agent_86.domain.models.session import Session
from backend.src.agent_86.domain.schemas.session import CreateSessionRequest, UpdateSessionRequest


class SessionRepository(Protocol):
    async def create_session(
        self,
        user_id: str,
        request: CreateSessionRequest,
    ) -> Session: ...

    async def get_session(
        self,
        user_id: str,
        session_id: str,
    ) -> Session | None: ...

    async def list_sessions(
        self,
        user_id: str,
    ) -> list[Session]: ...

    async def update_session(
        self,
        user_id: str,
        session_id: str,
        request: UpdateSessionRequest,
    ) -> Session | None: ...

    async def delete_session(
        self,
        user_id: str,
        session_id: str,
    ) -> bool: ...