import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import Response as FastAPIResponse

from agent_86.api.dependencies import get_artifact_service, get_session_service
from agent_86.auth.dependencies import get_authenticated_user
from agent_86.auth.models import AuthenticatedUser
from agent_86.domain.models.artifact import Artifact
from agent_86.domain.schemas.artifact import ArtifactResponse
from agent_86.services.artifact_service import ArtifactNotFoundError, ArtifactService
from agent_86.services.session_service import SessionService

router = APIRouter(prefix="/sessions/{session_id}/artifacts", tags=["artifacts"])


def to_response(artifact: Artifact) -> ArtifactResponse:
    return ArtifactResponse(
        id=artifact.id,
        session_id=artifact.session_id,
        user_id=artifact.user_id,
        filename=artifact.filename,
        content_type=artifact.content_type,
        size_bytes=artifact.size_bytes,
        metadata=artifact.metadata,
        created_at=artifact.created_at,
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


def _parse_metadata(metadata: str | None) -> dict:
    if metadata is None or not metadata.strip():
        return {}

    try:
        parsed = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Artifact metadata must be valid JSON",
        ) from exc

    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Artifact metadata must be a JSON object",
        )

    return parsed


@router.post("/upload", response_model=ArtifactResponse, status_code=status.HTTP_201_CREATED)
async def upload_artifact(
    session_id: str,
    file: UploadFile = File(...),
    metadata: str | None = Form(default=None),
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session_service: SessionService = Depends(get_session_service),
    artifact_service: ArtifactService = Depends(get_artifact_service),
) -> ArtifactResponse:
    await ensure_session_exists(user.user_id, session_id, session_service)

    content = await file.read()
    artifact = await artifact_service.upload_artifact(
        session_id=session_id,
        user_id=user.user_id,
        filename=file.filename or "artifact",
        content_type=file.content_type or "application/octet-stream",
        content=content,
        metadata=_parse_metadata(metadata),
    )
    return to_response(artifact)


@router.get("", response_model=list[ArtifactResponse])
async def list_artifacts(
    session_id: str,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session_service: SessionService = Depends(get_session_service),
    artifact_service: ArtifactService = Depends(get_artifact_service),
) -> list[ArtifactResponse]:
    await ensure_session_exists(user.user_id, session_id, session_service)
    artifacts = await artifact_service.list_artifacts(user.user_id, session_id)
    return [to_response(artifact) for artifact in artifacts]


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    session_id: str,
    artifact_id: str,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session_service: SessionService = Depends(get_session_service),
    artifact_service: ArtifactService = Depends(get_artifact_service),
) -> ArtifactResponse:
    await ensure_session_exists(user.user_id, session_id, session_service)
    artifact = await artifact_service.get_artifact(user.user_id, session_id, artifact_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found in session '{session_id}'",
        )
    return to_response(artifact)


@router.get("/{artifact_id}/download")
async def download_artifact(
    session_id: str,
    artifact_id: str,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session_service: SessionService = Depends(get_session_service),
    artifact_service: ArtifactService = Depends(get_artifact_service),
) -> Response:
    await ensure_session_exists(user.user_id, session_id, session_service)

    try:
        result = await artifact_service.get_artifact_content(user.user_id, session_id, artifact_id)
    except ArtifactNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return FastAPIResponse(
        content=result.download.content,
        media_type=result.download.content_type or result.artifact.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{result.artifact.filename}"',
        },
    )