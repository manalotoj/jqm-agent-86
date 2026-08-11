from dataclasses import dataclass, field
from types import SimpleNamespace

import httpx
import pytest

from agent_86.integrations.azure.resource_export_client import (
    ResourceExportClient,
    ResourceExportError,
    ResourceExportTimeoutError,
)


@dataclass
class FakeCredential:
    token_value: str = "fake-token"
    requested_scopes: list[tuple[str, ...]] = field(default_factory=list)

    async def get_token(self, *scopes: str) -> SimpleNamespace:
        self.requested_scopes.append(scopes)
        return SimpleNamespace(token=self.token_value)


@dataclass
class RecordingSleep:
    calls: list[float] = field(default_factory=list)

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


class SequenceTransport(httpx.AsyncBaseTransport):
    def __init__(self, responses: list[httpx.Response | Exception]) -> None:
        self._responses = list(responses)
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("No fake response configured for request")
        next_item = self._responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item


def _build_client(*, transport: SequenceTransport, sleep: RecordingSleep, monotonic=None) -> ResourceExportClient:
    http_client = httpx.AsyncClient(transport=transport, timeout=5.0)
    return ResourceExportClient(
        http_client=http_client,
        credential=FakeCredential(),
        sleep=sleep,
        monotonic=monotonic,
        backoff_seconds=0.25,
        export_poll_timeout_seconds=5.0,
    )


@pytest.mark.asyncio
async def test_get_resource_count_counts_paginated_resources() -> None:
    transport = SequenceTransport(
        responses=[
            httpx.Response(
                200,
                json={
                    "value": [{"id": "r1"}, {"id": "r2"}],
                    "nextLink": "https://management.azure.com/next-page",
                },
            ),
            httpx.Response(200, json={"value": [{"id": "r3"}]}),
        ]
    )
    sleep = RecordingSleep()
    client = _build_client(transport=transport, sleep=sleep)

    count = await client.get_resource_count(subscription_id="sub-1", resource_group_name="rg-1")

    assert count == 3
    assert len(transport.requests) == 2
    assert transport.requests[0].headers["Authorization"] == "Bearer fake-token"
    await client._http_client.aclose()


@pytest.mark.asyncio
async def test_export_resource_group_wildcard_retries_on_throttling_then_returns_template() -> None:
    transport = SequenceTransport(
        responses=[
            httpx.Response(429, headers={"Retry-After": "2"}, text="slow down"),
            httpx.Response(200, json={"template": {"resources": [{"name": "ok"}]}}),
        ]
    )
    sleep = RecordingSleep()
    client = _build_client(transport=transport, sleep=sleep)

    result = await client.export_resource_group_wildcard(subscription_id="sub-1", resource_group_name="rg-1")

    assert result.export_mode == "wildcard"
    assert result.template_json == {"resources": [{"name": "ok"}]}
    assert result.source_resource_ids == []
    assert sleep.calls == [2.0]
    assert transport.requests[0].method == "POST"
    assert transport.requests[0].url.path.endswith("/exportTemplate")
    assert transport.requests[0].content.decode() == '{"resources":["*"],"options":"IncludeParameterDefaultValue,IncludeComments"}'
    await client._http_client.aclose()


@pytest.mark.asyncio
async def test_export_resource_group_by_resource_ids_preserves_source_resource_ids() -> None:
    transport = SequenceTransport(
        responses=[httpx.Response(200, json={"template": {"resources": [{"name": "app"}]}})]
    )
    sleep = RecordingSleep()
    client = _build_client(transport=transport, sleep=sleep)
    resource_ids = [
        "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Mock/type/a",
        "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Mock/type/b",
    ]

    result = await client.export_resource_group_by_resource_ids(
        subscription_id="sub-1",
        resource_group_name="rg-1",
        resource_ids=resource_ids,
    )

    assert result.export_mode == "resource_id_list"
    assert result.source_resource_ids == resource_ids
    assert result.template_json == {"resources": [{"name": "app"}]}
    await client._http_client.aclose()


@pytest.mark.asyncio
async def test_export_resource_group_wildcard_polls_until_template_is_available() -> None:
    monotonic_values = iter([0.0, 1.0, 2.0])
    transport = SequenceTransport(
        responses=[
            httpx.Response(202, headers={"Azure-AsyncOperation": "https://management.azure.com/operations/123"}),
            httpx.Response(200, json={"status": "Running"}),
            httpx.Response(200, json={"status": "Succeeded", "template": {"resources": [{"name": "done"}]}}),
        ]
    )
    sleep = RecordingSleep()
    client = _build_client(transport=transport, sleep=sleep, monotonic=lambda: next(monotonic_values))

    result = await client.export_resource_group_wildcard(subscription_id="sub-1", resource_group_name="rg-1")

    assert result.template_json == {"resources": [{"name": "done"}]}
    assert sleep.calls == [0.25]
    await client._http_client.aclose()


@pytest.mark.asyncio
async def test_export_resource_group_wildcard_tolerates_empty_202_poll_response() -> None:
    monotonic_values = iter([0.0, 1.0, 2.0, 3.0])
    transport = SequenceTransport(
        responses=[
            httpx.Response(202, headers={"Azure-AsyncOperation": "https://management.azure.com/operations/123"}),
            httpx.Response(202, headers={"Retry-After": "1"}, content=b""),
            httpx.Response(200, json={"status": "Succeeded", "template": {"resources": [{"name": "done"}]}}),
        ]
    )
    sleep = RecordingSleep()
    client = _build_client(transport=transport, sleep=sleep, monotonic=lambda: next(monotonic_values))

    result = await client.export_resource_group_wildcard(subscription_id="sub-1", resource_group_name="rg-1")

    assert result.template_json == {"resources": [{"name": "done"}]}
    assert sleep.calls == [1.0]
    await client._http_client.aclose()


@pytest.mark.asyncio
async def test_export_resource_group_wildcard_raises_clear_error_for_non_json_terminal_poll_response() -> None:
    monotonic_values = iter([0.0, 1.0])
    transport = SequenceTransport(
        responses=[
            httpx.Response(202, headers={"Azure-AsyncOperation": "https://management.azure.com/operations/123"}),
            httpx.Response(200, headers={"Content-Type": "text/html"}, text="<html>gateway error</html>"),
        ]
    )
    sleep = RecordingSleep()
    client = _build_client(transport=transport, sleep=sleep, monotonic=lambda: next(monotonic_values))

    with pytest.raises(ResourceExportError, match="non-JSON response"):
        await client.export_resource_group_wildcard(subscription_id="sub-1", resource_group_name="rg-1")

    await client._http_client.aclose()


@pytest.mark.asyncio
async def test_export_resource_group_wildcard_raises_timeout_when_polling_exceeds_deadline() -> None:
    monotonic_values = iter([0.0, 6.0])
    transport = SequenceTransport(
        responses=[
            httpx.Response(202, headers={"Azure-AsyncOperation": "https://management.azure.com/operations/123"}),
        ]
    )
    sleep = RecordingSleep()
    client = _build_client(transport=transport, sleep=sleep, monotonic=lambda: next(monotonic_values))

    with pytest.raises(ResourceExportTimeoutError, match="polling exceeded"):
        await client.export_resource_group_wildcard(subscription_id="sub-1", resource_group_name="rg-1")

    await client._http_client.aclose()


@pytest.mark.asyncio
async def test_export_resource_group_wildcard_raises_after_retry_exhaustion() -> None:
    transport = SequenceTransport(
        responses=[
            httpx.Response(500, text="server-1"),
            httpx.Response(503, text="server-2"),
            httpx.Response(429, headers={"Retry-After": "1"}, text="server-3"),
            httpx.Response(500, text="server-4"),
        ]
    )
    sleep = RecordingSleep()
    client = _build_client(transport=transport, sleep=sleep)

    with pytest.raises(ResourceExportError, match="retry exhaustion"):
        await client.export_resource_group_wildcard(subscription_id="sub-1", resource_group_name="rg-1")

    assert sleep.calls == [0.25, 0.5, 1.0]
    await client._http_client.aclose()