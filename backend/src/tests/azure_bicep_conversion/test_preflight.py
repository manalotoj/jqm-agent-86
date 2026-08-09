import pytest

from agent_86.services.azure_bicep_conversion.preflight import determine_preflight_decision


def test_determine_preflight_decision_uses_wildcard_when_within_limit() -> None:
    decision = determine_preflight_decision(resource_count=200)

    assert decision.export_mode == "wildcard"
    assert decision.batch_count == 1
    assert decision.warnings == []


def test_determine_preflight_decision_uses_resource_id_batches_when_over_limit() -> None:
    decision = determine_preflight_decision(resource_count=401)

    assert decision.export_mode == "resource_id_list"
    assert decision.batch_count == 3
    assert decision.warnings == [
        "Resource group exceeds wildcard ARM export threshold; falling back to resource-id-list batching.",
    ]


@pytest.mark.parametrize("resource_count", [-1])
def test_determine_preflight_decision_rejects_negative_resource_count(resource_count: int) -> None:
    with pytest.raises(ValueError, match="resource_count"):
        determine_preflight_decision(resource_count=resource_count)