# Azure Bicep Conversion — Upstream Adoption Matrix

This document captures the recommended adoption strategy for the Azure resource-group-to-Bicep conversion feature.

Core principle:
- do not rebuild functionality Microsoft or Azure already provides
- do build the minimum repo-specific glue needed to turn upstream capabilities into this feature's conversion pipeline

---

## Executive recommendation

Use upstream where it already exists, but do not force everything through MCP just because some boundaries were originally named that way.

Best-fit approach by dependency:
- Azure export: thin wrapper around Azure upstream SDK/ARM APIs
- Bicep decompile/format/diagnostics: thin wrapper around official Bicep tooling
- AVM lookup: custom thin adapter still required
- composition/merge: custom implementation still required
- ARM MCP server: useful adjacent capability, but not the primary implementation for this conversion pipeline

---

## Adoption matrix

| Dependency area | Current repo boundary | Best approach | Why |
|---|---|---|---|
| Azure resource-group export | `ResourceExportClient` | **Thin wrapper around upstream** | The implementation plan explicitly says the Python backend owns Azure SDK export batching. The official ARM MCP server appears more query/deployment oriented than export-pipeline oriented. |
| Bicep decompile/format/diagnostics | `BicepToolClient` | **Thin wrapper around upstream** | Official Bicep tooling exists in `Azure/bicep`, but there is no confirmed official hostable Bicep MCP server artifact from the evidence reviewed. Reuse Bicep itself; do not reimplement compiler behavior. |
| AVM module lookup | `AvmCatalogClient` | **Custom thin adapter still required** | AVM is official, but no confirmed official Microsoft AVM MCP server was identified. Consume official AVM sources/catalogs, but likely implement a repo adapter. |
| Azure ARM MCP server | not directly modeled today | **Host as-is only if it covers a specific need** | The ARM MCP server is official and useful, but the visible tool surface appears focused on query/deploy flows, not the resource-group export batching contract this conversion flow needs. |
| Bicep composition sidecar | `CompositionApiClient` + `.NET` sidecar | **Custom implementation still required** | The implementation plan assigns AST-sensitive merge/dedup/rewrite/domain partitioning to the repo's own .NET sidecar. No upstream replacement was identified. |
| `microsoft/mcp` catalog | none | **Discovery source, not a runtime dependency by itself** | Good place to discover official Microsoft MCP servers; not itself the server to host for this feature. |

---

## 1. Azure export

### Recommendation

**Thin wrapper around upstream Azure SDK / ARM APIs**

### Why

The implementation plan explicitly says:
- Python backend owns Azure SDK export batching

The current pipeline expects specific operations:
- `get_resource_count(...)`
- `export_resource_group_wildcard(...)`
- `export_resource_group_by_resource_ids(...)`

The current `ExportPipeline` directly depends on those behaviors and includes batch planning based on:
- total resource count
- resource ID list batching

The official ARM MCP server appears to expose tools like:
- `execute_query`
- `generate_query`
- `validate_query`
- `create_template_deployment`
- `get_arm_template_deployment_status`
- `cancel_arm_template_deployment`

That is valuable, but it does not currently line up tightly with the repo's export pipeline contract.

### Verdict

- do not build raw ARM export logic from scratch
- do implement `ResourceExportClient` as a thin wrapper over Azure SDK/ARM export APIs
- do not replace this with ARM MCP unless the MCP server is confirmed to support the exact export-template flows required

---

## 2. Bicep decompile / format / diagnostics

### Recommendation

**Thin wrapper around official Bicep tooling**

### Why

`Azure/bicep` is clearly the official source for:
- the Bicep language
- compiler/tooling
- CLI/reference/tooling ecosystem

The orchestrator needs exactly:
- decompile ARM JSON to Bicep
- format Bicep
- retrieve diagnostics

Those are Bicep-tooling concerns, not business logic the repo should reimplement.

However, the evidence reviewed does not confirm that `Azure/bicep` is itself a ready-to-host MCP server repository or packaged MCP server artifact.

### Best practical interpretation

The preferred boundary name is `BicepToolClient`, because the implementation is likely to call:
- Bicep CLI directly, or
- a thin local bridge over official Bicep tooling

That still satisfies the core goal:
- reuse upstream
- do not rebuild compiler semantics

### Verdict

- do not rebuild decompile/format/diagnostics logic
- do consume official Bicep tooling
- likely implement as a thin wrapper unless a true official Bicep MCP server artifact is later confirmed

---

## 3. AVM lookup

### Recommendation

**Custom thin adapter still required**

### Why

AVM itself is official:
- official Microsoft initiative
- official module indexes/docs/catalogs

But there is no confirmed official Microsoft AVM MCP server from the evidence reviewed.

The orchestrator's need is modest:
- look up module recommendations by resource type
- return structured matches

That means the repo does not need to invent AVM module content, but it likely does need an adapter that:
- reads official AVM sources/indexes/catalog data
- normalizes matches into `AvmModuleMatch`

### Verdict

- use official AVM data sources
- implement the smallest possible repo adapter around them
- this is not rebuilding AVM; it is implementing the minimum lookup glue the feature needs

---

## 4. ARM MCP server

### Recommendation

**Host as-is only if it fits a clearly defined adjacent use case**

### Why

`Azure/Azure-Resource-Manager-MCP` appears to be an official Azure/Microsoft MCP server.

Based on the surfaced tool list, it appears optimized for:
- Azure Resource Graph querying
- template deployment operations
- validation/deployment management

The conversion path here needs:
- resource group resource counts
- export template retrieval
- possibly filtered export by resource IDs

That is not obviously the same thing.

### Verdict

- official: yes
- useful to this repo generally: yes
- direct replacement for `ResourceExportClient`: not yet proven

Use it where it directly fits, but do not center the conversion pipeline on it unless it is verified to expose the exact export behaviors needed.

---

## 5. `microsoft/mcp`

### Recommendation

**Use as a discovery/catalog source, not as the implementation itself**

### Why

`microsoft/mcp` is a catalog/monorepo of official Microsoft MCP servers.

That makes it valuable for adoption decisions:
- good for discovering existing official servers
- good for avoiding duplicate work

But it is not equivalent to:
- Azure export already solved
- Bicep server already solved
- AVM server already solved

### Verdict

- important reference source
- not the runtime answer by itself

---

## 6. Composition / merge sidecar

### Recommendation

**Custom implementation still required**

### Why

The implementation plan explicitly assigns to the .NET sidecar:
- parsing Bicep via `Bicep.Core`
- symbolic mapping
- intra-resource-group reference rewriting
- unresolved reference marking
- exact-match parameter and variable deduplication
- domain partitioning
- `main.bicep` generation

That is specialized composition behavior for this product.

No upstream Microsoft-hosted MCP server or sidecar was identified that clearly replaces that responsibility.

### Verdict

- custom implementation required
- this remains the main product-specific engineering work for the conversion pipeline

---

## Recommended final architecture

### Keep as custom boundaries
- `ResourceExportClient`
- `CompositionApiClient`

### Use these boundary names
- `BicepToolClient`
- `AvmCatalogClient`

Reason:
- if the real implementation does not actually use MCP transport, MCP-specific names become misleading

### Keep these behaviors repo-owned
- package assembly
- artifact persistence
- SSE streaming
- preflight/export batching decisions
- feature-specific diagnostics composition
- composition sidecar behavior

---

## Concrete adoption decisions by component

### Adopt/host as-is
- ARM MCP server only for scenarios where its published tools directly fit
- official Microsoft MCP servers discovered via `microsoft/mcp` when they match exact repo needs

### Thin wrapper around upstream
- Azure export via Azure SDK/ARM APIs
- Bicep decompile/format/diagnostics via official Bicep tooling

### Custom implementation still required
- AVM lookup adapter
- composition sidecar
- repo-specific dependency wiring, package generation, and SSE behavior

---

## Conclusion

The correct implementation stance for this feature is:
- do not rebuild Bicep
- do not invent Azure export semantics when Azure already provides them
- do not create a fake AVM ecosystem when official AVM catalogs already exist
- do build the minimum glue needed to turn upstream capabilities into the repo's conversion pipeline
- do build the custom composition layer, because that appears to be genuinely product-specific

---

## Operational notes

The adoption choices above carry several implementation guardrails:

- Azure export should remain a direct Azure SDK / ARM adapter and must handle throttling, retries, and long-running export polling.
- Bicep operations should prefer a direct process-driven tool client with isolated temporary workspaces rather than requiring MCP transport.
- AVM lookup should use a cached catalog or manifest rather than repeated per-resource-type network queries during conversion.
- Composition requests must preserve fragment `source_resource_ids` so the sidecar can perform symbolic-name mapping and cross-batch reference rewriting correctly.
- Fallback output must be explicitly labeled low-fidelity and must never be presented as AST-composed output.
- Deduplication must handle semantic name collisions through deterministic renaming plus reference rewriting.