from agent_86.repositories.in_memory_session_repository import (
    InMemorySessionRepository,
)
from agent_86.services.session_service import SessionService


_session_repository = InMemorySessionRepository()
_session_service = SessionService(_session_repository)


def get_session_service() -> SessionService:
    return _session_service