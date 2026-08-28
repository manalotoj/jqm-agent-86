"""Tests for POST /sessions/{session_id}/context-summary."""
import json
import os
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
os.environ.setdefault("ENTRA_API_AUDIENCE", "api://00000000-0000-0000-0000-000000000002")

from agent_86.api.dependencies import (
    get_chat_model_service,
    get_message_service,
    get_model_router,
    get_session_service,
)
from agent_86.auth.dependencies import get_token_validator
from agent_86.core.config import get_settings
from agent_86.main import create_app
from agent_86.services.chat_model_service import ChatModelReply
from agent_86.services.message_service import MessageService
from agent_86.services.session_service import SessionService
from agent_86.repositories.in_memory_session_repository import InMemorySessionRepository
from tests.test_auth_and_authorization import (
    InMemoryMessageRepository,
    StubTokenValidator,
    clear_settings_caches,
    auth_header,
    create_session_for,
)


def _parse_sse(raw: bytes) -> list[dict]:
    events = []
    current: dict = {}
    for line in raw.decode().splitlines():
        if line.startswith("event:"):
            current["event"] = line[len("event:"):].strip()
        elif line.startswith("data:"):
            current["data"] = json.loads(line[len("data:"):].strip())
        elif line == "" and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


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
    chat_model_service = SimpleNamespace(
        generate_reply=AsyncMock(
            return_value=ChatModelReply(
                assistant_text="You were working on a migration plan. The next step is to finalise the runbook.",
                transcript_messages=[],
            )
        ),
        generate_reply_stream=AsyncMock(),
        generate_structured_summary=AsyncMock(),
    )
    model_router = SimpleNamespace(
        choose_chat_model=lambda metadata: "gpt-4.1-mini",
        premium_model="gpt-5.4",
    )
    token_validator = StubTokenValidator(
        {
            "valid-user-1": {"oid": "user-1", "aud": "api://test"},
            "valid-user-2": {"oid": "user-2", "aud": "api://test"},
        }
    )
    app.dependency_overrides[get_token_validator] = lambda: token_validator
    app.dependency_overrides[get_session_service] = lambda: session_service
    app.dependency_overrides[get_message_service] = lambda: message_service
    app.dependency_overrides[get_chat_model_service] = lambda: chat_model_service
    app.dependency_overrides[get_model_router] = lambda: model_router
    with TestClient(app) as client:
        yield client, session_service, message_service, chat_model_service


def test_generate_context_summary_returns_sse_chunk_and_done(api_client):
    client, _, _, chat_model_service = api_client
    session = create_session_for(client, "valid-user-1", title="Context summary test")
    client.post(
        f"/sessions/{session['id']}/messages",
        headers=auth_header("valid-user-1"),
        json={"role": "user", "content": "Help me plan a migration", "metadata": {}},
    )

    response = client.post(
        f"/sessions/{session['id']}/context-summary",
        headers=auth_header("valid-user-1"),
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    events = _parse_sse(response.content)
    event_names = [e["event"] for e in events]
    assert "chunk" in event_names
    assert "done" in event_names
    chunk_event = next(e for e in events if e["event"] == "chunk")
    assert "text" in chunk_event["data"]
    assert chunk_event["data"]["text"] != ""


def test_generate_context_summary_passes_system_prompt_and_full_history(api_client):
    client, _, _, chat_model_service = api_client
    session = create_session_for(client, "valid-user-1")
    client.post(
        f"/sessions/{session['id']}/messages",
        headers=auth_header("valid-user-1"),
        json={"role": "user", "content": "First message", "metadata": {}},
    )
    client.post(
        f"/sessions/{session['id']}/messages",
        headers=auth_header("valid-user-1"),
        json={"role": "assistant", "content": "First reply", "metadata": {}},
    )

    client.post(
        f"/sessions/{session['id']}/context-summary",
        headers=auth_header("valid-user-1"),
    )

    call_args = chat_model_service.generate_reply.await_args
    messages_passed = call_args.kwargs["messages"]
    assert messages_passed[0].role == "system"
    assert "context block" in messages_passed[0].content
    roles = [m.role for m in messages_passed[1:]]
    assert "user" in roles
    assert "assistant" in roles


def test_generate_context_summary_returns_422_when_no_messages(api_client):
    client, _, _, _ = api_client
    session = create_session_for(client, "valid-user-1", title="Empty session")
    response = client.post(
        f"/sessions/{session['id']}/context-summary",
        headers=auth_header("valid-user-1"),
    )
    assert response.status_code == 422


def test_generate_context_summary_returns_404_for_unknown_session(api_client):
    client, _, _, _ = api_client
    response = client.post(
        "/sessions/nonexistent-session-id/context-summary",
        headers=auth_header("valid-user-1"),
    )
    assert response.status_code == 404


def test_generate_context_summary_enforces_session_ownership(api_client):
    client, _, _, _ = api_client
    session = create_session_for(client, "valid-user-1", title="Owned session")
    client.post(
        f"/sessions/{session['id']}/messages",
        headers=auth_header("valid-user-1"),
        json={"role": "user", "content": "Hello", "metadata": {}},
    )
    response = client.post(
        f"/sessions/{session['id']}/context-summary",
        headers=auth_header("valid-user-2"),
    )
    assert response.status_code == 404


def test_generate_context_summary_requires_authentication(api_client):
    client, _, _, _ = api_client
    session = create_session_for(client, "valid-user-1")
    response = client.post(f"/sessions/{session['id']}/context-summary")
    assert response.status_code == 401
