from types import SimpleNamespace

from agent_86.core.runtime_config import RuntimeConfiguration


def test_runtime_configuration_exposes_only_browser_safe_values() -> None:
    settings = SimpleNamespace(
        applicationinsights_connection_string="InstrumentationKey=browser-safe",
        log_level="INFO",
    )

    configuration = RuntimeConfiguration(settings)
    configuration.apply(
        {
            "agent86:backend:log_level": "DEBUG",
            "agent86:frontend:log_level": "ERROR",
            "agent86:frontend:telemetry_enabled": "false",
        }
    )

    assert configuration.browser_payload() == {
        "applicationInsightsConnectionString": "InstrumentationKey=browser-safe",
        "telemetryEnabled": False,
        "logLevel": "ERROR",
    }