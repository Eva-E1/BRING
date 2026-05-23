"""
BRING v2 — Enhanced utilities for atomic I/O, hashing, and data helpers.
"""
from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def atomic_write_json(path: Path, data: Any, indent: int = 2) -> None:
    """Write JSON atomically via temp file + rename. Prevents corruption on crash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=str(path.parent),
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            json.dump(data, tmp, indent=indent, ensure_ascii=False, default=str)
            tmp_name = tmp.name
        Path(tmp_name).rename(path)
    except OSError as e:
        logger.error(f"Atomic write failed for {path}: {e}")
        raise


def atomic_read_json(path: Path) -> Any:
    """Read JSON with error recovery."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # Try to find backup
        backup = path.with_suffix(path.suffix + ".bak")
        if backup.exists():
            logger.warning(f"Primary JSON corrupt, loading backup: {backup}")
            return json.loads(backup.read_text(encoding="utf-8"))
        raise


def deterministic_hash(text: str, length: int = 384) -> List[float]:
    """Generate a deterministic pseudo-embedding from text hash.
    Used as fallback when embedding API is unavailable."""
    hash_bytes = hashlib.sha256(text.encode()).digest()
    embedding = [(b - 128) / 128.0 for b in hash_bytes]
    while len(embedding) < length:
        embedding.extend(embedding[:length - len(embedding)])
    return embedding[:length]


def safe_names(items: List, key: str = "name") -> str:
    """Build comma-separated name list from items that may be dicts or strings."""
    names = []
    for it in items:
        if isinstance(it, dict):
            names.append(str(it.get(key, "")))
        elif hasattr(it, key):
            names.append(str(getattr(it, key, "")))
        elif hasattr(it, "name"):
            names.append(str(it.name))
        else:
            names.append(str(it))
    return ", ".join(names)


def truncate(text: str, max_len: int = 200) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def merge_dicts(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge overlay into base (non-destructive)."""
    result = base.copy()
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result

