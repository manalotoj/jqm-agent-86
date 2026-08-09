from dataclasses import dataclass, field


WILDCARD_EXPORT_RESOURCE_LIMIT = 200
DEFAULT_EXPORT_BATCH_SIZE = 200


@dataclass(frozen=True)
class PreflightDecision:
    resource_count: int
    export_mode: str
    batch_count: int
    batch_size: int
    warnings: list[str] = field(default_factory=list)


def determine_preflight_decision(
    *,
    resource_count: int,
    wildcard_export_resource_limit: int = WILDCARD_EXPORT_RESOURCE_LIMIT,
    batch_size: int = DEFAULT_EXPORT_BATCH_SIZE,
) -> PreflightDecision:
    if resource_count < 0:
        raise ValueError("resource_count must be >= 0")
    if wildcard_export_resource_limit <= 0:
        raise ValueError("wildcard_export_resource_limit must be > 0")
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")

    if resource_count <= wildcard_export_resource_limit:
        return PreflightDecision(
            resource_count=resource_count,
            export_mode="wildcard",
            batch_count=1,
            batch_size=batch_size,
        )

    batch_count = (resource_count + batch_size - 1) // batch_size
    return PreflightDecision(
        resource_count=resource_count,
        export_mode="resource_id_list",
        batch_count=batch_count,
        batch_size=batch_size,
        warnings=[
            (
                "Resource group exceeds wildcard ARM export threshold; "
                "falling back to resource-id-list batching."
            )
        ],
    )