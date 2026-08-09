import os
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
    get_chat_model_service,
    get_message_service,
    get_model_router,
    get_session_service,
    get_tool_service,
)
from agent_86.auth.dependencies import get_token_validator
from agent_86.auth.provider import TokenValidationError
from agent_86.core.config import get_settings
from agent_86.domain.models.artifact import Artifact
from agent_86.domain.models.message import Message
from agent_86.domain.schemas.artifact import CreateArtifactRequest
from agent_86.domain.schemas.message import CreateMessageRequest
from agent_86.domain.schemas.session import CreateSessionRequest
from agent_86.main import create_app
from agent_86.repositories.in_memory_session_repository import InMemorySessionRepository
from agent_86.services.artifact_service import ArtifactService
from agent_86.services.blob_storage_service import BlobDownload
from agent_86.services.chat_model_service import ChatModelReply
from agent_86.services.message_service import MessageService
from agent_86.services.session_service import SessionService
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
    chat_model_service = SimpleNamespace(
        generate_reply=AsyncMock(
            return_value=ChatModelReply(
                assistant_text="Assistant reply",
                transcript_messages=[],
            )
        ),
        generate_reply_stream=AsyncMock(),
    )
    model_router = SimpleNamespace(choose_chat_model=lambda metadata: "gpt-4.1-mini")
    tool_service = SimpleNamespace()
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
    app.dependency_overrides[get_chat_model_service] = lambda: chat_model_service
    app.dependency_overrides[get_model_router] = lambda: model_router
    app.dependency_overrides[get_tool_service] = lambda: tool_service

    with TestClient(app) as client:
        yield client, session_service, message_service, artifact_service, chat_model_service


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


def test_missing_token_returns_401(api_client):
    client, _, _, _, _ = api_client

    response = client.get("/sessions")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token"


def test_invalid_token_returns_401(api_client):
    client, _, _, _, _ = api_client

    response = client.get("/sessions", headers=auth_header("not-a-valid-token"))

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid access token"


def test_valid_token_authenticates_user_by_oid(api_client):
    client, _, _, _, _ = api_client

    created = create_session_for(client, "valid-user-1", title="Owned by oid")
    listed = client.get("/sessions", headers=auth_header("valid-user-1"))

    assert created["user_id"] == "user-1"
    assert listed.status_code == 200
    assert [session["id"] for session in listed.json()] == [created["id"]]


def test_sub_claim_is_used_when_oid_is_missing(api_client):
    client, _, _, _, _ = api_client

    response = client.post(
        "/sessions",
        headers=auth_header("valid-subject"),
        json={"title": "Fallback subject", "metadata": {}},
    )

    assert response.status_code == 201
    assert response.json()["user_id"] == "subject-user"


def test_token_missing_oid_and_sub_is_rejected(api_client):
    client, _, _, _, _ = api_client

    response = client.get("/sessions", headers=auth_header("missing-identity"))

    assert response.status_code == 401
    assert response.json()["detail"] == "Token is missing oid/sub claim"


def test_allowed_origin_get_response_includes_cors_header(api_client):
    client, _, _, _, _ = api_client

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
    client, _, _, _, _ = api_client

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


def test_session_ownership_is_enforced_for_list_get_update_delete_and_messages(api_client):
    client, session_service, message_service, _, _ = api_client

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
    client, _, _, _, chat_model_service = api_client

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


def test_artifact_routes_and_chat_attachment_metadata_enforce_ownership(api_client):
    client, _, _, _, _ = api_client

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


def test_startup_fails_with_concise_error_when_auth_configuration_is_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("ENTRA_TENANT_ID", raising=False)
    clear_settings_caches()

    with pytest.raises(SystemExit) as exc_info:
        create_app()

    assert str(exc_info.value) == "Missing required backend configuration: ENTRA_TENANT_ID"
