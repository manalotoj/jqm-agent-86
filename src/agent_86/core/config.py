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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()