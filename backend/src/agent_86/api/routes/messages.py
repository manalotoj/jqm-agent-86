from fastapi import APIRouter, Depends, HTTPException, status

from agent_86.auth.dependencies import get_authenticated_user
from agent_86.auth.models import AuthenticatedUser
from agent_86.api.dependencies import get_message_service, get_session_service
from agent_86.domain.models.message import Message
from agent_86.domain.schemas.message import CreateMessageRequest, MessageResponse
from agent_86.services.message_service import MessageService
from agent_86.services.session_service import SessionService

router = APIRouter(prefix="/sessions/{session_id}/messages", tags=["messages"])


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


@router.post("", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message(
    session_id: str,
    request: CreateMessageRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    message_service: MessageService = Depends(get_message_service),
    session_service: SessionService = Depends(get_session_service),
) -> MessageResponse:
    await ensure_session_exists(user.user_id, session_id, session_service)

    message = await message_service.create_message(
        session_id=session_id,
        user_id=user.user_id,
        request=request,
    )
    return to_response(message)


@router.get("", response_model=list[MessageResponse])
async def list_messages(
    session_id: str,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    message_service: MessageService = Depends(get_message_service),
    session_service: SessionService = Depends(get_session_service),
) -> list[MessageResponse]:
    await ensure_session_exists(user.user_id, session_id, session_service)

    messages = await message_service.list_messages(user.user_id, session_id)
    return [to_response(message) for message in messages]