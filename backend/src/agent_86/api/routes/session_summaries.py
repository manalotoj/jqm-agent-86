import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from agent_86.api.dependencies import (
    get_chat_model_service,
    get_message_service,
    get_model_router,
    get_session_service,
    get_session_summary_service,
)
from agent_86.auth.dependencies import get_authenticated_user
from agent_86.auth.models import AuthenticatedUser
from agent_86.domain.models.message import Message
from agent_86.domain.models.session_summary import SessionSummary
from agent_86.domain.schemas.session_summary import SessionSummaryResponse
from agent_86.services.chat_model_service import ChatModelService
from agent_86.services.message_service import MessageService
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


CONTEXT_SUMMARY_SYSTEM_PROMPT = """\
You are helping a user resume a chat session in a new conversation window.
Your task is to write a self-contained context block — in second person ("you") — that the user can paste into a new chat to pick up exactly where they left off.

The context block MUST cover:
1. The problem or goal the user was working on.
2. What has been decided, built, resolved, or ruled out so far.
3. For every file or artifact that was shared or discussed: what it contained, why it mattered, and its current status.
   Quote or paraphrase specific content from the files where it will help the new session — do not just mention filenames.
4. Any open questions, blockers, or unresolved threads.
5. The concrete next step — the most useful thing to do when the session resumes.

Write in clear prose (not bullet points or JSON). Be thorough enough that the recipient can continue without reading the original conversation.
Do not include greetings, sign-offs, or meta-commentary about this being a summary.
Output only the context block itself.
"""

context_summary_router = APIRouter(
    prefix="/sessions/{session_id}/context-summary",
    tags=["session-summary"],
)


@context_summary_router.post("", status_code=status.HTTP_200_OK)
async def generate_context_summary(
    session_id: str,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session_service: SessionService = Depends(get_session_service),
    message_service: MessageService = Depends(get_message_service),
    chat_model_service: ChatModelService = Depends(get_chat_model_service),
    model_router: ModelRouter = Depends(get_model_router),
) -> StreamingResponse:
    await ensure_session_exists(user.user_id, session_id, session_service)

    messages = await message_service.list_messages(user.user_id, session_id)
    if not messages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Session has no messages to summarise.",
        )

    system_message = Message(
        id="context-summary-system",
        session_id=session_id,
        user_id=user.user_id,
        role="system",
        content=CONTEXT_SUMMARY_SYSTEM_PROMPT,
        metadata={},
    )
    full_history = [system_message, *messages]
    selected_model = model_router.choose_chat_model({"model": None})

    async def event_generator():
        try:
            reply = await chat_model_service.generate_reply(
                messages=full_history,
                model=selected_model,
                tool_service=None,
                available_tool_names=[],
            )
            text = reply.assistant_text or ""
            yield f"event: chunk\ndata: {json.dumps({'text': text})}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"
        finally:
            yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")