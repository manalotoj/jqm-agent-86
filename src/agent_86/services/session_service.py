from agent_86.domain.schemas.session import CreateSessionRequest, SessionResponse
from agent_86.repositories.session_repository import SessionRepository


class SessionService:
    def __init__(self, repository: SessionRepository) -> None:
        self._repository = repository

    async def create_session(
        self,
        user_id: str,
        request: CreateSessionRequest,
    ) -> SessionResponse:
        return await self._repository.create_session(
            user_id=user_id,
            request=request,
        )

    async def get_session(
        self,
        session_id: str,
    ) -> SessionResponse | None:
        return await self._repository.get_session(session_id)