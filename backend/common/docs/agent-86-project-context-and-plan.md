# agent-86 — Project Context & Implementation Plan

Generated as a complete-context handoff document. Two audiences: (1) the project owner, for a prioritized view of what's done and what's left; (2) agent-86 itself, to be fed as context so it can reason about its own codebase and history without rediscovering decisions already made.

---

## 1. Project Purpose

agent-86 is a personal, Azure-native AI agent platform: a FastAPI backend persisting sessions/messages in Cosmos DB, routing between Azure AI Foundry-hosted models (gpt-4.1-mini primary, gpt-5.4 escalation), with an extensible tool layer (web search now; Azure inspection and GitHub integration planned) and an MCP server exposing those same tools to external agentic coding tools (Cline, Copilot). Used both personally and for consulting work (TriWest/DHA-adjacent, though agent-86 itself is not IL4/CUI-scoped).

Development is agent-assisted: Cline and GitHub Copilot execute scoped, pre-designed implementation prompts; architectural/design decisions are made deliberately before implementation, not left to the coding agent to infer.

---

## 2. Current Architecture

### Repo structure (monorepo, restructured mid-project)

```
root
  /common
    /scripts        # start_local.zsh, start_mcp.zsh, start_ui.zsh, start_cline_proxy.zsh
    /docs           # e2e-testing.md and other runbooks
    /utils
      /cline
        cline_proxy.py       # local FastAPI passthrough so Cline's "OpenAI Compatible"
        requirements-dev.txt # provider doesn't inject Azure-specific api-version params
  /backend
    /src
      /agent_86
        /api          # routes: sessions, messages, chat (+ chat/stream)
        /auth         # Entra token validation, dependencies
        /core         # config.py (pydantic-settings)
        /domain       # models (Message, Session), schemas
        /mcp          # MCP server adapter, exposes ToolRegistry
        /repositories # Cosmos + in-memory implementations
        /services     # SessionService, MessageService, ChatModelService,
                       # ModelRouter, ToolService, WebSearchService
        /tools        # Tool protocol, ToolRegistry, WebSearchTool, EchoTool, bootstrap.py
      /tests           # mocked/integration — no live network, no live server
      /tests_e2e       # TRUE e2e — real server, real Entra tokens, real (separate) Cosmos account
    .venv
    requirements.txt / requirements-mcp.txt / requirements-e2e.txt
    .env.common / .env.api / .env.e2e (server-side, gitignored)
  /frontend
    /src
      /api            # thin fetch wrapper (client.ts), typed session functions
      /auth           # msalConfig.ts, getApiToken.ts
      /components     # SessionList.tsx, etc.
      /hooks          # useSessions.ts (TanStack Query)
      /types          # Session, CreateSessionRequest, etc. — mirrors backend dataclasses
      App.tsx / main.tsx
    .env / .env.example (VITE_ENTRA_CLIENT_ID, VITE_ENTRA_TENANT_ID, VITE_API_SCOPE, VITE_API_BASE_URL)
```

Streamlit UI (`dev_ui.py`) has been retired in favor of the React frontend.

### Backend request flow

`/sessions/{id}/chat` and `/sessions/{id}/chat/stream`:
1. Validate Entra bearer token → resolve `AuthenticatedUser` (oid → sub claim precedence)
2. Persist user message
3. `ModelRouter` selects model tier
4. `ChatModelService` builds structured Responses API input (role-conditional content type: `input_text` for system/user, `output_text` for assistant history, `function_call`/`function_call_output` for tool turns)
5. Model-driven tool-calling loop (not keyword heuristics) — model decides whether to invoke `web_search`, executed via existing `ToolService`
6. Persist tool call (role=`assistant`, `metadata.message_type=function_call`) and tool result (role=`tool`, `metadata.message_type=function_call_output`) as first-class messages
7. Stream or return final assistant reply

**Streaming wire format** (custom, not a standard protocol — confirmed via raw curl, not assumed):
```
event: start    data: {"session_id", "model", "tools"}
event: delta    data: {"text": "..."}          (repeated)
event: complete data: {"message": {...full Message...}, "assistant_text": "..."}
event: done     data: {}
```
This does **not** match Vercel AI SDK's `useChat` v5 protocol (which expects `data:`-only lines with `type` fields, `text-start`/`text-delta`/`text-end`, and an `x-vercel-ai-ui-message-stream: v1` header). Decision made: skip `useChat`'s built-in transport, write a custom thin SSE consumer on the frontend against this existing format — not yet implemented (see Section 6).

### Auth (Entra ID)

- **No bypass mode** — single auth path in all environments, by deliberate choice
- Fail-fast startup if Entra config missing/invalid (tenant ID, client ID, `ENTRA_API_AUDIENCE`)
- `ENTRA_API_AUDIENCE` is explicit config, never derived from client ID
- Cross-user access returns **404** (not 403) to avoid existence leakage
- Identity claim precedence: `oid` → `sub`; reject tokens missing both
- Single-tenant today, config-driven (not hardcoded) so multi-tenant is a config change later, not a rewrite
- **Two separate Entra app registrations exist:**
  - **API app registration** (`80a45b0e-0c2e-42d1-9a38-0a1ff450924f`) — exposes the API, defines scope `access_as_user`, is the audience
  - **UI/client app registration** (`5627b327-a846-40e6-bf9d-45ff4c02cb43`) — has TWO separate platform-type entries under Authentication:
    - **Web** platform + client secret — used for manual Postman testing and client_credentials (service-to-service/testing) token acquisition
    - **SPA** platform, redirect URI `http://localhost:5173` — used by the React frontend's MSAL PKCE flow. **Critical: this redirect URI must exist ONLY under SPA, not also under Web** — a same-hostname duplicate across platform types (even with different ports) causes Entra to reject the SPA token exchange with `AADSTS9002326`.
- Streamlit (retired) used `DefaultAzureCredential` with cached token + expiry-skew refresh + retry-once-on-401; React frontend uses `msal-browser`/`msal-react` (`acquireTokenSilent` → `acquireTokenRedirect` fallback) instead
- MCP server uses a deliberate, separate **synthetic** identity (`user_id="mcp-client"`), untouched by any of the above — MCP-originated tool calls are not delegated-user calls

### MCP server

- Wraps existing `ToolRegistry`/`ToolService` — thin adapter, no duplicated tool logic
- stdio transport, low-level `mcp.server.Server` API
- `Tool.input_schema` (already existed as a protocol requirement, was just unimplemented) now implemented on concrete tools for MCP advertisement
- Does not import `api/dependencies.py` (avoids dragging in Cosmos/Foundry wiring) — uses a dedicated `tools/bootstrap.py` composition root instead, shared with the FastAPI app
- Known limitation, accepted for now: stdio carries no end-user identity — fine for machine/local-credential auth (current Azure tools would use `DefaultAzureCredential`), would become limiting if per-user delegated credentials are ever needed for a Phase 2 tool

### Testing

- **Mocked/integration** (`backend/src/tests/`): `TestClient`, no live network, mocked Cosmos/Foundry/auth — the default `pytest` run
- **True E2E** (`backend/src/tests_e2e/`): real running server (`AGENT86_ENV_MODE=e2e ./common/scripts/start_local.zsh`), real Entra tokens via `client_credentials` grant, **completely separate Cosmos DB account** (not just a different database) for isolation. Marked `@pytest.mark.e2e`, excluded from default `pytest` runs, only via `pytest -m e2e`. Coverage built so far: scaffolding (token fixture, reachability check, smoke tests), session CRUD, streaming (event-sequence + persistence verification). Messages-only CRUD batch was deliberately skipped. Cross-user isolation is NOT covered in e2e (single client_credentials identity available) — that's covered in the mocked suite instead; e2e only checks that a fabricated random session ID returns 404.
- Identity caveat specific to e2e: client_credentials tokens resolve to the **service principal's** `oid` as `user_id` — every e2e-created session is owned by the same fixed machine identity across all runs, forever. List assertions use containment, not exact equality, for this reason.

### Dev tooling

- **`cline_proxy.py`**: local FastAPI passthrough (`localhost:8787` → real Foundry `/openai/v1` endpoint). Necessary because Cline's provider logic auto-detects `azure.com` in the base URL and force-injects an `api-version` query param incompatible with Foundry's `/v1` endpoint — the proxy hides the `azure.com` string from Cline entirely. Shares `backend/.venv`.
- Cline model config: `gpt-4.1-mini-2` as default/Act-mode model, `gpt-5.4` reserved for Plan-mode/complex design work — Plan/Act model-split toggle in Cline was abandoned (buggy on OpenAI-Compatible providers, silently collapsed to one model) in favor of manual model switching per task
- Cline reasoning effort: Act mode set to **low** (deliberate choice — Act should be mechanical execution against an already-fully-specified plan; low effort tested successfully on a 5-deliverable scaffolding task with zero dropped requirements)
- GitHub Copilot also in use (credits/usage-based billing), same prompt content works across both tools

---

## 3. Completed Work

**Foundational backend:** FastAPI scaffold, Cosmos persistence (sessions/messages), model routing (2 tiers), tool protocol/registry/service, web search tool (Tavily/Brave fallback).

**Chat model contract hardening:** flattened-string prompts → structured Responses API message arrays; role-conditional content types (`input_text`/`output_text`) — found and fixed via a real production bug (400 error), not caught by the original test.

**Real tool-calling:** replaced keyword-heuristic tool triggering with model-driven Responses API tool calling; fixed a persistence-contract regression (structured tool-call data was leaking into `content` instead of `metadata`) and a duplicate-tool-execution bug (route was still calling `execute_tools` before the model's own loop, firing search twice per turn).

**MCP server:** built and verified working (MCP Inspector + live Cline integration) — `web_search` callable from Cline via MCP, not just via the chat endpoint.

**Entra ID auth:** full delegated-user auth (fail-fast, no bypass, 404-on-cross-user, oid/sub precedence) — this was the most debugging-intensive piece of the whole project (see Section 5).

**SSE streaming:** implemented server-side (custom event format, see Section 2).

**Repo restructure:** flat → `backend`/`frontend`/`common` monorepo split, `.venv` moved under `backend`, all scripts updated for new path depth, env-mode-selectable server startup (`AGENT86_ENV_MODE`).

**True E2E test suite:** scaffolding + session CRUD + streaming coverage, against a dedicated e2e-only Cosmos account.

**React frontend, Phase A (auth) + Phase B (sessions CRUD):**
- Vite + React + TypeScript scaffold, Oxlint (not ESLint) for linting
- MSAL React auth wiring — hit and resolved the SPA-vs-Web-platform + same-hostname-different-port Entra gotcha; standardized on `loginRedirect`/`logoutRedirect` over popup flow (popup hit a COOP/`window.opener` browser issue)
- Full session CRUD (API client layer, TanStack Query hooks, minimal list UI) — proven working end to end against the real backend

**Design work completed but not yet implemented:** persona architecture (concept + schema shape agreed), several generated-output workflow designs (see Section 6 and 7).

---

## 4. Key Decisions & Rationale (worth preserving, not re-litigating)

- **No Entra auth bypass, anywhere, ever** — one code path, always tested, rather than a bypass mode that's a latent security risk and an under-tested code path
- **404, not 403, for cross-user resource access** — avoids confirming a resource's existence to someone who doesn't own it
- **`ENTRA_API_AUDIENCE` always explicit** — never derive from client ID; explicit config over implicit coupling, given how many Entra bugs in this project traced back to exactly this kind of implicit derivation
- **Fail-fast on missing/invalid config at startup** — silent fallback (e.g., `cosmos_database_name` defaulting to production's name) is a worse failure mode than a loud crash; `Field(min_length=3)` used to catch empty-but-present values, not just missing ones
- **MCP server never imports `api/dependencies.py`** — keeps MCP startup lightweight and decoupled from the full FastAPI dependency graph
- **MCP synthetic identity is separate and untouched by delegated-user auth work** — different trust boundary, different concern, explicitly not conflated
- **E2E tests use a fully separate Cosmos account, not just a separate database** — stronger isolation than same-account/different-database, and serverless makes this ~free
- **Client-credentials identity in e2e resolves to a single fixed service-principal `oid`** — no per-run isolation; list assertions must use containment, not equality, to remain correct
- **`backend`/`frontend`/`common` split, not a flat `src`** — avoids the ambiguity of two directories both meaningfully named `src` at different depths
- **`.venv` lives under `backend`, recreated fresh (not moved) during the restructure** — venvs bake in absolute paths at creation time
- **Model tiering discipline:** gpt-4.1-mini for scoped, well-specified, single-concern tasks; gpt-5.4 for design/architecture work with real ambiguity to resolve. Plan/Act split abandoned as a Cline feature (buggy); the *practice* of "resolve design decisions before implementation" continues manually — decisions get made in a planning conversation first, then handed to Act as an already-fully-specified prompt
- **Prompts to coding agents should be scoped small and single-purpose**, not "comprehensive" — comprehensiveness is exactly the failure category where an agent silently drops requirements with no self-correcting signal (a missing test case doesn't fail a test suite; a missing file-edit doesn't throw an error)
- **Every implementation prompt should end with a self-verification instruction** ("confirm every file listed was actually touched," "grep and report") — catches silent partial completion regardless of which model is being used

---

## 5. Lessons Learned / Gotchas (worth agent-86 knowing about itself)

- **Never trust an SDK/API shape from training-data memory — verify against the actually-installed version.** This bit the project three separate times before the habit stuck: Responses API `input_text` vs `output_text` by role, `function_call_output` item shape, and repeated Azure OpenAI `api-version` scheme confusion (classic dated versions vs. `preview`/`latest` on the newer `/v1` unified endpoint — these are genuinely different API surfaces with different versioning rules).
- **Azure Entra platform-type mismatches produce confusing, generically-worded errors.** Specific patterns hit: (1) Web-platform-registered redirect URI + PKCE/no-secret exchange → `AADSTS9002326` "cross-origin token redemption"; (2) same redirect URI registered under both Web and SPA (or even just the same hostname under both, different ports) → same error, because Entra's cross-origin check appears to key on more than just the exact URI; (3) client ID and audience being the *same* app registration → `AADSTS90009`, requires a genuinely separate client app registration from the API app registration.
- **Cline's "OpenAI Compatible" provider silently switches to an Azure-specific HTTP client whenever the base URL contains the substring `azure.com`**, regardless of provider label or explicit config checkboxes — force-injects an incompatible `api-version` param. Only reliable fix found: a local reverse proxy that hides the `azure.com` string from Cline (`cline_proxy.py`).
- **Cline's "different models for Plan/Act mode" feature is unreliable on OpenAI-Compatible/Azure-style providers** — known to silently collapse both modes to the same model. Abandoned in favor of manual model switching.
- **Postman's OAuth 2.0 automation (both PKCE and even plain Authorization Code flows) has real bugs** — silent "request url is empty" failures during token exchange, unrelated to any actual Entra misconfiguration. Manual two-step token acquisition (build the auth URL by hand, capture the code, POST to the token endpoint manually with plain `x-www-form-urlencoded`, no Postman OAuth manager involved) is the reliable fallback and was ultimately the only way real tokens got obtained for testing.
- **`useChat`'s default request body is UIMessage-shaped (`{id, messages}` with `parts` arrays), not the flat `{content, metadata}` shape this backend uses** — full protocol mismatch on both request and response sides, not just streaming format; confirmed via raw curl inspection rather than assumed from library docs.
- **A model dropping one line item from a well-specified, multi-part plan is a recurring, specific gpt-4.1-mini failure mode** — not a prompt-clarity problem. Observed concretely: `MessageRole` needed a `"tool"` addition across two separate files; one file got updated, the other silently didn't, and nothing about the running app signaled the gap until an explicit audit was requested. The mitigation that actually works: explicit self-verification steps built into every prompt, not just clearer wording.
- **Print/repr defaults matter when debugging config:** pydantic `Settings`/dataclasses print field values usefully via default `__str__`; Cosmos SDK client objects (`ContainerProxy`) do not — use `.id` for a cheap, no-network-call check of what a client is actually pointed at.

---

## 6. Prioritized Remaining Work

Ordered by dependency and, within a tier, by value. "Designed" means the shape/schema was agreed in conversation but no code exists yet.

### Tier 1 — near-term, natural next steps
1. **Frontend streaming consumer** — custom SSE parser (not `useChat`'s built-in transport) matching the real `event:`/`data:` wire format in Section 2. This is the last piece of Phase D from the original frontend plan; without it, chat isn't usable in the new UI yet.
2. **`role="tool"` message rendering decision in the frontend** — was flagged as a deliberate UX choice to make (show distinctly vs. filter from main feed), not yet decided or built.
3. **Chat session summary system** — schema designed (Section 7), not yet implemented. This is a genuine prerequisite for the "assistant persona" idea in Tier 2 (a planner persona is only as good as the memory it can retrieve) and independently useful right now for reducing time spent re-reading old sessions.

### Tier 2 — depends on Tier 1
4. **Assistant persona architecture** — schema designed (Section 7). Requires the summary/memory system first (for `memory_scope: cross-session` to mean anything). First real persona to build: a "planner" persona (gpt-5.4 default, `web_search` + memory-retrieval tools only, structured planning-output system prompt) that produces Cline-ready implementation prompts — effectively moving the "resolve design decisions before implementation" role this conversation has played into agent-86 itself.
5. **Generated-output workflows, roughly in this order:**
   - Structured findings document (schema in Section 7) — highest immediate personal value, directly mirrors real work already done manually
   - RCA report (schema in Section 7) — same rendering pipeline as findings doc, different schema
   - Multi-source research report — mostly redundant with existing chat tool-calling; real value is enforced-thoroughness + persisted/cited document output, not new reasoning capability
   - Deployment diagrams — recommended approach: **draw.io/diagrams.net XML** (editable, real Azure icon library) as the default; PPTX-embedded Azure icons specifically when the diagram is going straight into a slide deck; Mermaid was explicitly rejected as insufficiently polished for client-facing use
   - Bicep snippet generation — explicitly deprioritized; not worth building as a dedicated workflow until it can be chained to a real Azure-inspection tool's live output (Tier 3) and include a `bicep build` validation step — until then, plain chat already does this adequately

### Tier 3 — deferred, real value but bigger lift or lower urgency
6. **Phase 2 tools: Azure inspection (read-only), GitHub integration (read-only first)** — original roadmap item, still not started. Unlocks the Bicep-generation and RCA-from-live-state workflows above.
7. **Key Vault migration** for Cosmos key and any other secrets currently in `.env` files — flagged repeatedly as overdue cleanup, never actioned. Do this before any real deployment.
8. **Containerize + Bicep deployment** (Container Apps target, per original architecture doc) — deliberately sequenced after auth (done) so nothing insecure is ever live, and after the frontend is further along so both halves deploy together sensibly.
9. **Observability** (Application Insights) — becomes non-optional once anything is actually deployed.
10. **Session archive system** — move idle sessions + their summaries to Blob Storage, separate searchable index (likely Azure AI Search / vector embeddings for semantic search, not just Cosmos field filtering). Explicitly noted as only worth building once session volume makes manual browsing genuinely painful — not yet.
11. **Narrow, memory-augmented coding assistant inside the React UI** ("my own Cline") — explicitly scoped DOWN from a general coding-agent rebuild (rejected — Cline/Copilot already solve that well) to: retrieve relevant session history → reason about a task → emit a Cline-ready prompt, text in/text out, no file access, no execution, no GitHub write access. Depends on the summary/memory system (Tier 1) and persona architecture (Tier 2).
12. **Frontend Phase E/F** — polish (model selector, web search toggle, responsive layout) and deployment (Azure Static Web Apps, CORS config) from the original frontend architecture plan — untouched since Phase A/B landed.

### Explicitly rejected / deprioritized, with reasoning (don't re-propose without new information)
- Multi-tenant Entra support — designed to be a config change later, not built now; single-tenant is sufficient for current usage
- Full dual-identity e2e cross-user testing — cost (second app registration, more secrets) doesn't justify the coverage gain given the mocked suite already covers this logic
- A general rebuild of Cline's file-editing/diffing capability inside agent-86's own UI — Cline/Copilot already do this well; not a good use of effort

---

## 7. Schemas for Generated Outputs

### Structured findings document
```python
class DecisionOption(BaseModel):
    name: str
    description: str
    pros: list[str]
    cons: list[str]

class DecisionMatrixRow(BaseModel):
    criterion: str
    weight: float | None = None
    scores: dict[str, float]  # option name -> score

class Citation(BaseModel):
    title: str
    url: str | None = None
    reference: str | None = None  # for internal/non-URL references

class StructuredFindingsDoc(BaseModel):
    title: str
    context: str
    problem_statement: str
    options_considered: list[DecisionOption] = []       # empty when not applicable —
    decision_matrix: list[DecisionMatrixRow] = []        # enforce via an explicit
                                                          # classification step, not
                                                          # left to model discretion
    findings_summary: str
    conclusion: str
    outcome: str
    resources: list[Citation]
```

### RCA report (same rendering pipeline, different schema)
```python
class TimelineEntry(BaseModel):
    timestamp: datetime
    event: str

class RCADoc(BaseModel):
    title: str
    incident_summary: str
    impact: str
    timeline: list[TimelineEntry]
    root_cause: str
    contributing_factors: list[str]
    remediation_taken: str
    preventive_actions: list[str]
    resources: list[Citation]
```

Architectural note: one generic "populate schema from conversation, render to docx" tool with multiple selectable schemas/templates — not separate overloaded tools, and not one tool with a giant grab-bag of optional fields across doc types.

### Chat session summary
```python
class ActionItem(BaseModel):
    description: str
    status: Literal["open", "done", "abandoned"]
    owner: str | None = None

class ArtifactRef(BaseModel):
    name: str
    artifact_type: Literal["docx", "pptx", "xlsx", "diagram", "code", "other"]
    location: str  # file path, URL, or blob reference

class ChatSessionSummary(BaseModel):
    session_id: str
    title: str
    date_range_start: datetime
    date_range_end: datetime
    one_line_summary: str
    topics: list[str]
    key_decisions: list[str]
    action_items: list[ActionItem] = []
    artifacts_generated: list[ArtifactRef] = []
    open_questions: list[str] = []       # the field that actually solves
                                          # "time-consuming to dig back through
                                          # a session" — unresolved threads you'd
                                          # otherwise have to re-read to find
    tools_used: list[str] = []
    tags: list[str] = []                 # freeform, not a fixed taxonomy —
                                          # cluster/rename later once patterns emerge
```
Decision: persist as a queryable Cosmos record (new container), not just a rendered file — the file can be generated on demand from the record. On-demand trigger only for now (no automatic background summarization — consistent with the project's original non-goal of avoiding background job orchestration in the first slice).

### Assistant persona
```python
class AssistantPersona(BaseModel):
    id: str  # "planner", "general", future personas added only as real needs emerge
    system_prompt: str
    default_model: Literal["default", "premium"]  # ties into existing ModelRouter tiers
    allowed_tools: list[str]   # explicit subset of ToolRegistry names — never
                                # implicit/all-by-default; a "planner" persona must
                                # not silently inherit write-capable tools later
    memory_scope: Literal["none", "session-only", "cross-session"]
```
First real persona to build: `"planner"` — `default_model="premium"`, `allowed_tools=["web_search", "memory_retrieval"]`, `memory_scope="cross-session"`, system prompt encoding: resolve ambiguity explicitly rather than picking silently, flag multi-file consistency requirements as checklist items, verify SDK/library behavior via `web_search` rather than assume from training data, output in a fixed structure (goal / context / resolved decisions / open questions / constraints / deliverables) matching the Cline-prompt format used throughout this project.

---

## 8. Tooling & Workflow Conventions

- **Requirements files split by concern:** `requirements.txt` (runtime), `requirements-mcp.txt` (MCP-optional), `requirements-dev.txt` (Cline proxy tooling), `requirements-e2e.txt` (e2e test-only)
- **Env files split by concern:** `.env.common` / `.env.api` (normal server config) / `.env.e2e` (server-side e2e overlay, separate Cosmos account) / `.env.e2e.client` (pytest's own config: base URL, client_credentials secret) — server-side and test-client concerns deliberately kept in separate files even though both relate to "e2e"
- **`start_local.zsh` supports `AGENT86_ENV_MODE`** (default `local`), loading common → api → `.env.${MODE}` last, so mode-specific overlays win
- **Every new script/file location gets a `.gitignore` check as an explicit step**, not assumed — this project has had a live API key pasted in plaintext chat multiple times; rotation was repeatedly flagged
- **Prompts to coding agents follow a consistent structure:** Goal / Context / Relevant modules / Finalized decisions (don't re-litigate) / Design questions requiring an explicit "report back before implementing" step when real ambiguity exists / Constraints / Test plan / Deliverables / Success criteria
- **Design-heavy or multi-file-consistency tasks → higher reasoning effort / stronger model (gpt-5.4 Plan-equivalent); mechanical, fully-specified execution → gpt-4.1-mini or low-effort gpt-5.4 Act**
