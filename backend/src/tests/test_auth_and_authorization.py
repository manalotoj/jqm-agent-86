import base64
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from unittest.mock import ANY

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("COSMOS_ENDPOINT", "https://example.documents.azure.com:443/")
os.environ.setdefault("COSMOS_KEY", "test-cosmos-key")
os.environ.setdefault("COSMOS_DATABASE_NAME", "agent86-test")
os.environ.setdefault("AZURE_BLOB_CONNECTION_STRING", "UseDevelopmentStorage=true")
os.environ.setdefault("AZURE_BLOB_CONTAINER_NAME", "agent86-test-artifacts")
os.environ.setdefault("FOUNDRY_OPENAI_BASE_URL", "https://example.openai.azure.com/")
os.environ.setdefault("FOUNDRY_OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("FOUNDRY_DEFAULT_CHAT_MODEL", "gpt-4.1-mini")
os.environ.setdefault("FOUNDRY_PREMIUM_CHAT_MODEL", "gpt-5.4")
os.environ.setdefault("ENTRA_TENANT_ID", "00000000-0000-0000-0000-000000000001")
os.environ.setdefault("ENTRA_API_CLIENT_ID", "00000000-0000-0000-0000-000000000002")
os.environ.setdefault(
    "ENTRA_API_AUDIENCE",
    "api://00000000-0000-0000-0000-000000000002",
)

from agent_86.api.dependencies import (
    get_artifact_service,
    get_artifact_processing_service,
    get_artifact_analysis_service,
    get_artifact_prompt_context_service,
    get_chat_model_service,
    get_message_service,
    get_model_router,
    get_session_service,
    get_session_summary_service,
    get_tool_service,
)
from agent_86.api.routes.chat import choose_tool_names
from agent_86.auth.dependencies import get_token_validator
from agent_86.auth.provider import TokenValidationError
from agent_86.core.config import get_settings
from agent_86.domain.models.artifact import Artifact
from agent_86.domain.models.message import Message
from agent_86.domain.models.session_summary import SessionSummary
from agent_86.domain.schemas.artifact import CreateArtifactRequest
from agent_86.domain.schemas.message import CreateMessageRequest
from agent_86.domain.schemas.session import CreateSessionRequest
from agent_86.domain.schemas.session_summary import ActionItem, ArtifactRef, ChatSessionSummary
from agent_86.main import create_app
from agent_86.repositories.in_memory_session_repository import InMemorySessionRepository
from agent_86.services.artifact_service import ArtifactService
from agent_86.services.artifact_processing_service import ArtifactProcessingService
from agent_86.services.artifact_analysis_service import ArtifactAnalysisService
from agent_86.services.artifact_prompt_context_service import ArtifactPromptContextService
from agent_86.services.blob_storage_service import BlobDownload
from agent_86.services.csv_artifact_processor import CsvArtifactProcessor
from agent_86.services.chat_model_service import ChatModelReply
from agent_86.services.message_service import MessageService
from agent_86.services.session_service import SessionService
from agent_86.services.session_summary_service import SessionSummaryService
from agent_86.tools.tool import ToolContext


def clear_settings_caches() -> None:
    get_settings.cache_clear()
    get_token_validator.cache_clear()


class StubTokenValidator:
    def __init__(self, claims_by_token: dict[str, dict]) -> None:
        self._claims_by_token = claims_by_token

    async def validate_token(self, token: str) -> dict:
        claims = self._claims_by_token.get(token)
        if claims is None:
            raise TokenValidationError("Invalid access token")

        return claims


class InMemoryMessageRepository:
    def __init__(self) -> None:
        self._messages: dict[str, Message] = {}
        self._sequence = 0

    async def create_message(
        self,
        session_id: str,
        user_id: str,
        request: CreateMessageRequest,
    ) -> Message:
        self._sequence += 1
        message = Message(
            id=f"m-{self._sequence}",
            session_id=session_id,
            user_id=user_id,
            role=request.role,
            content=request.content,
            metadata=request.metadata,
            created_at=datetime.now(UTC),
        )
        self._messages[message.id] = message
        return message

    async def list_messages(self, user_id: str, session_id: str) -> list[Message]:
        return sorted(
            [
                message
                for message in self._messages.values()
                if message.user_id == user_id and message.session_id == session_id
            ],
            key=lambda message: message.created_at or datetime.min.replace(tzinfo=UTC),
        )

    async def get_message(self, user_id: str, session_id: str, message_id: str) -> Message | None:
        message = self._messages.get(message_id)
        if message is None:
            return None
        if message.user_id != user_id or message.session_id != session_id:
            return None
        return message

    async def update_message_metadata(
        self,
        *,
        user_id: str,
        session_id: str,
        message_id: str,
        metadata: dict,
    ) -> Message | None:
        message = await self.get_message(user_id, session_id, message_id)
        if message is None:
            return None

        message.metadata = metadata
        return message

    async def delete_messages_for_session(self, user_id: str, session_id: str) -> None:
        to_delete = [
            message_id
            for message_id, message in self._messages.items()
            if message.user_id == user_id and message.session_id == session_id
        ]
        for message_id in to_delete:
            del self._messages[message_id]


class InMemoryArtifactRepository:
    def __init__(self) -> None:
        self._artifacts: dict[str, Artifact] = {}

    async def create_artifact(
        self,
        session_id: str,
        user_id: str,
        request: CreateArtifactRequest,
    ) -> Artifact:
        artifact = Artifact(
            id=request.artifact_id,
            session_id=session_id,
            user_id=user_id,
            filename=request.filename,
            content_type=request.content_type,
            size_bytes=request.size_bytes,
            blob_name=request.blob_name,
            metadata=request.metadata,
            created_at=datetime.now(UTC),
        )
        self._artifacts[artifact.id] = artifact
        return artifact

    async def get_artifact(
        self,
        user_id: str,
        session_id: str,
        artifact_id: str,
    ) -> Artifact | None:
        artifact = self._artifacts.get(artifact_id)
        if artifact is None:
            return None
        if artifact.user_id != user_id or artifact.session_id != session_id:
            return None
        return artifact

    async def list_artifacts(self, user_id: str, session_id: str) -> list[Artifact]:
        return sorted(
            [
                artifact
                for artifact in self._artifacts.values()
                if artifact.user_id == user_id and artifact.session_id == session_id
            ],
            key=lambda artifact: artifact.created_at or datetime.min.replace(tzinfo=UTC),
        )

    async def delete_artifacts_for_session(
        self,
        user_id: str,
        session_id: str,
    ) -> list[Artifact]:
        artifacts = await self.list_artifacts(user_id, session_id)
        for artifact in artifacts:
            del self._artifacts[artifact.id]
        return artifacts


class InMemoryBlobStorageService:
    def __init__(self) -> None:
        self._blobs: dict[str, BlobDownload] = {}

    async def upload_blob(self, blob_name: str, content: bytes, content_type: str) -> None:
        self._blobs[blob_name] = BlobDownload(content=content, content_type=content_type)

    async def download_blob(self, blob_name: str) -> BlobDownload:
        return self._blobs[blob_name]

    async def delete_blob(self, blob_name: str) -> None:
        self._blobs.pop(blob_name, None)


class InMemoryProcessingRepository:
    def __init__(self) -> None:
        self._manifests = {}

    async def get_manifest(self, user_id, session_id, artifact_id, source_sha256):
        return self._manifests.get((user_id, session_id, artifact_id, source_sha256))

    async def upsert_manifest(self, manifest):
        self._manifests[(manifest.user_id, manifest.session_id, manifest.artifact_id, manifest.source_sha256)] = manifest
        return manifest


class InMemoryAnalysisJobRepository:
    def __init__(self) -> None:
        self._jobs = {}
        self._chunk_results = {}

    async def get_job(self, user_id, session_id, job_id):
        return self._jobs.get((user_id, session_id, job_id))

    async def get_job_by_idempotency_key(self, user_id, session_id, artifact_id, source_sha256, analysis_type):
        return next(
            (
                job
                for job in self._jobs.values()
                if (job.user_id, job.session_id, job.artifact_id, job.source_sha256, job.analysis_type)
                == (user_id, session_id, artifact_id, source_sha256, analysis_type)
            ),
            None,
        )

    async def upsert_job(self, job):
        self._jobs[(job.user_id, job.session_id, job.id)] = job
        return job

    async def try_claim_job(self, job):
        key = (job.user_id, job.session_id, job.id)
        existing = self._jobs.get(key)
        if existing is not None and job.etag != existing.etag:
            return None
        job.etag = str(int(existing.etag or "0") + 1) if existing is not None else "1"
        self._jobs[key] = job
        return job

    async def list_chunk_results(self, user_id, session_id, job_id):
        return sorted(
            [result for (owner, session, result_job_id, _), result in self._chunk_results.items()
             if (owner, session, result_job_id) == (user_id, session_id, job_id)],
            key=lambda result: result.chunk_index,
        )

    async def upsert_chunk_result(self, result):
        self._chunk_results[(result.user_id, result.session_id, result.job_id, result.chunk_index)] = result
        return result


class InMemorySessionSummaryRepository:
    def __init__(self) -> None:
        self._summaries: dict[tuple[str, str], SessionSummary] = {}

    async def get_summary(self, user_id: str, session_id: str) -> SessionSummary | None:
        return self._summaries.get((user_id, session_id))

    async def upsert_summary(self, summary: SessionSummary) -> SessionSummary:
        existing = self._summaries.get((summary.user_id, summary.session_id))
        if existing is not None:
            summary.id = existing.id
            summary.created_at = existing.created_at
        elif summary.created_at is None:
            summary.created_at = datetime.now(UTC)

        if summary.updated_at is None:
            summary.updated_at = datetime.now(UTC)

        self._summaries[(summary.user_id, summary.session_id)] = summary
        return summary


@pytest.fixture(autouse=True)
def configured_environment(monkeypatch: pytest.MonkeyPatch):
    values = {
        "COSMOS_ENDPOINT": "https://example.documents.azure.com:443/",
        "COSMOS_KEY": "test-cosmos-key",
        "COSMOS_DATABASE_NAME": "agent86-test",
        "AZURE_BLOB_CONNECTION_STRING": "UseDevelopmentStorage=true",
        "AZURE_BLOB_CONTAINER_NAME": "agent86-test-artifacts",
        "FOUNDRY_OPENAI_BASE_URL": "https://example.openai.azure.com/",
        "FOUNDRY_OPENAI_API_KEY": "test-openai-key",
        "FOUNDRY_DEFAULT_CHAT_MODEL": "gpt-4.1-mini",
        "FOUNDRY_PREMIUM_CHAT_MODEL": "gpt-5.4",
        "ENTRA_TENANT_ID": "00000000-0000-0000-0000-000000000001",
        "ENTRA_API_CLIENT_ID": "00000000-0000-0000-0000-000000000002",
        "ENTRA_API_AUDIENCE": "api://00000000-0000-0000-0000-000000000002",
    }

    for key, value in values.items():
        monkeypatch.setenv(key, value)

    clear_settings_caches()
    yield
    clear_settings_caches()


@pytest.fixture
def api_client():
    app = create_app()

    session_service = SessionService(InMemorySessionRepository())
    message_service = MessageService(InMemoryMessageRepository())
    artifact_service = ArtifactService(
        InMemoryArtifactRepository(),
        InMemoryBlobStorageService(),
    )
    derived_blob_storage = InMemoryBlobStorageService()
    processing_service = ArtifactProcessingService(
        artifact_service,
        InMemoryProcessingRepository(),
        derived_blob_storage,
        CsvArtifactProcessor(max_rows=10, chunk_rows=2),
    )
    analysis_service = ArtifactAnalysisService(
        processing_service, InMemoryAnalysisJobRepository(), derived_blob_storage
    )
    artifact_prompt_context_service = ArtifactPromptContextService(artifact_service)
    chat_model_service = SimpleNamespace(
        generate_reply=AsyncMock(
            return_value=ChatModelReply(
                assistant_text="Assistant reply",
                transcript_messages=[],
            )
        ),
        generate_reply_stream=AsyncMock(),
        generate_structured_summary=AsyncMock(),
    )
    model_router = SimpleNamespace(choose_chat_model=lambda metadata: "gpt-4.1-mini")
    tool_service = SimpleNamespace()
    session_summary_service = SessionSummaryService(
        InMemorySessionSummaryRepository(),
        session_service,
        message_service,
        artifact_service,
        artifact_prompt_context_service,
        chat_model_service,
    )
    token_validator = StubTokenValidator(
        {
            "valid-user-1": {"oid": "user-1", "aud": "api://test"},
            "valid-user-2": {"oid": "user-2", "aud": "api://test"},
            "valid-subject": {"sub": "subject-user", "aud": "api://test"},
            "missing-identity": {"aud": "api://test"},
        }
    )

    app.dependency_overrides[get_token_validator] = lambda: token_validator
    app.dependency_overrides[get_session_service] = lambda: session_service
    app.dependency_overrides[get_message_service] = lambda: message_service
    app.dependency_overrides[get_artifact_service] = lambda: artifact_service
    app.dependency_overrides[get_artifact_processing_service] = lambda: processing_service
    app.dependency_overrides[get_artifact_analysis_service] = lambda: analysis_service
    app.dependency_overrides[get_artifact_prompt_context_service] = lambda: artifact_prompt_context_service
    app.dependency_overrides[get_chat_model_service] = lambda: chat_model_service
    app.dependency_overrides[get_model_router] = lambda: model_router
    app.dependency_overrides[get_session_summary_service] = lambda: session_summary_service
    app.dependency_overrides[get_tool_service] = lambda: tool_service

    with TestClient(app) as client:
        yield (
            client,
            session_service,
            message_service,
            artifact_service,
            chat_model_service,
            session_summary_service,
        )


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_session_for(client: TestClient, token: str, title: str = "Session") -> dict:
    response = client.post(
        "/sessions",
        headers=auth_header(token),
        json={"title": title, "metadata": {}},
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload_artifact_for(client: TestClient, token: str, session_id: str, filename: str, content: bytes, content_type: str) -> dict:
    response = client.post(
        f"/sessions/{session_id}/artifacts/upload",
        headers=auth_header(token),
        files={"file": (filename, content, content_type)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_artifact_processing_routes_are_owned_idempotent_and_report_status(api_client):
    client, _, _, _, _, _ = api_client
    session = create_session_for(client, "valid-user-1", title="CSV processing")
    artifact = upload_artifact_for(
        client, "valid-user-1", session["id"], "positions.csv", b"symbol,quantity\nMSFT,10\nAAPL,20\n", "text/csv"
    )
    processing_url = f"/sessions/{session['id']}/artifacts/{artifact['id']}/process"

    first = client.post(processing_url, headers=auth_header("valid-user-1"))
    second = client.post(processing_url, headers=auth_header("valid-user-1"))
    status_response = client.get(
        f"/sessions/{session['id']}/artifacts/{artifact['id']}/processing", headers=auth_header("valid-user-1")
    )

    assert first.status_code == 200, first.text
    assert first.json()["state"] == "ready"
    assert first.json()["total_rows"] == 2
    assert first.json()["chunk_row_ranges"] == [[1, 2]]
    assert second.json()["id"] == first.json()["id"]
    assert status_response.status_code == 200
    assert status_response.json()["id"] == first.json()["id"]


def test_artifact_processing_routes_hide_other_users_artifacts(api_client):
    client, _, _, _, _, _ = api_client
    owner_session = create_session_for(client, "valid-user-1")
    artifact = upload_artifact_for(
        client, "valid-user-1", owner_session["id"], "positions.csv", b"symbol\nMSFT\n", "text/csv"
    )
    other_session = create_session_for(client, "valid-user-2")

    response = client.post(
        f"/sessions/{other_session['id']}/artifacts/{artifact['id']}/process", headers=auth_header("valid-user-2")
    )

    assert response.status_code == 404


def test_artifact_processing_route_persists_unsupported_non_csv_status(api_client):
    client, _, _, _, _, _ = api_client
    session = create_session_for(client, "valid-user-1")
    artifact = upload_artifact_for(client, "valid-user-1", session["id"], "notes.txt", b"hello", "text/plain")

    response = client.post(
        f"/sessions/{session['id']}/artifacts/{artifact['id']}/process", headers=auth_header("valid-user-1")
    )

    assert response.status_code == 200
    assert response.json()["state"] == "unsupported"


def test_entire_csv_analysis_is_complete_idempotent_and_retrievable(api_client):
    client, _, _, _, _, _ = api_client
    session = create_session_for(client, "valid-user-1")
    artifact = upload_artifact_for(
        client, "valid-user-1", session["id"], "positions.csv", b"symbol,quantity\nMSFT,10\nAAPL,\n", "text/csv"
    )
    analysis_url = f"/sessions/{session['id']}/artifacts/{artifact['id']}/analyze"

    first = client.post(analysis_url, headers=auth_header("valid-user-1"))
    second = client.post(analysis_url, headers=auth_header("valid-user-1"))
    status_response = client.get(
        f"/sessions/{session['id']}/artifacts/{artifact['id']}/analysis/{first.json()['id']}",
        headers=auth_header("valid-user-1"),
    )

    assert first.status_code == 200, first.text
    assert first.json()["state"] == "completed"
    assert first.json()["successful_rows"] == 2
    assert first.json()["successful_chunks"] == 1
    assert first.json()["findings"]["non_empty_values_by_column"] == {"symbol": 2, "quantity": 1}
    assert second.json()["id"] == first.json()["id"]
    assert status_response.status_code == 200


def test_artifact_analysis_routes_hide_other_users_jobs_and_artifacts(api_client):
    client, _, _, _, _, _ = api_client
    owner_session = create_session_for(client, "valid-user-1")
    artifact = upload_artifact_for(
        client, "valid-user-1", owner_session["id"], "positions.csv", b"symbol\nMSFT\n", "text/csv"
    )
    job_response = client.post(
        f"/sessions/{owner_session['id']}/artifacts/{artifact['id']}/analyze", headers=auth_header("valid-user-1")
    )
    other_session = create_session_for(client, "valid-user-2")

    create_response = client.post(
        f"/sessions/{other_session['id']}/artifacts/{artifact['id']}/analyze", headers=auth_header("valid-user-2")
    )
    get_response = client.get(
        f"/sessions/{other_session['id']}/artifacts/{artifact['id']}/analysis/{job_response.json()['id']}",
        headers=auth_header("valid-user-2"),
    )

    assert job_response.status_code == 200, job_response.text
    assert create_response.status_code == 404
    assert get_response.status_code == 404


def test_missing_token_returns_401(api_client):
    client, _, _, _, _, _ = api_client

    response = client.get("/sessions")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token"


def test_invalid_token_returns_401(api_client):
    client, _, _, _, _, _ = api_client

    response = client.get("/sessions", headers=auth_header("not-a-valid-token"))

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid access token"


def test_valid_token_authenticates_user_by_oid(api_client):
    client, _, _, _, _, _ = api_client

    created = create_session_for(client, "valid-user-1", title="Owned by oid")
    listed = client.get("/sessions", headers=auth_header("valid-user-1"))

    assert created["user_id"] == "user-1"
    assert listed.status_code == 200
    assert [session["id"] for session in listed.json()] == [created["id"]]


def test_sub_claim_is_used_when_oid_is_missing(api_client):
    client, _, _, _, _, _ = api_client

    response = client.post(
        "/sessions",
        headers=auth_header("valid-subject"),
        json={"title": "Fallback subject", "metadata": {}},
    )

    assert response.status_code == 201
    assert response.json()["user_id"] == "subject-user"


def test_token_missing_oid_and_sub_is_rejected(api_client):
    client, _, _, _, _, _ = api_client

    response = client.get("/sessions", headers=auth_header("missing-identity"))

    assert response.status_code == 401
    assert response.json()["detail"] == "Token is missing oid/sub claim"


def test_allowed_origin_get_response_includes_cors_header(api_client):
    client, _, _, _, _, _ = api_client

    response = client.get(
        "/sessions",
        headers={
            **auth_header("valid-user-1"),
            "Origin": "http://localhost:5173",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "Origin" in response.headers["vary"]


def test_allowed_origin_preflight_returns_cors_headers(api_client):
    client, _, _, _, _, _ = api_client

    response = client.options(
        "/sessions",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-methods"]
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed_headers
    assert "content-type" in allowed_headers


def test_static_web_app_origin_is_allowed_for_preflight_and_request(api_client):
    client, _, _, _, _, _ = api_client
    origin = "https://brave-smoke-0b55bbd1e.7.azurestaticapps.net"

    preflight = client.options(
        "/sessions",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    request = client.get("/sessions", headers={**auth_header("valid-user-1"), "Origin": origin})

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    assert request.status_code == 200
    assert request.headers["access-control-allow-origin"] == origin


def test_upload_is_rejected_when_configured_byte_limit_is_exceeded(api_client, monkeypatch: pytest.MonkeyPatch):
    client, _, _, _, _, _ = api_client
    session = create_session_for(client, "valid-user-1", title="Upload limit")
    monkeypatch.setenv("ARTIFACT_UPLOAD_MAX_BYTES", "3")
    clear_settings_caches()

    response = client.post(
        f"/sessions/{session['id']}/artifacts/upload",
        headers=auth_header("valid-user-1"),
        files={"file": ("large.csv", b"1234", "text/csv")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Artifact exceeds the 3 byte upload limit"


def test_session_ownership_is_enforced_for_list_get_update_delete_and_messages(api_client):
    client, session_service, message_service, _, _, _ = api_client

    owned = create_session_for(client, "valid-user-1", title="User 1 session")
    other = create_session_for(client, "valid-user-2", title="User 2 session")

    list_for_user_1 = client.get("/sessions", headers=auth_header("valid-user-1"))
    assert list_for_user_1.status_code == 200
    assert [session["id"] for session in list_for_user_1.json()] == [owned["id"]]

    create_message_response = client.post(
        f"/sessions/{owned['id']}/messages",
        headers=auth_header("valid-user-1"),
        json={"role": "user", "content": "hello", "metadata": {}},
    )
    assert create_message_response.status_code == 201

    get_response = client.get(
        f"/sessions/{owned['id']}",
        headers=auth_header("valid-user-2"),
    )
    patch_response = client.patch(
        f"/sessions/{owned['id']}",
        headers=auth_header("valid-user-2"),
        json={"title": "should not work"},
    )
    delete_response = client.delete(
        f"/sessions/{owned['id']}",
        headers=auth_header("valid-user-2"),
    )
    messages_response = client.get(
        f"/sessions/{owned['id']}/messages",
        headers=auth_header("valid-user-2"),
    )

    assert get_response.status_code == 404
    assert patch_response.status_code == 404
    assert delete_response.status_code == 404
    assert messages_response.status_code == 404

    own_get_response = client.get(
        f"/sessions/{owned['id']}",
        headers=auth_header("valid-user-1"),
    )
    own_messages_response = client.get(
        f"/sessions/{owned['id']}/messages",
        headers=auth_header("valid-user-1"),
    )

    assert own_get_response.status_code == 200
    assert own_messages_response.status_code == 200
    assert len(own_messages_response.json()) == 1
    assert other["id"] != owned["id"]


def test_chat_route_passes_authenticated_user_into_tool_context(api_client):
    client, _, _, _, chat_model_service, _ = api_client

    session = create_session_for(client, "valid-user-1", title="Chat session")

    response = client.post(
        f"/sessions/{session['id']}/chat",
        headers=auth_header("valid-user-1"),
        json={
            "content": "Hello from the signed-in user",
            "metadata": {"enable_web_search": False},
            "tools": [],
        },
    )

    assert response.status_code == 201
    assert chat_model_service.generate_reply.await_count == 1

    kwargs = chat_model_service.generate_reply.await_args.kwargs
    tool_context = kwargs["tool_context"]

    assert isinstance(tool_context, ToolContext)
    assert tool_context.user_id == "user-1"
    assert tool_context.session_id == session["id"]
    assert tool_context.metadata == {"enable_web_search": False}


def test_choose_tool_names_includes_web_search_when_toggle_enabled_for_non_current_prompt():
    assert choose_tool_names(
        "What is the capital of France?",
        {"enable_web_search": True},
    ) == ["web_search"]


def test_choose_tool_names_excludes_web_search_when_toggle_disabled():
    assert choose_tool_names(
        "What is the latest AI news?",
        {"enable_web_search": False},
    ) == []


def test_artifact_routes_and_chat_attachment_metadata_enforce_ownership(api_client):
    client, _, _, _, _, _ = api_client

    owned_session = create_session_for(client, "valid-user-1", title="Owned")
    other_session = create_session_for(client, "valid-user-2", title="Other")

    upload_response = client.post(
        f"/sessions/{owned_session['id']}/artifacts/upload",
        headers=auth_header("valid-user-1"),
        files={"file": ("notes.txt", b"hello artifact", "text/plain")},
        data={"metadata": '{"label": "primary"}'},
    )

    assert upload_response.status_code == 201, upload_response.text
    artifact = upload_response.json()

    list_response = client.get(
        f"/sessions/{owned_session['id']}/artifacts",
        headers=auth_header("valid-user-1"),
    )
    get_response = client.get(
        f"/sessions/{owned_session['id']}/artifacts/{artifact['id']}",
        headers=auth_header("valid-user-1"),
    )
    download_response = client.get(
        f"/sessions/{owned_session['id']}/artifacts/{artifact['id']}/download",
        headers=auth_header("valid-user-1"),
    )

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [artifact["id"]]
    assert get_response.status_code == 200
    assert get_response.json()["metadata"] == {"label": "primary"}
    assert download_response.status_code == 200
    assert download_response.content == b"hello artifact"

    wrong_user_get = client.get(
        f"/sessions/{owned_session['id']}/artifacts/{artifact['id']}",
        headers=auth_header("valid-user-2"),
    )
    wrong_session_chat = client.post(
        f"/sessions/{other_session['id']}/chat",
        headers=auth_header("valid-user-2"),
        json={
            "content": "Try to use another user's artifact",
            "metadata": {"artifact_ids": [artifact["id"]]},
            "tools": [],
        },
    )

    assert wrong_user_get.status_code == 404
    assert wrong_session_chat.status_code == 404

    own_chat = client.post(
        f"/sessions/{owned_session['id']}/chat",
        headers=auth_header("valid-user-1"),
        json={
            "content": "Use my attachment",
            "metadata": {"artifact_ids": [artifact["id"], artifact["id"]]},
            "tools": [],
        },
    )

    assert own_chat.status_code == 201, own_chat.text

    persisted_messages = client.get(
        f"/sessions/{owned_session['id']}/messages",
        headers=auth_header("valid-user-1"),
    )
    assert persisted_messages.status_code == 200
    user_messages = [message for message in persisted_messages.json() if message["role"] == "user"]
    assert user_messages[-1]["metadata"] == {"artifact_ids": [artifact["id"]]}


def test_generated_artifact_route_persists_lineage_and_enforces_source_ownership(api_client):
    client, _, _, _, _, _ = api_client

    owned_session = create_session_for(client, "valid-user-1", title="Owned")
    other_session = create_session_for(client, "valid-user-2", title="Other")

    upload_response = client.post(
        f"/sessions/{owned_session['id']}/artifacts/upload",
        headers=auth_header("valid-user-1"),
        files={"file": ("notes.txt", b"hello artifact", "text/plain")},
        data={"metadata": '{"label": "primary"}'},
    )
    assert upload_response.status_code == 201, upload_response.text
    source_artifact = upload_response.json()

    message_response = client.post(
        f"/sessions/{owned_session['id']}/messages",
        headers=auth_header("valid-user-1"),
        json={"role": "assistant", "content": "Created a revision", "metadata": {}},
    )
    assert message_response.status_code == 201, message_response.text
    assistant_message = message_response.json()

    generated_content = b"revised artifact"
    create_generated_response = client.post(
        f"/sessions/{owned_session['id']}/artifacts/generated",
        headers=auth_header("valid-user-1"),
        json={
            "filename": "notes-revised.txt",
            "content_type": "text/plain",
            "content_base64": base64.b64encode(generated_content).decode("ascii"),
            "source_artifact_ids": [source_artifact["id"], source_artifact["id"]],
            "generated_by_message_id": assistant_message["id"],
            "metadata": {"label": "revised"},
        },
    )

    assert create_generated_response.status_code == 201, create_generated_response.text
    generated_artifact = create_generated_response.json()
    assert generated_artifact["filename"] == "notes-revised.txt"
    assert generated_artifact["metadata"] == {
        "label": "revised",
        "artifact_kind": "generated",
        "source_artifact_ids": [source_artifact["id"]],
        "generated_by_message_id": assistant_message["id"],
    }

    list_response = client.get(
        f"/sessions/{owned_session['id']}/artifacts",
        headers=auth_header("valid-user-1"),
    )
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [source_artifact["id"], generated_artifact["id"]]

    download_response = client.get(
        f"/sessions/{owned_session['id']}/artifacts/{generated_artifact['id']}/download",
        headers=auth_header("valid-user-1"),
    )
    assert download_response.status_code == 200
    assert download_response.content == generated_content

    wrong_session_response = client.post(
        f"/sessions/{other_session['id']}/artifacts/generated",
        headers=auth_header("valid-user-2"),
        json={
            "filename": "unauthorized.txt",
            "content_type": "text/plain",
            "content_base64": base64.b64encode(b"should fail").decode("ascii"),
            "source_artifact_ids": [source_artifact["id"]],
            "metadata": {},
        },
    )

    assert wrong_session_response.status_code == 404


def test_chat_route_injects_artifact_context_message_into_model_history(api_client):
    client, _, _, _, chat_model_service, _ = api_client

    session = create_session_for(client, "valid-user-1", title="Artifact context")
    upload_response = client.post(
        f"/sessions/{session['id']}/artifacts/upload",
        headers=auth_header("valid-user-1"),
        files={"file": ("context.txt", b"artifact body for model", "text/plain")},
        data={"metadata": "{}"},
    )
    assert upload_response.status_code == 201, upload_response.text
    artifact = upload_response.json()

    response = client.post(
        f"/sessions/{session['id']}/chat",
        headers=auth_header("valid-user-1"),
        json={
            "content": "Please use the attachment",
            "metadata": {"artifact_ids": [artifact["id"]]},
            "tools": [],
        },
    )

    assert response.status_code == 201, response.text
    chat_model_service.generate_reply.assert_awaited_once()
    call_kwargs = chat_model_service.generate_reply.await_args.kwargs
    messages = call_kwargs["messages"]
    assert messages[0].role == "system"
    assert messages[0].metadata["message_type"] == "artifact_context"
    assert "artifact body for model" in messages[0].content
    assert messages[1].role == "user"
    assert messages[1].content == "Please use the attachment"


def test_chat_route_persists_generated_artifacts_from_tool_results(api_client):
    client, _, _, _, chat_model_service, _ = api_client

    session = create_session_for(client, "valid-user-1", title="Generated outputs")
    source_upload_response = client.post(
        f"/sessions/{session['id']}/artifacts/upload",
        headers=auth_header("valid-user-1"),
        files={"file": ("source.txt", b"seed artifact", "text/plain")},
        data={"metadata": '{"label": "seed"}'},
    )
    assert source_upload_response.status_code == 201, source_upload_response.text
    source_artifact = source_upload_response.json()

    chat_model_service.generate_reply.return_value = ChatModelReply(
        assistant_text="I created a derived file.",
        transcript_messages=[],
        tool_results=[
            SimpleNamespace(
                tool_name="echo",
                content="done",
                metadata={
                    "output_artifacts": [
                        {
                            "filename": "derived.txt",
                            "content_type": "text/plain",
                            "content": "derived body",
                            "source_artifact_ids": [source_artifact["id"]],
                            "metadata": {"label": "derived"},
                        }
                    ]
                },
            )
        ],
    )

    response = client.post(
        f"/sessions/{session['id']}/chat",
        headers=auth_header("valid-user-1"),
        json={
            "content": "Please produce a derived file",
            "metadata": {},
            "tools": [],
        },
    )

    assert response.status_code == 201, response.text
    assistant_message = response.json()["message"]
    generated_artifacts = assistant_message["metadata"]["generated_artifacts"]
    assert len(generated_artifacts) == 1
    generated_artifact = generated_artifacts[0]
    assert generated_artifact["filename"] == "derived.txt"
    assert generated_artifact["content_type"] == "text/plain"
    assert generated_artifact["metadata"] == {
        "label": "derived",
        "artifact_kind": "generated",
        "source_artifact_ids": [source_artifact["id"]],
        "generated_by_message_id": assistant_message["id"],
    }

    artifacts_response = client.get(
        f"/sessions/{session['id']}/artifacts",
        headers=auth_header("valid-user-1"),
    )
    assert artifacts_response.status_code == 200, artifacts_response.text
    artifacts = artifacts_response.json()
    assert [artifact["filename"] for artifact in artifacts] == ["source.txt", "derived.txt"]

    persisted_messages_response = client.get(
        f"/sessions/{session['id']}/messages",
        headers=auth_header("valid-user-1"),
    )
    assert persisted_messages_response.status_code == 200, persisted_messages_response.text
    persisted_assistant_message = persisted_messages_response.json()[-1]
    assert persisted_assistant_message["metadata"] == assistant_message["metadata"]


def test_startup_fails_with_concise_error_when_auth_configuration_is_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("ENTRA_TENANT_ID", raising=False)
    clear_settings_caches()

    with pytest.raises(SystemExit) as exc_info:
        create_app()

    assert str(exc_info.value) == "Missing required backend configuration: ENTRA_TENANT_ID"


def test_get_session_summary_returns_404_when_missing(api_client):
    client, _, _, _, _, _ = api_client

    session = create_session_for(client, "valid-user-1", title="Summary target")

    response = client.get(
        f"/sessions/{session['id']}/summary",
        headers=auth_header("valid-user-1"),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == f"Summary for session '{session['id']}' not found"


def test_session_summary_routes_enforce_ownership(api_client):
    client, _, _, _, _, _ = api_client

    owned = create_session_for(client, "valid-user-1", title="Owned")

    response = client.get(
        f"/sessions/{owned['id']}/summary",
        headers=auth_header("valid-user-2"),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == f"Session '{owned['id']}' not found"


def test_generate_session_summary_creates_and_overwrites_existing_summary(api_client):
    client, _, _, _, chat_model_service, session_summary_service = api_client

    session = create_session_for(client, "valid-user-1", title="Summary target")
    create_message_response = client.post(
        f"/sessions/{session['id']}/messages",
        headers=auth_header("valid-user-1"),
        json={"role": "user", "content": "Discuss migration plan", "metadata": {}},
    )
    assert create_message_response.status_code == 201, create_message_response.text

    first_generated = ChatSessionSummary(
        session_id=session["id"],
        title="Migration planning discussion",
        date_range_start=datetime(2026, 1, 1, tzinfo=UTC),
        date_range_end=datetime(2026, 1, 1, 1, tzinfo=UTC),
        one_line_summary="The session focused on planning a migration.",
        topics=["migration", "planning"],
        key_decisions=["Use phased rollout"],
        action_items=[ActionItem(description="Draft runbook", status="open", owner="John")],
        artifacts_generated=[],
        open_questions=["Exact cutover window?"],
        tools_used=[],
        tags=["planning"],
    )
    second_generated = ChatSessionSummary(
        session_id=session["id"],
        title="Updated migration plan",
        date_range_start=datetime(2026, 1, 1, tzinfo=UTC),
        date_range_end=datetime(2026, 1, 1, 2, tzinfo=UTC),
        one_line_summary="The session finalized the updated migration approach.",
        topics=["migration", "rollout"],
        key_decisions=["Roll out by region"],
        action_items=[ActionItem(description="Notify stakeholders", status="done", owner="Ops")],
        artifacts_generated=[
            ArtifactRef(name="plan.docx", artifact_type="docx", location="artifact-123")
        ],
        open_questions=[],
        tools_used=["web_search"],
        tags=["decision"],
    )
    chat_model_service.generate_structured_summary.side_effect = [first_generated, second_generated]

    first_response = client.post(
        f"/sessions/{session['id']}/summary",
        headers=auth_header("valid-user-1"),
    )
    assert first_response.status_code == 201, first_response.text
    first_payload = first_response.json()
    assert first_payload["title"] == "Migration planning discussion"

    second_response = client.post(
        f"/sessions/{session['id']}/summary",
        headers=auth_header("valid-user-1"),
    )
    assert second_response.status_code == 201, second_response.text
    second_payload = second_response.json()
    assert second_payload["id"] == first_payload["id"]
    assert second_payload["title"] == "Updated migration plan"
    assert second_payload["one_line_summary"] == "The session finalized the updated migration approach."
    assert second_payload["tools_used"] == ["web_search"]

    stored_summary = client.get(
        f"/sessions/{session['id']}/summary",
        headers=auth_header("valid-user-1"),
    )
    assert stored_summary.status_code == 200, stored_summary.text
    assert stored_summary.json()["title"] == "Updated migration plan"
    assert session_summary_service is not None


def test_generate_session_summary_uses_messages_and_persisted_artifacts(api_client):
    client, _, _, _, chat_model_service, _ = api_client

    session = create_session_for(client, "valid-user-1", title="Artifacts and tools")
    upload_response = client.post(
        f"/sessions/{session['id']}/artifacts/upload",
        headers=auth_header("valid-user-1"),
        files={"file": ("plan.docx", b"doc body", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"metadata": '{"label": "draft"}'},
    )
    assert upload_response.status_code == 201, upload_response.text
    uploaded_artifact = upload_response.json()

    create_user_response = client.post(
        f"/sessions/{session['id']}/messages",
        headers=auth_header("valid-user-1"),
        json={"role": "user", "content": "Summarize our project plan", "metadata": {"tools": ["web_search"]}},
    )
    assert create_user_response.status_code == 201, create_user_response.text
    create_tool_response = client.post(
        f"/sessions/{session['id']}/messages",
        headers=auth_header("valid-user-1"),
        json={
            "role": "assistant",
            "content": "Called tool",
            "metadata": {"message_type": "function_call", "tool_name": "web_search"},
        },
    )
    assert create_tool_response.status_code == 201, create_tool_response.text

    chat_model_service.generate_structured_summary.return_value = ChatSessionSummary(
        session_id=session["id"],
        title="Project plan summary",
        date_range_start=datetime(2026, 1, 1, tzinfo=UTC),
        date_range_end=datetime(2026, 1, 1, 1, tzinfo=UTC),
        one_line_summary="The team reviewed the current project plan.",
        topics=["project plan"],
        key_decisions=[],
        action_items=[],
        artifacts_generated=[],
        open_questions=[],
        tools_used=[],
        tags=[],
    )

    response = client.post(
        f"/sessions/{session['id']}/summary",
        headers=auth_header("valid-user-1"),
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["tools_used"] == ["web_search"]
    assert payload["artifacts_generated"] == [
        {
            "name": "plan.docx",
            "artifact_type": "docx",
            "location": uploaded_artifact["id"],
        }
    ]

    call_kwargs = chat_model_service.generate_structured_summary.await_args.kwargs
    context_payload = call_kwargs["context_payload"]
    assert context_payload["artifact_prompt_context"] == [
        {
            "id": uploaded_artifact["id"],
            "filename": "plan.docx",
            "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "metadata": {"label": "draft"},
            "readability": "unreadable",
        }
    ]
