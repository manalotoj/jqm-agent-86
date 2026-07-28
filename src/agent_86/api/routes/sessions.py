from fastapi import APIRouter, Depends, HTTPException, status

from agent_86.api.dependencies import get_session_service
from agent_86.domain.schemas.session import CreateSessionRequest, SessionResponse
from agent_86.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest,
    session_service: SessionService = Depends(get_session_service),
) -> SessionResponse:
    return await session_service.create_session(
        user_id="local-dev-user",
        request=request,
    )


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

    return session