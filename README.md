agent-86

Purpose
agent-86 is a Python-based Azure-native custom AI agent project designed for iterative development. The system will begin as a local-first FastAPI backend and evolve into a secure, production-capable agent platform deployed into an Azure subscription.

Primary goals

Support chat-based interactions with persistent sessions
Persist conversation history in Azure Cosmos DB
Route requests between two model tiers:
gpt-4.1-mini for lower-cost and simpler tasks
gpt-5.4 for more complex reasoning tasks
Use Azure OpenAI-compatible API access to minimize early implementation overhead
Add tool-based capabilities over time, including:
Azure environment inspection
GitHub integration
file upload, manipulation, and generated outputs
Keep the architecture lean, budget-aware, and easy to iterate on
Current implementation approach
This repository will be built in manageable phases rather than all at once. The initial focus is a minimal but real backend with persistence, streaming chat, and model routing.

Initial technical direction

Language: Python 3.12
Package manager: uv
API framework: FastAPI
Local development first
Real Azure Cosmos DB from the start
Azure AD / Entra authentication targeted, with local development bypass initially
Azure OpenAI-compatible client pattern for model access
Custom orchestration code instead of a heavy agent framework
Why this project is structured this way
The goal is to avoid unnecessary abstraction and avoid losing critical setup knowledge. As the project grows, this repo will capture:

implementation code
architecture and decision records
scripts that must be executed
execution instructions and runbooks
examples and test inputs
future infrastructure definitions
Guiding principles

Lean, fail fast, iterate
Prefer the simplest thing that can work
Use real persistence where it matters
Keep model access abstract enough to swap deployments later
Separate domain logic from infrastructure concerns
Make setup repeatable
Document decisions when they affect future implementation
Planned near-term phases
Phase 0

Establish repository structure only as needed
Add foundational project documentation
Capture decisions already made
Phase 1A

FastAPI backend
Health endpoint
Session creation and retrieval
Chat streaming endpoint using server-sent events
Cosmos DB-backed sessions and messages
Model routing between gpt-4.1-mini and gpt-5.4
Local development identity mode
Phase 1B

Basic tool abstraction
Tool event persistence
Better prompt construction and routing rules
Early observability and smoke tests
Phase 2

Read-only Azure inspection tools
Read-only GitHub integration using PAT for prototype
Tool execution logging and safe boundaries
Phase 3

File upload support
Blob-backed artifact storage
Generated output artifacts
Input/output lineage between uploaded and generated files
Non-goals for the first implementation slice

Full production deployment
Containerization
Bicep-first infrastructure
Advanced authorization enforcement
Long-running background job orchestration
VS Code integration
Architecture summary
The long-term architecture centers on:

FastAPI backend as orchestrator
Azure OpenAI-compatible model access
Cosmos DB for sessions and messages
Blob Storage for future file and artifact handling
Key Vault for future secret management
Azure-managed identity for future secure Azure access
Application Insights for future observability
optional future additions such as Azure AI Search, background jobs, and queue-based processing
Current model strategy
Two model tiers are planned:

fast/low-cost model: gpt-4.1-mini
premium reasoning model: gpt-5.4
The system should treat these as capability tiers, not hardcoded assumptions, so the premium model can be changed later if needed.

Persistence strategy
Conversation persistence is a first-class concern, so Azure Cosmos DB will be included early rather than mocked or deferred. Initial persisted entities will include:

sessions
messages
later, tool events
later, file/artifact metadata
File handling direction
The chosen file capability direction is not only upload and storage, but also editing and generated outputs. This means the system will eventually support:

uploaded source files
parsed content
generated derivative files
artifact lineage between source and outputs
Authentication direction
The intended authentication target is Azure AD / Microsoft Entra ID. Early local development may use a controlled bypass mode, but the API should be designed so Entra-based validation can be introduced without major restructuring.

Repository evolution rule
New capabilities should be added incrementally. When appropriate, each capability should eventually include:

implementation code
setup or execution script
documentation or runbook updates
example requests or smoke tests
Status
Repository initialization and documentation scaffolding are in progress. Application code has not yet been generated.
