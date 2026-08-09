# Azure Bicep Conversion — Gated Execution Tracker

## Stage 0 — Baseline lock
**Goal**
- freeze names, ownership boundaries, fallback semantics, and validation commands

**Do**
- confirm canonical names
- confirm docs/code alignment
- confirm fallback is explicitly low-fidelity
- confirm composition must preserve full `source_resource_ids`

**Validate**
- search for stale names
- run current azure_bicep_conversion tests
- confirm docs and code tell the same story

**Gate**
- pass only if naming, ownership, and validation baseline are stable

---

## Stage 1 — Typed Python contracts
**Goal**
- make composition payloads typed and explicit

**Do**
- add/refine typed fragment/request models
- remove ad hoc dict assembly where possible
- preserve `batch_index`, `bicep_text`, `source_resource_ids`

**Validate**
- run orchestrator/model tests
- verify composition request shape
- verify source identity preservation

**Gate**
- pass only if typed request assembly is stable and tested

---

## Stage 2 — Azure export adapter
**Goal**
- implement real export behavior

**Do**
- implement resource count lookup
- implement wildcard export
- implement resource-ID-list export
- add retry/backoff/throttling/LRO handling

**Validate**
- run export pipeline tests
- run adapter tests for retry/timeout/batching
- verify `source_resource_ids` propagation

**Gate**
- pass only if export paths are resilient and source identity is preserved

---

## Stage 3 — Bicep tool client
**Goal**
- implement direct Bicep tooling in temp workspaces

**Do**
- implement decompile
- implement format
- implement diagnostics
- capture stdout/stderr
- clean up temp artifacts

**Validate**
- run client tests
- run orchestrator tests
- verify temp workspace behavior and diagnostics parsing

**Gate**
- pass only if tool execution is isolated, real, and diagnosable

---

## Stage 4 — AVM catalog client
**Goal**
- implement cached catalog-backed AVM lookup

**Do**
- load manifest/catalog
- build in-memory resource-type lookup
- return normalized matches
- avoid repeated online lookups per resource type

**Validate**
- run AVM tests
- verify repeated lookups stay local/cached
- verify approved-module annotation behavior

**Gate**
- pass only if AVM lookups are catalog-based and stable

---

## Stage 5 — Composition sidecar
**Goal**
- finalize typed Python/.NET compose boundary and merge behavior

**Do**
- use typed request/response contract
- preserve full fragment identity
- validate dedupe vs collision handling
- validate deterministic renaming and rewrite
- validate unresolved reference reporting

**Validate**
- run Python composition client/orchestrator tests
- run sidecar contract tests
- verify warnings/stats flow into summary

**Gate**
- pass only if composition contract and merge behavior are validated end-to-end

**Current status**
- typed Python/.NET request and response contract is implemented and validated
- full fragment identity is preserved across the boundary, including `source_resource_ids`
- sidecar contract mapping and a real HTTP `/compose` test are passing
- warnings, stats, and unresolved reference flow are validated in tests
- the sidecar now uses `Azure.Bicep.Core` for real parser-backed lex/parse diagnostics on fragment input/output
- param/var declaration discovery and dedupe comparison now use parser/syntax-backed extraction, including multiline decorated declarations
- param/var semantic-collision rename handling and declaration-local reference rewriting now use syntax-backed/token-aware processing so identifiers inside strings/decorators are not rewritten accidentally
- Stage 5 merge behavior is validated end-to-end across sidecar unit tests, HTTP contract tests, and Python client/orchestrator tests

**Decision right now**
- COMPLETE

**Why complete now**
- the Stage 5 gate is about a stable typed boundary plus validated merge behavior, rename safety, unresolved reference reporting, and generated package output
- exact-match dedupe, deterministic rename semantics, rename-aware rewriting, unresolved references, warning/stat propagation, and generated files are now covered by sidecar and Python tests
- broader future migration toward fully syntax-driven composition beyond param/var handling can continue in Stage 6+ without blocking Stage 5 acceptance

**Evidence**
- Python composition client/orchestrator targeted tests are passing
- sidecar build/tests validate HTTP `/compose`, typed contracts, compiler-derived warning flow, exact-match dedupe, deterministic rename, rename-aware rewriting, and unresolved reference reporting
- `BicepComposition.Core` now references `Azure.Bicep.Core`, and `BicepComposer` performs compiler-backed parsing plus syntax-backed param/var declaration matching, dedupe, and declaration-local rename-aware rewriting

---

## Stage 6 — Fallback + artifact + route integration
**Goal**
- validate full user-visible conversion behavior

**Do**
- ensure fallback activates immediately on compose failure
- ensure fallback is labeled low-fidelity
- validate package artifact contents
- validate route integration and summary diagnostics

**Validate**
- run full azure_bicep_conversion suite
- run route tests
- inspect package output
- verify summary fields and fallback labeling

**Gate**
- pass only if route behavior, artifact output, and failure reporting are correct

**Current status**
- fallback activates immediately when the composition sidecar is unavailable or compose execution fails
- fallback output remains explicitly labeled low-fidelity in generated content, merge mode, and diagnostics
- package artifact contents and generated file lists are validated through package-builder, orchestrator, and route tests
- route-level SSE integration validates summary propagation for both AST-composed and fallback conversion results
- full Azure Bicep conversion plus route test coverage is passing

**Decision right now**
- COMPLETE

**Why complete now**
- the Stage 6 gate is about user-visible behavior, not only isolated internals
- fallback conditions now produce explicit diagnostics describing why fallback was used in addition to the low-fidelity warning
- route responses propagate merge mode, fallback usage, diagnostics, and generated files cleanly to clients
- artifact packaging remains reviewable and validated through generated zip contents and persisted route artifacts

**Evidence**
- `python3 -m pytest backend/src/tests/azure_bicep_conversion backend/src/tests/test_azure_bicep_conversion_route.py -q` ✅ (`42 passed`)
- orchestrator tests validate both sidecar-unhealthy and compose-failure immediate fallback behavior
- route tests validate SSE summary fields for normal AST composition and low-fidelity fallback output

---

## Gate review checklist

**Scope completed**
- ...

**Files changed**
- ...

**Validation run**
- ...

**Artifact/output checked**
- ...

**Expected outcome achieved**
- yes / no

**Decision**
- PASS / FAIL