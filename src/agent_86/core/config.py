from pydantic_settings import BaseSettings, SettingsConfigDict


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
    foundry_default_chat_model: str
    foundry_premium_chat_model: str
    azure_openai_verify_ssl: bool = True

    tavily_api_key: str | None = None
    brave_search_api_key: str | None = None
    web_search_timeout_seconds: float = 10.0
    web_search_max_results: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()