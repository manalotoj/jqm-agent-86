from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter

from agent_86.domain.schemas.sessions import CreateSessionRequest, SessionResponse


router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse)
async def create_session(request: CreateSessionRequest) -> SessionResponse:
    now = datetime.now(UTC)

    return SessionResponse(
        id=str(uuid4()),
        user_id="local-dev-user",
        title=request.title,
        metadata=request.metadata,
        created_at=now,
        updated_at=now,
    )