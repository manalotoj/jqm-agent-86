import logging

import httpx

from agent_86.core.config import Settings


logger = logging.getLogger(__name__)


class WebSearchService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._timeout = settings.web_search_timeout_seconds
        self._max_results = settings.web_search_max_results

    async def search(self, query: str) -> tuple[str, dict]:
        configured_providers = self._configured_providers()
        if not configured_providers:
            return (
                "No web search provider is configured for this request.",
                {
                    "provider": "none",
                    "query": query,
                    "status": "not_configured",
                },
            )

        tavily_result = await self._search_tavily(query)
        if tavily_result is not None:
            return tavily_result

        brave_result = await self._search_brave(query)
        if brave_result is not None:
            return brave_result

        return (
            "Configured web search provider(s) are currently unavailable. Please try again later.",
            {
                "provider": ",".join(configured_providers),
                "query": query,
                "status": "provider_unavailable",
            },
        )

    def _configured_providers(self) -> list[str]:
        providers: list[str] = []
        if self._settings.tavily_api_key:
            providers.append("tavily")
        if self._settings.brave_search_api_key:
            providers.append("brave")
        return providers

    async def _search_tavily(self, query: str) -> tuple[str, dict] | None:
        if not self._settings.tavily_api_key:
            return None

        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self._settings.tavily_api_key,
            "query": query,
            "max_results": self._max_results,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            logger.warning("Tavily web search request failed: %s", type(exc).__name__)
            return None

        if response.status_code in {401, 402, 429}:
            logger.warning(
                "Tavily web search request was rejected with HTTP %s.",
                response.status_code,
            )
            return None

        if response.is_error:
            logger.warning(
                "Tavily web search request failed with HTTP %s.",
                response.status_code,
            )
            return None

        data = response.json()
        results = data.get("results", [])

        content = self._format_results(
            query=query,
            provider="tavily",
            results=[
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", ""),
                }
                for item in results
            ],
        )

        return (
            content,
            {
                "provider": "tavily",
                "query": query,
                "status": "ok",
                "result_count": len(results),
            },
        )

    async def _search_brave(self, query: str) -> tuple[str, dict] | None:
        if not self._settings.brave_search_api_key:
            return None

        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self._settings.brave_search_api_key,
        }
        params = {
            "q": query,
            "count": self._max_results,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, headers=headers, params=params)
        except httpx.HTTPError as exc:
            logger.warning("Brave web search request failed: %s", type(exc).__name__)
            return None

        if response.status_code in {401, 402, 429}:
            logger.warning(
                "Brave web search request was rejected with HTTP %s.",
                response.status_code,
            )
            return None

        if response.is_error:
            logger.warning(
                "Brave web search request failed with HTTP %s.",
                response.status_code,
            )
            return None

        data = response.json()
        results = data.get("web", {}).get("results", [])

        content = self._format_results(
            query=query,
            provider="brave",
            results=[
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("description", ""),
                }
                for item in results
            ],
        )

        return (
            content,
            {
                "provider": "brave",
                "query": query,
                "status": "ok",
                "result_count": len(results),
            },
        )

    def _format_results(
        self,
        query: str,
        provider: str,
        results: list[dict],
    ) -> str:
        if not results:
            return (
                f"Web search provider: {provider}\n"
                f"Query: {query}\n"
                "No results found."
            )

        lines = [
            f"Web search provider: {provider}",
            f"Query: {query}",
            "",
        ]

        for index, result in enumerate(results, start=1):
            title = result.get("title") or "(no title)"
            url = result.get("url") or "(no url)"
            snippet = result.get("snippet") or "(no snippet)"

            lines.extend(
                [
                    f"{index}. {title}",
                    f"URL: {url}",
                    f"Snippet: {snippet}",
                    "",
                ]
            )

        return "\n".join(lines).strip()