import re

from agent_86.integrations.avm.avm_catalog_client import AvmCatalogClient
from agent_86.integrations.bicep.bicep_tool_client import BicepToolClient
from agent_86.integrations.bicep_composition.composition_api_client import (
    CompositionApiClient,
    CompositionFragment,
    CompositionRequest,
)
from agent_86.services.azure_bicep_conversion.avm_annotation import annotate_bicep_with_avm_recommendations
from agent_86.services.azure_bicep_conversion.diagnostics import format_bicep_diagnostics
from agent_86.services.azure_bicep_conversion.export_pipeline import ExportPipeline
from agent_86.services.azure_bicep_conversion.fallback import build_text_fallback_package
from agent_86.services.azure_bicep_conversion.models import (
    ConversionResult,
    ConversionSummary,
    DecompiledFragment,
    GeneratedFile,
    SanitizedFragment,
)
from agent_86.services.azure_bicep_conversion.package_builder import build_bicep_package_artifact
from agent_86.services.azure_bicep_conversion.secret_sanitizer import sanitize_bicep_secrets


_RESOURCE_TYPE_RE = re.compile(r"resource\s+\w+\s+'([^'@]+)@[^']+'", re.MULTILINE)


class AzureBicepConversionOrchestrator:
    def __init__(
        self,
        *,
        export_pipeline: ExportPipeline,
        bicep_tool_client: BicepToolClient,
        avm_catalog_client: AvmCatalogClient,
        composition_api_client: CompositionApiClient,
    ) -> None:
        self._export_pipeline = export_pipeline
        self._bicep_tool_client = bicep_tool_client
        self._avm_catalog_client = avm_catalog_client
        self._composition_api_client = composition_api_client

    async def convert_resource_group(
        self,
        *,
        subscription_id: str,
        resource_group_name: str,
        azure_environment: str,
        gov_approved_avm_modules: list[str],
        resource_ids: list[str] | None = None,
    ) -> ConversionResult:
        plan, export_fragments = await self._export_pipeline.export_resource_group(
            subscription_id=subscription_id,
            resource_group_name=resource_group_name,
            resource_ids=resource_ids,
        )

        diagnostics: list[str] = list(plan.warnings)
        secure_parameter_count = 0
        avm_annotation_count = 0

        sanitized_fragments: list[SanitizedFragment] = []
        for export_fragment in export_fragments:
            logical_name = f"{resource_group_name}-{export_fragment.batch_index:03d}"
            decompiled_bicep = await self._bicep_tool_client.decompile_arm_template(
                template_json=export_fragment.template_json,
                logical_name=logical_name,
            )
            decompiled_fragment = DecompiledFragment(
                batch_index=export_fragment.batch_index,
                source_resource_ids=export_fragment.source_resource_ids,
                bicep_text=decompiled_bicep,
            )

            sanitization_result = sanitize_bicep_secrets(bicep_text=decompiled_fragment.bicep_text)
            secure_parameter_count += sanitization_result.secure_parameter_count

            resource_type_to_matches = await self._resolve_avm_matches(
                bicep_text=sanitization_result.bicep_text,
                gov_approved_avm_modules=gov_approved_avm_modules,
            )
            annotation_result = annotate_bicep_with_avm_recommendations(
                bicep_text=sanitization_result.bicep_text,
                resource_type_to_matches=resource_type_to_matches,
                gov_approved_avm_modules=gov_approved_avm_modules,
            )
            avm_annotation_count += annotation_result.annotation_count

            formatted_bicep = await self._bicep_tool_client.format_bicep(
                bicep_text=annotation_result.annotated_bicep_text,
                logical_name=logical_name,
            )
            diagnostics_result = await self._bicep_tool_client.get_diagnostics(
                bicep_text=formatted_bicep,
                logical_name=logical_name,
            )
            diagnostics.extend(format_bicep_diagnostics(result=diagnostics_result))

            sanitized_fragments.append(
                SanitizedFragment(
                    batch_index=decompiled_fragment.batch_index,
                    source_resource_ids=decompiled_fragment.source_resource_ids,
                    bicep_text=formatted_bicep,
                    secure_parameter_count=sanitization_result.secure_parameter_count,
                )
            )

        generated_files: list[GeneratedFile]
        merge_mode: str
        fallback_used = False
        unresolved_reference_count = 0

        try:
            composition_healthy = await self._composition_api_client.check_health()
        except Exception as exc:
            composition_healthy = False
            diagnostics.append(f"Composition sidecar health check failed; using fallback package instead: {exc}")

        if composition_healthy:
            try:
                composition_result = await self._composition_api_client.compose(
                    request=CompositionRequest(
                        subscription_id=subscription_id,
                        resource_group_name=resource_group_name,
                        azure_environment=azure_environment,
                        fragments=[
                            CompositionFragment(
                                batch_index=fragment.batch_index,
                                source_resource_ids=list(fragment.source_resource_ids),
                                bicep_text=fragment.bicep_text,
                            )
                            for fragment in sanitized_fragments
                        ],
                    ),
                )
                merge_mode = composition_result.merge_mode
                unresolved_reference_count = composition_result.stats.unresolved_reference_count
                diagnostics.extend(composition_result.warnings)
                generated_files = [GeneratedFile(path=file.path, content=file.content) for file in composition_result.files]
            except Exception as exc:
                diagnostics.append(f"Composition sidecar failed during compose; using fallback package instead: {exc}")
                fallback_result = build_text_fallback_package(fragments=sanitized_fragments)
                merge_mode = fallback_result.merge_mode
                fallback_used = True
                diagnostics.extend(fallback_result.warnings)
                generated_files = fallback_result.files
        else:
            diagnostics.append("Composition sidecar was unavailable; using fallback package instead.")
            fallback_result = build_text_fallback_package(fragments=sanitized_fragments)
            merge_mode = fallback_result.merge_mode
            fallback_used = True
            diagnostics.extend(fallback_result.warnings)
            generated_files = fallback_result.files

        package_result = build_bicep_package_artifact(
            resource_group_name=resource_group_name,
            files=generated_files,
            metadata={
                "artifact_kind": "generated",
                "conversion_kind": "azure_export_to_bicep",
                "subscription_id": subscription_id,
                "resource_group_name": resource_group_name,
                "azure_environment": azure_environment,
            },
        )

        summary = ConversionSummary(
            subscription_id=subscription_id,
            resource_group_name=resource_group_name,
            azure_environment=azure_environment,
            resource_count=plan.resource_count,
            export_mode=plan.export_mode,
            batch_count=max(len(plan.batches), 1),
            merge_mode=merge_mode,
            fallback_used=fallback_used,
            unresolved_reference_count=unresolved_reference_count,
            secure_parameter_count=secure_parameter_count,
            avm_annotation_count=avm_annotation_count,
            diagnostics=diagnostics,
            generated_files=package_result.generated_files,
        )
        return ConversionResult(artifact=package_result.artifact, summary=summary)

    async def _resolve_avm_matches(
        self,
        *,
        bicep_text: str,
        gov_approved_avm_modules: list[str],
    ) -> dict[str, list]:
        if not gov_approved_avm_modules:
            return {}

        resource_types = sorted(set(_RESOURCE_TYPE_RE.findall(bicep_text)))
        if not resource_types:
            return {}

        matches_by_resource_type: dict[str, list] = {}
        for resource_type in resource_types:
            matches_by_resource_type[resource_type] = await self._avm_catalog_client.search_module(
                resource_type=resource_type
            )
        return matches_by_resource_type