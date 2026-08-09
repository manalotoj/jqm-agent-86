from dataclasses import dataclass
import re


_SECURE_DECORATOR_RE = re.compile(r"@secure(?:\(\))?\s*\n\s*param\s+([A-Za-z_][A-Za-z0-9_]*)\s+", re.MULTILINE)
_PLAINTEXT_DEFAULT_RE = re.compile(
    r"(^\s*param\s+([A-Za-z_][A-Za-z0-9_]*)\s+string\s*=\s*)'[^'\n]*'",
    re.MULTILINE,
)


@dataclass(frozen=True)
class SanitizationResult:
    bicep_text: str
    secure_parameter_count: int


def sanitize_bicep_secrets(*, bicep_text: str) -> SanitizationResult:
    secure_names = {match.group(1) for match in _SECURE_DECORATOR_RE.finditer(bicep_text)}
    secure_parameter_count = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal secure_parameter_count
        prefix = match.group(1)
        parameter_name = match.group(2)
        if parameter_name not in secure_names:
            return match.group(0)

        secure_parameter_count += 1
        return f"{prefix}''"

    sanitized_text = _PLAINTEXT_DEFAULT_RE.sub(_replace, bicep_text)
    return SanitizationResult(
        bicep_text=sanitized_text,
        secure_parameter_count=secure_parameter_count,
    )