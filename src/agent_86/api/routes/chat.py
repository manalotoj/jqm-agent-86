from fastapi import APIRouter, Depends, HTTPException, status

from agent_86.api.dependencies import get_message_service, get_session_service
from agent_86.domain.models.message import Message
from agent_86.domain.schemas.chat import ChatRequest, ChatResponse
from agent_86.domain.schemas.message import CreateMessageRequest, MessageResponse
from agent_86.services.message_service import MessageService
from agent_86.services.session_service import SessionService

router = APIRouter(prefix="/sessions/{session_id}/chat", tags=["chat"])

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

    assistant_message = await message_service.create_message(
        session_id=session_id,
        user_id="local-dev-user",
        request=CreateMessageRequest(
            role="assistant",
            content=f"Echo: {request.content}",
            metadata={"source": "stub-chat"},
        ),
    )

    return ChatResponse(message=to_response(assistant_message))