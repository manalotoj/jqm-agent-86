from functools import lru_cache

from azure.cosmos import PartitionKey
from azure.cosmos.aio import CosmosClient

from agent_86.core.config import Settings, get_settings
from agent_86.integrations.avm.avm_catalog_client import AvmCatalogClient
from agent_86.integrations.bicep.bicep_tool_client import BicepToolClient
from agent_86.integrations.azure.resource_export_client import ResourceExportClient
from agent_86.integrations.bicep_composition.composition_api_client import CompositionApiClient
from agent_86.repositories.cosmos_artifact_repository import CosmosArtifactRepository
from agent_86.repositories.cosmos_artifact_analysis_repository import CosmosArtifactAnalysisJobRepository, CosmosArtifactProcessingRepository
from agent_86.repositories.cosmos_message_repository import CosmosMessageRepository
from agent_86.repositories.cosmos_session_repository import CosmosSessionRepository
from agent_86.repositories.cosmos_session_summary_repository import CosmosSessionSummaryRepository
from agent_86.services.artifact_service import ArtifactService
from agent_86.services.artifact_processing_service import ArtifactProcessingService
from agent_86.services.artifact_analysis_service import ArtifactAnalysisService
from agent_86.services.artifact_prompt_context_service import ArtifactPromptContextService
from agent_86.services.azure_blob_storage_service import AzureBlobStorageService
from agent_86.services.blob_storage_service import BlobStorageService
from agent_86.services.chat_model_service import ChatModelService
from agent_86.services.csv_artifact_processor import CsvArtifactProcessor
from agent_86.services.message_service import MessageService
from agent_86.services.model_router import ModelRouter
from agent_86.services.session_service import SessionService
from agent_86.services.session_summary_service import SessionSummaryService
from agent_86.services.azure_bicep_conversion.export_pipeline import ExportPipeline
from agent_86.services.azure_bicep_conversion.orchestrator import AzureBicepConversionOrchestrator
from agent_86.services.web_search_service import WebSearchService
from agent_86.services.tool_service import ToolService
from agent_86.tools.bootstrap import build_default_tool_service


@lru_cache(maxsize=1)
def _settings() -> Settings:
    return get_settings()


@lru_cache(maxsize=1)
def _cosmos_client() -> CosmosClient:
    settings = _settings()
    print(f"cosmos endpoint: {settings.cosmos_endpoint}, cosmos database: {settings.cosmos_database_name}")
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
def _artifacts_container():
    settings = _settings()
    database = _cosmos_client().get_database_client(settings.cosmos_database_name)
    return database.get_container_client(settings.cosmos_artifacts_container_name)


@lru_cache(maxsize=1)
def _artifact_processing_container():
    settings = _settings()
    database = _cosmos_client().get_database_client(settings.cosmos_database_name)
    return database.get_container_client(settings.cosmos_artifact_processing_container_name)


@lru_cache(maxsize=1)
def _artifact_analysis_jobs_container():
    settings = _settings()
    database = _cosmos_client().get_database_client(settings.cosmos_database_name)
    return database.get_container_client(settings.cosmos_artifact_analysis_jobs_container_name)


@lru_cache(maxsize=1)
def _summaries_container():
    settings = _settings()
    database = _cosmos_client().get_database_client(settings.cosmos_database_name)
    return database.create_container_if_not_exists(
        id=settings.cosmos_summaries_container_name,
        partition_key=PartitionKey(path="/user_id"),
    )


@lru_cache(maxsize=1)
def _session_repository() -> CosmosSessionRepository:
    return CosmosSessionRepository(_sessions_container())


@lru_cache(maxsize=1)
def _message_repository() -> CosmosMessageRepository:
    return CosmosMessageRepository(_messages_container())


@lru_cache(maxsize=1)
def _artifact_repository() -> CosmosArtifactRepository:
    return CosmosArtifactRepository(_artifacts_container())


@lru_cache(maxsize=1)
def _artifact_processing_repository() -> CosmosArtifactProcessingRepository:
    return CosmosArtifactProcessingRepository(_artifact_processing_container())


@lru_cache(maxsize=1)
def _artifact_analysis_job_repository() -> CosmosArtifactAnalysisJobRepository:
    return CosmosArtifactAnalysisJobRepository(_artifact_analysis_jobs_container())


@lru_cache(maxsize=1)
def _session_summary_repository() -> CosmosSessionSummaryRepository:
    return CosmosSessionSummaryRepository(_summaries_container())


@lru_cache(maxsize=1)
def _blob_storage_service() -> BlobStorageService:
    settings = _settings()
    return AzureBlobStorageService(
        connection_string=settings.azure_blob_connection_string,
        container_name=settings.azure_blob_container_name,
    )


@lru_cache(maxsize=1)
def _derived_blob_storage_service() -> BlobStorageService:
    settings = _settings()
    return AzureBlobStorageService(
        connection_string=settings.azure_blob_connection_string,
        container_name=settings.azure_blob_derived_container_name,
    )


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
def _artifact_service_instance() -> ArtifactService:
    return ArtifactService(_artifact_repository(), _blob_storage_service())


@lru_cache(maxsize=1)
def _artifact_processing_service_instance() -> ArtifactProcessingService:
    settings = _settings()
    return ArtifactProcessingService(
        _artifact_service_instance(),
        _artifact_processing_repository(),
        _derived_blob_storage_service(),
        CsvArtifactProcessor(max_rows=settings.artifact_csv_max_rows, chunk_rows=settings.artifact_csv_chunk_rows),
    )


@lru_cache(maxsize=1)
def _artifact_analysis_service_instance() -> ArtifactAnalysisService:
    return ArtifactAnalysisService(
        _artifact_processing_service_instance(), _artifact_analysis_job_repository(), _derived_blob_storage_service(),
        findings_inline_max_bytes=_settings().artifact_analysis_findings_inline_max_bytes,
    )


@lru_cache(maxsize=1)
def _artifact_prompt_context_service_instance() -> ArtifactPromptContextService:
    return ArtifactPromptContextService(_artifact_service_instance())


@lru_cache(maxsize=1)
def _chat_model_service() -> ChatModelService:
    return ChatModelService(_settings())


@lru_cache(maxsize=1)
def _model_router() -> ModelRouter:
    return ModelRouter(_settings())


@lru_cache(maxsize=1)
def _tool_service() -> ToolService:
    return build_default_tool_service(web_search_service=_web_search_service())


@lru_cache(maxsize=1)
def _resource_export_client() -> ResourceExportClient:
    return ResourceExportClient()


@lru_cache(maxsize=1)
def _bicep_tool_client() -> BicepToolClient:
    settings = _settings()
    return BicepToolClient(executable=settings.bicep_cli_path or "bicep")


@lru_cache(maxsize=1)
def _avm_catalog_client() -> AvmCatalogClient:
    return AvmCatalogClient()


@lru_cache(maxsize=1)
def _composition_api_client() -> CompositionApiClient:
    return CompositionApiClient(base_url=_settings().bicep_composition_base_url)


@lru_cache(maxsize=1)
def _export_pipeline() -> ExportPipeline:
    return ExportPipeline(resource_export_client=_resource_export_client())


@lru_cache(maxsize=1)
def _azure_bicep_conversion_orchestrator() -> AzureBicepConversionOrchestrator:
    return AzureBicepConversionOrchestrator(
        export_pipeline=_export_pipeline(),
        bicep_tool_client=_bicep_tool_client(),
        avm_catalog_client=_avm_catalog_client(),
        composition_api_client=_composition_api_client(),
    )


@lru_cache(maxsize=1)
def _session_summary_service_instance() -> SessionSummaryService:
    return SessionSummaryService(
        _session_summary_repository(),
        _session_service_instance(),
        _message_service_instance(),
        _artifact_service_instance(),
        _artifact_prompt_context_service_instance(),
        _chat_model_service(),
    )


def get_session_service() -> SessionService:
    return _session_service_instance()


def get_message_service() -> MessageService:
    return _message_service_instance()


def get_artifact_service() -> ArtifactService:
    return _artifact_service_instance()


def get_artifact_processing_service() -> ArtifactProcessingService:
    return _artifact_processing_service_instance()


def get_artifact_analysis_service() -> ArtifactAnalysisService:
    return _artifact_analysis_service_instance()


def get_artifact_prompt_context_service() -> ArtifactPromptContextService:
    return _artifact_prompt_context_service_instance()


def get_chat_model_service() -> ChatModelService:
    return _chat_model_service()


def get_model_router() -> ModelRouter:
    return _model_router()


def get_tool_service() -> ToolService:
    return _tool_service()


def get_azure_bicep_conversion_orchestrator() -> AzureBicepConversionOrchestrator:
    return _azure_bicep_conversion_orchestrator()


def get_session_summary_service() -> SessionSummaryService:
    return _session_summary_service_instance()