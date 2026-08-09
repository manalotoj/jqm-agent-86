from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ExportBatch:
    batch_index: int
    resource_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExportFragment:
    batch_index: int
    export_mode: Literal["wildcard", "resource_id_list"]
    source_resource_ids: list[str]
    template_json: dict[str, Any]


@dataclass(frozen=True)
class DecompiledFragment:
    batch_index: int
    source_resource_ids: list[str]
    bicep_text: str


@dataclass(frozen=True)
class SanitizedFragment:
    batch_index: int
    source_resource_ids: list[str]
    bicep_text: str
    secure_parameter_count: int = 0


@dataclass(frozen=True)
class GeneratedFile:
    path: str
    content: str


@dataclass(frozen=True)
class ConversionSummary:
    subscription_id: str
    resource_group_name: str
    azure_environment: Literal["AzureCloud", "AzureUSGovernment"]
    resource_count: int
    export_mode: Literal["wildcard", "resource_id_list"]
    batch_count: int
    merge_mode: Literal["ast", "low_fidelity_text_fallback"]
    fallback_used: bool
    unresolved_reference_count: int = 0
    secure_parameter_count: int = 0
    avm_annotation_count: int = 0
    diagnostics: list[str] = field(default_factory=list)
    generated_files: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ConversionArtifactPayload:
    filename: str
    content_type: str
    content: bytes
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConversionResult:
    artifact: ConversionArtifactPayload
    summary: ConversionSummary