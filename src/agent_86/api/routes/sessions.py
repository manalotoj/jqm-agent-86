from fastapi import APIRouter, Depends, HTTPException, Response, status

from agent_86.api.dependencies import get_message_service, get_session_service
from agent_86.domain.models.session import Session
from agent_86.domain.schemas.session import (
    CreateSessionRequest,
    SessionResponse,
    UpdateSessionRequest,
)
from agent_86.services.message_service import MessageService
from agent_86.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


def to_response(session: Session) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        title=session.title,
        metadata=session.metadata,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest,
    session_service: SessionService = Depends(get_session_service),
) -> SessionResponse:
    session = await session_service.create_session(
        user_id="local-dev-user",
        request=request,
    )
    return to_response(session)


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    session_service: SessionService = Depends(get_session_service),
) -> list[SessionResponse]:
    sessions = await session_service.list_sessions(user_id="local-dev-user")
    return [to_response(session) for session in sessions]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
) -> SessionResponse:
    session = await session_service.get_session(session_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )

    return to_response(session)


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    session_service: SessionService = Depends(get_session_service),
) -> SessionResponse:
    session = await session_service.update_session(session_id, request)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )

    return to_response(session)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
    message_service: MessageService = Depends(get_message_service),
) -> Response:
    session = await session_service.get_session(session_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )

    await message_service.delete_messages_for_session(session_id)
    await session_service.delete_session(session_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)