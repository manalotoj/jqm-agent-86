from agent_86.core.config import Settings


def configure_telemetry(settings: Settings) -> None:
    if not settings.applicationinsights_connection_string:
        return

    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
        from opentelemetry.sdk.resources import Resource
    except ImportError:
        return

    resource_attributes = {
        "service.name": settings.otel_service_name,
        "deployment.environment": settings.otel_environment or settings.app_env,
    }
    if settings.otel_service_version:
        resource_attributes["service.version"] = settings.otel_service_version

    configure_azure_monitor(
        connection_string=settings.applicationinsights_connection_string,
        resource=Resource.create(resource_attributes),
        logger_name="agent_86",
    )