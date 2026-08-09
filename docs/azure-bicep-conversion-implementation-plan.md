# Azure Export to Bicep implementation plan

Last updated
2026-08-09

Purpose
This document captures the agreed implementation plan for the new "Convert Azure Export to Bicep" capability in agent-86. It records the architecture, repository layout, and compressed 5-day delivery plan so implementation can proceed without later structural refactors.

## Agreed decisions

- Python backend remains the orchestrator.
- A local .NET sidecar provides real Bicep AST composition using `Bicep.Core`.
- Output is one package artifact per Resource Group, not one flat `.bicep` file.
- Each package is rooted at `main.bicep` and may include supporting files under `modules/`.
- Final modularization should be by domain or resource family, not export batch.
- The .NET sidecar should live under top-level `tooling/`, not `dotnet/` and not `tools/`.

## Repository placement

Top-level structure:

```text
/Users/johnmanaloto/source/github/jqm-agent-86/
├── backend/
├── tooling/
│   └── bicep-composition-service/
├── frontend/
├── common/
└── docs/
```

Backend feature structure:

```text
/Users/johnmanaloto/source/github/jqm-agent-86/backend/src/agent_86/
├── api/routes/azure_bicep_conversion.py
├── domain/schemas/azure_bicep_conversion.py
├── integrations/
│   ├── azure/resource_export_client.py
│   ├── bicep/bicep_tool_client.py
│   ├── avm/avm_catalog_client.py
│   └── bicep_composition/composition_api_client.py
└── services/azure_bicep_conversion/
    ├── __init__.py
    ├── orchestrator.py
    ├── models.py
    ├── preflight.py
    ├── export_pipeline.py
    ├── secret_sanitizer.py
    ├── avm_annotation.py
    ├── diagnostics.py
    ├── fallback.py
    └── package_builder.py
```

Test structure:

```text
/Users/johnmanaloto/source/github/jqm-agent-86/backend/src/tests/azure_bicep_conversion/
├── test_route.py
├── test_orchestrator.py
├── test_preflight.py
├── test_export_pipeline.py
├── test_secret_sanitizer.py
├── test_avm_annotation.py
├── test_diagnostics.py
├── test_fallback.py
├── test_package_builder.py
└── test_composition_api_client.py
```

.NET sidecar structure:

```text
/Users/johnmanaloto/source/github/jqm-agent-86/tooling/bicep-composition-service/
├── BicepComposition.sln
├── README.md
└── src/
    ├── BicepComposition.Api/
    │   ├── BicepComposition.Api.csproj
    │   ├── Program.cs
    │   ├── Endpoints/
    │   │   ├── HealthEndpoints.cs
    │   │   └── CompositionEndpoints.cs
    │   ├── Contracts/
    │   │   ├── ComposeRequest.cs
    │   │   ├── ComposeFragment.cs
    │   │   ├── ComposeResponse.cs
    │   │   └── CompositionStats.cs
    │   └── DependencyInjection/
    │       └── ServiceCollectionExtensions.cs
    ├── BicepComposition.Core/
    │   ├── BicepComposition.Core.csproj
    │   ├── Composition/
    │   │   ├── BicepComposer.cs
    │   │   ├── DomainPartitioner.cs
    │   │   ├── ReferenceRewriter.cs
    │   │   ├── SymbolicNameMapper.cs
    │   │   └── DeduplicationEngine.cs
    │   ├── Models/
    │   │   ├── ComposedBicepFile.cs
    │   │   └── CompositionResult.cs
    │   └── Diagnostics/
    │       └── CompositionWarning.cs
    └── BicepComposition.Tests/
        ├── BicepComposition.Tests.csproj
        ├── Composition/
        │   ├── BicepComposerTests.cs
        │   ├── ReferenceRewriterTests.cs
        │   └── DomainPartitionerTests.cs
        └── Api/
            └── CompositionEndpointsTests.cs
```

## Primary API shape

Recommended route:
- `POST /sessions/{session_id}/azure/resource-groups/convert-to-bicep/stream`

Recommended SSE events:
- `start`
- `progress`
- `complete`
- `done`
- `error`

Recommended behavior:
- never stream raw Bicep as inline chat text
- publish one package artifact per Resource Group
- return artifact metadata and summary metadata in the `complete` event

## Package artifact shape

Recommended package contents:
- `main.bicep`
- `modules/network.bicep`
- `modules/storage.bicep`
- `modules/keyvault.bicep`
- `modules/compute.bicep`
- `modules/data.bicep`
- `modules/monitoring.bicep`
- `modules/misc.bicep`
- `conversion-summary.json`
- `diagnostics.txt` when needed

Interpretation of the original requirement:
- "one per Resource Group" means one package artifact per Resource Group, not one flat `.bicep` file

## Responsibility split

Python backend owns:
- auth and session integration
- Azure SDK / ARM export orchestration
- export batching and batch sequencing
- Bicep decompile, format, and diagnostics invocation
- secret sanitization for redacted values
- AVM annotation policy
- package assembly
- artifact persistence
- SSE progress streaming
- failure classification and fallback activation

Azure export adapter owns:
- resource group resource counting
- wildcard export-template requests
- resource-ID-list export-template requests
- retry and backoff for transient ARM failures
- throttling handling for `429 Too Many Requests`
- long-running operation polling and timeout handling for export requests

Bicep tool client owns:
- isolated local execution of official Bicep tooling
- temp-workspace input/output handling
- stdout/stderr capture for decompile, format, and diagnostics operations
- cleanup of temporary execution artifacts

AVM catalog client owns:
- loading a canonical AVM catalog or manifest
- high-speed in-memory resource-type-to-module matching
- optional refresh behavior on a controlled TTL or version boundary

.NET sidecar owns:
- parsing Bicep via `Bicep.Core`
- symbolic mapping
- intra-resource-group and cross-batch reference rewriting
- unresolved reference marking
- parameter, variable, and symbolic-name collision resolution
- exact-match deduplication where semantically safe
- domain partitioning
- `main.bicep` generation
- composed module file generation

## Implementation guardrails

### 1. Azure export resilience

The Azure export path should use a direct Azure SDK / ARM adapter rather than the ARM MCP server for resource-group export-template generation.

Operational requirements:
- do not rely on ARM MCP query tools as a substitute for export-template APIs
- support both wildcard export and explicit resource-ID-list export
- assume that large resource-ID-list exports may still trigger expensive dependency calculation on the ARM side
- handle `429 Too Many Requests` with bounded retry and backoff
- handle transient `5xx` and retryable transport failures
- handle long-running export polling and poll timeouts explicitly
- record retry exhaustion or timeout failures in conversion diagnostics

Implementation guidance:
- keep batch planning in Python orchestration
- keep ARM request submission, polling, and retry behavior in the Azure export adapter
- avoid back-to-back unbounded large-batch requests without pacing or retry control

### 2. Bicep tool execution model

Bicep decompile, formatting, and diagnostics should be executed through official Bicep tooling without requiring an MCP server transport.

Operational requirements:
- execute Bicep in a per-invocation temporary workspace
- never write tool scratch files into application source paths
- capture stdout and stderr into memory buffers for diagnostics and logging
- clean up temporary files after each invocation
- validate actual CLI behavior before depending on a specific stdout flag pattern

Implementation guidance:
- a direct process-driven `BicepToolClient` is preferred over a transport-specific MCP-only abstraction
- prefer stdout-based capture where supported by the installed Bicep CLI version
- otherwise read generated outputs from the temporary workspace and normalize them before returning to the orchestrator

### 3. AVM catalog lookup model

AVM lookup should be treated as a catalog problem, not a per-resource online query problem.

Operational requirements:
- avoid individual network lookups per resource type during fragment processing
- load a comprehensive AVM index once per process, or read from a locally shipped manifest
- perform resource-type matching from an in-memory dictionary or similarly efficient local structure
- refresh catalog data only on a controlled TTL, version, or startup policy

Implementation guidance:
- the AVM client should expose fast local lookup semantics even if its backing data originally came from a remote Microsoft source
- the conversion loop should not block on repeated remote catalog requests for each resource type discovered in Bicep text

### 4. Composition payload contract

The .NET composition sidecar remains the main custom value-add of the pipeline and requires a strict fragment contract.

Each fragment sent to composition must include:
- `batch_index`
- raw `bicep_text`
- the full list of `source_resource_ids` represented by that fragment
- any future metadata required for diagnostics or rename tracking

Operational requirements:
- preserve source resource identity across export, decompile, sanitization, annotation, and composition stages
- do not reduce source identity to a single resource ID when a fragment contains multiple resources
- use a typed request contract rather than an unstructured dictionary payload when finalizing the sidecar API

Rationale:
- symbolic-name mapping and cross-batch reference rewriting depend on preserving the source Azure resource ID context for every fragment

### 5. Fallback behavior

If AST composition is unavailable or fails during composition, fallback must activate immediately and still produce a package artifact.

Operational requirements:
- fallback output must be clearly labeled as low-fidelity
- fallback activation must be recorded in summary diagnostics
- fallback artifacts must remain reviewable and safe to inspect manually
- fallback must not silently pretend to be AST-composed output

Current fallback expectation:
- package output may remain modular, including `main.bicep` plus fragment-backed module files under `modules/`

Important note:
- fallback composition is not AST-safe and may require manual repair of references, names, parameters, or outputs before deployment
- a monolithic single-file fallback should be considered only if testing proves it is more reliable than the current module-per-fragment fallback

### 6. Collision handling and rename safety

Deduplication must distinguish exact duplicates from semantic collisions.

Examples of collisions:
- same parameter name with different default values
- same variable name with different expressions
- same symbolic resource name reused across batches
- same output name with different meanings
- generated module identifiers that would collide in the final package

Operational requirements:
- exact-match duplicates may be deduplicated
- same-name, different-value or different-expression declarations must be renamed deterministically
- dependent references must be rewritten to the renamed symbol
- rename operations should be recorded in diagnostics, stats, or both

Example:
- if one batch defines `param location string = 'eastus'`
- and another defines `param location string = 'westus'`
- the sidecar must not emit both declarations unchanged into the composed package
- it should rename deterministically, for example `location_batch2`, and rewrite all corresponding references

## 5-day compressed implementation plan

### Day 1 — structure, contracts, stubs

Goals:
- create the final folder structure
- define Python request and result schemas
- define .NET compose contracts
- stub integration clients
- lock package artifact format and SSE event shape

Primary files:
- `backend/src/agent_86/domain/schemas/azure_bicep_conversion.py`
- `backend/src/agent_86/services/azure_bicep_conversion/models.py`
- `backend/src/agent_86/integrations/azure/resource_export_client.py`
- `backend/src/agent_86/integrations/bicep/bicep_tool_client.py`
- `backend/src/agent_86/integrations/avm/avm_catalog_client.py`
- `backend/src/agent_86/integrations/bicep_composition/composition_api_client.py`
- `tooling/bicep-composition-service/src/BicepComposition.Api/Contracts/ComposeRequest.cs`
- `tooling/bicep-composition-service/src/BicepComposition.Api/Contracts/ComposeFragment.cs`
- `tooling/bicep-composition-service/src/BicepComposition.Api/Contracts/ComposeResponse.cs`
- `tooling/bicep-composition-service/src/BicepComposition.Api/Contracts/CompositionStats.cs`

Outcome:
- architecture and transport contracts are locked
- implementation can proceed without later structural rework

### Day 2 — Python helper modules + tests

Goals:
- implement deterministic helpers first
- land low-risk, high-testability modules

Implement:
- preflight
- secret sanitization
- AVM annotation policy
- fallback generation
- package builder

Primary files:
- `backend/src/agent_86/services/azure_bicep_conversion/preflight.py`
- `backend/src/agent_86/services/azure_bicep_conversion/secret_sanitizer.py`
- `backend/src/agent_86/services/azure_bicep_conversion/avm_annotation.py`
- `backend/src/agent_86/services/azure_bicep_conversion/fallback.py`
- `backend/src/agent_86/services/azure_bicep_conversion/package_builder.py`
- tests under `backend/src/tests/azure_bicep_conversion/`

Outcome:
- deterministic building blocks exist and are unit-tested

### Day 3 — Azure export pipeline + .NET service shell

Goals:
- implement export batching logic in Python
- stand up the .NET service shell and transport endpoints

Implement:
- Resource Group resource count lookup
- wildcard export path for `<= 200`
- resource-id-list export path for `> 200`
- .NET solution and project files
- `.NET` `/health`
- `.NET` `/compose`
- request and response plumbing

Primary files:
- `backend/src/agent_86/services/azure_bicep_conversion/export_pipeline.py`
- `tooling/bicep-composition-service/BicepComposition.sln`
- `tooling/bicep-composition-service/src/BicepComposition.Api/BicepComposition.Api.csproj`
- `tooling/bicep-composition-service/src/BicepComposition.Core/BicepComposition.Core.csproj`
- `tooling/bicep-composition-service/src/BicepComposition.Tests/BicepComposition.Tests.csproj`
- `tooling/bicep-composition-service/src/BicepComposition.Api/Program.cs`
- `tooling/bicep-composition-service/src/BicepComposition.Api/Endpoints/HealthEndpoints.cs`
- `tooling/bicep-composition-service/src/BicepComposition.Api/Endpoints/CompositionEndpoints.cs`
- `tooling/bicep-composition-service/src/BicepComposition.Api/DependencyInjection/ServiceCollectionExtensions.cs`
- `tooling/bicep-composition-service/src/BicepComposition.Core/Composition/BicepComposer.cs`

Outcome:
- backend export logic works
- sidecar is bootable and callable

### Day 4 — composition core + orchestrator

Goals:
- implement real AST-backed composition behavior
- connect all stages in the Python orchestrator

Implement:
- parse fragments
- symbolic mapping
- domain partitioning
- intra-Resource Group reference rewriting
- exact-match dedupe
- unresolved reference reporting
- Python orchestrator end-to-end flow

Primary files:
- `tooling/bicep-composition-service/src/BicepComposition.Core/Composition/BicepComposer.cs`
- `tooling/bicep-composition-service/src/BicepComposition.Core/Composition/ReferenceRewriter.cs`
- `tooling/bicep-composition-service/src/BicepComposition.Core/Composition/DomainPartitioner.cs`
- `tooling/bicep-composition-service/src/BicepComposition.Core/Composition/SymbolicNameMapper.cs`
- `tooling/bicep-composition-service/src/BicepComposition.Core/Composition/DeduplicationEngine.cs`
- `tooling/bicep-composition-service/src/BicepComposition.Core/Models/ComposedBicepFile.cs`
- `tooling/bicep-composition-service/src/BicepComposition.Core/Models/CompositionResult.cs`
- `tooling/bicep-composition-service/src/BicepComposition.Core/Diagnostics/CompositionWarning.cs`
- `backend/src/agent_86/services/azure_bicep_conversion/orchestrator.py`

Outcome:
- the high-fidelity pipeline exists in code

### Day 5 — route, SSE, diagnostics, polish

Goals:
- expose the feature through FastAPI
- finish diagnostics handling
- validate the end-to-end path with tests

Implement:
- FastAPI SSE route
- dependency wiring
- formatting and diagnostics pass
- artifact creation flow
- final tests and supporting docs

Primary files:
- `backend/src/agent_86/api/routes/azure_bicep_conversion.py`
- updates to `backend/src/agent_86/api/dependencies.py`
- `backend/src/agent_86/services/azure_bicep_conversion/diagnostics.py`
- route and orchestrator tests
- sidecar tests

Outcome:
- complete v1 feature path is available through the API

## Recommended minimum clean-start file set

If implementation needs to begin with the smallest clean structure, create these first.

Python:
1. `backend/src/agent_86/domain/schemas/azure_bicep_conversion.py`
2. `backend/src/agent_86/integrations/azure/resource_export_client.py`
3. `backend/src/agent_86/integrations/bicep/bicep_tool_client.py`
4. `backend/src/agent_86/integrations/avm/avm_catalog_client.py`
5. `backend/src/agent_86/integrations/bicep_composition/composition_api_client.py`
6. `backend/src/agent_86/services/azure_bicep_conversion/models.py`
7. `backend/src/agent_86/services/azure_bicep_conversion/orchestrator.py`
8. `backend/src/agent_86/services/azure_bicep_conversion/preflight.py`
9. `backend/src/agent_86/services/azure_bicep_conversion/export_pipeline.py`
10. `backend/src/agent_86/services/azure_bicep_conversion/secret_sanitizer.py`
11. `backend/src/agent_86/services/azure_bicep_conversion/package_builder.py`
12. `backend/src/agent_86/api/routes/azure_bicep_conversion.py`

.NET:
13. `tooling/bicep-composition-service/src/BicepComposition.Api/Program.cs`
14. `tooling/bicep-composition-service/src/BicepComposition.Api/Contracts/ComposeRequest.cs`
15. `tooling/bicep-composition-service/src/BicepComposition.Api/Contracts/ComposeResponse.cs`
16. `tooling/bicep-composition-service/src/BicepComposition.Core/Composition/BicepComposer.cs`

## Guardrails to avoid future refactors

Do not start by putting implementation logic in:
- the FastAPI route file
- `api/dependencies.py`
- unrelated top-level `services/*.py` files
- `.NET` endpoint handlers or `Program.cs`

Keep these boundaries strict:
- API contracts in schema or contract files
- external systems in integration clients
- feature logic in `services/azure_bicep_conversion/`
- AST-sensitive composition logic in `.NET BicepComposition.Core`

## Gated execution plan

This section expands the compressed implementation schedule into a gated execution model. Each day/part is a checkpoint. Act-mode implementation should complete only the scoped work for that stage, validate the resulting artifacts and outcomes, and stop if the gate does not pass.

### Operating rule

For each stage:

1. implement only that stage's scoped work
2. run the targeted validation for that stage
3. inspect the changed artifacts, contracts, or outputs
4. confirm the expected outcome was achieved
5. proceed only if the gate passes

If a gate fails:
- stop implementation for subsequent stages
- fix the failing stage
- re-run validation before continuing

---

### Stage 0 — Baseline lock and acceptance criteria

**Goal**
- freeze the final implementation boundaries, naming, and validation expectations before deeper implementation begins

**Scope**
- confirm approved adapter names
- confirm pipeline ownership boundaries
- confirm fallback semantics
- confirm stage-level validation commands and expected outcomes

**Implementation**
- retain the approved boundary names:
  - `ResourceExportClient`
  - `BicepToolClient`
  - `AvmCatalogClient`
  - `CompositionApiClient`
- confirm the documented responsibility split remains authoritative
- confirm fallback remains explicitly low-fidelity
- confirm composition input must preserve full `source_resource_ids`
- confirm Azure export remains a direct Azure SDK / ARM adapter with retry, throttling, and LRO handling

**Validation**
- verify docs and code use the same boundary names
- verify the current Azure Bicep conversion tests still collect and run cleanly
- verify there are no contradictory references to MCP-specific names in the feature path

**Expected outcome**
- docs, code, and tests reflect a single agreed design baseline

**Gate**
- do not proceed until naming, ownership, fallback behavior, and validation targets are stable

---

### Stage 1 — Typed Python contracts and composition request shape

**Goal**
- replace loose payload assembly with explicit typed contracts for composition and pipeline handoff

**Scope**
- typed request/response models on the Python side
- typed composition fragment shape
- explicit preservation of `source_resource_ids`

**Implementation**
- define or refine typed models for conversion fragments and composition requests
- replace ad hoc fragment dictionaries with typed request structures before serialization
- ensure each composition fragment includes:
  - `batch_index`
  - `bicep_text`
  - `source_resource_ids`
  - optional metadata only if required
- update orchestrator usage to assemble typed composition input

**Validation**
- add or update tests to verify composition requests preserve full fragment identity
- verify `source_resource_ids` survive export → decompile → sanitize → annotate → compose input
- run targeted orchestrator and model tests

**Expected outcome**
- composition request assembly is typed and explicit, not dependent on unstructured dictionaries

**Gate**
- do not proceed until the Python-side composition contract is stable and covered by tests

---

### Stage 2 — Azure export adapter implementation

**Goal**
- implement the real Azure export adapter with resilient export behavior

**Scope**
- wildcard export
- explicit resource-ID export
- retry and backoff
- throttling handling
- long-running operation polling
- timeout/failure classification

**Implementation**
- implement `ResourceExportClient`
- support:
  - resource count lookup
  - wildcard resource group export
  - resource-ID-list export
- handle:
  - `429 Too Many Requests`
  - transient `5xx`
  - retryable transport failures
  - export polling and timeout behavior
- preserve fragment `source_resource_ids` correctly for downstream composition

**Validation**
- run export pipeline tests
- add adapter-focused tests for retry, timeout, and batching behavior
- verify successful exports produce the expected fragment structure
- verify retry exhaustion and timeout failures are surfaced as diagnostics-ready failures

**Expected outcome**
- export behavior is production-shaped and no longer just a stub boundary

**Gate**
- do not proceed until wildcard and batched export paths are implemented, tested, and preserve source identity

---

### Stage 3 — Bicep tool client implementation

**Goal**
- implement direct Bicep tooling execution using isolated temporary workspaces

**Scope**
- decompile
- format
- diagnostics
- stdout/stderr capture
- temp workspace cleanup

**Implementation**
- implement `BicepToolClient`
- execute official Bicep tooling in per-invocation temporary workspaces
- avoid writing tool scratch files into application source paths
- normalize diagnostics into the existing Python model
- surface tool failure details cleanly for orchestration and diagnostics

**Validation**
- add tests for command construction, workspace handling, and diagnostics parsing
- verify cleanup of temporary artifacts
- run orchestrator tests against the real client contract
- validate actual CLI behavior before depending on specific stdout conventions

**Expected outcome**
- Bicep operations are direct-tool based, isolated, and diagnosable

**Gate**
- do not proceed until decompile/format/diagnostics behavior is implemented, stable, and validated

---

### Stage 4 — AVM catalog client implementation

**Goal**
- implement AVM lookup as a catalog-backed adapter rather than repeated per-resource online queries

**Scope**
- catalog loading
- in-memory matching
- optional refresh behavior
- normalized module match results

**Implementation**
- implement `AvmCatalogClient`
- load a canonical AVM catalog or manifest
- build a resource-type-to-module lookup structure
- use cached/in-memory matching during conversion
- keep refresh behavior controlled by TTL or explicit version boundary if needed

**Validation**
- add tests for catalog load, lookup behavior, and repeated-request efficiency
- verify annotation logic still applies only approved recommendations
- verify the orchestrator does not depend on repeated network calls per resource type

**Expected outcome**
- AVM annotation behavior is fast, stable, and consistent with the catalog model

**Gate**
- do not proceed until AVM lookup is cache/catalog based and validated under repeated use

---

### Stage 5 — Composition sidecar contract and merge behavior

**Goal**
- finalize the Python/.NET composition boundary and validate merge behavior, rename safety, and unresolved reference reporting

**Scope**
- typed sidecar request/response contract
- fragment identity preservation
- deterministic collision handling
- unresolved reference reporting
- generated package file output

**Implementation**
- update `CompositionApiClient` to use typed request serialization
- finalize sidecar contracts for:
  - compose request
  - compose fragment
  - compose response
  - composition stats
- ensure composition requests preserve:
  - `batch_index`
  - `bicep_text`
  - full `source_resource_ids`
- implement or validate sidecar behavior for:
  - symbolic mapping
  - cross-batch reference rewriting
  - exact-match deduplication
  - deterministic rename of semantic collisions
  - rename-aware reference rewriting
  - unresolved reference reporting
  - generated `main.bicep` plus composed modules

**Validation**
- add tests for semantic collision handling, rename determinism, and unresolved references
- validate typed request/response handling across the Python/.NET boundary
- verify stats and warnings are preserved into conversion summaries

**Expected outcome**
- AST composition behavior is contractually stable and safely handles merge/collision scenarios

**Gate**
- do not proceed until the typed sidecar contract and merge behavior are validated end-to-end

---

### Stage 6 — Fallback, artifact, and route-level integration

**Goal**
- validate the full user-visible conversion path including failure handling and packaged output

**Scope**
- fallback behavior
- artifact package assembly
- route/API behavior
- summary diagnostics
- end-to-end validation

**Implementation**
- keep fallback activation immediate when composition is unavailable or fails
- ensure fallback is clearly labeled as low-fidelity
- verify artifact output remains reviewable and safe to inspect manually
- validate route wiring and dependency usage for conversion entry points
- ensure summaries include:
  - merge mode
  - fallback usage
  - unresolved reference count
  - secure parameter count
  - AVM annotation count
  - diagnostics
  - generated files

**Validation**
- run full Azure Bicep conversion test coverage
- add or run route-level tests
- inspect generated package contents
- verify fallback output is distinguishable from AST-composed output
- verify diagnostics clearly explain failure and fallback conditions

**Expected outcome**
- the feature behaves correctly at the route and artifact level, not just in isolated components

**Gate**
- do not consider the feature complete until route behavior, artifact output, and fallback diagnostics all validate cleanly

---

## Recommended day-by-day sequence

### Day 1
**Part 1**
- Stage 0 — baseline lock and acceptance criteria

**Part 2**
- Stage 1 — typed Python contracts and composition request shape

**Proceed only if**
- the design baseline is stable
- typed composition request behavior is covered by tests

---

### Day 2
**Part 1**
- Stage 2 — Azure export adapter implementation

**Part 2**
- Stage 2 validation and error-path coverage

**Proceed only if**
- wildcard and batched export paths are implemented
- retry, throttling, and timeout behavior are validated
- source identity is preserved

---

### Day 3
**Part 1**
- Stage 3 — Bicep tool client implementation

**Part 2**
- Stage 3 validation against the orchestrator path

**Proceed only if**
- decompile/format/diagnostics work through the direct tool client
- temporary workspace behavior is validated

---

### Day 4
**Part 1**
- Stage 4 — AVM catalog client implementation

**Part 2**
- Stage 4 validation and repeated-lookup behavior

**Proceed only if**
- AVM lookup is catalog-backed
- repeated lookups are efficient and stable
- annotation behavior remains correct

---

### Day 5
**Part 1**
- Stage 5 — composition sidecar contract and typed boundary validation

**Part 2**
- Stage 5 merge/collision handling validation

**Proceed only if**
- typed sidecar contracts are stable
- collision handling and unresolved reference behavior are validated

---

### Day 6
**Part 1**
- Stage 6 — fallback, artifact, and route-level integration

**Part 2**
- full-system validation and documentation reconciliation

**Complete only if**
- route behavior, package output, fallback labeling, and conversion summaries all validate cleanly

---

## Gate review template

Use this template at the end of each stage during implementation:

### Stage gate review

**Scope completed**
- ...

**Files changed**
- ...

**Validation run**
- command:
  - `...`
- result:
  - passed / failed

**Artifact/output checked**
- ...

**Expected outcome achieved**
- yes / no

**Gate decision**
- PASS: proceed to next stage
- FAIL: stop and resolve before continuing