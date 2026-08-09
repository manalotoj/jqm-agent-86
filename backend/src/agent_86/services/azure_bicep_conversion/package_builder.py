from dataclasses import dataclass
import io
from pathlib import Path
import zipfile

from agent_86.services.azure_bicep_conversion.models import ConversionArtifactPayload, GeneratedFile


PACKAGE_CONTENT_TYPE = "application/zip"


@dataclass(frozen=True)
class PackageBuildResult:
    artifact: ConversionArtifactPayload
    generated_files: list[str]


def build_bicep_package_artifact(
    *,
    resource_group_name: str,
    files: list[GeneratedFile],
    metadata: dict,
) -> PackageBuildResult:
    normalized_rg_name = _sanitize_filename_segment(resource_group_name) or "resource-group"
    artifact_filename = f"{normalized_rg_name}-bicep-package.zip"

    buffer = io.BytesIO()
    archived_files: list[str] = []
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for generated_file in files:
            normalized_path = _normalize_archive_path(generated_file.path)
            archive.writestr(normalized_path, generated_file.content)
            archived_files.append(normalized_path)

    artifact = ConversionArtifactPayload(
        filename=artifact_filename,
        content_type=PACKAGE_CONTENT_TYPE,
        content=buffer.getvalue(),
        metadata=dict(metadata),
    )
    return PackageBuildResult(artifact=artifact, generated_files=archived_files)


def _normalize_archive_path(path: str) -> str:
    normalized = Path(path).as_posix().lstrip("/")
    if not normalized:
        raise ValueError("generated file path must not be empty")
    if normalized.startswith("../") or "/../" in normalized:
        raise ValueError("generated file path must not escape the package root")
    return normalized


def _sanitize_filename_segment(value: str) -> str:
    safe_chars = [character if character.isalnum() or character in {"-", "_"} else "-" for character in value.strip()]
    sanitized = "".join(safe_chars).strip("-")
    return sanitized[:128]