import asyncio
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Protocol


class BicepToolError(RuntimeError):
    """Raised when direct Bicep CLI execution fails."""


@dataclass(frozen=True)
class BicepCommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class _CommandRunner(Protocol):
    async def __call__(self, command: list[str], *, cwd: str) -> BicepCommandResult: ...


@dataclass(frozen=True)
class BicepDiagnostic:
    code: str
    level: str
    message: str
    file_path: str | None = None


@dataclass(frozen=True)
class BicepDiagnosticsResult:
    diagnostics: list[BicepDiagnostic] = field(default_factory=list)


class BicepToolClient:
    """Boundary for official Bicep tooling operations used by the conversion pipeline."""

    def __init__(
        self,
        *,
        executable: str = "bicep",
        command_runner: _CommandRunner | None = None,
        tempdir_factory: Callable[[], tempfile.TemporaryDirectory[str]] | None = None,
        which: Callable[[str], str | None] | None = None,
    ) -> None:
        self._executable = executable
        self._command_runner = command_runner or _run_subprocess
        self._tempdir_factory = tempdir_factory or (lambda: tempfile.TemporaryDirectory(prefix="agent86-bicep-"))
        self._which = which or shutil.which

    async def ping(self) -> bool:
        if self._which(self._executable) is None:
            return False
        try:
            result = await self._command_runner([self._executable, "--version"], cwd=str(Path.cwd()))
        except Exception:
            return False
        return result.returncode == 0

    async def decompile_arm_template(self, *, template_json: dict, logical_name: str) -> str:
        with self._tempdir_factory() as workspace:
            workspace_path = Path(workspace)
            template_path = workspace_path / f"{logical_name}.json"
            bicep_path = workspace_path / f"{logical_name}.bicep"
            template_path.write_text(json.dumps(template_json, indent=2), encoding="utf-8")

            result = await self._command_runner(
                [self._executable, "decompile", "--file", template_path.name],
                cwd=str(workspace_path),
            )
            _raise_for_failed_command(result=result, action="decompile ARM template")

            if result.stdout.strip():
                return _normalize_bicep_text(result.stdout)
            if not bicep_path.exists():
                raise BicepToolError("Bicep decompile did not produce stdout or an output file")
            return _normalize_bicep_text(bicep_path.read_text(encoding="utf-8"))

    async def format_bicep(self, *, bicep_text: str, logical_name: str) -> str:
        with self._tempdir_factory() as workspace:
            workspace_path = Path(workspace)
            bicep_path = workspace_path / f"{logical_name}.bicep"
            bicep_path.write_text(bicep_text, encoding="utf-8")

            result = await self._command_runner(
                [self._executable, "format", "--file", bicep_path.name, "--stdout"],
                cwd=str(workspace_path),
            )
            _raise_for_failed_command(result=result, action="format Bicep")

            if result.stdout.strip():
                return _normalize_bicep_text(result.stdout)
            return _normalize_bicep_text(bicep_path.read_text(encoding="utf-8"))

    async def get_diagnostics(self, *, bicep_text: str, logical_name: str) -> BicepDiagnosticsResult:
        with self._tempdir_factory() as workspace:
            workspace_path = Path(workspace)
            bicep_path = workspace_path / f"{logical_name}.bicep"
            bicep_path.write_text(bicep_text, encoding="utf-8")

            result = await self._command_runner(
                [self._executable, "build", "--file", bicep_path.name, "--stdout"],
                cwd=str(workspace_path),
            )
            diagnostics = _parse_bicep_diagnostics(stderr=result.stderr, default_file_path=bicep_path.name)
            if result.returncode not in {0, 1}:
                _raise_for_failed_command(result=result, action="collect Bicep diagnostics")
            return BicepDiagnosticsResult(diagnostics=diagnostics)


async def _run_subprocess(command: list[str], *, cwd: str) -> BicepCommandResult:
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return BicepCommandResult(
        returncode=process.returncode,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
    )


def _raise_for_failed_command(*, result: BicepCommandResult, action: str) -> None:
    if result.returncode == 0:
        return
    details = result.stderr.strip() or result.stdout.strip() or "no command output"
    raise BicepToolError(f"Failed to {action}: {details}")


def _normalize_bicep_text(bicep_text: str) -> str:
    normalized = bicep_text.replace("\r\n", "\n")
    if not normalized.endswith("\n"):
        normalized += "\n"
    return normalized


def _parse_bicep_diagnostics(*, stderr: str, default_file_path: str | None = None) -> list[BicepDiagnostic]:
    diagnostics: list[BicepDiagnostic] = []
    for raw_line in stderr.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parsed = _parse_bicep_diagnostic_line(line=line, default_file_path=default_file_path)
        if parsed is not None:
            diagnostics.append(parsed)
    return diagnostics


def _parse_bicep_diagnostic_line(*, line: str, default_file_path: str | None) -> BicepDiagnostic | None:
    prefix, separator, message = line.partition(": ")
    if not separator:
        return None

    prefix_tokens = prefix.split()
    if len(prefix_tokens) < 2:
        return None

    level = prefix_tokens[0].lower()
    code = prefix_tokens[1]
    file_path: str | None = default_file_path

    if len(prefix_tokens) >= 3:
        file_path = " ".join(prefix_tokens[2:]).strip("[]") or default_file_path

    return BicepDiagnostic(code=code, level=level, message=message.strip(), file_path=file_path)