import os
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("COSMOS_ENDPOINT", "https://example.documents.azure.com:443/")
os.environ.setdefault("COSMOS_KEY", "test-cosmos-key")
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
    get_chat_model_service,
    get_message_service,
    get_model_router,
    get_session_service,
    get_tool_service,
)
from agent_86.auth.dependencies import get_token_validator
from agent_86.auth.provider import TokenValidationError
from agent_86.core.config import Settings, get_settings
from agent_86.domain.models.message import Message
from agent_86.domain.schemas.message import CreateMessageRequest
from agent_86.domain.schemas.session import CreateSessionRequest
from agent_86.main import create_app
from agent_86.repositories.in_memory_session_repository import InMemorySessionRepository
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


@pytest.fixture(autouse=True)
def configured_environment(monkeypatch: pytest.MonkeyPatch):
    values = {
        "COSMOS_ENDPOINT": "https://example.documents.azure.com:443/",
        "COSMOS_KEY": "test-cosmos-key",
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

    original_env_file = Settings.model_config.get("env_file")
    Settings.model_config["env_file"] = None

    clear_settings_caches()
    yield
    Settings.model_config["env_file"] = original_env_file
    clear_settings_caches()


@pytest.fixture
def api_client():
    app = create_app()

    session_service = SessionService(InMemorySessionRepository())
    message_service = MessageService(InMemoryMessageRepository())
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
    app.dependency_overrides[get_chat_model_service] = lambda: chat_model_service
    app.dependency_overrides[get_model_router] = lambda: model_router
    app.dependency_overrides[get_tool_service] = lambda: tool_service

    with TestClient(app) as client:
        yield client, session_service, message_service, chat_model_service


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
    client, _, _, _ = api_client

    response = client.get("/sessions")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token"


def test_invalid_token_returns_401(api_client):
    client, _, _, _ = api_client

    response = client.get("/sessions", headers=auth_header("not-a-valid-token"))

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid access token"


def test_valid_token_authenticates_user_by_oid(api_client):
    client, _, _, _ = api_client

    created = create_session_for(client, "valid-user-1", title="Owned by oid")
    listed = client.get("/sessions", headers=auth_header("valid-user-1"))

    assert created["user_id"] == "user-1"
    assert listed.status_code == 200
    assert [session["id"] for session in listed.json()] == [created["id"]]


def test_sub_claim_is_used_when_oid_is_missing(api_client):
    client, _, _, _ = api_client

    response = client.post(
        "/sessions",
        headers=auth_header("valid-subject"),
        json={"title": "Fallback subject", "metadata": {}},
    )

    assert response.status_code == 201
    assert response.json()["user_id"] == "subject-user"


def test_token_missing_oid_and_sub_is_rejected(api_client):
    client, _, _, _ = api_client

    response = client.get("/sessions", headers=auth_header("missing-identity"))

    assert response.status_code == 401
    assert response.json()["detail"] == "Token is missing oid/sub claim"


def test_session_ownership_is_enforced_for_list_get_update_delete_and_messages(api_client):
    client, session_service, message_service, _ = api_client

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
    client, _, _, chat_model_service = api_client

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


def test_startup_fails_with_concise_error_when_auth_configuration_is_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("ENTRA_TENANT_ID", raising=False)
    clear_settings_caches()

    with pytest.raises(SystemExit) as exc_info:
        create_app()

    assert str(exc_info.value) == "Missing required backend configuration: ENTRA_TENANT_ID"
