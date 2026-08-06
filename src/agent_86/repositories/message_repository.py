from typing import Protocol

from agent_86.domain.models.message import Message
from agent_86.domain.schemas.message import CreateMessageRequest


class MessageRepository(Protocol):
    async def create_message(
        self,
        session_id: str,
        user_id: str,
        request: CreateMessageRequest,
    ) -> Message: ...

    async def list_messages(
        self,
        user_id: str,
        session_id: str,
    ) -> list[Message]: ...

    async def delete_messages_for_session(
        self,
        user_id: str,
        session_id: str,
    ) -> None: ...