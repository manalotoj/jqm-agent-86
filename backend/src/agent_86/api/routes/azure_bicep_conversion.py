from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from agent_86.api.dependencies import (
    get_artifact_service,
    get_azure_bicep_conversion_orchestrator,
    get_message_service,
    get_session_service,
)
from agent_86.api.routes.artifacts import ensure_session_exists
from agent_86.api.routes.chat import encode_sse, to_stream_event
from agent_86.auth.dependencies import get_authenticated_user
from agent_86.auth.models import AuthenticatedUser
from agent_86.domain.models.artifact import Artifact
from agent_86.domain.schemas.azure_bicep_conversion import (
    BicepConversionArtifactDescriptor,
    BicepConversionCompleteEvent,
    BicepConversionSummaryResponse,
    ConvertResourceGroupToBicepRequest,
)
from agent_86.integrations.bicep.bicep_tool_client import BicepCliNotFoundError
from agent_86.core.logging import get_logger
from agent_86.services.artifact_service import ArtifactService, MessageNotFoundError
from agent_86.services.azure_bicep_conversion.orchestrator import AzureBicepConversionOrchestrator
from agent_86.services.message_service import MessageService
from agent_86.services.session_service import SessionService

router = APIRouter(prefix="/sessions/{session_id}/azure-bicep-conversion", tags=["azure-bicep-conversion"])
logger = get_logger(__name__)


def _to_artifact_descriptor(artifact: Artifact) -> BicepConversionArtifactDescriptor:
    return BicepConversionArtifactDescriptor(
        artifact_id=artifact.id,
        filename=artifact.filename,
        content_type=artifact.content_type,
        size_bytes=artifact.size_bytes,
        metadata=artifact.metadata,
    )


def _to_summary_response(summary) -> BicepConversionSummaryResponse:
    return BicepConversionSummaryResponse(
        subscription_id=summary.subscription_id,
        resource_group_name=summary.resource_group_name,
        azure_environment=summary.azure_environment,
        resource_count=summary.resource_count,
        export_mode=summary.export_mode,
        batch_count=summary.batch_count,
        merge_mode=summary.merge_mode,
        fallback_used=summary.fallback_used,
        unresolved_reference_count=summary.unresolved_reference_count,
        secure_parameter_count=summary.secure_parameter_count,
        avm_annotation_count=summary.avm_annotation_count,
        diagnostics=summary.diagnostics,
        generated_files=summary.generated_files,
    )


@router.post("/stream")
async def convert_resource_group_to_bicep_stream(
    session_id: str,
    request: ConvertResourceGroupToBicepRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session_service: SessionService = Depends(get_session_service),
    artifact_service: ArtifactService = Depends(get_artifact_service),
    message_service: MessageService = Depends(get_message_service),
    orchestrator: AzureBicepConversionOrchestrator = Depends(get_azure_bicep_conversion_orchestrator),
) -> StreamingResponse:
    await ensure_session_exists(user.user_id, session_id, session_service)
    correlation_id = str(uuid4())

    async def event_generator() -> AsyncIterator[str]:
        bound_logger = logger.bind(
            correlation_id=correlation_id,
            session_id=session_id,
            user_id=user.user_id,
            subscription_id=request.subscription_id,
            resource_group_name=request.resource_group_name,
            azure_environment=request.azure_environment,
        )
        bound_logger.info("azure_bicep_conversion_stream_started")
        yield encode_sse(
            to_stream_event(
                "start",
                {
                    "session_id": session_id,
                    "subscription_id": request.subscription_id,
                    "resource_group_name": request.resource_group_name,
                    "azure_environment": request.azure_environment,
                },
            )
        )

        try:
            conversion_result = await orchestrator.convert_resource_group(
                subscription_id=request.subscription_id,
                resource_group_name=request.resource_group_name,
                azure_environment=request.azure_environment,
                gov_approved_avm_modules=request.gov_approved_avm_modules,
            )

            artifact = await artifact_service.create_generated_artifact(
                session_id=session_id,
                user_id=user.user_id,
                filename=conversion_result.artifact.filename,
                content_type=conversion_result.artifact.content_type,
                content=conversion_result.artifact.content,
                source_artifact_ids=[],
                generated_by_message_id=request.generated_by_message_id,
                metadata=conversion_result.artifact.metadata | request.metadata,
                message_service=message_service,
            )

            complete_event = BicepConversionCompleteEvent(
                artifact=_to_artifact_descriptor(artifact),
                summary=_to_summary_response(conversion_result.summary),
            )
            bound_logger.info(
                "azure_bicep_conversion_stream_completed",
                artifact_id=artifact.id,
                generated_files=conversion_result.summary.generated_files,
                fallback_used=conversion_result.summary.fallback_used,
            )
            yield encode_sse(to_stream_event("complete", complete_event.model_dump(mode="json")))
        except MessageNotFoundError as exc:
            bound_logger.warning("azure_bicep_conversion_stream_message_not_found", error=str(exc))
            yield encode_sse(
                to_stream_event(
                    "error",
                    {
                        "message": str(exc),
                        "code": "message_not_found",
                        "correlation_id": correlation_id,
                    },
                )
            )
        except BicepCliNotFoundError:
            bound_logger.exception("azure_bicep_conversion_stream_bicep_cli_missing")
            yield encode_sse(
                to_stream_event(
                    "error",
                    {
                        "message": "Bicep CLI not installed or not available to the API process.",
                        "code": "bicep_cli_missing",
                        "correlation_id": correlation_id,
                    },
                )
            )
        except Exception as exc:
            bound_logger.exception("azure_bicep_conversion_stream_failed")
            yield encode_sse(
                to_stream_event(
                    "error",
                    {
                        "message": str(exc),
                        "code": "conversion_failed",
                        "correlation_id": correlation_id,
                    },
                )
            )
        finally:
            bound_logger.info("azure_bicep_conversion_stream_done")
            yield encode_sse(to_stream_event("done", {}))

    return StreamingResponse(event_generator(), media_type="text/event-stream")