from fastapi import APIRouter, Depends, HTTPException, status

from agent_86.api.dependencies import (
    get_model_router,
    get_session_service,
    get_session_summary_service,
)
from agent_86.auth.dependencies import get_authenticated_user
from agent_86.auth.models import AuthenticatedUser
from agent_86.domain.models.session_summary import SessionSummary
from agent_86.domain.schemas.session_summary import SessionSummaryResponse
from agent_86.services.model_router import ModelRouter
from agent_86.services.session_service import SessionService
from agent_86.services.session_summary_service import (
    SessionSummaryNotFoundError,
    SessionSummaryService,
)

router = APIRouter(prefix="/sessions/{session_id}/summary", tags=["session-summary"])


def to_response(summary: SessionSummary) -> SessionSummaryResponse:
    return SessionSummaryResponse(
        id=summary.id,
        session_id=summary.session_id,
        user_id=summary.user_id,
        title=summary.title,
        date_range_start=summary.date_range_start,
        date_range_end=summary.date_range_end,
        one_line_summary=summary.one_line_summary,
        topics=summary.topics,
        key_decisions=summary.key_decisions,
        action_items=summary.action_items,
        artifacts_generated=summary.artifacts_generated,
        open_questions=summary.open_questions,
        tools_used=summary.tools_used,
        tags=summary.tags,
        continuation_context=summary.continuation_context,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
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


@router.get("", response_model=SessionSummaryResponse)
async def get_summary(
    session_id: str,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session_service: SessionService = Depends(get_session_service),
    summary_service: SessionSummaryService = Depends(get_session_summary_service),
) -> SessionSummaryResponse:
    await ensure_session_exists(user.user_id, session_id, session_service)

    try:
        summary = await summary_service.get_summary(user.user_id, session_id)
    except SessionSummaryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return to_response(summary)


@router.post("", response_model=SessionSummaryResponse, status_code=status.HTTP_201_CREATED)
async def generate_summary(
    session_id: str,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session_service: SessionService = Depends(get_session_service),
    summary_service: SessionSummaryService = Depends(get_session_summary_service),
    model_router: ModelRouter = Depends(get_model_router),
) -> SessionSummaryResponse:
    await ensure_session_exists(user.user_id, session_id, session_service)

    selected_model = model_router.choose_chat_model({"model": None})
    summary = await summary_service.generate_summary(user.user_id, session_id, selected_model)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )

    return to_response(summary)