from functools import lru_cache

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from agent_86.core.errors import ConfigurationError


class Settings(BaseSettings):
    app_name: str = "agent-86"
    app_env: str = "dev"

    cosmos_endpoint: str
    cosmos_key: str
    cosmos_database_name: str = "agent86"
    cosmos_sessions_container_name: str = "sessions"
    cosmos_messages_container_name: str = "messages"
    cosmos_verify_ssl: bool = True

    foundry_openai_base_url: str
    foundry_openai_api_key: str = Field(min_length=1)
    foundry_default_chat_model: str
    foundry_premium_chat_model: str
    azure_openai_verify_ssl: bool = True

    tavily_api_key: str | None = None
    brave_search_api_key: str | None = None
    web_search_timeout_seconds: float = 10.0
    web_search_max_results: int = 5

    entra_tenant_id: str = Field(min_length=1)
    entra_api_client_id: str = Field(min_length=1)
    entra_api_audience: str = Field(min_length=1)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

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