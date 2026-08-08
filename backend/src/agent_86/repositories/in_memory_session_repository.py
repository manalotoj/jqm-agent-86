from datetime import UTC, datetime
from uuid import uuid4

from agent_86.domain.models.session import Session
from agent_86.domain.schemas.session import CreateSessionRequest, UpdateSessionRequest


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    async def create_session(
        self,
        user_id: str,
        request: CreateSessionRequest,
    ) -> Session:
        now = datetime.now(UTC)

        session = Session(
            id=str(uuid4()),
            user_id=user_id,
            title=request.title,
            metadata=request.metadata,
            created_at=now,
            updated_at=now,
        )

        self._sessions[session.id] = session
        return session

    async def get_session(
        self,
        user_id: str,
        session_id: str,
    ) -> Session | None:
        session = self._sessions.get(session_id)
        if session is None or session.user_id != user_id:
            return None

        return session

    async def list_sessions(self, user_id: str) -> list[Session]:
        return [session for session in self._sessions.values() if session.user_id == user_id]

    async def update_session(
        self,
        user_id: str,
        session_id: str,
        request: UpdateSessionRequest,
    ) -> Session | None:
        session = await self.get_session(user_id, session_id)
        if session is None:
            return None

        session.title = request.title
        session.updated_at = datetime.now(UTC)
        return session

    async def delete_session(self, user_id: str, session_id: str) -> bool:
        session = await self.get_session(user_id, session_id)
        if session is None:
            return False

        del self._sessions[session_id]
        return True