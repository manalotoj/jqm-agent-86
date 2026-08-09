from datetime import UTC, datetime
from uuid import uuid4

from azure.cosmos import ContainerProxy

from agent_86.domain.models.message import Message
from agent_86.domain.schemas.message import CreateMessageRequest


class CosmosMessageRepository:
    def __init__(self, container: ContainerProxy) -> None:
        self._container = container

    async def create_message(
        self,
        session_id: str,
        user_id: str,
        request: CreateMessageRequest,
    ) -> Message:
        message = Message(
            id=str(uuid4()),
            session_id=session_id,
            user_id=user_id,
            role=request.role,
            content=request.content,
            metadata=request.metadata,
            created_at=datetime.now(UTC),
        )

        document = self._to_document(message)
        created = await self._container.create_item(document)

        return self._from_document(created)

    async def get_message(
        self,
        user_id: str,
        session_id: str,
        message_id: str,
    ) -> Message | None:
        query = """
        SELECT *
        FROM c
        WHERE c.id = @message_id AND c.session_id = @session_id AND c.user_id = @user_id
        """

        parameters = [
            {"name": "@message_id", "value": message_id},
            {"name": "@session_id", "value": session_id},
            {"name": "@user_id", "value": user_id},
        ]

        async for item in self._container.query_items(
            query=query,
            parameters=parameters,
            partition_key=session_id,
        ):
            return self._from_document(item)

        return None

    async def list_messages(
        self,
        user_id: str,
        session_id: str,
    ) -> list[Message]:
        query = """
        SELECT *
        FROM c
        WHERE c.session_id = @session_id AND c.user_id = @user_id
        ORDER BY c.created_at ASC
        """

        parameters = [
            {"name": "@session_id", "value": session_id},
            {"name": "@user_id", "value": user_id},
        ]

        messages: list[Message] = []

        async for item in self._container.query_items(
            query=query,
            parameters=parameters,
            partition_key=session_id,
        ):
            messages.append(self._from_document(item))

        return messages

    async def update_message_metadata(
        self,
        *,
        user_id: str,
        session_id: str,
        message_id: str,
        metadata: dict,
    ) -> Message | None:
        message = await self.get_message(
            user_id=user_id,
            session_id=session_id,
            message_id=message_id,
        )
        if message is None:
            return None

        message.metadata = metadata
        updated = await self._container.upsert_item(self._to_document(message))
        return self._from_document(updated)

    async def delete_messages_for_session(
        self,
        user_id: str,
        session_id: str,
    ) -> None:
        messages = await self.list_messages(user_id, session_id)

        for message in messages:
            await self._container.delete_item(
                item=message.id,
                partition_key=session_id,
            )
            
    def _to_document(self, message: Message) -> dict:
        return {
            "id": message.id,
            "session_id": message.session_id,
            "user_id": message.user_id,
            "role": message.role,
            "content": message.content,
            "metadata": message.metadata,
            "created_at": message.created_at.isoformat().replace("+00:00", "Z"),
        }

    def _from_document(self, document: dict) -> Message:
        return Message(
            id=document["id"],
            session_id=document["session_id"],
            user_id=document["user_id"],
            role=document["role"],
            content=document["content"],
            metadata=document.get("metadata", {}),
            created_at=self._parse_datetime(document["created_at"]),
        )

    def _parse_datetime(self, value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))