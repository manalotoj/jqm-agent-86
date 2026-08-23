#!/usr/bin/env python3
"""Create an Azure Storage lifecycle-policy document for derived artifacts.

The script is deliberately independent from Azure CLI calls so it can be unit
tested and so the caller can retain unrelated lifecycle rules returned by Azure.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

RULE_NAME = "delete-agent86-derived-artifacts"
DERIVED_CONTAINER_NAME = "agent86-artifact-derived"


def build_rule(days_after_modification: int) -> dict[str, Any]:
    return {
        "enabled": True,
        "name": RULE_NAME,
        "type": "Lifecycle",
        "definition": {
            "actions": {
                "baseBlob": {
                    "delete": {
                        "daysAfterModificationGreaterThan": days_after_modification,
                    },
                },
            },
            "filters": {
                "blobTypes": ["blockBlob"],
                "prefixMatch": [f"{DERIVED_CONTAINER_NAME}/"],
            },
        },
    }


def update_policy(policy: dict[str, Any], days_after_modification: int) -> dict[str, Any]:
    """Replace only this application's named rule, retaining all other rules."""
    root = policy.setdefault("policy", {})
    rules = root.setdefault("rules", [])
    if not isinstance(rules, list):
        raise ValueError("Azure lifecycle policy field policy.rules must be an array")

    replacement = build_rule(days_after_modification)
    root["rules"] = [rule for rule in rules if rule.get("name") != RULE_NAME] + [replacement]
    return policy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Existing lifecycle-policy JSON file")
    parser.add_argument("--output", required=True, help="Path for the updated lifecycle-policy JSON file")
    parser.add_argument("--days", required=True, type=int, help="Delete derived blobs after this many days")
    args = parser.parse_args()

    if args.days < 1:
        parser.error("--days must be at least 1")

    try:
        with open(args.input, encoding="utf-8") as source:
            policy = json.load(source)
        updated = update_policy(policy, args.days)
        with open(args.output, "w", encoding="utf-8") as destination:
            json.dump(updated, destination, indent=2, sort_keys=True)
            destination.write("\n")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())