from dataclasses import dataclass, field

from agent_86.services.azure_bicep_conversion.models import GeneratedFile, SanitizedFragment


@dataclass(frozen=True)
class FallbackCompositionResult:
    files: list[GeneratedFile] = field(default_factory=list)
    merge_mode: str = "low_fidelity_text_fallback"
    warnings: list[str] = field(default_factory=list)


def build_text_fallback_package(*, fragments: list[SanitizedFragment]) -> FallbackCompositionResult:
    main_sections = [
        "// Generated via low-fidelity fallback composition.",
        "// Review resource declarations, parameters, and outputs before deployment.",
        "",
    ]
    module_files: list[GeneratedFile] = []

    for fragment in fragments:
        module_path = f"modules/fragment_{fragment.batch_index:03d}.bicep"
        module_files.append(GeneratedFile(path=module_path, content=fragment.bicep_text))
        main_sections.extend(
            [
                (
                    f"module fragment_{fragment.batch_index:03d} './{module_path}' = {{\n"
                    f"  name: 'fragment-{fragment.batch_index:03d}'\n"
                    "}"
                ),
                "",
            ]
        )

    return FallbackCompositionResult(
        files=[GeneratedFile(path="main.bicep", content="\n".join(main_sections).rstrip() + "\n"), *module_files],
        warnings=[
            "AST composition was unavailable; generated a low-fidelity text fallback package.",
        ],
    )