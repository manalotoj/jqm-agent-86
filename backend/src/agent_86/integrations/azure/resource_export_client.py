import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

import httpx
from azure.identity.aio import DefaultAzureCredential


_ARM_RESOURCE_API_VERSION = "2021-04-01"
_ARM_EXPORT_API_VERSION = "2021-04-01"
_ARM_SCOPE = "https://management.azure.com/.default"


class _TokenCredential(Protocol):
    async def get_token(self, *scopes: str) -> Any: ...


class ResourceExportError(RuntimeError):
    """Raised when Azure resource export fails in a non-retryable or exhausted way."""


class ResourceExportTimeoutError(ResourceExportError):
    """Raised when Azure export polling exceeds the configured timeout."""


@dataclass(frozen=True)
class ResourceExportTemplate:
    template_json: dict[str, Any]
    export_mode: str
    source_resource_ids: list[str] = field(default_factory=list)


class ResourceExportClient:
    """Azure Resource Manager export adapter boundary for RG-to-Bicep conversion."""

    def __init__(
        self,
        *,
        base_url: str = "https://management.azure.com",
        credential: _TokenCredential | None = None,
        http_client: httpx.AsyncClient | None = None,
        resource_api_version: str = _ARM_RESOURCE_API_VERSION,
        export_api_version: str = _ARM_EXPORT_API_VERSION,
        request_timeout_seconds: float = 30.0,
        export_poll_timeout_seconds: float = 120.0,
        max_attempts: int = 4,
        backoff_seconds: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._credential = credential or DefaultAzureCredential()
        self._http_client = http_client or httpx.AsyncClient(timeout=request_timeout_seconds)
        self._resource_api_version = resource_api_version
        self._export_api_version = export_api_version
        self._request_timeout_seconds = request_timeout_seconds
        self._export_poll_timeout_seconds = export_poll_timeout_seconds
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._sleep = sleep or asyncio.sleep
        self._monotonic = monotonic or time.monotonic

    async def get_resource_count(self, *, subscription_id: str, resource_group_name: str) -> int:
        next_url = (
            f"{self._base_url}/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}"
            f"/resources?api-version={self._resource_api_version}"
        )
        resource_count = 0
        while next_url:
            response = await self._request_with_retry("GET", next_url)
            payload = response.json()
            resource_count += len(payload.get("value", []))
            next_url = payload.get("nextLink")
        return resource_count

    async def export_resource_group_wildcard(
        self,
        *,
        subscription_id: str,
        resource_group_name: str,
    ) -> ResourceExportTemplate:
        return await self._export_template(
            subscription_id=subscription_id,
            resource_group_name=resource_group_name,
            resource_ids=["*"],
            export_mode="wildcard",
            source_resource_ids=[],
        )

    async def export_resource_group_by_resource_ids(
        self,
        *,
        subscription_id: str,
        resource_group_name: str,
        resource_ids: list[str],
    ) -> ResourceExportTemplate:
        normalized_resource_ids = [resource_id.strip() for resource_id in resource_ids if resource_id.strip()]
        if not normalized_resource_ids:
            raise ValueError("resource_ids must contain at least one non-empty resource ID")
        return await self._export_template(
            subscription_id=subscription_id,
            resource_group_name=resource_group_name,
            resource_ids=normalized_resource_ids,
            export_mode="resource_id_list",
            source_resource_ids=normalized_resource_ids,
        )

    async def _export_template(
        self,
        *,
        subscription_id: str,
        resource_group_name: str,
        resource_ids: list[str],
        export_mode: str,
        source_resource_ids: list[str],
    ) -> ResourceExportTemplate:
        export_url = (
            f"{self._base_url}/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}"
            f"/exportTemplate?api-version={self._export_api_version}"
        )
        response = await self._request_with_retry(
            "POST",
            export_url,
            json={
                "resources": resource_ids,
                "options": "IncludeParameterDefaultValue,IncludeComments",
            },
        )

        if response.status_code in {200, 201}:
            payload = response.json()
        elif response.status_code == 202:
            payload = await self._poll_export_completion(response=response)
        else:
            raise ResourceExportError(
                f"Azure export failed with status {response.status_code}: {response.text}"
            )

        template_json = payload.get("template") if isinstance(payload, dict) and "template" in payload else payload
        if not isinstance(template_json, dict):
            raise ResourceExportError("Azure export returned an invalid template payload")

        returned_source_resource_ids = source_resource_ids
        if export_mode == "resource_id_list":
            returned_source_resource_ids = list(source_resource_ids)
        return ResourceExportTemplate(
            template_json=template_json,
            export_mode=export_mode,
            source_resource_ids=returned_source_resource_ids,
        )

    async def _poll_export_completion(self, *, response: httpx.Response) -> dict[str, Any]:
        poll_url = response.headers.get("Azure-AsyncOperation") or response.headers.get("Location")
        if not poll_url:
            raise ResourceExportError("Azure export returned 202 without a polling URL")

        deadline = self._monotonic() + self._export_poll_timeout_seconds
        while True:
            if self._monotonic() > deadline:
                raise ResourceExportTimeoutError(
                    f"Azure export polling exceeded {self._export_poll_timeout_seconds} seconds"
                )

            poll_response = await self._request_with_retry("GET", poll_url)
            payload = poll_response.json()
            status = str(payload.get("status", "")).lower()

            if poll_response.status_code in {200, 201} and "template" in payload:
                return payload
            if status == "succeeded":
                if "template" in payload:
                    return payload
                resource_location = payload.get("properties", {}).get("output")
                if isinstance(resource_location, dict):
                    return resource_location
                raise ResourceExportError("Azure export polling completed without a template payload")
            if status in {"failed", "canceled", "cancelled"}:
                raise ResourceExportError(f"Azure export polling reported terminal status: {status}")

            retry_after_seconds = _get_retry_after_seconds(poll_response.headers)
            await self._sleep(retry_after_seconds or self._backoff_seconds)

    async def _request_with_retry(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}))
        headers.update(await self._build_auth_headers())
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._http_client.request(method, url, headers=headers, **kwargs)
                if not _is_retryable_status(response.status_code):
                    return response
                last_error = ResourceExportError(
                    f"Azure request returned retryable status {response.status_code}: {response.text}"
                )
                if attempt == self._max_attempts:
                    break
                await self._sleep(_get_retry_after_seconds(response.headers) or self._backoff_seconds * attempt)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt == self._max_attempts:
                    break
                await self._sleep(self._backoff_seconds * attempt)

        if last_error is None:
            raise ResourceExportError("Azure request failed without a response")
        raise ResourceExportError("Azure request failed after retry exhaustion") from last_error

    async def _build_auth_headers(self) -> dict[str, str]:
        access_token = await self._credential.get_token(_ARM_SCOPE)
        return {"Authorization": f"Bearer {access_token.token}"}


def _is_retryable_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code < 600


def _get_retry_after_seconds(headers: httpx.Headers | dict[str, str]) -> float | None:
    retry_after_value = headers.get("Retry-After")
    if retry_after_value is None:
        return None
    try:
        return max(float(retry_after_value), 0.0)
    except ValueError:
        return None