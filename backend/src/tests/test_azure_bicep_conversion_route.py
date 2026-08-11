import json
import os
from dataclasses import dataclass
from types import SimpleNamespace

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
    get_artifact_service,
    get_azure_bicep_conversion_orchestrator,
    get_message_service,
    get_session_service,
)
from agent_86.auth.dependencies import get_token_validator
from agent_86.domain.schemas.session import CreateSessionRequest
from agent_86.integrations.bicep.bicep_tool_client import BicepCliNotFoundError
from agent_86.main import create_app
from agent_86.repositories.in_memory_session_repository import InMemorySessionRepository
from agent_86.services.artifact_service import ArtifactService
from agent_86.services.message_service import MessageService
from agent_86.services.session_service import SessionService
from tests.test_auth_and_authorization import (
    InMemoryArtifactRepository,
    InMemoryBlobStorageService,
    InMemoryMessageRepository,
    StubTokenValidator,
    clear_settings_caches,
)


def _parse_sse_events(response) -> list[dict]:
    events: list[dict] = []
    current_event_name: str | None = None
    current_data_lines: list[str] = []

    for line in response.iter_lines():
        if line == "":
            if current_event_name is not None:
                payload_text = "\n".join(current_data_lines) if current_data_lines else "{}"
                events.append({"event": current_event_name, "data": json.loads(payload_text)})
            current_event_name = None
            current_data_lines = []
            continue

        if line.startswith("event: "):
            current_event_name = line.removeprefix("event: ")
            continue

        if line.startswith("data: "):
            current_data_lines.append(line.removeprefix("data: "))

    if current_event_name is not None:
        payload_text = "\n".join(current_data_lines) if current_data_lines else "{}"
        events.append({"event": current_event_name, "data": json.loads(payload_text)})

    return events


@dataclass
class StubConversionArtifact:
    filename: str
    content_type: str
    content: bytes
    metadata: dict


@dataclass
class StubConversionSummary:
    subscription_id: str
    resource_group_name: str
    azure_environment: str
    resource_count: int
    export_mode: str
    batch_count: int
    merge_mode: str
    fallback_used: bool
    unresolved_reference_count: int
    secure_parameter_count: int
    avm_annotation_count: int
    diagnostics: list[str]
    generated_files: list[str]


class StubConversionOrchestrator:
    def __init__(self, *, should_raise: bool = False, fallback_used: bool = False) -> None:
        self.calls: list[dict] = []
        self._should_raise = should_raise
        self._fallback_used = fallback_used

    async def convert_resource_group(self, **kwargs):
        self.calls.append(kwargs)
        if self._should_raise:
            raise RuntimeError("conversion failed")
        return SimpleNamespace(
            artifact=StubConversionArtifact(
                filename="rg-route-bicep-package.zip",
                content_type="application/zip",
                content=b"zip-bytes",
                metadata={"conversion_kind": "azure_export_to_bicep"},
            ),
            summary=StubConversionSummary(
                subscription_id=kwargs["subscription_id"],
                resource_group_name=kwargs["resource_group_name"],
                azure_environment=kwargs["azure_environment"],
                resource_count=2,
                export_mode="wildcard",
                batch_count=1,
                merge_mode="low_fidelity_text_fallback" if self._fallback_used else "ast",
                fallback_used=self._fallback_used,
                unresolved_reference_count=0,
                secure_parameter_count=1,
                avm_annotation_count=1,
                diagnostics=(
                    [
                        "Composition sidecar failed during compose; using fallback package instead: composition failed",
                        "AST composition was unavailable; generated a low-fidelity text fallback package.",
                    ]
                    if self._fallback_used
                    else ["done"]
                ),
                generated_files=["main.bicep", "modules/fragment_000.bicep"] if self._fallback_used else ["main.bicep"],
            ),
        )


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
def conversion_api_client():
    app = create_app()
    session_service = SessionService(InMemorySessionRepository())
    message_service = MessageService(InMemoryMessageRepository())
    artifact_service = ArtifactService(InMemoryArtifactRepository(), InMemoryBlobStorageService())
    orchestrator = StubConversionOrchestrator()
    token_validator = StubTokenValidator({"valid-user": {"oid": "user-1", "aud": "api://test"}})

    app.dependency_overrides[get_token_validator] = lambda: token_validator
    app.dependency_overrides[get_session_service] = lambda: session_service
    app.dependency_overrides[get_message_service] = lambda: message_service
    app.dependency_overrides[get_artifact_service] = lambda: artifact_service
    app.dependency_overrides[get_azure_bicep_conversion_orchestrator] = lambda: orchestrator

    with TestClient(app) as client:
        yield client, session_service, artifact_service, orchestrator


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_convert_resource_group_to_bicep_stream_returns_named_sse_events_and_persists_artifact(conversion_api_client) -> None:
    client, session_service, artifact_service, orchestrator = conversion_api_client
    session = await session_service.create_session("user-1", CreateSessionRequest(title="Conversion", metadata={}))

    with client.stream(
        "POST",
        f"/sessions/{session.id}/azure-bicep-conversion/stream",
        headers={**auth_header("valid-user"), "Accept": "text/event-stream"},
        json={
            "subscription_id": "sub-123",
            "resource_group_name": "rg-route",
            "azure_environment": "AzureCloud",
            "gov_approved_avm_modules": ["avm/res/storage/storage-account"],
            "metadata": {"label": "conversion-output"},
        },
    ) as response:
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse_events(response)

    assert [event["event"] for event in events] == ["start", "complete", "done"]
    assert events[0]["data"] == {
        "session_id": session.id,
        "subscription_id": "sub-123",
        "resource_group_name": "rg-route",
        "azure_environment": "AzureCloud",
    }
    assert events[1]["data"]["artifact"]["filename"] == "rg-route-bicep-package.zip"
    assert events[1]["data"]["artifact"]["content_type"] == "application/zip"
    assert events[1]["data"]["artifact"]["metadata"]["artifact_kind"] == "generated"
    assert events[1]["data"]["artifact"]["metadata"]["conversion_kind"] == "azure_export_to_bicep"
    assert events[1]["data"]["artifact"]["metadata"]["label"] == "conversion-output"
    assert events[1]["data"]["summary"]["merge_mode"] == "ast"
    assert events[1]["data"]["summary"]["fallback_used"] is False
    assert events[1]["data"]["summary"]["generated_files"] == ["main.bicep"]

    assert orchestrator.calls == [
        {
            "subscription_id": "sub-123",
            "resource_group_name": "rg-route",
            "azure_environment": "AzureCloud",
            "gov_approved_avm_modules": ["avm/res/storage/storage-account"],
        }
    ]

    artifacts = await artifact_service.list_artifacts("user-1", session.id)
    assert len(artifacts) == 1
    assert artifacts[0].filename == "rg-route-bicep-package.zip"


@pytest.mark.asyncio
async def test_convert_resource_group_to_bicep_stream_surfaces_fallback_summary_details(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    session_service = SessionService(InMemorySessionRepository())
    message_service = MessageService(InMemoryMessageRepository())
    artifact_service = ArtifactService(InMemoryArtifactRepository(), InMemoryBlobStorageService())
    orchestrator = StubConversionOrchestrator(fallback_used=True)
    token_validator = StubTokenValidator({"valid-user": {"oid": "user-1", "aud": "api://test"}})

    app.dependency_overrides[get_token_validator] = lambda: token_validator
    app.dependency_overrides[get_session_service] = lambda: session_service
    app.dependency_overrides[get_message_service] = lambda: message_service
    app.dependency_overrides[get_artifact_service] = lambda: artifact_service
    app.dependency_overrides[get_azure_bicep_conversion_orchestrator] = lambda: orchestrator

    session = await session_service.create_session("user-1", CreateSessionRequest(title="Conversion", metadata={}))

    with TestClient(app) as client:
        with client.stream(
            "POST",
            f"/sessions/{session.id}/azure-bicep-conversion/stream",
            headers={**auth_header("valid-user"), "Accept": "text/event-stream"},
            json={
                "subscription_id": "sub-123",
                "resource_group_name": "rg-route",
                "azure_environment": "AzureCloud",
                "gov_approved_avm_modules": [],
                "metadata": {},
            },
        ) as response:
            assert response.status_code == 200, response.text
            events = _parse_sse_events(response)

    assert [event["event"] for event in events] == ["start", "complete", "done"]
    assert events[1]["data"]["summary"]["merge_mode"] == "low_fidelity_text_fallback"
    assert events[1]["data"]["summary"]["fallback_used"] is True
    assert events[1]["data"]["summary"]["generated_files"] == ["main.bicep", "modules/fragment_000.bicep"]
    assert events[1]["data"]["summary"]["diagnostics"] == [
        "Composition sidecar failed during compose; using fallback package instead: composition failed",
        "AST composition was unavailable; generated a low-fidelity text fallback package.",
    ]


def test_convert_resource_group_to_bicep_stream_returns_404_for_missing_session(conversion_api_client) -> None:
    client, _, _, _ = conversion_api_client

    response = client.post(
        "/sessions/missing-session/azure-bicep-conversion/stream",
        headers=auth_header("valid-user"),
        json={
            "subscription_id": "sub-123",
            "resource_group_name": "rg-route",
            "azure_environment": "AzureCloud",
            "gov_approved_avm_modules": [],
            "metadata": {},
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Session 'missing-session' not found"


@pytest.mark.asyncio
async def test_convert_resource_group_to_bicep_stream_emits_error_event_when_conversion_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    session_service = SessionService(InMemorySessionRepository())
    message_service = MessageService(InMemoryMessageRepository())
    artifact_service = ArtifactService(InMemoryArtifactRepository(), InMemoryBlobStorageService())
    orchestrator = StubConversionOrchestrator(should_raise=True)
    token_validator = StubTokenValidator({"valid-user": {"oid": "user-1", "aud": "api://test"}})

    app.dependency_overrides[get_token_validator] = lambda: token_validator
    app.dependency_overrides[get_session_service] = lambda: session_service
    app.dependency_overrides[get_message_service] = lambda: message_service
    app.dependency_overrides[get_artifact_service] = lambda: artifact_service
    app.dependency_overrides[get_azure_bicep_conversion_orchestrator] = lambda: orchestrator

    session = await session_service.create_session("user-1", CreateSessionRequest(title="Conversion", metadata={}))

    with TestClient(app) as client:
        with client.stream(
            "POST",
            f"/sessions/{session.id}/azure-bicep-conversion/stream",
            headers={**auth_header("valid-user"), "Accept": "text/event-stream"},
            json={
                "subscription_id": "sub-123",
                "resource_group_name": "rg-route",
                "azure_environment": "AzureCloud",
                "gov_approved_avm_modules": [],
                "metadata": {},
            },
        ) as response:
            assert response.status_code == 200, response.text
            events = _parse_sse_events(response)

    assert [event["event"] for event in events] == ["start", "error", "done"]
    assert events[1]["data"]["message"] == "conversion failed"
    assert events[1]["data"]["code"] == "conversion_failed"
    assert isinstance(events[1]["data"]["correlation_id"], str)
    artifacts = await artifact_service.list_artifacts("user-1", session.id)
    assert artifacts == []


@pytest.mark.asyncio
async def test_convert_resource_group_to_bicep_stream_emits_bicep_cli_missing_error_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    session_service = SessionService(InMemorySessionRepository())
    message_service = MessageService(InMemoryMessageRepository())
    artifact_service = ArtifactService(InMemoryArtifactRepository(), InMemoryBlobStorageService())
    orchestrator = StubConversionOrchestrator()
    orchestrator.should_raise = False

    async def raise_bicep_missing(*args, **kwargs):
        raise BicepCliNotFoundError("Bicep CLI not installed or not on PATH")

    orchestrator.convert_resource_group = raise_bicep_missing
    token_validator = StubTokenValidator({"valid-user": {"oid": "user-1", "aud": "api://test"}})

    app.dependency_overrides[get_token_validator] = lambda: token_validator
    app.dependency_overrides[get_session_service] = lambda: session_service
    app.dependency_overrides[get_message_service] = lambda: message_service
    app.dependency_overrides[get_artifact_service] = lambda: artifact_service
    app.dependency_overrides[get_azure_bicep_conversion_orchestrator] = lambda: orchestrator

    session = await session_service.create_session("user-1", CreateSessionRequest(title="Conversion", metadata={}))

    with TestClient(app) as client:
        with client.stream(
            "POST",
            f"/sessions/{session.id}/azure-bicep-conversion/stream",
            headers={**auth_header("valid-user"), "Accept": "text/event-stream"},
            json={
                "subscription_id": "sub-123",
                "resource_group_name": "rg-route",
                "azure_environment": "AzureCloud",
                "gov_approved_avm_modules": [],
                "metadata": {},
            },
        ) as response:
            assert response.status_code == 200, response.text
            events = _parse_sse_events(response)

    assert [event["event"] for event in events] == ["start", "error", "done"]
    assert events[1]["data"]["message"] == "Bicep CLI not installed or not available to the API process."
    assert events[1]["data"]["code"] == "bicep_cli_missing"
    assert isinstance(events[1]["data"]["correlation_id"], str)