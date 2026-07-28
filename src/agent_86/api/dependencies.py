from azure.cosmos.aio import CosmosClient

from agent_86.core.config import settings
from agent_86.repositories.cosmos_message_repository import CosmosMessageRepository
from agent_86.repositories.cosmos_session_repository import CosmosSessionRepository
from agent_86.services.message_service import MessageService
from agent_86.services.session_service import SessionService


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


def get_session_service() -> SessionService:
    return _session_service


def get_message_service() -> MessageService:
    return _message_service