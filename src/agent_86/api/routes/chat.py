from fastapi import APIRouter, Depends, HTTPException, status

from agent_86.api.dependencies import (
    get_chat_model_service,
    get_message_service,
    get_model_router,
    get_session_service,
    get_tool_service,
)
from agent_86.domain.models.message import Message
from agent_86.domain.schemas.chat import ChatRequest, ChatResponse
from agent_86.domain.schemas.message import CreateMessageRequest, MessageResponse
from agent_86.services.chat_model_service import ChatModelService
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

    await message_service.create_message(
        session_id=session_id,
        user_id="local-dev-user",
        request=CreateMessageRequest(
            role="user",
            content=request.content,
            metadata=request.metadata,
        ),
    )

    await session_service.maybe_title_session_from_prompt(
        session_id=session_id,
        prompt=request.content,
    )

    selected_model = model_router.choose_chat_model(request.metadata)

    tool_names: list[str] = []

    if is_web_search_enabled(request.metadata) and should_use_web_search(request.content):
        tool_names.append("web_search")

    tool_results = await tool_service.execute_tools(
        tool_names=tool_names,
        query=request.content,
        context=ToolContext(
            session_id=session_id,
            user_id="local-dev-user",
            metadata=request.metadata or {},
        ),
    )

    for tool_result in tool_results:
        await message_service.create_message(
            session_id=session_id,
            user_id="local-dev-user",
            request=CreateMessageRequest(
                role="system",
                content=f"[tool:{tool_result.tool_name}] {tool_result.content}",
                metadata={
                    "source": "tool",
                    "tool_name": tool_result.tool_name,
                    **tool_result.metadata,
                },
            ),
        )

    history = await message_service.list_messages(session_id)

    assistant_text = await chat_model_service.generate_reply(
        messages=history,
        model=selected_model,
        tool_results=tool_results,
    )

    assistant_message = await message_service.create_message(
        session_id=session_id,
        user_id="local-dev-user",
        request=CreateMessageRequest(
            role="assistant",
            content=assistant_text,
            metadata={
                "source": "foundry",
                "model": selected_model,
                "tools": tool_names,
            },
        ),
    )

    return ChatResponse(message=to_response(assistant_message))