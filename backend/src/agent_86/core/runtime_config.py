import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field

from agent_86.core.config import Settings
from agent_86.core.logging import configure_log_level, get_logger


logger = get_logger(__name__)

_BACKEND_LOG_LEVEL_KEY = "agent86:backend:log_level"
_FRONTEND_LOG_LEVEL_KEY = "agent86:frontend:log_level"
_FRONTEND_TELEMETRY_ENABLED_KEY = "agent86:frontend:telemetry_enabled"


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class RuntimeConfiguration:
    settings: Settings
    values: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.values.setdefault(_BACKEND_LOG_LEVEL_KEY, self.settings.log_level)
        self.values.setdefault(_FRONTEND_LOG_LEVEL_KEY, "WARN")
        self.values.setdefault(_FRONTEND_TELEMETRY_ENABLED_KEY, "true")

    def browser_payload(self) -> dict[str, str | bool | None]:
        return {
            "applicationInsightsConnectionString": self.settings.applicationinsights_connection_string,
            "telemetryEnabled": _as_bool(self.values.get(_FRONTEND_TELEMETRY_ENABLED_KEY), True),
            "logLevel": self.values[_FRONTEND_LOG_LEVEL_KEY],
        }

    def apply(self, values: Mapping[str, str]) -> None:
        self.values.update(values)
        configure_log_level(self.values[_BACKEND_LOG_LEVEL_KEY])


class AppConfigurationRefresher:
    """Reads non-secret runtime controls with managed identity, never browser credentials."""

    def __init__(self, runtime_configuration: RuntimeConfiguration) -> None:
        self._runtime_configuration = runtime_configuration
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        endpoint = self._runtime_configuration.settings.azure_app_configuration_endpoint
        if not endpoint:
            return None

        from azure.appconfiguration import AzureAppConfigurationClient
        from azure.identity import DefaultAzureCredential

        self._client = AzureAppConfigurationClient(endpoint, DefaultAzureCredential())
        return self._client

    def refresh_sync(self) -> None:
        client = self._get_client()
        if client is None:
            return

        loaded: dict[str, str] = {}
        for key in (_BACKEND_LOG_LEVEL_KEY, _FRONTEND_LOG_LEVEL_KEY, _FRONTEND_TELEMETRY_ENABLED_KEY):
            try:
                setting = client.get_configuration_setting(key=key)
            except Exception as exc:
                # A missing optional key and a transient data-plane error both retain safe defaults.
                logger.warning("app_configuration_setting_unavailable", key=key, error_type=type(exc).__name__)
                continue
            if setting.value is not None:
                loaded[key] = setting.value

        if loaded:
            self._runtime_configuration.apply(loaded)
            logger.info("app_configuration_refreshed", keys=sorted(loaded))

    async def refresh_loop(self, stop_event: asyncio.Event) -> None:
        delay = self._runtime_configuration.settings.app_configuration_refresh_seconds
        while not stop_event.is_set():
            try:
                await asyncio.to_thread(self.refresh_sync)
            except Exception:
                logger.exception("app_configuration_refresh_failed")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=delay)
            except TimeoutError:
                pass