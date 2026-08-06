from functools import lru_cache

from azure.cosmos.aio import CosmosClient

from agent_86.core.config import Settings, get_settings
from agent_86.repositories.cosmos_message_repository import CosmosMessageRepository
from agent_86.repositories.cosmos_session_repository import CosmosSessionRepository
from agent_86.services.chat_model_service import ChatModelService
from agent_86.services.message_service import MessageService
from agent_86.services.model_router import ModelRouter
from agent_86.services.session_service import SessionService
from agent_86.services.web_search_service import WebSearchService
from agent_86.services.tool_service import ToolService
from agent_86.tools.bootstrap import build_default_tool_service


@lru_cache(maxsize=1)
def _settings() -> Settings:
    return get_settings()


@lru_cache(maxsize=1)
def _cosmos_client() -> CosmosClient:
    settings = _settings()
    return CosmosClient(
        settings.cosmos_endpoint,
        credential=settings.cosmos_key,
        connection_verify=settings.cosmos_verify_ssl,
    )


@lru_cache(maxsize=1)
def _sessions_container():
    settings = _settings()
    database = _cosmos_client().get_database_client(settings.cosmos_database_name)
    return database.get_container_client(settings.cosmos_sessions_container_name)


@lru_cache(maxsize=1)
def _messages_container():
    settings = _settings()
    database = _cosmos_client().get_database_client(settings.cosmos_database_name)
    return database.get_container_client(settings.cosmos_messages_container_name)


@lru_cache(maxsize=1)
def _session_repository() -> CosmosSessionRepository:
    return CosmosSessionRepository(_sessions_container())


@lru_cache(maxsize=1)
def _message_repository() -> CosmosMessageRepository:
    return CosmosMessageRepository(_messages_container())


@lru_cache(maxsize=1)
def _web_search_service() -> WebSearchService:
    return WebSearchService(_settings())


@lru_cache(maxsize=1)
def _session_service_instance() -> SessionService:
    return SessionService(_session_repository())


@lru_cache(maxsize=1)
def _message_service_instance() -> MessageService:
    return MessageService(_message_repository())


@lru_cache(maxsize=1)
def _chat_model_service() -> ChatModelService:
    return ChatModelService(_settings())


@lru_cache(maxsize=1)
def _model_router() -> ModelRouter:
    return ModelRouter(_settings())


@lru_cache(maxsize=1)
def _tool_service() -> ToolService:
    return build_default_tool_service(web_search_service=_web_search_service())


def get_session_service() -> SessionService:
    return _session_service_instance()


def get_message_service() -> MessageService:
    return _message_service_instance()


def get_chat_model_service() -> ChatModelService:
    return _chat_model_service()


def get_model_router() -> ModelRouter:
    return _model_router()


def get_tool_service() -> ToolService:
    return _tool_service()