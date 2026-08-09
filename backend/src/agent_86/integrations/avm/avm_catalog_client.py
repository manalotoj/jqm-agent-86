import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class AvmModuleMatch:
    module_path: str
    resource_type: str
    summary: str | None = None


class AvmCatalogError(RuntimeError):
    """Raised when the AVM catalog cannot be loaded or parsed."""


class AvmCatalogClient:
    """Boundary for AVM catalog lookups used for advisory module annotations."""

    def __init__(
        self,
        *,
        catalog_path: str | Path | None = None,
        json_loader: Callable[[str], object] | None = None,
    ) -> None:
        self._catalog_path = Path(catalog_path) if catalog_path is not None else Path(__file__).with_name("avm_catalog.json")
        self._json_loader = json_loader or json.loads
        self._matches_by_resource_type: dict[str, list[AvmModuleMatch]] | None = None

    async def ping(self) -> bool:
        try:
            self._ensure_catalog_loaded()
        except AvmCatalogError:
            return False
        return True

    async def search_module(self, *, resource_type: str) -> list[AvmModuleMatch]:
        matches_by_resource_type = self._ensure_catalog_loaded()
        normalized_resource_type = _normalize_resource_type(resource_type)
        return list(matches_by_resource_type.get(normalized_resource_type, []))

    def _ensure_catalog_loaded(self) -> dict[str, list[AvmModuleMatch]]:
        if self._matches_by_resource_type is not None:
            return self._matches_by_resource_type

        try:
            catalog_text = self._catalog_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise AvmCatalogError(f"AVM catalog file was not found: {self._catalog_path}") from exc
        except OSError as exc:
            raise AvmCatalogError(f"AVM catalog file could not be read: {self._catalog_path}") from exc

        try:
            payload = self._json_loader(catalog_text)
        except Exception as exc:
            raise AvmCatalogError(f"AVM catalog file is not valid JSON: {self._catalog_path}") from exc

        self._matches_by_resource_type = _build_catalog_index(payload=payload)
        return self._matches_by_resource_type


def _build_catalog_index(*, payload: object) -> dict[str, list[AvmModuleMatch]]:
    if not isinstance(payload, dict):
        raise AvmCatalogError("AVM catalog payload must be a JSON object")

    raw_modules = payload.get("modules")
    if not isinstance(raw_modules, list):
        raise AvmCatalogError("AVM catalog payload must contain a 'modules' list")

    matches_by_resource_type: dict[str, list[AvmModuleMatch]] = {}
    for entry in raw_modules:
        if not isinstance(entry, dict):
            raise AvmCatalogError("AVM catalog module entries must be objects")

        module_path = entry.get("module_path")
        resource_type = entry.get("resource_type")
        summary = entry.get("summary")

        if not isinstance(module_path, str) or not module_path.strip():
            raise AvmCatalogError("AVM catalog module entries must include a non-empty 'module_path'")
        if not isinstance(resource_type, str) or not resource_type.strip():
            raise AvmCatalogError("AVM catalog module entries must include a non-empty 'resource_type'")
        if summary is not None and not isinstance(summary, str):
            raise AvmCatalogError("AVM catalog module entry 'summary' values must be strings when provided")

        normalized_resource_type = _normalize_resource_type(resource_type)
        match = AvmModuleMatch(
            module_path=module_path.strip(),
            resource_type=resource_type.strip(),
            summary=summary.strip() if isinstance(summary, str) else None,
        )
        matches_by_resource_type.setdefault(normalized_resource_type, []).append(match)

    for resource_type_matches in matches_by_resource_type.values():
        resource_type_matches.sort(key=lambda match: (match.module_path, match.summary or ""))

    return matches_by_resource_type


def _normalize_resource_type(resource_type: str) -> str:
    return resource_type.strip().lower()