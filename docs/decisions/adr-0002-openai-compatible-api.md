ADR-0002: use Azure OpenAI-compatible API style for model access

Status
Accepted

Date
2026-07-28

Context
agent-86 requires access to two model tiers:

gpt-4.1-mini for lower-cost and simpler tasks
gpt-5.4 for more complex reasoning
The project already has these models available in Azure AI Foundry. However, the implementation goal for the first phase is to avoid overhead that is not needed yet. The system should use a model access pattern that is simple to implement in Python, easy to debug locally, and flexible enough to evolve later.

Decision
Use the Azure OpenAI-compatible API style as the initial model access pattern.

Why this decision was made
This choice fits the current project goals:

it minimizes implementation overhead in the first phase
it is straightforward to use from Python
it supports the immediate need for chat completion style interactions
it keeps the code path clear and easier to troubleshoot
it does not prevent later expansion into broader Azure AI or Foundry patterns if needed
Clarification on Azure AI Foundry
The decision to use the OpenAI-compatible API style does not mean Azure AI Foundry is being rejected. It means the project will avoid adding management or orchestration overhead that is not required in the first implementation. If model deployments are already managed through Azure AI services, this access style remains a practical and low-friction way to begin.

Cost note
Using Azure AI Foundry-managed models through an Azure OpenAI-compatible interface does not inherently add meaningful extra cost by itself. Cost is primarily driven by:

model inference usage
storage
observability and logging choices
compute and hosting choices
retrieval or indexing services if later added
The main concern here is not platform surcharge but implementation complexity. The selected approach reduces early complexity.

Alternatives considered

Direct Foundry-specific project or inference patterns
Pros

may align with broader future Azure AI platform usage
may support a wider model or project management surface later
Cons

adds implementation concepts not yet needed
risks introducing overhead before the core chat workflow is proven
may complicate the first local development iteration
Heavy agent framework abstraction over model access
Pros

may provide convenience features
Cons

hides model access behavior too early
makes cost and routing behavior harder to inspect
not aligned with the lean, fail-fast approach
Consequences

Positive consequences

lower friction to first working implementation
easier local testing and debugging
simpler model client wrapper design
easier to route between model tiers explicitly
lower risk of premature abstraction
Negative consequences

future expansion into broader Azure AI capabilities may require additional integration work
some implementation details may need adaptation if the model access path changes later
Implementation notes

model access should still be wrapped behind a local interface in the codebase
deployment names should be configuration-driven
the application should treat model choices as capability tiers rather than hardcoded product assumptions
routing logic should remain outside the raw client implementation
the client layer should support future expansion without forcing a rewrite of chat orchestration
Follow-up impact
This decision directly supports:

heuristic model routing between gpt-4.1-mini and gpt-5.4
a simple Python client layer for Phase 1A
server-sent event response streaming
easier local-first implementation
Related decisions

FastAPI as the backend web framework
Cosmos DB for session and message persistence
local development auth bypass
model routing strategy
