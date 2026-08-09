from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_86.core.config import Settings
from agent_86.tools.tool import ToolContext, ToolResult

_STATE_KEY = "_tool_guardrails"


def normalize_web_search_query(query: str) -> str:
    return " ".join(query.strip().lower().split())


@dataclass(frozen=True)
class WebSearchGuardrails:
    max_calls_per_request: int = 1
    max_query_length: int = 200
    block_duplicate_queries: bool = True

    @classmethod
    def from_settings(cls, settings: Settings) -> "WebSearchGuardrails":
        return cls(
            max_calls_per_request=settings.web_search_max_calls_per_request,
            max_query_length=settings.web_search_max_query_length,
            block_duplicate_queries=settings.web_search_block_duplicate_queries,
        )

    def check(
        self,
        *,
        tool_name: str,
        query: str,
        context: ToolContext,
    ) -> ToolResult | None:
        if tool_name != "web_search":
            return None

        normalized_query = normalize_web_search_query(query)
        if not normalized_query:
            return self._build_blocked_result(
                context=context,
                query=query,
                reason="empty_query",
                message="Web search was skipped because the search query was empty.",
            )

        if len(normalized_query) > self.max_query_length:
            return self._build_blocked_result(
                context=context,
                query=query,
                reason="query_too_long",
                message=(
                    "Web search was skipped because the search query exceeded the allowed length."
                ),
            )

        state = self._get_request_state(context)
        seen_queries = state.setdefault("web_search_queries", [])

        if self.block_duplicate_queries and normalized_query in seen_queries:
            return self._build_blocked_result(
                context=context,
                query=query,
                reason="duplicate_query",
                message="Web search was skipped because the same query already ran for this request.",
            )

        web_search_calls = int(state.get("web_search_calls", 0))
        if web_search_calls >= self.max_calls_per_request:
            return self._build_blocked_result(
                context=context,
                query=query,
                reason="request_limit_exceeded",
                message="Web search was skipped because the per-request search limit was reached.",
            )

        state["web_search_calls"] = web_search_calls + 1
        seen_queries.append(normalized_query)
        return None

    def _get_request_state(self, context: ToolContext) -> dict[str, Any]:
        state = context.metadata.get(_STATE_KEY)
        if isinstance(state, dict):
            return state

        state = {
            "web_search_calls": 0,
            "web_search_queries": [],
        }
        context.metadata[_STATE_KEY] = state
        return state

    def _build_blocked_result(
        self,
        *,
        context: ToolContext,
        query: str,
        reason: str,
        message: str,
    ) -> ToolResult:
        return ToolResult(
            tool_name="web_search",
            content=message,
            metadata={
                "session_id": context.session_id,
                "user_id": context.user_id,
                "query": query,
                "status": "blocked",
                "blocked": True,
                "reason": reason,
            },
        )