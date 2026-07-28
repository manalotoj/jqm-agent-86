ADR-0001: use FastAPI as the backend web framework

Status
Accepted

Date
2026-07-28

Context
agent-86 needs a Python web framework for the first implementation phase. The backend must support:

HTTP API endpoints
streaming responses for chat
simple local development
clean request and response modeling
future authentication integration
future extensibility for tools, files, and operational concerns
The project is being built with a lean, fail-fast approach. Early implementation should minimize overhead and avoid unnecessary framework complexity.

Decision
Use FastAPI as the backend web framework.

Why this decision was made
FastAPI is the preferred choice for the first implementation because it aligns well with the immediate needs of the project:

it is well suited for building API-first Python services
it supports asynchronous request handling cleanly
it works well for streaming response patterns
it has straightforward model validation
it is lightweight compared to larger framework options
it is commonly used for service-style backends and integrates well with the Python ecosystem
Alternatives considered

Flask
Pros

simple
widely understood
minimal starting overhead
Cons

requires more manual structure for validation and modern async patterns
less aligned with the desired API-first, typed-service style
would likely require more supporting choices to reach the same shape
Django
Pros

mature
batteries included
strong ecosystem
Cons

too heavy for the initial service scope
introduces concepts and structure not needed for this backend-first iteration
not the best fit for a lean local-first API service starting point
Other agent-oriented frameworks
Examples include higher-level frameworks or orchestration stacks that may include API hosting assumptions or opinionated abstractions.

Pros

may accelerate certain advanced features later
Cons

unnecessary abstraction for the first implementation
increases cognitive load
can hide model and tool interactions in ways that make debugging and cost control harder
Consequences

Positive consequences

faster path to a usable API
easier local development
good fit for server-sent event streaming
easier request and response schema handling
cleaner path for incremental endpoint growth
Negative consequences

the project team remains responsible for designing application layering and service boundaries
some operational concerns will still need to be deliberately added rather than inherited from a larger framework
Implementation notes

the application should remain modular and not place all logic in route handlers
API routes should be thin
business logic should live outside the route layer
infrastructure concerns such as Cosmos DB and model clients should remain isolated from domain logic
the framework choice should not justify overbuilding the app structure before needed
Follow-up impact
This decision supports the planned Phase 1A implementation:

health endpoint
session endpoints
streaming chat endpoint
local-first execution
Related decisions expected

Azure OpenAI-compatible API style
Cosmos DB for session and message persistence
local development auth bypass
model routing strategy
