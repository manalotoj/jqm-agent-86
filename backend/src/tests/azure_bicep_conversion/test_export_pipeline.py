from dataclasses import dataclass, field

import pytest

from agent_86.integrations.azure.resource_export_client import ResourceExportTemplate
from agent_86.services.azure_bicep_conversion.export_pipeline import ExportPipeline


@dataclass
class RecordingResourceExportClient:
    resource_count: int
    wildcard_template: ResourceExportTemplate | None = None
    by_id_templates: list[ResourceExportTemplate] = field(default_factory=list)
    wildcard_calls: list[tuple[str, str]] = field(default_factory=list)
    by_id_calls: list[tuple[str, str, list[str]]] = field(default_factory=list)

    async def get_resource_count(self, *, subscription_id: str, resource_group_name: str) -> int:
        return self.resource_count

    async def export_resource_group_wildcard(
        self,
        *,
        subscription_id: str,
        resource_group_name: str,
    ) -> ResourceExportTemplate:
        self.wildcard_calls.append((subscription_id, resource_group_name))
        if self.wildcard_template is None:
            raise AssertionError("wildcard_template was not configured")
        return self.wildcard_template

    async def export_resource_group_by_resource_ids(
        self,
        *,
        subscription_id: str,
        resource_group_name: str,
        resource_ids: list[str],
    ) -> ResourceExportTemplate:
        self.by_id_calls.append((subscription_id, resource_group_name, list(resource_ids)))
        if not self.by_id_templates:
            raise AssertionError("by_id_templates was not configured")
        return self.by_id_templates.pop(0)


@pytest.mark.asyncio
async def test_export_pipeline_uses_wildcard_path_when_resource_count_is_within_limit() -> None:
    client = RecordingResourceExportClient(
        resource_count=2,
        wildcard_template=ResourceExportTemplate(
            template_json={"resources": ["a", "b"]},
            export_mode="wildcard",
            source_resource_ids=[],
        ),
    )
    pipeline = ExportPipeline(client)

    plan, fragments = await pipeline.export_resource_group(
        subscription_id="sub-1",
        resource_group_name="rg-1",
    )

    assert plan.export_mode == "wildcard"
    assert plan.batches == [] or plan.batches == [plan.batches[0]]
    assert len(fragments) == 1
    assert fragments[0].export_mode == "wildcard"
    assert client.wildcard_calls == [("sub-1", "rg-1")]
    assert client.by_id_calls == []


@pytest.mark.asyncio
async def test_export_pipeline_batches_resource_ids_when_resource_count_exceeds_limit() -> None:
    resource_ids = [f"/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Mock/type/{index}" for index in range(5)]
    client = RecordingResourceExportClient(
        resource_count=5,
        by_id_templates=[
            ResourceExportTemplate(
                template_json={"resources": [0, 1]},
                export_mode="resource_id_list",
                source_resource_ids=resource_ids[:2],
            ),
            ResourceExportTemplate(
                template_json={"resources": [2, 3]},
                export_mode="resource_id_list",
                source_resource_ids=resource_ids[2:4],
            ),
            ResourceExportTemplate(
                template_json={"resources": [4]},
                export_mode="resource_id_list",
                source_resource_ids=resource_ids[4:],
            ),
        ],
    )
    pipeline = ExportPipeline(client)

    plan, fragments = await pipeline.export_resource_group(
        subscription_id="sub-1",
        resource_group_name="rg-1",
        resource_ids=resource_ids,
        wildcard_export_resource_limit=2,
        batch_size=2,
    )

    assert plan.export_mode == "resource_id_list"
    assert [batch.resource_ids for batch in plan.batches] == [
        resource_ids[:2],
        resource_ids[2:4],
        resource_ids[4:],
    ]
    assert [fragment.batch_index for fragment in fragments] == [0, 1, 2]
    assert client.by_id_calls == [
        ("sub-1", "rg-1", resource_ids[:2]),
        ("sub-1", "rg-1", resource_ids[2:4]),
        ("sub-1", "rg-1", resource_ids[4:]),
    ]
    assert client.wildcard_calls == []


@pytest.mark.asyncio
async def test_export_pipeline_requires_resource_ids_for_batched_export_mode() -> None:
    client = RecordingResourceExportClient(resource_count=3)
    pipeline = ExportPipeline(client)

    with pytest.raises(ValueError, match="resource_ids are required"):
        await pipeline.export_resource_group(
            subscription_id="sub-1",
            resource_group_name="rg-1",
            wildcard_export_resource_limit=2,
            batch_size=2,
        )