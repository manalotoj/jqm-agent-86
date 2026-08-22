import sys
from types import SimpleNamespace
from types import ModuleType
from unittest.mock import MagicMock

import pytest
from opentelemetry.sdk.resources import Resource

from agent_86.core.telemetry import configure_telemetry


def test_configure_telemetry_skips_azure_monitor_without_connection_string() -> None:
    settings = SimpleNamespace(applicationinsights_connection_string=None)

    configure_telemetry(settings)


def test_configure_telemetry_passes_an_opentelemetry_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        applicationinsights_connection_string="InstrumentationKey=test-key",
        otel_service_name="agent-86-api",
        otel_environment=None,
        app_env="dev",
        otel_service_version="test-version",
    )

    configure_monitor = MagicMock()
    azure_monitor_module = ModuleType("azure.monitor.opentelemetry")
    azure_monitor_module.configure_azure_monitor = configure_monitor
    monkeypatch.setitem(sys.modules, "azure.monitor.opentelemetry", azure_monitor_module)

    configure_telemetry(settings)

    resource = configure_monitor.call_args.kwargs["resource"]
    assert isinstance(resource, Resource)
    assert resource.attributes["service.name"] == "agent-86-api"
    assert resource.attributes["deployment.environment"] == "dev"
    assert resource.attributes["service.version"] == "test-version"
    assert configure_monitor.call_args.kwargs["connection_string"] == "InstrumentationKey=test-key"
    assert configure_monitor.call_args.kwargs["logger_name"] == "agent_86"