from types import SimpleNamespace

import httpx
import pytest

from agent_86.services.web_search_service import WebSearchService


def _settings(*, tavily_api_key: str | None = None, brave_search_api_key: str | None = None):
    return SimpleNamespace(
        tavily_api_key=tavily_api_key,
        brave_search_api_key=brave_search_api_key,
        web_search_timeout_seconds=10.0,
        web_search_max_results=5,
    )


@pytest.mark.asyncio
async def test_search_reports_not_configured_when_no_provider_key_is_available():
    content, metadata = await WebSearchService(_settings()).search("MSFT stock current price")

    assert content == "No web search provider is configured for this request."
    assert metadata == {
        "provider": "none",
        "query": "MSFT stock current price",
        "status": "not_configured",
    }


@pytest.mark.asyncio
async def test_search_uses_tavily_when_its_key_is_configured(monkeypatch):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Microsoft stock quote",
                        "url": "https://example.com/msft",
                        "content": "MSFT current price",
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def mock_client(*args, **kwargs):
        return real_async_client(transport=transport, *args, **kwargs)

    monkeypatch.setattr("agent_86.services.web_search_service.httpx.AsyncClient", mock_client)

    content, metadata = await WebSearchService(
        _settings(tavily_api_key="test-tavily-key")
    ).search("MSFT stock current price")

    assert requests[0].url == httpx.URL("https://api.tavily.com/search")
    assert content.startswith("Web search provider: tavily")
    assert metadata == {
        "provider": "tavily",
        "query": "MSFT stock current price",
        "status": "ok",
        "result_count": 1,
    }


@pytest.mark.asyncio
async def test_search_reports_configured_provider_failure_without_exposing_credentials(
    monkeypatch, caplog
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def mock_client(*args, **kwargs):
        return real_async_client(transport=transport, *args, **kwargs)

    monkeypatch.setattr("agent_86.services.web_search_service.httpx.AsyncClient", mock_client)

    content, metadata = await WebSearchService(
        _settings(tavily_api_key="test-tavily-key")
    ).search("MSFT stock current price")

    assert content == (
        "Configured web search provider(s) are currently unavailable. "
        "Please try again later."
    )
    assert metadata == {
        "provider": "tavily",
        "query": "MSFT stock current price",
        "status": "provider_unavailable",
    }
    assert "HTTP 401" in caplog.text
    assert "test-tavily-key" not in caplog.text