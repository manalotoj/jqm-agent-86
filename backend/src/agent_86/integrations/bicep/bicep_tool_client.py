import asyncio
import json
import shutil
import tempfile
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from agent_86.core.logging import get_logger


class BicepToolError(RuntimeError):
    """Raised when direct Bicep CLI execution fails."""


class BicepCliNotFoundError(BicepToolError):
    """Raised when the Bicep CLI executable cannot be resolved."""


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
        self._logger = get_logger(__name__).bind(configured_executable=executable)

    async def ping(self) -> bool:
        with suppress(BicepCliNotFoundError):
            executable = self._resolve_executable(raise_if_missing=True)
            try:
                result = await self._run_command(
                    [executable, "--version"],
                    cwd=str(Path.cwd()),
                    action="ping Bicep CLI",
                )
            except Exception:
                return False
            return result.returncode == 0
        return False

    async def decompile_arm_template(self, *, template_json: dict, logical_name: str) -> str:
        executable = self._resolve_executable()
        with self._tempdir_factory() as workspace:
            workspace_path = Path(workspace)
            template_path = workspace_path / f"{logical_name}.json"
            bicep_path = workspace_path / f"{logical_name}.bicep"
            template_path.write_text(json.dumps(template_json, indent=2), encoding="utf-8")

            result = await self._run_command(
                [executable, "decompile", template_path.name],
                cwd=str(workspace_path),
                action="decompile ARM template",
            )
            _raise_for_failed_command(result=result, action="decompile ARM template")

            if result.stdout.strip():
                return _normalize_bicep_text(result.stdout)
            if not bicep_path.exists():
                raise BicepToolError("Bicep decompile did not produce stdout or an output file")
            return _normalize_bicep_text(bicep_path.read_text(encoding="utf-8"))

    async def format_bicep(self, *, bicep_text: str, logical_name: str) -> str:
        executable = self._resolve_executable()
        with self._tempdir_factory() as workspace:
            workspace_path = Path(workspace)
            bicep_path = workspace_path / f"{logical_name}.bicep"
            bicep_path.write_text(bicep_text, encoding="utf-8")

            result = await self._run_command(
                [executable, "format", bicep_path.name, "--stdout"],
                cwd=str(workspace_path),
                action="format Bicep",
            )
            _raise_for_failed_command(result=result, action="format Bicep")

            if result.stdout.strip():
                return _normalize_bicep_text(result.stdout)
            return _normalize_bicep_text(bicep_path.read_text(encoding="utf-8"))

    async def get_diagnostics(self, *, bicep_text: str, logical_name: str) -> BicepDiagnosticsResult:
        executable = self._resolve_executable()
        with self._tempdir_factory() as workspace:
            workspace_path = Path(workspace)
            bicep_path = workspace_path / f"{logical_name}.bicep"
            bicep_path.write_text(bicep_text, encoding="utf-8")

            result = await self._run_command(
                [executable, "build", bicep_path.name, "--stdout"],
                cwd=str(workspace_path),
                action="collect Bicep diagnostics",
            )
            diagnostics = _parse_bicep_diagnostics(stderr=result.stderr, default_file_path=bicep_path.name)
            if result.returncode not in {0, 1}:
                _raise_for_failed_command(result=result, action="collect Bicep diagnostics")
            return BicepDiagnosticsResult(diagnostics=diagnostics)

    def _resolve_executable(self, *, raise_if_missing: bool = True) -> str:
        candidates = [self._executable]
        if self._executable == "bicep":
            candidates.append(str(Path.home() / ".azure" / "bin" / "bicep"))

        for candidate in candidates:
            if Path(candidate).is_absolute():
                resolved = candidate if Path(candidate).exists() else None
            else:
                resolved = self._which(candidate)
            if resolved:
                return resolved

        message = "Bicep CLI not installed or not on PATH"
        self._logger.error("bicep_cli_missing", candidates=candidates)
        if raise_if_missing:
            raise BicepCliNotFoundError(message)
        return self._executable

    async def _run_command(self, command: list[str], *, cwd: str, action: str) -> BicepCommandResult:
        started = time.perf_counter()
        self._logger.info("bicep_command_started", action=action, command=command, cwd=cwd)
        try:
            result = await self._command_runner(command, cwd=cwd)
        except FileNotFoundError as exc:
            self._logger.exception(
                "bicep_command_failed_missing_executable",
                action=action,
                command=command,
                cwd=cwd,
            )
            raise BicepCliNotFoundError("Bicep CLI not installed or not on PATH") from exc

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        self._logger.info(
            "bicep_command_completed",
            action=action,
            command=command,
            cwd=cwd,
            returncode=result.returncode,
            duration_ms=duration_ms,
            stdout_preview=_preview_output(result.stdout),
            stderr_preview=_preview_output(result.stderr),
        )
        return result


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


def _preview_output(value: str, *, limit: int = 500) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


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