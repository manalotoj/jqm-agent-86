agent-86 decisions

Last updated
2026-07-28

Purpose
This file summarizes the implementation decisions currently committed for agent-86. It is intentionally brief. If a future decision needs more depth or changes materially affect implementation, it can later be broken out into a dedicated ADR.

Current decisions

Backend framework
Use FastAPI
Reason: lightweight, API-first, good fit for async endpoints and streaming responses
Language and package management
Use Python 3.12
Use uv for package management
Reason: modern Python baseline and fast, simple dependency workflow
Development approach
Start locally first
Do not start with containers
Reason: reduce friction and move faster in early implementation
Model access style
Use Azure OpenAI-compatible API style
Reason: lowest overhead path for Python implementation and does not block future expansion
Model tiers
Use gpt-4.1-mini as the default lower-cost model
Use gpt-5.4 as the premium reasoning model
Reason: explicit cost/capability tiering from the start
Model routing approach
Use simple heuristic routing first
Default to gpt-4.1-mini
Escalate to gpt-5.4 for more complex requests
Reason: cheap, transparent, and easy to evolve later
Orchestration approach
Use custom orchestration code
Do not introduce a heavy agent framework initially
Reason: lower overhead, better control, easier debugging, easier cost visibility
Persistence
Use real Azure Cosmos DB from the start
Persist sessions and messages first
Reason: chat history is a core requirement and not worth mocking first
File capability direction
Target upload plus editing and generated outputs
Reason: files should be first-class artifacts, not just passive attachments
Authentication direction
Long-term target is Azure AD / Microsoft Entra ID
Allow local development bypass initially
Reason: do not block early implementation, but preserve the future auth shape
Azure tool scope
Start with read-only Azure inspection
Reason: safer boundary for early tool execution
GitHub integration scope
Start with read-only access using a PAT for prototype
Reason: fastest path to working integration, with migration to GitHub App later if needed
Streaming approach
Use server-sent events first
Reason: simpler than websockets for initial chat streaming
Infrastructure approach
Start with CLI/manual resource creation
Derive and refine Bicep later from validated implementation
Reason: avoid speculative infrastructure templates before the runtime path is proven
Implementation style
Lean, fail fast, iterate
Build in manageable chunks
Only create directory structure as needed
Reason: minimize waste and keep the repo aligned with actual progress
Near-term implementation focus
Phase 1A will target:

FastAPI backend
health endpoint
session endpoints
SSE chat endpoint
Cosmos-backed persistence
Azure OpenAI-compatible model client
heuristic model routing
local development identity mode
How to use this file

update this file when a decision is made that affects implementation
keep entries short
if a decision becomes complex or controversial later, split it into a dedicated ADR at that time
