from unittest.mock import MagicMock

from backend.src.agent_86.tools.bootstrap import build_default_tool_registry


def test_build_default_tool_registry_uses_settings_when_service_not_provided(monkeypatch) -> None:
    settings = MagicMock()
    created_services: list[object] = []

    class FakeWebSearchService:
        def __init__(self, received_settings) -> None:
            self.received_settings = received_settings
            created_services.append(self)

    monkeypatch.setattr("agent_86.core.config.get_settings", lambda: settings)
    monkeypatch.setattr("agent_86.services.web_search_service.WebSearchService", FakeWebSearchService)

    registry = build_default_tool_registry()

    assert len(created_services) == 1
    assert created_services[0].received_settings is settings
    assert len(registry.list_tools()) == 1
    assert registry.list_tools()[0].name == "web_search"