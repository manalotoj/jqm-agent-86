from datetime import UTC, datetime

from azure.cosmos import ContainerProxy

from backend.src.agent_86.domain.models.session import Session
from backend.src.agent_86.domain.schemas.session import CreateSessionRequest, UpdateSessionRequest


class CosmosSessionRepository:
    def __init__(self, container: ContainerProxy) -> None:
        self._container = container

    async def create_session(
        self,
        user_id: str,
        request: CreateSessionRequest,
    ) -> Session:
        now = datetime.now(UTC)

        session = Session(
            id=self._new_id(),
            user_id=user_id,
            title=request.title,
            metadata=request.metadata,
            created_at=now,
            updated_at=now,
        )

        document = self._to_document(session)
        created = await self._container.create_item(document)

        return self._from_document(created)

    async def get_session(
        self,
        user_id: str,
        session_id: str,
    ) -> Session | None:
        query = """
        SELECT *
        FROM c
        WHERE c.id = @session_id AND c.user_id = @user_id
        """

        parameters = [
            {"name": "@session_id", "value": session_id},
            {"name": "@user_id", "value": user_id},
        ]

        items = []
        async for item in self._container.query_items(
            query=query,
            parameters=parameters,
            partition_key=user_id,
        ):
            items.append(item)

        if not items:
            return None

        return self._from_document(items[0])

    async def list_sessions(
        self,
        user_id: str,
    ) -> list[Session]:
        query = """
        SELECT *
        FROM c
        WHERE c.user_id = @user_id
        ORDER BY c.updated_at DESC
        """

        parameters = [
            {"name": "@user_id", "value": user_id},
        ]

        sessions: list[Session] = []
        async for item in self._container.query_items(
            query=query,
            parameters=parameters,
            partition_key=user_id,
        ):
            sessions.append(self._from_document(item))

        return sessions

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

        updated = await self._container.upsert_item(self._to_document(session))

        return self._from_document(updated)

    async def delete_session(
        self,
        user_id: str,
        session_id: str,
    ) -> bool:
        session = await self.get_session(user_id, session_id)
        if session is None:
            return False

        await self._container.delete_item(
            item=session.id,
            partition_key=session.user_id,
        )

        return True
    
    def _to_document(self, session: Session) -> dict:
        return {
            "id": session.id,
            "user_id": session.user_id,
            "title": session.title,
            "metadata": session.metadata,
            "created_at": session.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": session.updated_at.isoformat().replace("+00:00", "Z"),
        }

    def _from_document(self, document: dict) -> Session:
        return Session(
            id=document["id"],
            user_id=document["user_id"],
            title=document.get("title"),
            metadata=document.get("metadata", {}),
            created_at=self._parse_datetime(document["created_at"]),
            updated_at=self._parse_datetime(document["updated_at"]),
        )

    def _parse_datetime(self, value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def _new_id(self) -> str:
        from uuid import uuid4

        return str(uuid4())