from agent_86.integrations.bicep.bicep_tool_client import BicepDiagnostic, BicepDiagnosticsResult


def format_bicep_diagnostics(*, result: BicepDiagnosticsResult) -> list[str]:
    return [_format_bicep_diagnostic(diagnostic) for diagnostic in result.diagnostics]


def _format_bicep_diagnostic(diagnostic: BicepDiagnostic) -> str:
    location = f" [{diagnostic.file_path}]" if diagnostic.file_path else ""
    return f"{diagnostic.level.upper()} {diagnostic.code}{location}: {diagnostic.message}"