from agent_86.services.azure_bicep_conversion.fallback import build_text_fallback_package
from agent_86.services.azure_bicep_conversion.models import SanitizedFragment


def test_build_text_fallback_package_creates_main_and_module_files() -> None:
    result = build_text_fallback_package(
        fragments=[
            SanitizedFragment(batch_index=0, source_resource_ids=["r1"], bicep_text="resource a 'Type@1' = {}"),
            SanitizedFragment(batch_index=1, source_resource_ids=["r2"], bicep_text="resource b 'Type@1' = {}"),
        ]
    )

    assert result.merge_mode == "low_fidelity_text_fallback"
    assert [generated_file.path for generated_file in result.files] == [
        "main.bicep",
        "modules/fragment_000.bicep",
        "modules/fragment_001.bicep",
    ]
    assert "module fragment_000 './modules/fragment_000.bicep'" in result.files[0].content
    assert result.warnings == [
        "AST composition was unavailable; generated a low-fidelity text fallback package.",
    ]