import base64
from dataclasses import dataclass, field
from typing import Any

from agent_86.domain.models.artifact import Artifact
from agent_86.domain.models.message import Message
from agent_86.services.artifact_service import ArtifactService


ARTIFACT_DISCLOSURE_INSTRUCTION = (
    "If any artifact content below is marked partial, truncated, or unreadable, explicitly say so in your answer "
    "when you rely on that artifact or when the user asks about attached files."
)


@dataclass(frozen=True)
class ArtifactPromptContextResult:
    context_message: Message | None
    artifact_details: list[dict[str, object]]
    has_partial_artifacts: bool
    has_unreadable_artifacts: bool
    image_content_blocks: list[dict[str, Any]] = field(default_factory=list)
    requires_vision: bool = False


class ArtifactPromptContextService:
    SUPPORTED_TEXT_EXTENSIONS = {
        ".txt",
        ".md",
        ".markdown",
        ".json",
        ".yaml",
        ".yml",
        ".csv",
        ".log",
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".html",
        ".css",
        ".xml",
        ".sql",
        ".sh",
    }
    SUPPORTED_TEXT_CONTENT_TYPE_PREFIXES = (
        "text/",
        "application/json",
        "application/xml",
        "application/yaml",
        "application/x-yaml",
        "application/javascript",
        "application/x-javascript",
        "application/sql",
    )
    SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    SUPPORTED_IMAGE_CONTENT_TYPES = frozenset({
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/gif",
        "image/webp",
    })

    def __init__(
        self,
        artifact_service: ArtifactService,
        *,
        small_file_char_limit: int = 4_000,
        medium_file_char_limit: int = 20_000,
        medium_head_char_count: int = 4_000,
        medium_tail_char_count: int = 4_000,
        large_excerpt_char_count: int = 6_000,
        image_max_bytes: int = 5 * 1024 * 1024,
    ) -> None:
        self._artifact_service = artifact_service
        self._small_file_char_limit = small_file_char_limit
        self._medium_file_char_limit = medium_file_char_limit
        self._medium_head_char_count = medium_head_char_count
        self._medium_tail_char_count = medium_tail_char_count
        self._large_excerpt_char_count = large_excerpt_char_count
        self._image_max_bytes = image_max_bytes

    async def build_message_for_artifact_ids(
        self,
        *,
        user_id: str,
        session_id: str,
        artifact_ids: list[str],
    ) -> ArtifactPromptContextResult:
        if not artifact_ids:
            return ArtifactPromptContextResult(None, [], False, False)

        artifact_details: list[dict[str, object]] = []
        sections: list[str] = []
        image_content_blocks: list[dict[str, Any]] = []
        has_partial_artifacts = False
        has_unreadable_artifacts = False

        for artifact_id in artifact_ids:
            artifact_with_content = await self._artifact_service.get_artifact_content(user_id, session_id, artifact_id)
            artifact = artifact_with_content.artifact
            content_bytes = artifact_with_content.download.content

            if self._is_supported_image_artifact(artifact):
                detail, image_block = self._build_image_artifact_section(artifact, content_bytes)
                artifact_details.append(detail)
                if image_block is not None:
                    image_content_blocks.append(image_block)
                has_unreadable_artifacts = has_unreadable_artifacts or bool(detail["is_unreadable"])
                # produce a brief text note in the system context so the model knows the image filename/id
                sections.append(self._format_image_reference_section(artifact, detail))
            else:
                detail, section = self._build_artifact_section(artifact, content_bytes)
                artifact_details.append(detail)
                sections.append(section)
                has_partial_artifacts = has_partial_artifacts or bool(detail["is_partial"])
                has_unreadable_artifacts = has_unreadable_artifacts or bool(detail["is_unreadable"])

        requires_vision = len(image_content_blocks) > 0

        instruction_lines = [
            "System note: the user attached session artifacts for this request.",
            ARTIFACT_DISCLOSURE_INSTRUCTION,
        ]
        if requires_vision:
            instruction_lines.append(
                "One or more image artifacts are attached as inline images in this message. "
                "Extract all visible text and analyze the content as instructed by the user."
            )
        if has_partial_artifacts:
            instruction_lines.append(
                "Some attachments are only partially visible below. Do not imply you reviewed the full file when you only saw an excerpt."
            )
        if has_unreadable_artifacts:
            instruction_lines.append(
                "Some attachments could not be read as supported text and are listed as unreadable below."
            )

        content = "\n\n".join(["\n".join(instruction_lines), *sections])
        return ArtifactPromptContextResult(
            context_message=Message(
                id="artifact-context",
                session_id=session_id,
                user_id=user_id,
                role="system",
                content=content,
                metadata={
                    "message_type": "artifact_context",
                    "artifact_ids": artifact_ids,
                    "has_partial_artifacts": has_partial_artifacts,
                    "has_unreadable_artifacts": has_unreadable_artifacts,
                    "requires_vision": requires_vision,
                },
            ),
            artifact_details=artifact_details,
            has_partial_artifacts=has_partial_artifacts,
            has_unreadable_artifacts=has_unreadable_artifacts,
            image_content_blocks=image_content_blocks,
            requires_vision=requires_vision,
        )

    def build_summary_artifact_details(self, artifacts: list[Artifact]) -> list[dict[str, object]]:
        return [
            {
                "id": artifact.id,
                "filename": artifact.filename,
                "content_type": artifact.content_type,
                "metadata": artifact.metadata,
                "readability": "supported_text" if self._is_supported_text_artifact(artifact) else "unreadable",
            }
            for artifact in artifacts
        ]

    def _build_artifact_section(self, artifact: Artifact, raw_content: bytes) -> tuple[dict[str, object], str]:
        if not self._is_supported_text_artifact(artifact):
            detail = {
                "id": artifact.id,
                "filename": artifact.filename,
                "content_type": artifact.content_type,
                "strategy": "unreadable",
                "is_partial": False,
                "is_unreadable": True,
            }
            section = (
                f"Artifact: {artifact.filename} (id={artifact.id}, content_type={artifact.content_type})\n"
                "Status: attached but unreadable in v1 because this file type is not a supported text artifact."
            )
            return detail, section

        try:
            decoded_content = raw_content.decode("utf-8")
        except UnicodeDecodeError:
            detail = {
                "id": artifact.id,
                "filename": artifact.filename,
                "content_type": artifact.content_type,
                "strategy": "decode_error",
                "is_partial": False,
                "is_unreadable": True,
            }
            section = (
                f"Artifact: {artifact.filename} (id={artifact.id}, content_type={artifact.content_type})\n"
                "Status: attached but unreadable in v1 because the file could not be decoded as UTF-8 text."
            )
            return detail, section

        content_length = len(decoded_content)
        if content_length <= self._small_file_char_limit:
            strategy = "full"
            excerpt = decoded_content
            section = self._format_section(
                artifact=artifact,
                status=f"Full text provided ({content_length} characters visible).",
                excerpt_label="Full content",
                excerpt=excerpt,
            )
            return {
                "id": artifact.id,
                "filename": artifact.filename,
                "content_type": artifact.content_type,
                "strategy": strategy,
                "is_partial": False,
                "is_unreadable": False,
            }, section

        if content_length <= self._medium_file_char_limit:
            strategy = "head_tail"
            head = decoded_content[: self._medium_head_char_count]
            tail = decoded_content[-self._medium_tail_char_count :]
            omitted_chars = max(content_length - len(head) - len(tail), 0)
            excerpt = (
                f"--- BEGIN HEAD ({len(head)} chars) ---\n{head}\n--- END HEAD ---\n"
                f"--- OMITTED MIDDLE ({omitted_chars} chars not shown) ---\n"
                f"--- BEGIN TAIL ({len(tail)} chars) ---\n{tail}\n--- END TAIL ---"
            )
            section = self._format_section(
                artifact=artifact,
                status=(
                    "Partial text provided using head+tail excerpt "
                    f"({content_length} total characters; omitted middle: {omitted_chars} characters)."
                ),
                excerpt_label="Head and tail excerpt",
                excerpt=excerpt,
            )
            return {
                "id": artifact.id,
                "filename": artifact.filename,
                "content_type": artifact.content_type,
                "strategy": strategy,
                "is_partial": True,
                "is_unreadable": False,
            }, section

        strategy = "truncated"
        excerpt = decoded_content[: self._large_excerpt_char_count]
        omitted_chars = max(content_length - len(excerpt), 0)
        section = self._format_section(
            artifact=artifact,
            status=(
                "Partial text provided using leading excerpt only "
                f"({content_length} total characters; omitted trailing content: {omitted_chars} characters)."
            ),
            excerpt_label="Truncated excerpt",
            excerpt=excerpt,
        )
        return {
            "id": artifact.id,
            "filename": artifact.filename,
            "content_type": artifact.content_type,
            "strategy": strategy,
            "is_partial": True,
            "is_unreadable": False,
        }, section

    def _is_supported_text_artifact(self, artifact: Artifact) -> bool:
        lower_filename = artifact.filename.lower()
        if any(lower_filename.endswith(extension) for extension in self.SUPPORTED_TEXT_EXTENSIONS):
            return True

        lower_content_type = artifact.content_type.lower()
        return any(lower_content_type.startswith(prefix) for prefix in self.SUPPORTED_TEXT_CONTENT_TYPE_PREFIXES)

    def _is_supported_image_artifact(self, artifact: Artifact) -> bool:
        lower_filename = artifact.filename.lower()
        if any(lower_filename.endswith(ext) for ext in self.SUPPORTED_IMAGE_EXTENSIONS):
            return True

        lower_content_type = artifact.content_type.lower().split(";")[0].strip()
        return lower_content_type in self.SUPPORTED_IMAGE_CONTENT_TYPES

    def _build_image_artifact_section(
        self,
        artifact: Artifact,
        content_bytes: bytes,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        if len(content_bytes) > self._image_max_bytes:
            detail: dict[str, Any] = {
                "id": artifact.id,
                "filename": artifact.filename,
                "content_type": artifact.content_type,
                "strategy": "image_too_large",
                "is_partial": False,
                "is_unreadable": True,
            }
            return detail, None

        content_type = artifact.content_type.lower().split(";")[0].strip()
        if content_type not in self.SUPPORTED_IMAGE_CONTENT_TYPES:
            # Infer from extension as a fallback
            ext = artifact.filename.lower().rsplit(".", 1)[-1] if "." in artifact.filename else ""
            ext_to_mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}
            content_type = ext_to_mime.get(ext, "image/png")

        encoded = base64.b64encode(content_bytes).decode("ascii")
        image_block: dict[str, Any] = {
            "type": "input_image",
            "image_url": f"data:{content_type};base64,{encoded}",
        }
        detail = {
            "id": artifact.id,
            "filename": artifact.filename,
            "content_type": artifact.content_type,
            "strategy": "image_inline",
            "is_partial": False,
            "is_unreadable": False,
        }
        return detail, image_block

    def _format_image_reference_section(self, artifact: Artifact, detail: dict[str, Any]) -> str:
        if detail.get("is_unreadable"):
            status = (
                f"Image too large to inline (exceeds {self._image_max_bytes // (1024 * 1024)} MB limit). "
                "The image was not sent to the model."
            )
        else:
            status = "Image attached inline. Extract and analyze visible text and content."
        return (
            f"Artifact: {artifact.filename} (id={artifact.id}, content_type={artifact.content_type})\n"
            f"Status: {status}"
        )

    def _format_section(self, *, artifact: Artifact, status: str, excerpt_label: str, excerpt: str) -> str:
        return (
            f"Artifact: {artifact.filename} (id={artifact.id}, content_type={artifact.content_type})\n"
            f"Status: {status}\n"
            f"{excerpt_label}:\n"
            "```\n"
            f"{excerpt}\n"
            "```"
        )