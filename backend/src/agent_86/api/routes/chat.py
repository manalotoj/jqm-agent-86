import asyncio
import base64
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from agent_86.auth.dependencies import get_authenticated_user
from agent_86.auth.models import AuthenticatedUser
from agent_86.api.dependencies import (
    get_artifact_service,
    get_chat_model_service,
    get_message_service,
    get_model_router,
    get_session_service,
    get_tool_service,
)
from agent_86.domain.models.message import Message
from agent_86.domain.schemas.chat import ChatRequest, ChatResponse, ChatStreamEvent as ChatStreamEventSchema
from agent_86.domain.schemas.message import CreateMessageRequest, MessageResponse
from agent_86.services.artifact_service import ArtifactNotFoundError, ArtifactService
from agent_86.services.chat_model_service import ChatModelReply, ChatModelService, ChatStreamEvent
from agent_86.services.message_service import MessageService
from agent_86.services.model_router import ModelRouter
from agent_86.services.session_service import SessionService
from agent_86.services.tool_service import ToolService
from agent_86.tools.tool import ToolContext

router = APIRouter(prefix="/sessions/{session_id}/chat", tags=["chat"])


def is_web_search_enabled(metadata: dict | None) -> bool:
    if not metadata:
        return False

    return bool(metadata.get("enable_web_search", False))


def to_response(message: Message) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        session_id=message.session_id,
        user_id=message.user_id,
        role=message.role,
        content=message.content,
        metadata=message.metadata,
        created_at=message.created_at,
    )


async def ensure_session_exists(
    user_id: str,
    session_id: str,
    session_service: SessionService,
) -> None:
    session = await session_service.get_session(user_id, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )


def choose_tool_names(content: str, metadata: dict | None) -> list[str]:
    tool_names: list[str] = []

    if is_web_search_enabled(metadata):
        tool_names.append("web_search")

    return tool_names


def build_tool_context(*, session_id: str, user_id: str, request_metadata: dict | None) -> ToolContext:
    return ToolContext(
        session_id=session_id,
        user_id=user_id,
        metadata=dict(request_metadata or {}),
    )


def build_assistant_metadata(selected_model: str, tool_names: list[str]) -> dict:
    return {
        "source": "foundry",
        "model": selected_model,
        "tools": tool_names,
    }


def _normalize_output_artifact_spec(spec: Any) -> dict[str, Any] | None:
    if not isinstance(spec, dict):
        return None

    filename = str(spec.get("filename", "")).strip()
    content_type = str(spec.get("content_type", "")).strip()
    content_value = spec.get("content")

    if not filename or not content_type or not isinstance(content_value, str):
        return None

    source_artifact_ids = spec.get("source_artifact_ids", [])
    if not isinstance(source_artifact_ids, list) or not all(
        isinstance(artifact_id, str) and artifact_id.strip()
        for artifact_id in source_artifact_ids
    ):
        return None

    metadata = spec.get("metadata", {})
    if not isinstance(metadata, dict):
        return None

    encoding = str(spec.get("content_encoding", "utf-8")).strip().lower()
    if encoding not in {"utf-8", "base64"}:
        return None

    return {
        "filename": filename,
        "content_type": content_type,
        "content": content_value,
        "content_encoding": encoding,
        "source_artifact_ids": source_artifact_ids,
        "metadata": metadata,
    }


def _decode_output_artifact_content(spec: dict[str, Any]) -> bytes:
    if spec["content_encoding"] == "base64":
        return base64.b64decode(spec["content"], validate=True)

    return spec["content"].encode("utf-8")


async def persist_generated_artifacts_from_tool_results(
    *,
    user_id: str,
    session_id: str,
    reply: ChatModelReply,
    assistant_message: Message,
    artifact_service: ArtifactService,
    message_service: MessageService,
) -> list[dict[str, Any]]:
    persisted_artifacts: list[dict[str, Any]] = []

    for tool_result in reply.tool_results:
        output_artifacts = tool_result.metadata.get("output_artifacts", [])
        if not isinstance(output_artifacts, list):
            continue

        for artifact_spec in output_artifacts:
            normalized_spec = _normalize_output_artifact_spec(artifact_spec)
            if normalized_spec is None:
                continue

            try:
                artifact = await artifact_service.create_generated_artifact(
                    session_id=session_id,
                    user_id=user_id,
                    filename=normalized_spec["filename"],
                    content_type=normalized_spec["content_type"],
                    content=_decode_output_artifact_content(normalized_spec),
                    source_artifact_ids=normalized_spec["source_artifact_ids"],
                    generated_by_message_id=assistant_message.id,
                    metadata=normalized_spec["metadata"],
                    message_service=message_service,
                )
            except (ArtifactNotFoundError, ValueError):
                continue

            persisted_artifacts.append(
                {
                    "id": artifact.id,
                    "filename": artifact.filename,
                    "content_type": artifact.content_type,
                    "size_bytes": artifact.size_bytes,
                    "metadata": artifact.metadata,
                }
            )

    return persisted_artifacts


async def validate_and_enrich_request_metadata(
    user_id: str,
    session_id: str,
    request: ChatRequest,
    artifact_service: ArtifactService,
) -> None:
    artifact_ids = request.metadata.get("artifact_ids")
    if artifact_ids is None:
        return

    try:
        validated_ids = await artifact_service.validate_artifact_ids(
            user_id=user_id,
            session_id=session_id,
            artifact_ids=artifact_ids,
        )
    except ArtifactNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    request.metadata["artifact_ids"] = validated_ids


async def create_user_message(
    user_id: str,
    session_id: str,
    request: ChatRequest,
    message_service: MessageService,
) -> None:
    await message_service.create_message(
        session_id=session_id,
        user_id=user_id,
        request=CreateMessageRequest(
            role="user",
            content=request.content,
            metadata=request.metadata,
        ),
    )


async def persist_transcript_messages(
    user_id: str,
    session_id: str,
    transcript_messages,
    message_service: MessageService,
) -> None:
    for transcript_message in transcript_messages:
        await message_service.create_message(
            session_id=session_id,
            user_id=user_id,
            request=CreateMessageRequest(
                role=transcript_message.role,
                content=transcript_message.content,
                metadata=transcript_message.metadata,
            ),
        )


async def persist_assistant_message(
    user_id: str,
    session_id: str,
    reply: ChatModelReply,
    selected_model: str,
    tool_names: list[str],
    message_service: MessageService,
    artifact_service: ArtifactService,
) -> Message:
    await persist_transcript_messages(
        user_id=user_id,
        session_id=session_id,
        transcript_messages=reply.transcript_messages,
        message_service=message_service,
    )

    assistant_message = await message_service.create_message(
        session_id=session_id,
        user_id=user_id,
        request=CreateMessageRequest(
            role="assistant",
            content=reply.assistant_text,
            metadata=build_assistant_metadata(selected_model, tool_names),
        ),
    )

    generated_artifacts = await persist_generated_artifacts_from_tool_results(
        user_id=user_id,
        session_id=session_id,
        reply=reply,
        assistant_message=assistant_message,
        artifact_service=artifact_service,
        message_service=message_service,
    )

    if not generated_artifacts:
        return assistant_message

    assistant_message.metadata = {
        **assistant_message.metadata,
        "generated_artifacts": generated_artifacts,
    }

    persisted_assistant_message = await message_service.update_message_metadata(
        user_id=user_id,
        session_id=session_id,
        message_id=assistant_message.id,
        metadata=assistant_message.metadata,
    )
    return persisted_assistant_message or assistant_message


async def prepare_chat_context(
    user_id: str,
    session_id: str,
    request: ChatRequest,
    *,
    artifact_service: ArtifactService,
    message_service: MessageService,
    session_service: SessionService,
    model_router: ModelRouter,
) -> tuple[str, list[str], list[Message]]:
    await validate_and_enrich_request_metadata(
        user_id=user_id,
        session_id=session_id,
        request=request,
        artifact_service=artifact_service,
    )

    await create_user_message(user_id, session_id, request, message_service)

    await session_service.maybe_title_session_from_prompt(
        user_id=user_id,
        session_id=session_id,
        prompt=request.content,
    )

    selected_model = model_router.choose_chat_model(request.metadata)
    tool_names = choose_tool_names(request.content, request.metadata)
    history = await message_service.list_messages(user_id, session_id)

    return selected_model, tool_names, history


def to_stream_event(event: str, data: dict) -> ChatStreamEventSchema:
    return ChatStreamEventSchema(event=event, data=data)


def encode_sse(event: ChatStreamEventSchema) -> str:
    return f"event: {event.event}\ndata: {json.dumps(event.data)}\n\n"


@router.post("", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def chat(
    session_id: str,
    request: ChatRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    artifact_service: ArtifactService = Depends(get_artifact_service),
    message_service: MessageService = Depends(get_message_service),
    session_service: SessionService = Depends(get_session_service),
    chat_model_service: ChatModelService = Depends(get_chat_model_service),
    model_router: ModelRouter = Depends(get_model_router),
    tool_service: ToolService = Depends(get_tool_service),
) -> ChatResponse:
    await ensure_session_exists(user.user_id, session_id, session_service)

    selected_model, tool_names, history = await prepare_chat_context(
        user_id=user.user_id,
        session_id=session_id,
        request=request,
        artifact_service=artifact_service,
        message_service=message_service,
        session_service=session_service,
        model_router=model_router,
    )

    reply = await chat_model_service.generate_reply(
        messages=history,
        model=selected_model,
        tool_service=tool_service,
        available_tool_names=tool_names,
        tool_context=build_tool_context(
            session_id=session_id,
            user_id=user.user_id,
            request_metadata=request.metadata,
        ),
    )

    assistant_message = await persist_assistant_message(
        user_id=user.user_id,
        session_id=session_id,
        reply=reply,
        selected_model=selected_model,
        tool_names=tool_names,
        message_service=message_service,
        artifact_service=artifact_service,
    )

    return ChatResponse(message=to_response(assistant_message))


@router.post("/stream")
async def chat_stream(
    session_id: str,
    request: ChatRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    artifact_service: ArtifactService = Depends(get_artifact_service),
    message_service: MessageService = Depends(get_message_service),
    session_service: SessionService = Depends(get_session_service),
    chat_model_service: ChatModelService = Depends(get_chat_model_service),
    model_router: ModelRouter = Depends(get_model_router),
    tool_service: ToolService = Depends(get_tool_service),
) -> StreamingResponse:
    await ensure_session_exists(user.user_id, session_id, session_service)

    async def event_generator() -> AsyncIterator[str]:
        queue: asyncio.Queue[ChatStreamEventSchema] = asyncio.Queue()

        selected_model, tool_names, history = await prepare_chat_context(
            user_id=user.user_id,
            session_id=session_id,
            request=request,
            artifact_service=artifact_service,
            message_service=message_service,
            session_service=session_service,
            model_router=model_router,
        )

        await queue.put(
            to_stream_event(
                "start",
                {
                    "session_id": session_id,
                    "model": selected_model,
                    "tools": tool_names,
                },
            )
        )

        async def on_chat_event(event: ChatStreamEvent) -> None:
            await queue.put(to_stream_event(event.event, event.data))

        async def run_chat() -> None:
            try:
                reply = await chat_model_service.generate_reply_stream(
                    messages=history,
                    model=selected_model,
                    tool_service=tool_service,
                    available_tool_names=tool_names,
                    tool_context=build_tool_context(
                        session_id=session_id,
                        user_id=user.user_id,
                        request_metadata=request.metadata,
                    ),
                    event_callback=on_chat_event,
                )

                assistant_message = await persist_assistant_message(
                    user_id=user.user_id,
                    session_id=session_id,
                    reply=reply,
                    selected_model=selected_model,
                    tool_names=tool_names,
                    message_service=message_service,
                    artifact_service=artifact_service,
                )

                await queue.put(
                    to_stream_event(
                        "complete",
                        {
                            "message": to_response(assistant_message).model_dump(mode="json"),
                            "assistant_text": reply.assistant_text,
                        },
                    )
                )
            except Exception as exc:
                await queue.put(to_stream_event("error", {"message": str(exc)}))
            finally:
                await queue.put(to_stream_event("done", {}))

        task = asyncio.create_task(run_chat())

        try:
            while True:
                event = await queue.get()
                yield encode_sse(event)

                if event.event == "done":
                    break
        finally:
            await task

    return StreamingResponse(event_generator(), media_type="text/event-stream")