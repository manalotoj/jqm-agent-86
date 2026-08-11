from functools import lru_cache

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from agent_86.core.errors import ConfigurationError


class Settings(BaseSettings):
    app_name: str = "agent-86"
    app_env: str = "dev"
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    log_level: str = "INFO"
    log_json: bool = True
    applicationinsights_connection_string: str | None = None
    otel_service_name: str = "agent-86-api"
    otel_service_version: str | None = None
    otel_environment: str | None = None

    cosmos_endpoint: str
    cosmos_key: str
    cosmos_database_name: str = Field(min_length=3)
    cosmos_sessions_container_name: str = "sessions"
    cosmos_messages_container_name: str = "messages"
    cosmos_artifacts_container_name: str = "artifacts"
    cosmos_summaries_container_name: str = "summaries"
    cosmos_verify_ssl: bool = True

    azure_blob_connection_string: str = Field(min_length=1)
    azure_blob_container_name: str = Field(min_length=1)

    foundry_openai_base_url: str
    foundry_openai_api_key: str = Field(min_length=1)
    foundry_default_chat_model: str
    foundry_premium_chat_model: str
    azure_openai_verify_ssl: bool = True

    tavily_api_key: str | None = None
    brave_search_api_key: str | None = None
    web_search_timeout_seconds: float = 10.0
    web_search_max_results: int = 5
    web_search_max_calls_per_request: int = Field(default=1, ge=0)
    web_search_max_query_length: int = Field(default=200, ge=1)
    web_search_block_duplicate_queries: bool = True
    tool_roundtrip_max_per_request: int = Field(default=4, ge=0)
    bicep_composition_base_url: str = "http://127.0.0.1:5057"
    bicep_cli_path: str | None = None

    entra_tenant_id: str = Field(min_length=1)
    entra_api_client_id: str = Field(min_length=1)
    entra_api_audience: str = Field(min_length=1)

    model_config = SettingsConfigDict(extra="ignore")

    @property
    def entra_authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.entra_tenant_id}"

    @property
    def entra_issuer(self) -> str:
        return f"https://login.microsoftonline.com/{self.entra_tenant_id}/v2.0"

    @property
    def entra_openid_configuration_url(self) -> str:
        return (
            f"{self.entra_authority}/v2.0/.well-known/openid-configuration"
        )

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]


def _format_validation_error(exc: ValidationError) -> str:
    missing_fields: list[str] = []

    for error in exc.errors():
        if error.get("type") != "missing":
            continue

        location = error.get("loc", ())
        if not location:
            continue

        missing_fields.append(str(location[0]).upper())

    if missing_fields:
        fields = ", ".join(sorted(set(missing_fields)))
        return f"Missing required backend configuration: {fields}"

    return "Invalid backend configuration. Check required environment variables."


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        raise ConfigurationError(_format_validation_error(exc)) from None