import json
from pathlib import Path

import pytest

from agent_86.integrations.avm.avm_catalog_client import AvmCatalogClient, AvmCatalogError, AvmModuleMatch


@pytest.mark.asyncio
async def test_search_module_loads_catalog_and_returns_normalized_matches(tmp_path: Path) -> None:
    catalog_path = tmp_path / "avm_catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "modules": [
                    {
                        "module_path": "avm/res/storage/storage-account",
                        "resource_type": "Microsoft.Storage/storageAccounts",
                        "summary": "Storage account module",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    client = AvmCatalogClient(catalog_path=catalog_path)

    matches = await client.search_module(resource_type=" Microsoft.Storage/storageAccounts ")

    assert matches == [
        AvmModuleMatch(
            module_path="avm/res/storage/storage-account",
            resource_type="Microsoft.Storage/storageAccounts",
            summary="Storage account module",
        )
    ]


@pytest.mark.asyncio
async def test_search_module_is_case_insensitive_and_returns_copy(tmp_path: Path) -> None:
    catalog_path = tmp_path / "avm_catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "modules": [
                    {
                        "module_path": "avm/res/key-vault/vault",
                        "resource_type": "Microsoft.KeyVault/vaults",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    client = AvmCatalogClient(catalog_path=catalog_path)

    first_result = await client.search_module(resource_type="microsoft.keyvault/vaults")
    second_result = await client.search_module(resource_type="MICROSOFT.KEYVAULT/VAULTS")

    assert first_result == second_result
    assert first_result is not second_result


@pytest.mark.asyncio
async def test_search_module_uses_in_memory_cache_after_first_load(tmp_path: Path) -> None:
    catalog_path = tmp_path / "avm_catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "modules": [
                    {
                        "module_path": "avm/res/web/site",
                        "resource_type": "Microsoft.Web/sites",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    client = AvmCatalogClient(catalog_path=catalog_path)

    first_result = await client.search_module(resource_type="Microsoft.Web/sites")
    catalog_path.write_text(json.dumps({"modules": []}), encoding="utf-8")
    second_result = await client.search_module(resource_type="Microsoft.Web/sites")

    assert first_result == second_result
    assert second_result == [AvmModuleMatch(module_path="avm/res/web/site", resource_type="Microsoft.Web/sites", summary=None)]


@pytest.mark.asyncio
async def test_ping_returns_false_when_catalog_is_missing(tmp_path: Path) -> None:
    client = AvmCatalogClient(catalog_path=tmp_path / "missing.json")

    assert await client.ping() is False


@pytest.mark.asyncio
async def test_search_module_raises_when_catalog_payload_is_invalid(tmp_path: Path) -> None:
    catalog_path = tmp_path / "avm_catalog.json"
    catalog_path.write_text("[]", encoding="utf-8")
    client = AvmCatalogClient(catalog_path=catalog_path)

    with pytest.raises(AvmCatalogError, match="JSON object"):
        await client.search_module(resource_type="Microsoft.Storage/storageAccounts")