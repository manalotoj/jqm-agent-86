# Futures

This document captures follow-up work identified while implementing backend web-search guard rails, MCP parity, and the generic per-request tool round-trip cap.

## Current follow-up items

| Area | Future item | Why it matters | Suggested next step | Status |
| --- | --- | --- | --- | --- |
| Streaming / e2e | Extend `/Users/johnmanaloto/source/github/jqm-agent-86/backend/src/tests_e2e/test_chat_stream.py` to cover blocked second-search scenarios and capped tool round-trips. | Unit tests now cover the important stream-health behavior, but a full server-level SSE regression test would verify persistence, emitted events, and final completion behavior together. | Add an e2e chat-stream case that triggers an initial web search, then a blocked follow-up search or round-trip-capped continuation, and assert SSE `tool_call`, `tool_result`, `complete`, and `done` behavior. | Pending |
| Tool orchestration | Monitor whether `tool_roundtrip_max_per_request` default (`4`) is the right request-level cap. | The cap is now generic and safe, but the correct threshold may depend on real chat behavior, model quality, and tool usage patterns. | Observe test/dev usage, then tune the setting or make per-environment overrides explicit in local/e2e config. | Pending |
| Web search UX / product behavior | Decide whether duplicate web-search queries should remain blocked-only or evolve into request-local cached results. | Blocking prevents duplicate credit spend, but caching could improve answer quality by letting the model re-use prior results more naturally. | Choose between current blocked-result semantics and a request-local cache design, then update `ToolService`, guardrails, and tests accordingly. | Pending |
| Observability | Add telemetry for blocked tool executions and capped tool round-trips if operational visibility is needed. | Structured blocked `ToolResult`s preserve chat/stream health, but there is currently no dedicated logging or metric trail for guardrail decisions. | Define the desired telemetry surface (logs, counters, traces), then instrument guardrail and chat-model decision points. | Pending |
| Docs / config hygiene | Document new request-level safety settings in user-facing setup docs if they should be externally configurable. | `web_search_*` and `tool_roundtrip_max_per_request` exist in settings now, but readers may not discover them unless they inspect code. | Update README or backend docs with a short “request safety limits” section when the settings are considered stable. | Pending |
