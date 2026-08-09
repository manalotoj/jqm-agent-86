from typing import Any, Literal

from pydantic import BaseModel, Field


class ConvertResourceGroupToBicepRequest(BaseModel):
    subscription_id: str = Field(min_length=1)
    resource_group_name: str = Field(min_length=1)
    azure_environment: Literal["AzureCloud", "AzureUSGovernment"]
    gov_approved_avm_modules: list[str] = Field(default_factory=list)
    generated_by_message_id: str | None = Field(default=None, min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BicepConversionArtifactDescriptor(BaseModel):
    artifact_id: str
    filename: str
    content_type: str
    size_bytes: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BicepConversionSummaryResponse(BaseModel):
    subscription_id: str
    resource_group_name: str
    azure_environment: Literal["AzureCloud", "AzureUSGovernment"]
    resource_count: int = Field(ge=0)
    export_mode: Literal["wildcard", "resource_id_list"]
    batch_count: int = Field(ge=0)
    merge_mode: Literal["ast", "low_fidelity_text_fallback"]
    fallback_used: bool = False
    unresolved_reference_count: int = Field(default=0, ge=0)
    secure_parameter_count: int = Field(default=0, ge=0)
    avm_annotation_count: int = Field(default=0, ge=0)
    diagnostics: list[str] = Field(default_factory=list)
    generated_files: list[str] = Field(default_factory=list)


class BicepConversionCompleteEvent(BaseModel):
    artifact: BicepConversionArtifactDescriptor
    summary: BicepConversionSummaryResponse