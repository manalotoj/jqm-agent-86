from agent_86.domain.models.message import Message
from agent_86.domain.schemas.message import CreateMessageRequest
from agent_86.repositories.message_repository import MessageRepository


class MessageService:
    def __init__(self, repository: MessageRepository) -> None:
        self._repository = repository

    async def create_message(
        self,
        session_id: str,
        user_id: str,
        request: CreateMessageRequest,
    ) -> Message:
        return await self._repository.create_message(
            session_id=session_id,
            user_id=user_id,
            request=request,
        )

    async def list_messages(
        self,
        session_id: str,
    ) -> list[Message]:
        return await self._repository.list_messages(session_id)