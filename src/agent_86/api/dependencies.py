from azure.cosmos.aio import CosmosClient

from agent_86.core.config import settings
from agent_86.repositories.cosmos_message_repository import CosmosMessageRepository
from agent_86.repositories.cosmos_session_repository import CosmosSessionRepository
from agent_86.services.chat_model_service import ChatModelService
from agent_86.services.message_service import MessageService
from agent_86.services.model_router import ModelRouter
from agent_86.services.session_service import SessionService
from agent_86.services.tool_service import ToolService
from agent_86.tools.bootstrap import build_default_tool_service

_cosmos_client = CosmosClient(
    settings.cosmos_endpoint,
    credential=settings.cosmos_key,
    connection_verify=settings.cosmos_verify_ssl,
)

_database = _cosmos_client.get_database_client(settings.cosmos_database_name)

_sessions_container = _database.get_container_client(
    settings.cosmos_sessions_container_name
)

_messages_container = _database.get_container_client(
    settings.cosmos_messages_container_name
)

_session_repository = CosmosSessionRepository(_sessions_container)
_message_repository = CosmosMessageRepository(_messages_container)

_session_service = SessionService(_session_repository)
_message_service = MessageService(_message_repository)
_chat_model_service = ChatModelService()

_model_router = ModelRouter()
_tool_service = build_default_tool_service()


def get_session_service() -> SessionService:
    return _session_service


def get_message_service() -> MessageService:
    return _message_service


def get_chat_model_service() -> ChatModelService:
    return _chat_model_service


def get_model_router() -> ModelRouter:
    return _model_router


def get_tool_service() -> ToolService:
    return _tool_service