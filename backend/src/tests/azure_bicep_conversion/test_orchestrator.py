from dataclasses import dataclass, field

import pytest

from agent_86.integrations.bicep_composition.composition_api_client import (
    CompositionFile,
    CompositionFragment,
    CompositionRequest,
    CompositionResult,
    CompositionStats,
)
from agent_86.integrations.azure.resource_export_client import ResourceExportTemplate
from agent_86.integrations.avm.avm_catalog_client import AvmModuleMatch
from agent_86.integrations.bicep.bicep_tool_client import BicepDiagnostic, BicepDiagnosticsResult
from agent_86.services.azure_bicep_conversion.export_pipeline import ExportPipeline
from agent_86.services.azure_bicep_conversion.orchestrator import AzureBicepConversionOrchestrator


@dataclass
class FakeResourceExportClient:
    resource_count: int
    wildcard_template: ResourceExportTemplate

    async def get_resource_count(self, *, subscription_id: str, resource_group_name: str) -> int:
        return self.resource_count

    async def export_resource_group_wildcard(self, *, subscription_id: str, resource_group_name: str) -> ResourceExportTemplate:
        return self.wildcard_template

    async def export_resource_group_by_resource_ids(
        self,
        *,
        subscription_id: str,
        resource_group_name: str,
        resource_ids: list[str],
    ) -> ResourceExportTemplate:
        raise AssertionError("batched export was not expected in this test")


@dataclass
class FakeBicepToolClient:
    diagnostics: list[BicepDiagnostic] = field(default_factory=list)

    async def ping(self) -> bool:
        return True

    async def decompile_arm_template(self, *, template_json: dict, logical_name: str) -> str:
        return template_json["bicep"]

    async def format_bicep(self, *, bicep_text: str, logical_name: str) -> str:
        return bicep_text.strip() + "\n"

    async def get_diagnostics(self, *, bicep_text: str, logical_name: str) -> BicepDiagnosticsResult:
        return BicepDiagnosticsResult(diagnostics=list(self.diagnostics))


@dataclass
class FakeAvmCatalogClient:
    matches_by_resource_type: dict[str, list[AvmModuleMatch]] = field(default_factory=dict)

    async def ping(self) -> bool:
        return True

    async def search_module(self, *, resource_type: str) -> list[AvmModuleMatch]:
        return list(self.matches_by_resource_type.get(resource_type, []))


@dataclass
class FakeCompositionApiClient:
    healthy: bool = True
    result: CompositionResult | None = None
    should_raise: bool = False
    requests: list[CompositionRequest] = field(default_factory=list)

    async def check_health(self) -> bool:
        return self.healthy

    async def compose(self, *, request: CompositionRequest) -> CompositionResult:
        self.requests.append(request)
        if self.should_raise:
            raise RuntimeError("composition failed")
        if self.result is None:
            raise AssertionError("composition result was not configured")
        return self.result


@pytest.mark.asyncio
async def test_orchestrator_returns_composed_package_when_sidecar_is_healthy() -> None:
    composition_api_client = FakeCompositionApiClient(
        healthy=True,
        result=CompositionResult(
            status="ok",
            merge_mode="ast",
            files=[
                CompositionFile(path="main.bicep", content="targetScope = 'resourceGroup'"),
                CompositionFile(path="modules/storage.bicep", content="resource stg 'Type@1' = {}"),
            ],
            stats=CompositionStats(
                fragment_count=1,
                deduplicated_params=0,
                deduplicated_vars=0,
                unresolved_reference_count=2,
            ),
            warnings=["composition warning"],
        ),
    )
    orchestrator = AzureBicepConversionOrchestrator(
        export_pipeline=ExportPipeline(
            FakeResourceExportClient(
                resource_count=1,
                wildcard_template=ResourceExportTemplate(
                    template_json={
                        "bicep": """
@secure()
param adminPassword string = 'SuperSecret!'
resource stg 'Microsoft.Storage/storageAccounts@2023-05-01' = {}
""".strip()
                    },
                    export_mode="wildcard",
                    source_resource_ids=["resource-1"],
                ),
            )
        ),
        bicep_tool_client=FakeBicepToolClient(
            diagnostics=[BicepDiagnostic(code="BCP001", level="warning", message="stub warning")]
        ),
        avm_catalog_client=FakeAvmCatalogClient(
            matches_by_resource_type={
                "Microsoft.Storage/storageAccounts": [
                    AvmModuleMatch(
                        module_path="avm/res/storage/storage-account",
                        resource_type="Microsoft.Storage/storageAccounts",
                    )
                ]
            }
        ),
        composition_api_client=composition_api_client,
    )

    result = await orchestrator.convert_resource_group(
        subscription_id="sub-1",
        resource_group_name="rg-1",
        azure_environment="AzureCloud",
        gov_approved_avm_modules=["avm/res/storage/storage-account"],
    )

    assert result.summary.merge_mode == "ast"
    assert result.summary.fallback_used is False
    assert result.summary.unresolved_reference_count == 2
    assert result.summary.secure_parameter_count == 1
    assert result.summary.avm_annotation_count == 1
    assert "WARNING BCP001: stub warning" in result.summary.diagnostics
    assert "composition warning" in result.summary.diagnostics
    assert result.summary.generated_files == ["main.bicep", "modules/storage.bicep"]
    assert result.artifact.filename == "rg-1-bicep-package.zip"
    assert result.artifact.metadata["conversion_kind"] == "azure_export_to_bicep"
    assert len(composition_api_client.requests) == 1
    composition_request = composition_api_client.requests[0]
    assert composition_request == CompositionRequest(
        subscription_id="sub-1",
        resource_group_name="rg-1",
        azure_environment="AzureCloud",
        fragments=composition_request.fragments,
    )
    assert len(composition_request.fragments) == 1
    fragment = composition_request.fragments[0]
    assert fragment.batch_index == 0
    assert fragment.source_resource_ids == ["resource-1"]
    assert fragment.metadata == {}
    assert "avm/res/storage/storage-account" in fragment.bicep_text
    assert "param adminPassword string" in fragment.bicep_text
    assert "SuperSecret!" not in fragment.bicep_text
    assert "Microsoft.Storage/storageAccounts" in fragment.bicep_text


@pytest.mark.asyncio
async def test_orchestrator_falls_back_when_sidecar_is_unhealthy() -> None:
    orchestrator = AzureBicepConversionOrchestrator(
        export_pipeline=ExportPipeline(
            FakeResourceExportClient(
                resource_count=1,
                wildcard_template=ResourceExportTemplate(
                    template_json={"bicep": "resource app 'Microsoft.Web/sites@2023-01-01' = {}"},
                    export_mode="wildcard",
                    source_resource_ids=["resource-1"],
                ),
            )
        ),
        bicep_tool_client=FakeBicepToolClient(),
        avm_catalog_client=FakeAvmCatalogClient(),
        composition_api_client=FakeCompositionApiClient(healthy=False),
    )

    result = await orchestrator.convert_resource_group(
        subscription_id="sub-1",
        resource_group_name="rg-fallback",
        azure_environment="AzureUSGovernment",
        gov_approved_avm_modules=[],
    )

    assert result.summary.merge_mode == "low_fidelity_text_fallback"
    assert result.summary.fallback_used is True
    assert result.summary.generated_files == ["main.bicep", "modules/fragment_000.bicep"]
    assert "Composition sidecar was unavailable; using fallback package instead." in result.summary.diagnostics
    assert "AST composition was unavailable; generated a low-fidelity text fallback package." in result.summary.diagnostics


@pytest.mark.asyncio
async def test_orchestrator_falls_back_immediately_when_compose_raises() -> None:
    orchestrator = AzureBicepConversionOrchestrator(
        export_pipeline=ExportPipeline(
            FakeResourceExportClient(
                resource_count=1,
                wildcard_template=ResourceExportTemplate(
                    template_json={"bicep": "resource app 'Microsoft.Web/sites@2023-01-01' = {}"},
                    export_mode="wildcard",
                    source_resource_ids=["resource-1"],
                ),
            )
        ),
        bicep_tool_client=FakeBicepToolClient(),
        avm_catalog_client=FakeAvmCatalogClient(),
        composition_api_client=FakeCompositionApiClient(healthy=True, should_raise=True),
    )

    result = await orchestrator.convert_resource_group(
        subscription_id="sub-1",
        resource_group_name="rg-compose-failure",
        azure_environment="AzureCloud",
        gov_approved_avm_modules=[],
    )

    assert result.summary.merge_mode == "low_fidelity_text_fallback"
    assert result.summary.fallback_used is True
    assert result.summary.generated_files == ["main.bicep", "modules/fragment_000.bicep"]
    assert (
        "Composition sidecar failed during compose; using fallback package instead: RuntimeError: composition failed"
        in result.summary.diagnostics
    )
    assert "AST composition was unavailable; generated a low-fidelity text fallback package." in result.summary.diagnostics


@pytest.mark.asyncio
async def test_orchestrator_preserves_full_fragment_identity_when_multiple_batches_are_composed() -> None:
    composition_api_client = FakeCompositionApiClient(
        healthy=True,
        result=CompositionResult(
            status="ok",
            merge_mode="ast",
            files=[
                CompositionFile(path="main.bicep", content="// composed"),
                CompositionFile(path="modules/fragment_000.bicep", content="resource first 'Type@1' = {}"),
                CompositionFile(path="modules/fragment_001.bicep", content="resource second 'Type@1' = {}"),
            ],
            stats=CompositionStats(fragment_count=2, deduplicated_params=1, deduplicated_vars=0, unresolved_reference_count=0),
            unresolved_references=[],
            warnings=["deterministic rename validated"],
        ),
    )

    orchestrator = AzureBicepConversionOrchestrator(
        export_pipeline=ExportPipeline(
            FakeResourceExportClient(
                resource_count=2,
                wildcard_template=ResourceExportTemplate(
                    template_json={
                        "bicep": (
                            "resource first 'Microsoft.Storage/storageAccounts@2023-01-01' = {}\n"
                            "resource second 'Microsoft.Web/sites@2023-01-01' = {}"
                        )
                    },
                    export_mode="wildcard",
                    source_resource_ids=["resource-1", "resource-2"],
                ),
            )
        ),
        bicep_tool_client=FakeBicepToolClient(),
        avm_catalog_client=FakeAvmCatalogClient(),
        composition_api_client=composition_api_client,
    )

    result = await orchestrator.convert_resource_group(
        subscription_id="sub-1",
        resource_group_name="rg-identity",
        azure_environment="AzureCloud",
        gov_approved_avm_modules=[],
    )

    assert result.summary.merge_mode == "ast"
    assert result.summary.generated_files == ["main.bicep", "modules/fragment_000.bicep", "modules/fragment_001.bicep"]
    assert "deterministic rename validated" in result.summary.diagnostics
    assert composition_api_client.requests == [
        CompositionRequest(
            subscription_id="sub-1",
            resource_group_name="rg-identity",
            azure_environment="AzureCloud",
            fragments=[
                CompositionFragment(
                    batch_index=0,
                    source_resource_ids=["resource-1", "resource-2"],
                    bicep_text="resource first 'Microsoft.Storage/storageAccounts@2023-01-01' = {}\nresource second 'Microsoft.Web/sites@2023-01-01' = {}\n",
                    metadata={},
                )
            ],
        )
    ]