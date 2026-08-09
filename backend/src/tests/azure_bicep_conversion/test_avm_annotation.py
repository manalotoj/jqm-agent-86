from agent_86.integrations.avm.avm_catalog_client import AvmModuleMatch
from agent_86.services.azure_bicep_conversion.avm_annotation import annotate_bicep_with_avm_recommendations


def test_annotate_bicep_with_avm_recommendations_prepends_approved_annotations() -> None:
    result = annotate_bicep_with_avm_recommendations(
        bicep_text="resource stg 'Microsoft.Storage/storageAccounts@2023-05-01' = {}",
        resource_type_to_matches={
            "Microsoft.Storage/storageAccounts": [
                AvmModuleMatch(
                    module_path="avm/res/storage/storage-account",
                    resource_type="Microsoft.Storage/storageAccounts",
                )
            ]
        },
        gov_approved_avm_modules=["avm/res/storage/storage-account"],
    )

    assert result.annotation_count == 1
    assert result.annotations[0].approved_module_path == "avm/res/storage/storage-account"
    assert result.annotated_bicep_text.startswith(
        "// AVM candidate for Microsoft.Storage/storageAccounts: avm/res/storage/storage-account"
    )


def test_annotate_bicep_with_avm_recommendations_ignores_unapproved_matches() -> None:
    result = annotate_bicep_with_avm_recommendations(
        bicep_text="resource kv 'Microsoft.KeyVault/vaults@2023-02-01' = {}",
        resource_type_to_matches={
            "Microsoft.KeyVault/vaults": [
                AvmModuleMatch(
                    module_path="avm/res/key-vault/vault",
                    resource_type="Microsoft.KeyVault/vaults",
                )
            ]
        },
        gov_approved_avm_modules=["avm/res/storage/storage-account"],
    )

    assert result.annotation_count == 0
    assert result.annotated_bicep_text == "resource kv 'Microsoft.KeyVault/vaults@2023-02-01' = {}"