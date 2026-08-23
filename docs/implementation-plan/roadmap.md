
agent-86 implementation roadmap

Purpose
This document defines the phased implementation plan for agent-86. It is intentionally practical and incremental. The project will be built in manageable slices, with each phase producing something usable and reviewable before additional complexity is added.

Project goals this roadmap supports

Build a Python-based Azure-native AI agent backend
Persist chat sessions and message history
Route between low-cost and premium model tiers
Support future tool-based actions for Azure and GitHub
Support future file upload, manipulation, and generated outputs
Keep implementation lean, local-first, and easy to evolve
Avoid unnecessary framework overhead in the first iterations
Decisions already locked in

Python 3.12
uv package manager
FastAPI
local development first
real Azure Cosmos DB from the beginning
Azure OpenAI-compatible API style
custom orchestration code instead of a heavy framework
Azure AD / Entra is the long-term auth target
local dev bypass is acceptable initially
model tiers:
gpt-4.1-mini
gpt-5.4
file direction:
upload plus editing and generated outputs
implementation style:
lean, fail fast, iterate
infrastructure approach:
CLI/manual first
derive and refine Bicep later
Implementation strategy
The project will be built from outside-in:

repository and documentation foundation
backend application skeleton
persistence and core chat flow
model routing and streaming
auth structure and operational polish
tools
file workflows
infrastructure hardening and deployment
This order is deliberate. It ensures the project gains a stable spine early and avoids spending time on infrastructure or abstractions before the core chat workflow is working.

Phase 0: repository foundation
Objective
Create only the minimum repository structure needed to support disciplined implementation and avoid losing project context.

Deliverables

root README
implementation roadmap
first decision records
first runbooks as needed
only the directories required by the files actually being added
Success criteria

repo has a clear purpose
repo captures decisions already made
next implementation steps are explicit
no unnecessary directory scaffolding yet
Out of scope

application code
test framework
infrastructure templates
placeholder directories with no immediate use
Phase 1A: minimal working backend with real persistence
Objective
Create a working local FastAPI backend with real persistence in Cosmos DB and model-backed chat response streaming.

Expected deliverables

Python project initialized with uv
FastAPI app entry point
health endpoint
create session endpoint
get session endpoint
list messages endpoint
streaming chat endpoint using server-sent events
Azure OpenAI-compatible model client wrapper
heuristic model router:
default to gpt-4.1-mini
escalate to gpt-5.4 for complex prompts
Cosmos DB-backed session persistence
Cosmos DB-backed message persistence
local development identity mode
env-driven configuration
Suggested API surface for this phase

GET /health
POST /sessions
GET /sessions/{session_id}
GET /sessions/{session_id}/messages
POST /chat/stream
Core flow for Phase 1A

user sends session_id and message
API loads prior session messages from Cosmos DB
prompt is constructed from recent history and system rules
router selects gpt-4.1-mini or gpt-5.4
response is streamed back to client using SSE
user and assistant messages are persisted
response metadata is retained for later inspection
Success criteria

app runs locally
messages persist across restarts
sessions are retrievable
routing between models works
streaming works from a client
no heavy framework dependency is introduced
Out of scope

blob storage
file upload
GitHub integration
Azure inspection tools
App Insights
Key Vault
production auth enforcement
container deployment
Bicep authoring
Phase 1B: harden the application spine
Objective
Improve maintainability and prepare the core service for tool execution and better operational visibility.

Expected deliverables

tool abstraction interfaces
tool event message types or records
prompt builder refinement
stronger request/response validation
better logging
smoke-test scripts
basic integration tests
clearer error handling
session title derivation if useful
Success criteria

the application is easier to extend
errors are diagnosable
tool hooks exist even if tools are not implemented yet
local workflows are documented and repeatable
Out of scope

actual Azure inspection execution
actual GitHub repository access
artifact storage
Phase 2: read-only tools
Objective
Add safe, read-only external tool capabilities.

Phase 2A: Azure inspection
Expected deliverables

read-only Azure identity/access pattern
Azure SDK or Resource Graph-backed inspection tools
subscription/resource group/resource listing
tool call and tool result persistence
clear safety boundaries
Notes
This phase should remain read-only. No write operations should be introduced without explicit review and a separate decision record.

Phase 2B: GitHub integration
Expected deliverables

read-only GitHub client
PAT-based prototype integration
repository metadata access
file retrieval
basic repository browsing
persisted tool event records
Notes
The prototype may use a personal access token initially, but the design should not prevent migration to a GitHub App later.

Success criteria for Phase 2

the agent can call external tools intentionally and safely
tool execution is observable in stored history
failure handling is explicit
read-only boundaries are respected
Out of scope

PR creation
issue creation
repo writes
Azure writes
Phase 3: file and artifact workflows
Objective
Add support for user-uploaded files and generated outputs as first-class artifacts.

Expected deliverables

blob storage integration
upload flow
artifact metadata persistence
artifact references linked to sessions/messages
generated output support
source-to-output lineage tracking
simple parsers for selected file types
Artifact direction
The system should treat both uploaded files and generated outputs as artifacts. Generated files should be linked back to source artifacts where applicable.

Examples

upload a markdown file and generate a revised version
upload a JSON or config file and produce a cleaned variant
upload a text file and create a structured summary output
Success criteria

uploaded files can be stored and referenced
generated outputs can be stored and referenced
provenance between source and generated artifacts is preserved
Out of scope

advanced document indexing
semantic retrieval over large corpora
collaborative editing workflows
Phase 3A: large CSV artifact analysis
Objective
Add an explicit, auditable whole-file CSV analysis workflow while preserving bounded normal-chat attachment behavior.

Expected deliverables

private derived-artifact Blob container with retention policy
Cosmos processing-manifest and analysis-job containers
bounded upload handling and configurable CSV limits
CSV normalization and deterministic JSONL chunks
persisted row-range coverage and complete/partial/failed state
explicit API and UI action to analyze an entire file
unit, regression, and Azure E2E tests including CORS

Success criteria

every valid CSV data row is processed exactly once for a completed portfolio analysis
final results expose coverage and supporting source row ranges
existing artifact APIs, session isolation, and chat behavior remain unchanged
Phase 4: authentication and operational maturity
Objective
Move from local-development assumptions toward secure team use.

Expected deliverables

Entra token validation
role-aware user identity extraction
improved secret handling approach
App Insights integration
operational runbooks for common failures
stricter config validation
Success criteria

local dev remains workable
production auth path is clear
logging and diagnostics improve significantly
Phase 5: deployment and infrastructure maturity
Objective
Move from local-only execution to deployable Azure-hosted operation.

Expected deliverables

Azure Container Apps deployment path
managed identity usage
Key Vault integration
environment-specific configuration
derived and refined Bicep templates after practical validation
deployment documentation
Success criteria

service can be deployed repeatably
Azure resource dependencies are explicit
infra definitions reflect proven implementation choices, not speculation
Cross-cutting implementation rules
Rule 1
Do not add major framework overhead unless a real implementation need appears.

Rule 2
Prefer real persistence over temporary mocks for sessions and messages.

Rule 3
Do not create broad directory trees before they are needed.

Rule 4
When a script is needed, document it with a README in the same script area.

Rule 5
When a design choice affects future implementation, record it as a decision.

Rule 6
Keep tool actions constrained and observable.

Rule 7
Default to read-only external operations first.

Known near-term documents still needed

first ADR for FastAPI
first ADR for OpenAI-compatible API style
first ADR for Cosmos DB chat persistence
local development runbook
Azure resource bootstrap runbook
Current working mode
The current repository is still in planning and scaffolding mode. Files should continue to be added one at a time, only when they support an immediate next step.
