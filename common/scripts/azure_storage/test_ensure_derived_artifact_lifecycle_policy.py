from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("ensure_derived_artifact_lifecycle_policy.py")
SPEC = importlib.util.spec_from_file_location("lifecycle_policy", SCRIPT_PATH)
assert SPEC and SPEC.loader
lifecycle_policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lifecycle_policy)


def test_update_policy_preserves_unrelated_rules_and_replaces_its_own_rule() -> None:
    original = {
        "policy": {
            "rules": [
                {"name": "keep-unrelated-rule", "enabled": False},
                {"name": lifecycle_policy.RULE_NAME, "enabled": False},
            ],
        },
    }

    updated = lifecycle_policy.update_policy(original, 45)

    assert updated["policy"]["rules"][0] == {"name": "keep-unrelated-rule", "enabled": False}
    assert updated["policy"]["rules"][1] == {
        "enabled": True,
        "name": lifecycle_policy.RULE_NAME,
        "type": "Lifecycle",
        "definition": {
            "actions": {"baseBlob": {"delete": {"daysAfterModificationGreaterThan": 45}}},
            "filters": {
                "blobTypes": ["blockBlob"],
                "prefixMatch": ["agent86-artifact-derived/"],
            },
        },
    }