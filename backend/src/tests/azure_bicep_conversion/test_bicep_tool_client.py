from dataclasses import dataclass, field
from pathlib import Path
import tempfile
from typing import Callable

import pytest

from agent_86.integrations.bicep.bicep_tool_client import (
    BicepCommandResult,
    BicepDiagnostic,
    BicepToolClient,
    BicepToolError,
)


@dataclass
class RecordingRunner:
    results: list[BicepCommandResult] = field(default_factory=list)
    commands: list[tuple[list[str], str]] = field(default_factory=list)
    callback: Callable[..., None] | None = None

    async def __call__(self, command: list[str], *, cwd: str) -> BicepCommandResult:
        self.commands.append((list(command), cwd))
        if self.callback is not None:
            self.callback(command=command, cwd=cwd)
        if not self.results:
            raise AssertionError("No fake command result configured")
        return self.results.pop(0)


@dataclass
class RecordingTempdirFactory:
    created_paths: list[Path] = field(default_factory=list)

    def __call__(self):
        tempdir = tempfile.TemporaryDirectory(prefix="agent86-bicep-test-")
        self.created_paths.append(Path(tempdir.name))
        return tempdir


@pytest.mark.asyncio
async def test_ping_returns_true_when_bicep_cli_is_available() -> None:
    runner = RecordingRunner(results=[BicepCommandResult(returncode=0, stdout="Bicep CLI version 0.30.0")])
    client = BicepToolClient(command_runner=runner, which=lambda _: "/usr/local/bin/bicep")

    assert await client.ping() is True
    assert runner.commands == [(["bicep", "--version"], str(Path.cwd()))]


@pytest.mark.asyncio
async def test_decompile_arm_template_reads_output_file_from_isolated_workspace() -> None:
    tempdirs = RecordingTempdirFactory()

    def write_output(*, command: list[str], cwd: str) -> None:
        assert command == ["bicep", "decompile", "--file", "rg-001.json"]
        workspace = Path(cwd)
        assert (workspace / "rg-001.json").exists()
        (workspace / "rg-001.bicep").write_text("resource stg 'Type@1' = {}", encoding="utf-8")

    runner = RecordingRunner(results=[BicepCommandResult(returncode=0)], callback=write_output)
    client = BicepToolClient(command_runner=runner, tempdir_factory=tempdirs)

    result = await client.decompile_arm_template(template_json={"resources": []}, logical_name="rg-001")

    assert result == "resource stg 'Type@1' = {}\n"
    assert not tempdirs.created_paths[0].exists()


@pytest.mark.asyncio
async def test_format_bicep_prefers_stdout_output() -> None:
    tempdirs = RecordingTempdirFactory()
    runner = RecordingRunner(results=[BicepCommandResult(returncode=0, stdout="param location string = 'eastus'\n")])
    client = BicepToolClient(command_runner=runner, tempdir_factory=tempdirs)

    result = await client.format_bicep(bicep_text="param location string='eastus'", logical_name="main")

    assert result == "param location string = 'eastus'\n"
    command, cwd = runner.commands[0]
    assert command == ["bicep", "format", "--file", "main.bicep", "--stdout"]
    assert not Path(cwd).exists()


@pytest.mark.asyncio
async def test_get_diagnostics_parses_warning_and_error_lines() -> None:
    runner = RecordingRunner(
        results=[
            BicepCommandResult(
                returncode=1,
                stderr=(
                    "WARNING BCP036 [main.bicep]: The property is invalid.\n"
                    "ERROR BCP089 [main.bicep]: The parameter expected a value.\n"
                ),
            )
        ]
    )
    client = BicepToolClient(command_runner=runner)

    result = await client.get_diagnostics(bicep_text="resource bad 'Type@1' = {}", logical_name="main")

    assert result.diagnostics == [
        BicepDiagnostic(code="BCP036", level="warning", message="The property is invalid.", file_path="main.bicep"),
        BicepDiagnostic(code="BCP089", level="error", message="The parameter expected a value.", file_path="main.bicep"),
    ]


@pytest.mark.asyncio
async def test_get_diagnostics_raises_for_non_diagnostic_command_failure() -> None:
    runner = RecordingRunner(results=[BicepCommandResult(returncode=2, stderr="fatal: CLI crashed")])
    client = BicepToolClient(command_runner=runner)

    with pytest.raises(BicepToolError, match="collect Bicep diagnostics"):
        await client.get_diagnostics(bicep_text="param location string", logical_name="main")


@pytest.mark.asyncio
async def test_decompile_arm_template_raises_with_stderr_details() -> None:
    runner = RecordingRunner(results=[BicepCommandResult(returncode=1, stderr="decompile failed badly")])
    client = BicepToolClient(command_runner=runner)

    with pytest.raises(BicepToolError, match="decompile ARM template: decompile failed badly"):
        await client.decompile_arm_template(template_json={"resources": []}, logical_name="main")