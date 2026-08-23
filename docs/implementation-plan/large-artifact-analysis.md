# Large artifact analysis

## Purpose

This document defines the first scalable, cost-aware artifact-analysis capability for Agent 86. It is intentionally limited to CSV processing first. It enables an explicit exhaustive review of a user-uploaded CSV, such as an investment portfolio, without introducing Azure AI Search or a vector database.

## Decisions

- Keep original artifact binaries in the existing private `agent86-artifacts` Blob container.
- Store derived normalized content, chunk JSONL, and oversized analysis results in a separate private `agent86-artifact-derived` Blob container.
- Store only compact processing and analysis metadata in Cosmos DB. Do not store complete chunks, vectors, or full extracted content in Cosmos DB.
- Add `artifact-processing` and `artifact-analysis-jobs` Cosmos containers, both partitioned by `/session_id`.
- Preserve all existing artifact upload, download, list, generated-artifact, chat, and summary behavior.
- Do not add Azure AI Search in this phase. Normal attachment chat continues to use its current bounded context behavior.
- Whole-file analysis is explicit. It is never implied by attaching a file to an ordinary chat message.

## CSV completeness contract

`complete` has a precise meaning for CSV analysis:

1. The uploaded bytes are content-hashed and parsed as a CSV with a header row.
2. Each non-empty data row is assigned to one and only one chunk.
3. A persisted manifest records the total parsed rows, chunk count, rows per chunk, and derived Blob references.
4. The analysis can be reported as `complete` only when every expected row has a successful chunk result and there are no failed or excluded data rows.
5. Results identify the artifact and row ranges that support each aggregate result. If a parse or chunk fails, the result is `partial` or `failed`, never `complete`.

This contract does not claim that the raw file is injected into a single model prompt. For large portfolios, every row participates through a map/reduce workflow, avoiding model-context limits while retaining coverage evidence.

## Storage layout

The original Blob layout remains unchanged. Derived blobs use stable, session-scoped paths:

```
derived/{session_id}/{artifact_id}/{sha256}/normalized.jsonl
derived/{session_id}/{artifact_id}/{sha256}/chunks.jsonl
derived/{session_id}/{artifact_id}/{sha256}/analysis/{analysis_id}.json
```

`artifact-processing` stores the artifact identity, owner/session scope, source hash, detected CSV schema, row and chunk counts, processing state, error detail, and derived Blob names. `artifact-analysis-jobs` stores an explicit analysis request, its lifecycle, coverage counters, compact findings, and a Blob reference when findings exceed a safe Cosmos document size.

## Lifecycle

Processing states are `queued`, `processing`, `ready`, `unsupported`, and `failed`. Analysis states are `requested`, `running`, `completed`, `partial`, and `failed`.

The implementation is idempotent by source content hash. Reprocessing the same artifact version may reuse its derived data. Retries preserve completed chunk records and must not duplicate row coverage. A running analysis job carries a finite claim lease. Requests return a job while its lease is valid; after its lease expires, such as when its worker process died, a request conditionally reclaims it using the Cosmos ETag. Only the winner performs recovery work. Terminal jobs clear their lease.

## Cost and safety controls

- CSV-only exhaustive processing in the first release.
- Configurable upload-byte, CSV-row, chunk-size, and analysis-request limits.
- A user explicitly requests exhaustive analysis before model work occurs.
- Derived Blob data is private and subject to lifecycle retention policy; original uploads retain their current behavior.
- The API returns coverage and error disclosures for all processing and analysis states.
- Portfolio output is informational and must not be presented as financial advice.

## Rollout order

1. Provision Blob/Cosmos infrastructure only; verify existing application behavior remains unchanged.
2. Deploy backend APIs, processing implementation, unit tests, and Azure-targeted E2E tests.
3. Deploy frontend status and explicit whole-file-analysis controls after the backend deployment passes its regression suite.

## Testing requirements

Unit tests prove CSV parsing, stable chunk boundaries, hash determinism, state transitions, limits, and that first, middle, and final data rows are each covered exactly once. Azure E2E tests cover upload, processing, status reads, analysis coverage, ownership/session isolation, CORS preflight, and all existing artifact lifecycle/chat tests.