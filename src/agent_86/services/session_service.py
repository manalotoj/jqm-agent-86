from agent_86.domain.models.session import Session
from agent_86.domain.schemas.session import CreateSessionRequest
from agent_86.repositories.session_repository import SessionRepository


class SessionService:
    def __init__(self, repository: SessionRepository) -> None:
        self._repository = repository

    async def create_session(
        self,
        user_id: str,
        request: CreateSessionRequest,
    ) -> Session:
        return await self._repository.create_session(
            user_id=user_id,
            request=request,
        )

    async def get_session(
        self,
        session_id: str,
    ) -> Session | None:
        return await self._repository.get_session(session_id)

    async def list_sessions(
        self,
        user_id: str,
    ) -> list[Session]:
        return await self._repository.list_sessions(user_id)