from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx
import msal
import pytest
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
CLIENT_ENV_FILE = BACKEND_ROOT / ".env.e2e.client"
HEALTH_PATH = "/health"
SESSIONS_PATH = "/sessions"
SERVER_START_COMMAND = "AGENT86_ENV_MODE=e2e ./common/scripts/start_local.zsh"


class E2EClientSettings(BaseSettings):
    e2e_api_base_url: str = Field(min_length=1)
    e2e_entra_tenant_id: str = Field(min_length=1)
    e2e_entra_client_id: str = Field(min_length=1)
    e2e_entra_client_secret: str = Field(min_length=1)
    e2e_entra_api_audience: str = Field(min_length=1)

    model_config = SettingsConfigDict(
        env_file=str(CLIENT_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.e2e_entra_tenant_id}"

    @property
    def token_scope(self) -> str:
        audience = self.e2e_entra_api_audience.rstrip("/")
        if audience.endswith("/.default"):
            return audience

        return f"{audience}/.default"


@dataclass(frozen=True)
class AuthenticatedE2EClient:
    base_url: str
    access_token: str

    @property
    def authorization_header(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


@pytest.fixture(scope="session")
def e2e_client_settings() -> E2EClientSettings:
    try:
        return E2EClientSettings()
    except Exception as exc:  # pragma: no cover - exercised only in env misconfiguration
        pytest.exit(
            "Failed to load e2e client configuration from "
            f"{CLIENT_ENV_FILE}. Create it from {CLIENT_ENV_FILE}.example and fill in real values. "
            f"Underlying error: {exc}",
            returncode=2,
        )


@pytest.fixture(scope="session")
def ensure_e2e_server_reachable(e2e_client_settings: E2EClientSettings) -> None:
    health_url = f"{e2e_client_settings.e2e_api_base_url.rstrip('/')}{HEALTH_PATH}"

    try:
        with httpx.Client(timeout=5.0, follow_redirects=True) as client:
            response = client.get(health_url)
    except httpx.HTTPError as exc:
        pytest.exit(
            "E2E target server not reachable at "
            f"{e2e_client_settings.e2e_api_base_url}. Start it with: {SERVER_START_COMMAND}. "
            f"Health check URL: {health_url}. Underlying error: {exc}",
            returncode=2,
        )

    if response.status_code != 200:
        pytest.exit(
            "E2E target server responded unexpectedly at "
            f"{health_url}: HTTP {response.status_code} body={response.text!r}. "
            f"Start it with: {SERVER_START_COMMAND}",
            returncode=2,
        )


@pytest.fixture(scope="session", autouse=True)
def _session_bootstrap(ensure_e2e_server_reachable: None) -> None:
    return None


@pytest.fixture(scope="session")
def e2e_access_token(e2e_client_settings: E2EClientSettings) -> str:
    app = msal.ConfidentialClientApplication(
        client_id=e2e_client_settings.e2e_entra_client_id,
        authority=e2e_client_settings.authority,
        client_credential=e2e_client_settings.e2e_entra_client_secret,
    )
    result = app.acquire_token_for_client(scopes=[e2e_client_settings.token_scope])
    access_token = result.get("access_token")
    if access_token:
        return str(access_token)

    error = result.get("error", "unknown_error")
    description = result.get("error_description", "No error_description returned by Entra.")
    correlation_id = result.get("correlation_id", "n/a")
    pytest.exit(
        "Failed to acquire E2E access token via client_credentials. "
        f"authority={e2e_client_settings.authority!r} scope={e2e_client_settings.token_scope!r} "
        f"error={error!r} correlation_id={correlation_id!r} description={description!r}",
        returncode=2,
    )


@pytest.fixture(scope="session")
def e2e_authenticated_client(
    e2e_client_settings: E2EClientSettings,
    e2e_access_token: str,
) -> AuthenticatedE2EClient:
    return AuthenticatedE2EClient(
        base_url=e2e_client_settings.e2e_api_base_url.rstrip("/"),
        access_token=e2e_access_token,
    )


@pytest.fixture()
def e2e_http_client() -> httpx.Client:
    with httpx.Client(timeout=10.0, follow_redirects=True) as client:
        yield client