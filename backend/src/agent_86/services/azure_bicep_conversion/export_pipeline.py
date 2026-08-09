from dataclasses import dataclass, field

from agent_86.integrations.azure.resource_export_client import ResourceExportClient
from agent_86.services.azure_bicep_conversion.models import ExportBatch, ExportFragment
from agent_86.services.azure_bicep_conversion.preflight import (
    DEFAULT_EXPORT_BATCH_SIZE,
    PreflightDecision,
    determine_preflight_decision,
)


@dataclass(frozen=True)
class ExportPlan:
    resource_count: int
    export_mode: str
    batches: list[ExportBatch] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ExportPipeline:
    def __init__(self, resource_export_client: ResourceExportClient) -> None:
        self._resource_export_client = resource_export_client

    async def plan_export(
        self,
        *,
        subscription_id: str,
        resource_group_name: str,
        resource_ids: list[str] | None = None,
        wildcard_export_resource_limit: int = 200,
        batch_size: int = DEFAULT_EXPORT_BATCH_SIZE,
    ) -> ExportPlan:
        resource_count = await self._resource_export_client.get_resource_count(
            subscription_id=subscription_id,
            resource_group_name=resource_group_name,
        )
        preflight = determine_preflight_decision(
            resource_count=resource_count,
            wildcard_export_resource_limit=wildcard_export_resource_limit,
            batch_size=batch_size,
        )

        batches = _build_export_batches(
            preflight=preflight,
            resource_ids=resource_ids,
        )
        return ExportPlan(
            resource_count=resource_count,
            export_mode=preflight.export_mode,
            batches=batches,
            warnings=preflight.warnings,
        )

    async def export_resource_group(
        self,
        *,
        subscription_id: str,
        resource_group_name: str,
        resource_ids: list[str] | None = None,
        wildcard_export_resource_limit: int = 200,
        batch_size: int = DEFAULT_EXPORT_BATCH_SIZE,
    ) -> tuple[ExportPlan, list[ExportFragment]]:
        plan = await self.plan_export(
            subscription_id=subscription_id,
            resource_group_name=resource_group_name,
            resource_ids=resource_ids,
            wildcard_export_resource_limit=wildcard_export_resource_limit,
            batch_size=batch_size,
        )

        if plan.export_mode == "wildcard":
            export_template = await self._resource_export_client.export_resource_group_wildcard(
                subscription_id=subscription_id,
                resource_group_name=resource_group_name,
            )
            return plan, [
                ExportFragment(
                    batch_index=0,
                    export_mode="wildcard",
                    source_resource_ids=export_template.source_resource_ids,
                    template_json=export_template.template_json,
                )
            ]

        fragments: list[ExportFragment] = []
        for batch in plan.batches:
            export_template = await self._resource_export_client.export_resource_group_by_resource_ids(
                subscription_id=subscription_id,
                resource_group_name=resource_group_name,
                resource_ids=batch.resource_ids,
            )
            fragments.append(
                ExportFragment(
                    batch_index=batch.batch_index,
                    export_mode="resource_id_list",
                    source_resource_ids=export_template.source_resource_ids or list(batch.resource_ids),
                    template_json=export_template.template_json,
                )
            )

        return plan, fragments


def _build_export_batches(*, preflight: PreflightDecision, resource_ids: list[str] | None) -> list[ExportBatch]:
    if preflight.export_mode == "wildcard":
        return [ExportBatch(batch_index=0, resource_ids=[])]

    normalized_resource_ids = _normalize_resource_ids(resource_ids)
    if len(normalized_resource_ids) != preflight.resource_count:
        raise ValueError(
            "resource_ids are required for resource_id_list export mode and must match the resource count"
        )

    batches: list[ExportBatch] = []
    for batch_index, start in enumerate(range(0, len(normalized_resource_ids), preflight.batch_size)):
        batches.append(
            ExportBatch(
                batch_index=batch_index,
                resource_ids=normalized_resource_ids[start : start + preflight.batch_size],
            )
        )
    return batches


def _normalize_resource_ids(resource_ids: list[str] | None) -> list[str]:
    if resource_ids is None:
        return []

    normalized_ids: list[str] = []
    for resource_id in resource_ids:
        normalized_id = resource_id.strip()
        if not normalized_id:
            raise ValueError("resource_ids must contain only non-empty strings")
        normalized_ids.append(normalized_id)
    return normalized_ids