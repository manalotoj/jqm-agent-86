from datetime import UTC, datetime
from inspect import isawaitable
from typing import Any

from azure.cosmos import ContainerProxy

from agent_86.domain.models.session_summary import SessionSummary
from agent_86.domain.schemas.session_summary import ActionItem, ArtifactRef


class CosmosSessionSummaryRepository:
    def __init__(self, container: ContainerProxy) -> None:
        self._container = container

    async def _get_container(self) -> Any:
        if isawaitable(self._container):
            self._container = await self._container

        return self._container

    async def get_summary(
        self,
        user_id: str,
        session_id: str,
    ) -> SessionSummary | None:
        container = await self._get_container()
        query = """
        SELECT *
        FROM c
        WHERE c.session_id = @session_id AND c.user_id = @user_id
        """

        parameters = [
            {"name": "@session_id", "value": session_id},
            {"name": "@user_id", "value": user_id},
        ]

        async for item in container.query_items(
            query=query,
            parameters=parameters,
            partition_key=user_id,
        ):
            return self._from_document(item)

        return None

    async def upsert_summary(self, summary: SessionSummary) -> SessionSummary:
        container = await self._get_container()
        now = datetime.now(UTC)
        existing = await self.get_summary(summary.user_id, summary.session_id)
        if existing is None:
            summary.created_at = summary.created_at or now
        else:
            summary.id = existing.id
            summary.created_at = existing.created_at

        summary.updated_at = now
        if summary.created_at is None:
            summary.created_at = now

        document = self._to_document(summary)
        stored = await container.upsert_item(document)
        return self._from_document(stored)

    def _to_document(self, summary: SessionSummary) -> dict:
        return {
            "id": summary.id,
            "session_id": summary.session_id,
            "user_id": summary.user_id,
            "title": summary.title,
            "date_range_start": summary.date_range_start.isoformat().replace("+00:00", "Z"),
            "date_range_end": summary.date_range_end.isoformat().replace("+00:00", "Z"),
            "one_line_summary": summary.one_line_summary,
            "topics": summary.topics,
            "key_decisions": summary.key_decisions,
            "action_items": [item.model_dump() for item in summary.action_items],
            "artifacts_generated": [artifact.model_dump() for artifact in summary.artifacts_generated],
            "open_questions": summary.open_questions,
            "tools_used": summary.tools_used,
            "tags": summary.tags,
            "continuation_context": summary.continuation_context,
            "created_at": summary.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": summary.updated_at.isoformat().replace("+00:00", "Z"),
            # TODO: If continuation_context or other fields grow large enough to approach
            # the Cosmos 2 MB document limit, add a summary_blob_name field here and
            # implement a blob overflow read/write path in the repository.
        }

    def _from_document(self, document: dict) -> SessionSummary:
        return SessionSummary(
            id=document["id"],
            session_id=document["session_id"],
            user_id=document["user_id"],
            title=document["title"],
            date_range_start=self._parse_datetime(document["date_range_start"]),
            date_range_end=self._parse_datetime(document["date_range_end"]),
            one_line_summary=document["one_line_summary"],
            topics=list(document.get("topics", [])),
            key_decisions=list(document.get("key_decisions", [])),
            action_items=[ActionItem.model_validate(item) for item in document.get("action_items", [])],
            artifacts_generated=[
                ArtifactRef.model_validate(item) for item in document.get("artifacts_generated", [])
            ],
            open_questions=list(document.get("open_questions", [])),
            tools_used=list(document.get("tools_used", [])),
            tags=list(document.get("tags", [])),
            continuation_context=document.get("continuation_context", ""),
            created_at=self._parse_datetime(document["created_at"]),
            updated_at=self._parse_datetime(document["updated_at"]),
        )

    def _parse_datetime(self, value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))