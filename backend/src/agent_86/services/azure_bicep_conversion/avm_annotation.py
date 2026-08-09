from dataclasses import dataclass, field

from agent_86.integrations.avm.avm_catalog_client import AvmModuleMatch


@dataclass(frozen=True)
class AvmAnnotation:
    resource_type: str
    approved_module_path: str
    comment: str


@dataclass(frozen=True)
class AvmAnnotationResult:
    annotated_bicep_text: str
    annotation_count: int
    annotations: list[AvmAnnotation] = field(default_factory=list)


def annotate_bicep_with_avm_recommendations(
    *,
    bicep_text: str,
    resource_type_to_matches: dict[str, list[AvmModuleMatch]],
    gov_approved_avm_modules: list[str],
) -> AvmAnnotationResult:
    approved_module_set = {module_path.strip() for module_path in gov_approved_avm_modules if module_path.strip()}
    annotations: list[AvmAnnotation] = []

    for resource_type, matches in resource_type_to_matches.items():
        approved_match = next((match for match in matches if match.module_path in approved_module_set), None)
        if approved_match is None:
            continue

        comment = (
            f"// AVM candidate for {resource_type}: {approved_match.module_path}"
        )
        annotations.append(
            AvmAnnotation(
                resource_type=resource_type,
                approved_module_path=approved_match.module_path,
                comment=comment,
            )
        )

    if not annotations:
        return AvmAnnotationResult(
            annotated_bicep_text=bicep_text,
            annotation_count=0,
            annotations=[],
        )

    annotation_block = "\n".join(annotation.comment for annotation in annotations)
    annotated_text = f"{annotation_block}\n{bicep_text}"
    return AvmAnnotationResult(
        annotated_bicep_text=annotated_text,
        annotation_count=len(annotations),
        annotations=annotations,
    )