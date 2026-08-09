import json

import httpx
import pytest

from agent_86.integrations.bicep_composition.composition_api_client import (
    CompositionApiClient,
    CompositionApiError,
    CompositionFragment,
    CompositionRequest,
    CompositionUnresolvedReference,
)


def _build_client(handler) -> CompositionApiClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, timeout=5.0)
    return CompositionApiClient(base_url="http://composition.local", http_client=http_client)


@pytest.mark.asyncio
async def test_check_health_returns_true_for_healthy_sidecar() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok"})

    client = _build_client(handler)

    assert await client.check_health() is True


@pytest.mark.asyncio
async def test_check_health_returns_false_for_http_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"status": "down"})

    client = _build_client(handler)

    assert await client.check_health() is False


@pytest.mark.asyncio
async def test_compose_serializes_typed_request_and_parses_typed_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/compose"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload == {
            "subscriptionId": "sub-1",
            "resourceGroupName": "rg-1",
            "azureEnvironment": "AzureCloud",
            "fragments": [
                {
                    "batchIndex": 3,
                    "bicepText": "resource stg 'Type@1' = {}",
                    "sourceResourceIds": ["resource-1", "resource-2"],
                    "metadata": {"domain": "storage"},
                }
            ],
        }
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "mergeMode": "ast",
                "files": [{"path": "main.bicep", "content": "targetScope = 'resourceGroup'"}],
                "stats": {
                    "fragmentCount": 1,
                    "deduplicatedParams": 2,
                    "deduplicatedVars": 1,
                    "unresolvedReferenceCount": 1,
                },
                "unresolvedReferences": [
                    {
                        "sourceSymbol": "stg",
                        "sourceResourceId": "resource-1",
                        "targetResourceId": "resource-missing",
                        "referenceExpression": "stg.properties.primaryEndpoints.blob",
                    }
                ],
                "warnings": ["stub warning"],
            },
        )

    client = _build_client(handler)

    result = await client.compose(
        request=CompositionRequest(
            subscription_id="sub-1",
            resource_group_name="rg-1",
            azure_environment="AzureCloud",
            fragments=[
                CompositionFragment(
                    batch_index=3,
                    bicep_text="resource stg 'Type@1' = {}",
                    source_resource_ids=["resource-1", "resource-2"],
                    metadata={"domain": "storage"},
                )
            ],
        )
    )

    assert result.status == "ok"
    assert result.merge_mode == "ast"
    assert [(item.path, item.content) for item in result.files] == [("main.bicep", "targetScope = 'resourceGroup'")]
    assert result.stats.fragment_count == 1
    assert result.stats.deduplicated_params == 2
    assert result.stats.deduplicated_vars == 1
    assert result.stats.unresolved_reference_count == 1
    assert result.unresolved_references == [
        CompositionUnresolvedReference(
            source_symbol="stg",
            source_resource_id="resource-1",
            target_resource_id="resource-missing",
            reference_expression="stg.properties.primaryEndpoints.blob",
        )
    ]
    assert result.warnings == ["stub warning"]


@pytest.mark.asyncio
async def test_compose_raises_for_invalid_payload() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"mergeMode": "ast"})

    client = _build_client(handler)

    with pytest.raises(CompositionApiError):
        await client.compose(
            request=CompositionRequest(
                subscription_id="sub-1",
                resource_group_name="rg-1",
                azure_environment="AzureCloud",
            )
        )