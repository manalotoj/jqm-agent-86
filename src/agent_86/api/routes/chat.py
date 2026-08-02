import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from agent_86.api.dependencies import (
    get_chat_model_service,
    get_message_service,
    get_model_router,
    get_session_service,
    get_tool_service,
)
from agent_86.domain.models.message import Message
from agent_86.domain.schemas.chat import ChatRequest, ChatResponse, ChatStreamEvent as ChatStreamEventSchema
from agent_86.domain.schemas.message import CreateMessageRequest, MessageResponse
from agent_86.services.chat_model_service import ChatModelReply, ChatModelService, ChatStreamEvent
from agent_86.services.message_service import MessageService
from agent_86.services.model_router import ModelRouter
from agent_86.services.session_service import SessionService
from agent_86.services.tool_service import ToolService
from agent_86.tools.tool import ToolContext

router = APIRouter(prefix="/sessions/{session_id}/chat", tags=["chat"])
LOCAL_USER_ID = "local-dev-user"


def is_web_search_enabled(metadata: dict | None) -> bool:
    if not metadata:
        return False

    return bool(metadata.get("enable_web_search", False))


def should_use_web_search(content: str) -> bool:
    text = content.lower()

    web_search_signals = [
        "current",
        "latest",
        "today",
        "news",
        "recent",
        "right now",
        "check internet",
        "on the internet",
        "online",
        "stock price",
        "weather",
        "score",
    ]

    return any(signal in text for signal in web_search_signals)


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
    session_id: str,
    session_service: SessionService,
) -> None:
    session = await session_service.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )


def choose_tool_names(content: str, metadata: dict | None) -> list[str]:
    tool_names: list[str] = []

    if is_web_search_enabled(metadata) and should_use_web_search(content):
        tool_names.append("web_search")

    return tool_names


def build_assistant_metadata(selected_model: str, tool_names: list[str]) -> dict:
    return {
        "source": "foundry",
        "model": selected_model,
        "tools": tool_names,
    }


async def create_user_message(
    session_id: str,
    request: ChatRequest,
    message_service: MessageService,
) -> None:
    await message_service.create_message(
        session_id=session_id,
        user_id=LOCAL_USER_ID,
        request=CreateMessageRequest(
            role="user",
            content=request.content,
            metadata=request.metadata,
        ),
    )


async def persist_transcript_messages(
    session_id: str,
    transcript_messages,
    message_service: MessageService,
) -> None:
    for transcript_message in transcript_messages:
        await message_service.create_message(
            session_id=session_id,
            user_id=LOCAL_USER_ID,
            request=CreateMessageRequest(
                role=transcript_message.role,
                content=transcript_message.content,
                metadata=transcript_message.metadata,
            ),
        )


async def persist_assistant_message(
    session_id: str,
    reply: ChatModelReply,
    selected_model: str,
    tool_names: list[str],
    message_service: MessageService,
) -> Message:
    await persist_transcript_messages(
        session_id=session_id,
        transcript_messages=reply.transcript_messages,
        message_service=message_service,
    )

    return await message_service.create_message(
        session_id=session_id,
        user_id=LOCAL_USER_ID,
        request=CreateMessageRequest(
            role="assistant",
            content=reply.assistant_text,
            metadata=build_assistant_metadata(selected_model, tool_names),
        ),
    )


async def prepare_chat_context(
    session_id: str,
    request: ChatRequest,
    *,
    message_service: MessageService,
    session_service: SessionService,
    model_router: ModelRouter,
) -> tuple[str, list[str], list[Message]]:
    await create_user_message(session_id, request, message_service)

    await session_service.maybe_title_session_from_prompt(
        session_id=session_id,
        prompt=request.content,
    )

    selected_model = model_router.choose_chat_model(request.metadata)
    tool_names = choose_tool_names(request.content, request.metadata)
    history = await message_service.list_messages(session_id)

    return selected_model, tool_names, history


def to_stream_event(event: str, data: dict) -> ChatStreamEventSchema:
    return ChatStreamEventSchema(event=event, data=data)


def encode_sse(event: ChatStreamEventSchema) -> str:
    return f"event: {event.event}\ndata: {json.dumps(event.data)}\n\n"


@router.post("", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def chat(
    session_id: str,
    request: ChatRequest,
    message_service: MessageService = Depends(get_message_service),
    session_service: SessionService = Depends(get_session_service),
    chat_model_service: ChatModelService = Depends(get_chat_model_service),
    model_router: ModelRouter = Depends(get_model_router),
    tool_service: ToolService = Depends(get_tool_service),
) -> ChatResponse:
    await ensure_session_exists(session_id, session_service)

    selected_model, tool_names, history = await prepare_chat_context(
        session_id=session_id,
        request=request,
        message_service=message_service,
        session_service=session_service,
        model_router=model_router,
    )

    reply = await chat_model_service.generate_reply(
        messages=history,
        model=selected_model,
        tool_service=tool_service,
        available_tool_names=tool_names,
        tool_context=ToolContext(session_id=session_id, user_id=LOCAL_USER_ID),
    )

    assistant_message = await persist_assistant_message(
        session_id=session_id,
        reply=reply,
        selected_model=selected_model,
        tool_names=tool_names,
        message_service=message_service,
    )

    return ChatResponse(message=to_response(assistant_message))


@router.post("/stream")
async def chat_stream(
    session_id: str,
    request: ChatRequest,
    message_service: MessageService = Depends(get_message_service),
    session_service: SessionService = Depends(get_session_service),
    chat_model_service: ChatModelService = Depends(get_chat_model_service),
    model_router: ModelRouter = Depends(get_model_router),
    tool_service: ToolService = Depends(get_tool_service),
) -> StreamingResponse:
    await ensure_session_exists(session_id, session_service)

    async def event_generator() -> AsyncIterator[str]:
        queue: asyncio.Queue[ChatStreamEventSchema] = asyncio.Queue()

        selected_model, tool_names, history = await prepare_chat_context(
            session_id=session_id,
            request=request,
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
                    tool_context=ToolContext(session_id=session_id, user_id=LOCAL_USER_ID),
                    event_callback=on_chat_event,
                )

                assistant_message = await persist_assistant_message(
                    session_id=session_id,
                    reply=reply,
                    selected_model=selected_model,
                    tool_names=tool_names,
                    message_service=message_service,
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