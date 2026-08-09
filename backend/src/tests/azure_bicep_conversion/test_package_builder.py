import io
import zipfile

import pytest

from agent_86.services.azure_bicep_conversion.models import GeneratedFile
from agent_86.services.azure_bicep_conversion.package_builder import build_bicep_package_artifact


def test_build_bicep_package_artifact_creates_zip_payload_with_expected_files() -> None:
    result = build_bicep_package_artifact(
        resource_group_name="rg-app-prod",
        files=[
            GeneratedFile(path="main.bicep", content="targetScope = 'resourceGroup'"),
            GeneratedFile(path="modules/network.bicep", content="resource vnet 'Type@1' = {}"),
        ],
        metadata={"artifact_kind": "generated"},
    )

    assert result.artifact.filename == "rg-app-prod-bicep-package.zip"
    assert result.artifact.content_type == "application/zip"
    assert result.generated_files == ["main.bicep", "modules/network.bicep"]

    archive = zipfile.ZipFile(io.BytesIO(result.artifact.content))
    assert sorted(archive.namelist()) == ["main.bicep", "modules/network.bicep"]
    assert archive.read("main.bicep").decode("utf-8") == "targetScope = 'resourceGroup'"


def test_build_bicep_package_artifact_rejects_parent_directory_escape() -> None:
    with pytest.raises(ValueError, match="package root"):
        build_bicep_package_artifact(
            resource_group_name="rg-app-prod",
            files=[GeneratedFile(path="../escape.bicep", content="bad")],
            metadata={},
        )