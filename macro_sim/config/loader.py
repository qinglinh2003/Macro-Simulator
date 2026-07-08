"""YAML-backed configuration loading.

Configuration files are small overlay documents. Each file may extend one or
more other files, then override a subset of ``Config`` fields under ``params``.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Mapping

import yaml

from macro_sim.config.model import Config

_ALLOWED_TOP_LEVEL_KEYS = {"extends", "metadata", "params"}
_CONFIG_FIELDS = {field.name for field in dataclasses.fields(Config)}


def config_to_dict(cfg: Config) -> dict[str, Any]:
    """Return a plain resolved parameter dictionary for a ``Config`` instance."""
    return dataclasses.asdict(cfg)


def load_config_file(path: str | Path, *, overrides: Mapping[str, Any] | None = None) -> Config:
    """Load a ``Config`` from a YAML file and optional final overrides."""
    params = resolve_config_params(path)
    if overrides:
        _validate_params(overrides, source="<overrides>")
        params.update(dict(overrides))
    return Config(**params)


def resolve_config_params(path: str | Path) -> dict[str, Any]:
    """Resolve YAML ``extends`` and return merged Config constructor params."""
    return _resolve_config_params(Path(path), stack=[])


def _resolve_config_params(path: Path, *, stack: list[Path]) -> dict[str, Any]:
    path = path.expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()

    if path in stack:
        cycle = " -> ".join(str(p) for p in [*stack, path])
        raise ValueError(f"Config extends cycle detected: {cycle}")
    if not path.exists():
        raise FileNotFoundError(path)

    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top-level YAML value must be a mapping")

    unknown_sections = set(raw) - _ALLOWED_TOP_LEVEL_KEYS
    if unknown_sections:
        names = ", ".join(sorted(unknown_sections))
        raise ValueError(f"{path}: unknown top-level key(s): {names}")

    params: dict[str, Any] = {}
    for parent in _extends_list(raw.get("extends")):
        parent_path = Path(parent)
        if not parent_path.is_absolute():
            parent_path = path.parent / parent_path
        params.update(_resolve_config_params(parent_path, stack=[*stack, path]))

    local_params = raw.get("params") or {}
    if not isinstance(local_params, dict):
        raise ValueError(f"{path}: params must be a mapping")
    _validate_params(local_params, source=str(path))
    params.update(local_params)
    return params


def _extends_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise ValueError("extends must be a string or a list of strings")


def _validate_params(params: Mapping[str, Any], *, source: str) -> None:
    unknown = sorted(set(params) - _CONFIG_FIELDS)
    if unknown:
        names = ", ".join(unknown)
        raise ValueError(f"{source}: unknown Config field(s): {names}")
