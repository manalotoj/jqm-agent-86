from unittest.mock import MagicMock

from agent_86.services.tool_guardrails import WebSearchGuardrails
from agent_86.tools.bootstrap import build_default_tool_registry, build_default_tool_service


def test_build_default_tool_registry_uses_settings_when_service_not_provided(monkeypatch) -> None:
    settings = MagicMock()
    created_services: list[object] = []

    class FakeWebSearchService:
        def __init__(self, received_settings) -> None:
            self.received_settings = received_settings
            created_services.append(self)

    monkeypatch.setattr("agent_86.tools.bootstrap.get_settings", lambda: settings)
    monkeypatch.setattr("agent_86.services.web_search_service.WebSearchService", FakeWebSearchService)

    registry = build_default_tool_registry()

    assert len(created_services) == 1
    assert created_services[0].received_settings is settings
    assert len(registry.list_tools()) == 1
    assert registry.list_tools()[0].name == "web_search"


def test_build_default_tool_service_uses_settings_backed_guardrails(monkeypatch) -> None:
    settings = MagicMock(
        web_search_max_calls_per_request=3,
        web_search_max_query_length=123,
        web_search_block_duplicate_queries=False,
    )

    monkeypatch.setattr("agent_86.tools.bootstrap.get_settings", lambda: settings)
    monkeypatch.setattr(
        "agent_86.tools.bootstrap.build_default_tool_registry",
        lambda web_search_service=None: MagicMock(),
    )

    tool_service = build_default_tool_service()

    assert tool_service._web_search_guardrails == WebSearchGuardrails(
        max_calls_per_request=3,
        max_query_length=123,
        block_duplicate_queries=False,
    )