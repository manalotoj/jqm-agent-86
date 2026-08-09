# Azure Bicep Conversion API

Day 5 exposes the resource-group-to-Bicep conversion flow as a FastAPI SSE endpoint.

## Related manual testing assets

- Manual testing guide: `/Users/johnmanaloto/source/github/jqm-agent-86/docs/azure-bicep-conversion-manual-testing.md`
- Postman collection: `/Users/johnmanaloto/source/github/jqm-agent-86/docs/postman/azure-bicep-conversion.postman_collection.json`

## Endpoint

- `POST /sessions/{session_id}/azure-bicep-conversion/stream`
- Request body: `ConvertResourceGroupToBicepRequest`
- Response content type: `text/event-stream`

## Stream events

The endpoint emits named SSE events using the same wire format as the chat stream route.

### `start`

Sent when request validation and session validation succeed.

```text
event: start
data: {"session_id":"...","subscription_id":"...","resource_group_name":"...","azure_environment":"AzureCloud"}
```

### `complete`

Sent after the orchestrator finishes and the generated zip artifact has been persisted through `ArtifactService.create_generated_artifact`.

Payload shape matches `BicepConversionCompleteEvent`:

```json
{
  "artifact": {
    "artifact_id": "...",
    "filename": "rg-name-bicep-package.zip",
    "content_type": "application/zip",
    "size_bytes": 1234,
    "metadata": {
      "artifact_kind": "generated",
      "conversion_kind": "azure_export_to_bicep"
    }
  },
  "summary": {
    "subscription_id": "...",
    "resource_group_name": "...",
    "azure_environment": "AzureCloud",
    "resource_count": 0,
    "export_mode": "wildcard",
    "batch_count": 1,
    "merge_mode": "ast",
    "fallback_used": false,
    "unresolved_reference_count": 0,
    "secure_parameter_count": 0,
    "avm_annotation_count": 0,
    "diagnostics": [],
    "generated_files": ["main.bicep"]
  }
}
```

### `error`

Sent if conversion or artifact persistence fails after the stream has started.

```text
event: error
data: {"message":"..."}
```

### `done`

Always emitted as the terminal event.

```text
event: done
data: {}
```

## Diagnostics formatting

The formatting/diagnostics pass is completed in the orchestrator by:

1. formatting each sanitized/annotated Bicep fragment through `BicepToolClient.format_bicep`
2. retrieving diagnostics through `BicepToolClient.get_diagnostics`
3. normalizing those diagnostics via `services/azure_bicep_conversion/diagnostics.py`

Diagnostic strings are surfaced in the final `summary.diagnostics` array along with export-plan and composition/fallback warnings.