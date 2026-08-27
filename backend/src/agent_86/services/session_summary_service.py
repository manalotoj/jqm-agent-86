from datetime import UTC, datetime

from agent_86.domain.models.artifact import Artifact
from agent_86.domain.models.message import Message
from agent_86.domain.models.session_summary import SessionSummary
from agent_86.domain.schemas.session_summary import ArtifactRef, ChatSessionSummary
from agent_86.repositories.session_summary_repository import SessionSummaryRepository
from agent_86.services.artifact_service import ArtifactService
from agent_86.services.artifact_prompt_context_service import ArtifactPromptContextService
from agent_86.services.chat_model_service import ChatModelService
from agent_86.services.message_service import MessageService
from agent_86.services.session_service import SessionService


SUMMARY_SYSTEM_PROMPT = """You are generating a structured summary of a single chat session.
Return JSON only, matching the required schema exactly.
Use only the supplied session context.
Do not call tools, do not invent external facts, and do not mention missing context unless needed in open_questions.
Generate a concise title based on the session context instead of copying the stored session title.
artifact refs may include persisted artifacts and meaningful generated outputs or references present in the message history.
Each artifacts_generated entry must be an object with name, artifact_type, and location; never return a bare string or artifact ID.
For persisted artifacts, use the supplied filename as name and its id as location. artifact_type must be docx, pptx, xlsx, diagram, code, or other.
Keep lists concise and useful for later retrieval.
If artifact metadata indicates unsupported or partially visible attachments, reflect that accurately instead of implying full inspection.

In addition to the standard summary fields, you MUST populate the continuation_context field.
The continuation_context is a self-contained narrative block — written in second person ("you") — that gives a new chat session
all the context needed to pick up exactly where this session left off. It must include:
1. A clear statement of the problem or goal being worked on.
2. The current state of progress: what has been decided, built, or resolved.
3. The role of each artifact: what it contains, what it was used for, and whether it is still relevant.
   Draw on the artifact_content_sections to describe actual file contents where available.
   If an artifact is unreadable, note its name and type and state that its contents are not available.
4. Any open threads, blockers, or unresolved questions.
5. The suggested next step — the most logical thing to do when the session resumes.
Write in clear prose (not bullet points). Be thorough enough that the recipient can continue without needing to re-read
the original conversation, but avoid padding. Do not repeat the structured fields verbatim; synthesize them into narrative.
"""


class SessionSummaryNotFoundError(Exception):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"Summary for session '{session_id}' not found")
        self.session_id = session_id


class SessionSummaryService:
    def __init__(
        self,
        repository: SessionSummaryRepository,
        session_service: SessionService,
        message_service: MessageService,
        artifact_service: ArtifactService,
        artifact_prompt_context_service: ArtifactPromptContextService,
        chat_model_service: ChatModelService,
    ) -> None:
        self._repository = repository
        self._session_service = session_service
        self._message_service = message_service
        self._artifact_service = artifact_service
        self._artifact_prompt_context_service = artifact_prompt_context_service
        self._chat_model_service = chat_model_service

    async def get_summary(self, user_id: str, session_id: str) -> SessionSummary:
        summary = await self._repository.get_summary(user_id, session_id)
        if summary is None:
            raise SessionSummaryNotFoundError(session_id)
        return summary

    async def generate_summary(self, user_id: str, session_id: str, model: str) -> SessionSummary | None:
        session = await self._session_service.get_session(user_id, session_id)
        if session is None:
            return None

        messages = await self._message_service.list_messages(user_id, session_id)
        artifacts = await self._artifact_service.list_artifacts(user_id, session_id)

        context_payload = await self._build_context_payload(
            user_id=user_id,
            session_id=session_id,
            messages=messages,
            artifacts=artifacts,
        )

        generated_summary = await self._chat_model_service.generate_structured_summary(
            model=model,
            system_prompt=SUMMARY_SYSTEM_PROMPT,
            context_payload=context_payload,
        )

        summary = SessionSummary(
            id=self._build_summary_id(session_id),
            session_id=session_id,
            user_id=user_id,
            title=generated_summary.title,
            date_range_start=generated_summary.date_range_start,
            date_range_end=generated_summary.date_range_end,
            one_line_summary=generated_summary.one_line_summary,
            topics=generated_summary.topics,
            key_decisions=generated_summary.key_decisions,
            action_items=generated_summary.action_items,
            artifacts_generated=self._merge_artifact_refs(generated_summary.artifacts_generated, artifacts),
            open_questions=generated_summary.open_questions,
            tools_used=self._merge_tools_used(generated_summary.tools_used, messages),
            tags=generated_summary.tags,
            continuation_context=generated_summary.continuation_context,
        )

        return await self._repository.upsert_summary(summary)

    def _build_summary_id(self, session_id: str) -> str:
        return f"summary:{session_id}"

    async def _build_context_payload(
        self,
        *,
        user_id: str,
        session_id: str,
        messages: list[Message],
        artifacts: list[Artifact],
    ) -> dict:
        start = self._first_message_datetime(messages)
        end = self._last_message_datetime(messages)

        artifact_ids = [artifact.id for artifact in artifacts]
        artifact_content_result = await self._artifact_prompt_context_service.build_message_for_artifact_ids(
            user_id=user_id,
            session_id=session_id,
            artifact_ids=artifact_ids,
        )

        return {
            "session_id": session_id,
            "date_range_start": start.isoformat().replace("+00:00", "Z"),
            "date_range_end": end.isoformat().replace("+00:00", "Z"),
            "messages": [
                {
                    "role": message.role,
                    "message_type": self._classify_message_type(message),
                    "content": message.content,
                    "metadata": message.metadata,
                    "created_at": message.created_at.isoformat().replace("+00:00", "Z")
                    if message.created_at is not None
                    else None,
                }
                for message in messages
            ],
            "persisted_artifacts": [
                {
                    "id": artifact.id,
                    "filename": artifact.filename,
                    "content_type": artifact.content_type,
                    "metadata": artifact.metadata,
                }
                for artifact in artifacts
            ],
            "artifact_prompt_context": artifact_content_result.artifact_details,
            "artifact_content_sections": (
                artifact_content_result.context_message.content
                if artifact_content_result.context_message is not None
                else ""
            ),
        }

    def _classify_message_type(self, message: Message) -> str:
        """Return a human-readable message type label derived from message role and metadata."""
        metadata = message.metadata or {}
        message_type = str(metadata.get("message_type", "")).strip()
        if message_type == "function_call":
            return "tool_call"
        if message_type == "function_call_output":
            return "tool_result"
        if message.role == "tool":
            return "tool_result"
        if message.role == "system":
            return "system"
        if message.role == "user":
            return "user"
        if message.role == "assistant":
            return "assistant"
        return message.role

    def _merge_tools_used(self, model_tools_used: list[str], messages: list[Message]) -> list[str]:
        seen: set[str] = set()
        merged: list[str] = []

        for tool_name in model_tools_used:
            normalized = tool_name.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                merged.append(normalized)

        for message in messages:
            tool_name = str(message.metadata.get("tool_name", "")).strip()
            if tool_name and tool_name not in seen:
                seen.add(tool_name)
                merged.append(tool_name)

            tools = message.metadata.get("tools")
            if isinstance(tools, list):
                for tool in tools:
                    normalized = str(tool).strip()
                    if normalized and normalized not in seen:
                        seen.add(normalized)
                        merged.append(normalized)

        return merged

    def _merge_artifact_refs(
        self,
        model_artifacts: list[ArtifactRef],
        persisted_artifacts: list[Artifact],
    ) -> list[ArtifactRef]:
        merged: list[ArtifactRef] = []
        seen: set[tuple[str, str]] = set()

        for artifact_ref in model_artifacts:
            key = (artifact_ref.name, artifact_ref.location)
            if key in seen:
                continue
            seen.add(key)
            merged.append(artifact_ref)

        for artifact in persisted_artifacts:
            ref = ArtifactRef(
                name=artifact.filename,
                artifact_type=self._infer_artifact_type(artifact.filename, artifact.content_type),
                location=artifact.id,
            )
            key = (ref.name, ref.location)
            if key in seen:
                continue
            seen.add(key)
            merged.append(ref)

        return merged

    def _infer_artifact_type(self, filename: str, content_type: str) -> str:
        lower_name = filename.lower()
        lower_content_type = content_type.lower()
        if lower_name.endswith(".docx"):
            return "docx"
        if lower_name.endswith(".pptx"):
            return "pptx"
        if lower_name.endswith(".xlsx"):
            return "xlsx"
        if any(ext in lower_name for ext in (".drawio", ".vsdx", ".mmd", ".svg")):
            return "diagram"
        if any(ext in lower_name for ext in (".py", ".ts", ".tsx", ".js", ".json", ".yaml", ".yml", ".md")):
            return "code"
        if "officedocument.wordprocessingml" in lower_content_type:
            return "docx"
        if "presentationml" in lower_content_type:
            return "pptx"
        if "spreadsheetml" in lower_content_type:
            return "xlsx"
        return "other"

    def _first_message_datetime(self, messages: list[Message]) -> datetime:
        timestamps = [message.created_at for message in messages if message.created_at is not None]
        if timestamps:
            return min(timestamps)
        return datetime.now(UTC)

    def _last_message_datetime(self, messages: list[Message]) -> datetime:
        timestamps = [message.created_at for message in messages if message.created_at is not None]
        if timestamps:
            return max(timestamps)
        return datetime.now(UTC)