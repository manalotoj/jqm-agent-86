# Azure Bicep Conversion Manual Testing

This guide explains how to manually validate the Azure Bicep conversion feature as an end user using API calls and Postman.

It is intended to validate the full user-visible behavior covered by Stages 1-6:

- session-scoped conversion invocation
- SSE conversion progress and completion events
- persisted generated artifact output
- conversion summary fields and diagnostics
- fallback labeling when AST composition is unavailable or fails

## Prerequisites

Before testing, make sure you have:

1. a running backend instance
2. a valid bearer token for the API
3. a real Azure subscription and resource group that the backend can export from
4. Postman installed
5. backend configuration set up for auth, storage, and Azure access

## Important note about Postman auth

This repository already documents that Postman's OAuth automation can be unreliable in this environment.

For manual testing, prefer supplying a pre-acquired bearer token directly in the `Authorization` header:

```text
Authorization: Bearer <access_token>
```

If Postman's built-in OAuth helper is flaky, use manual token acquisition outside the collection and then paste the resulting token into the Postman environment.

## Postman environment variables

Create a Postman environment with the following variables:

- `baseUrl` — for example `http://localhost:8000`
- `token` — bearer token value only, without the `Bearer ` prefix
- `subscriptionId` — Azure subscription ID to test
- `resourceGroupName` — Azure resource group name to test
- `azureEnvironment` — `AzureCloud` or `AzureUSGovernment`
- `sessionId` — blank at first; set automatically after session creation
- `artifactId` — blank at first; set automatically after artifact listing
- `label` — optional descriptive label such as `manual-postman-test`

## Manual test flow

Run the requests in this order:

1. create a session
2. run the conversion stream
3. list session artifacts
4. get artifact metadata
5. download the artifact zip

Optional negative tests:

6. missing session
7. invalid request body
8. missing authorization header

---

## 1. Create a session

### Request

- method: `POST`
- URL: `{{baseUrl}}/sessions`

### Headers

- `Authorization: Bearer {{token}}`
- `Content-Type: application/json`

### Body

```json
{
  "title": "Azure Bicep Conversion Manual Test",
  "metadata": {
    "source": "postman",
    "feature": "azure-bicep-conversion"
  }
}
```

### Expected result

- HTTP `201 Created`
- response includes a non-empty `id`
- save that value as `sessionId`

### Pass criteria

- session creation succeeds
- `sessionId` is captured for later requests

---

## 2. Run the conversion stream

### Request

- method: `POST`
- URL: `{{baseUrl}}/sessions/{{sessionId}}/azure-bicep-conversion/stream`

### Headers

- `Authorization: Bearer {{token}}`
- `Accept: text/event-stream`
- `Content-Type: application/json`

### Body

```json
{
  "subscription_id": "{{subscriptionId}}",
  "resource_group_name": "{{resourceGroupName}}",
  "azure_environment": "{{azureEnvironment}}",
  "gov_approved_avm_modules": [],
  "metadata": {
    "label": "{{label}}",
    "source": "postman"
  }
}
```

### Expected SSE event order

The stream should emit named SSE events in this order:

1. `start`
2. `complete` or `error`
3. `done`

### Expected success shape

If conversion succeeds, the `complete` event should include:

- `artifact`
  - `artifact_id`
  - `filename`
  - `content_type`
  - `size_bytes`
  - `metadata`
- `summary`
  - `subscription_id`
  - `resource_group_name`
  - `azure_environment`
  - `resource_count`
  - `export_mode`
  - `batch_count`
  - `merge_mode`
  - `fallback_used`
  - `unresolved_reference_count`
  - `secure_parameter_count`
  - `avm_annotation_count`
  - `diagnostics`
  - `generated_files`

### Success pass criteria

- `start` is emitted
- `complete` is emitted
- `done` is emitted
- `artifact.filename` ends with `.zip`
- `artifact.metadata.conversion_kind` equals `azure_export_to_bicep`
- `summary.generated_files` is non-empty
- `summary.merge_mode` is either:
  - `ast`, or
  - `low_fidelity_text_fallback`

### Fallback-specific pass criteria

If fallback is used, confirm all of the following:

- `summary.merge_mode == "low_fidelity_text_fallback"`
- `summary.fallback_used == true`
- `summary.diagnostics` clearly explains why fallback was used
- `summary.generated_files` still contains reviewable Bicep output

### Postman note

Postman can send the request, but SSE inspection may still be more manual than standard JSON APIs.

If the stream view is awkward in Postman, use the same endpoint with `curl -N` for raw SSE inspection while keeping the rest of the flow in Postman.

---

## 3. List session artifacts

### Request

- method: `GET`
- URL: `{{baseUrl}}/sessions/{{sessionId}}/artifacts`

### Headers

- `Authorization: Bearer {{token}}`

### Expected result

- HTTP `200 OK`
- response is an array
- array contains at least one generated zip artifact for the conversion

### What to verify

Look for an artifact where:

- `filename` ends with `.zip`
- `content_type == "application/zip"`
- `metadata.conversion_kind == "azure_export_to_bicep"`

Save that artifact's `id` as `artifactId`.

---

## 4. Get artifact metadata

### Request

- method: `GET`
- URL: `{{baseUrl}}/sessions/{{sessionId}}/artifacts/{{artifactId}}`

### Headers

- `Authorization: Bearer {{token}}`

### Expected result

- HTTP `200 OK`
- response includes artifact metadata for the generated zip

### What to verify

- `filename` ends with `.zip`
- `content_type == "application/zip"`
- `metadata.conversion_kind == "azure_export_to_bicep"`

---

## 5. Download the artifact zip

### Request

- method: `GET`
- URL: `{{baseUrl}}/sessions/{{sessionId}}/artifacts/{{artifactId}}/download`

### Headers

- `Authorization: Bearer {{token}}`

### Expected result

- HTTP `200 OK`
- response body is binary zip content
- response includes `Content-Disposition` with the generated filename

### What to verify manually

After saving and opening the zip:

- the archive opens successfully
- it contains `main.bicep`
- it may also contain one or more files under `modules/`
- the actual file list matches `summary.generated_files` from the conversion stream

This is one of the strongest end-to-end validations because it proves that the generated artifact is both persisted and reviewable.

---

## Optional negative tests

### 6. Missing session

Call the conversion stream using a session ID that does not exist.

Expected result:

- HTTP `404 Not Found`
- response body detail similar to:

```json
{
  "detail": "Session 'missing-session' not found"
}
```

### 7. Invalid request body

Use an invalid request such as:

```json
{
  "subscription_id": "",
  "resource_group_name": "",
  "azure_environment": "NotAzure"
}
```

Expected result:

- HTTP `422 Unprocessable Entity`

### 8. Missing auth

Send the request without the `Authorization` header.

Expected result:

- auth failure, typically HTTP `401 Unauthorized`

---

## End-user acceptance checklist

Treat the feature as manually validated if all of the following are true:

- session creation works
- the conversion stream emits `start -> complete -> done`
- the complete event contains both `artifact` and `summary`
- the summary clearly reports `merge_mode`
- the summary clearly reports `fallback_used`
- diagnostics are understandable
- a zip artifact is persisted to the session
- the artifact can be downloaded successfully
- the zip contents are reviewable and match `generated_files`
- fallback output, when used, is clearly distinguishable from AST-composed output

## Related files

- API overview: `/Users/johnmanaloto/source/github/jqm-agent-86/docs/azure-bicep-conversion-api.md`
- Postman collection: `/Users/johnmanaloto/source/github/jqm-agent-86/docs/postman/azure-bicep-conversion.postman_collection.json`
- Postman environment template: `/Users/johnmanaloto/source/github/jqm-agent-86/docs/postman/azure-bicep-conversion.local.postman_environment.json`