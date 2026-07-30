from agent_86.domain.models.session import Session
from agent_86.domain.schemas.session import CreateSessionRequest, UpdateSessionRequest
from agent_86.repositories.session_repository import SessionRepository


class SessionService:
    def __init__(self, repository: SessionRepository) -> None:
        self._repository = repository

    async def create_session(
        self,
        user_id: str,
        request: CreateSessionRequest,
    ) -> Session:
        title = request.title

        if title is None or not title.strip():
            sessions = await self._repository.list_sessions(user_id)
            title = f"New session {len(sessions) + 1:03d}"

        request = CreateSessionRequest(
            title=title,
            metadata=request.metadata,
        )

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

    async def update_session(
        self,
        session_id: str,
        request: UpdateSessionRequest,
    ) -> Session | None:
        return await self._repository.update_session(session_id, request)

    async def delete_session(
        self,
        session_id: str,
    ) -> bool:
        return await self._repository.delete_session(session_id)

    async def maybe_title_session_from_prompt(
        self,
        session_id: str,
        prompt: str,
    ) -> Session | None:
        session = await self._repository.get_session(session_id)
        if session is None:
            return None

        if not self._is_default_title(session.title):
            return session

        derived_title = self._derive_title_from_prompt(prompt)

        return await self._repository.update_session(
            session_id,
            UpdateSessionRequest(title=derived_title),
        )

    def _is_default_title(
        self,
        title: str | None,
    ) -> bool:
        return title is not None and title.startswith("New session ")

    def _derive_title_from_prompt(
        self,
        prompt: str,
    ) -> str:
        cleaned = " ".join(prompt.strip().split())

        if not cleaned:
            return "New session"

        cleaned = cleaned.rstrip(" .,!?:;")
        return cleaned[:60]