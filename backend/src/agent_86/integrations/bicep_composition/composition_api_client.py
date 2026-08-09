from dataclasses import dataclass, field
from typing import Any

import httpx


class CompositionApiError(RuntimeError):
    """Raised when the local composition sidecar cannot be reached or returns invalid data."""


@dataclass(frozen=True)
class CompositionFragment:
    batch_index: int
    bicep_text: str
    source_resource_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CompositionRequest:
    subscription_id: str
    resource_group_name: str
    azure_environment: str
    fragments: list[CompositionFragment] = field(default_factory=list)


@dataclass(frozen=True)
class CompositionFile:
    path: str
    content: str


@dataclass(frozen=True)
class CompositionStats:
    fragment_count: int = 0
    deduplicated_params: int = 0
    deduplicated_vars: int = 0
    unresolved_reference_count: int = 0


@dataclass(frozen=True)
class CompositionUnresolvedReference:
    source_symbol: str = ""
    source_resource_id: str = ""
    target_resource_id: str = ""
    reference_expression: str = ""


@dataclass(frozen=True)
class CompositionResult:
    status: str
    merge_mode: str
    files: list[CompositionFile] = field(default_factory=list)
    stats: CompositionStats = field(default_factory=CompositionStats)
    unresolved_references: list[CompositionUnresolvedReference] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class CompositionApiClient:
    """Boundary for the local .NET Bicep composition service."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:5057",
        http_client: httpx.AsyncClient | None = None,
        request_timeout_seconds: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http_client = http_client or httpx.AsyncClient(timeout=request_timeout_seconds)

    async def check_health(self) -> bool:
        try:
            response = await self._http_client.get(f"{self._base_url}/health")
            response.raise_for_status()
        except (httpx.HTTPError, ValueError):
            return False

        payload = response.json()
        return bool(payload.get("status"))

    async def compose(self, *, request: CompositionRequest) -> CompositionResult:
        payload = {
            "subscriptionId": request.subscription_id,
            "resourceGroupName": request.resource_group_name,
            "azureEnvironment": request.azure_environment,
            "fragments": [
                {
                    "batchIndex": fragment.batch_index,
                    "bicepText": fragment.bicep_text,
                    "sourceResourceIds": list(fragment.source_resource_ids),
                    "metadata": dict(fragment.metadata),
                }
                for fragment in request.fragments
            ],
        }

        try:
            response = await self._http_client.post(f"{self._base_url}/compose", json=payload)
            response.raise_for_status()
            response_payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CompositionApiError("Composition sidecar request failed") from exc

        try:
            return CompositionResult(
                status=str(response_payload["status"]),
                merge_mode=str(response_payload["mergeMode"]),
                files=[
                    CompositionFile(path=str(item["path"]), content=str(item["content"]))
                    for item in response_payload.get("files", [])
                ],
                stats=CompositionStats(**_camel_dict_to_snake_dict(response_payload.get("stats", {}))),
                unresolved_references=[
                    CompositionUnresolvedReference(**_camel_dict_to_snake_dict(item))
                    for item in response_payload.get("unresolvedReferences", [])
                ],
                warnings=[str(item) for item in response_payload.get("warnings", [])],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CompositionApiError("Composition sidecar returned an invalid payload") from exc


def _camel_dict_to_snake_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        _camel_to_snake(key): value
        for key, value in payload.items()
    }


def _camel_to_snake(value: str) -> str:
    characters: list[str] = []
    for index, character in enumerate(value):
        if character.isupper() and index > 0:
            characters.append("_")
        characters.append(character.lower())
    return "".join(characters)