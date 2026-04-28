"""Shared project settings helpers for BRING's root configuration file."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Mapping, Optional, Sequence

DEFAULT_SETTINGS_FILE = ".bring.env"


def parse_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def merge_settings_sources(
    file_values: Mapping[str, str],
    env_values: Mapping[str, str],
) -> Dict[str, str]:
    merged = dict(file_values)
    for key, value in env_values.items():
        if value:
            merged[key] = value
    return merged


def resolve_settings_path(
    path: Optional[str | Path],
    *,
    env_var_names: Sequence[str],
    default_files: Sequence[str],
) -> Path:
    if path is not None:
        return Path(path)

    for env_var in env_var_names:
        configured = os.getenv(env_var)
        if configured:
            return Path(configured)

    for candidate in default_files:
        candidate_path = Path(candidate)
        if candidate_path.exists():
            return candidate_path

    return Path(default_files[0])


def load_settings(
    path: Optional[str | Path],
    *,
    env: Optional[Mapping[str, str]],
    env_var_names: Sequence[str],
    default_files: Sequence[str],
) -> Dict[str, str]:
    settings_path = resolve_settings_path(
        path,
        env_var_names=env_var_names,
        default_files=default_files,
    )
    file_values = parse_env_file(settings_path)
    runtime_env = env if env is not None else os.environ
    return merge_settings_sources(file_values, runtime_env)


def read_str(merged: Mapping[str, str], *keys: str, default: Optional[str] = None) -> Optional[str]:
    for key in keys:
        value = merged.get(key)
        if value not in (None, ""):
            return value
    return default


def read_int(merged: Mapping[str, str], *keys: str, default: int) -> int:
    value = read_str(merged, *keys)
    return int(value) if value is not None else default


def read_float(merged: Mapping[str, str], *keys: str, default: float) -> float:
    value = read_str(merged, *keys)
    return float(value) if value is not None else default


def read_bool(merged: Mapping[str, str], *keys: str, default: bool) -> bool:
    value = read_str(merged, *keys)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
