from datetime import UTC, datetime
from uuid import uuid4

from agent_86.domain.models.session import Session
from agent_86.domain.schemas.session import CreateSessionRequest


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
        session_id: str,
    ) -> Session | None:
        return self._sessions.get(session_id)