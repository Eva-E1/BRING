"""Helper utilities for the BRING CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

from bring_settings import DEFAULT_SETTINGS_FILE, parse_env_file


def infer_provider(base_url: Optional[str], model: str) -> tuple[str, str]:
    model_lower = model.strip().lower()
    host = (urlparse(base_url).netloc if base_url else "").lower()
    full = f"{host} {base_url or ''} {model_lower}"

    if "azure" in full:
        return "azure", "azure"
    if "anthropic" in full or model_lower.startswith("claude"):
        return "anthropic", "anthropic"
    if "cohere" in full or model_lower.startswith("command"):
        return "cohere", "cohere"
    if "ollama" in full or model_lower.startswith("llama") or "mistral" in model_lower:
        return "ollama", "ollama"
    if "gemini" in full or "google" in full:
        return "google", "google"
    return "openai", "openai"


def suggest_embedding_dimensions(model: str) -> int:
    name = model.strip().lower()
    if "3-large" in name:
        return 3072
    if "3-small" in name:
        return 1536
    if "ada-002" in name:
        return 1536
    if "bge-large" in name:
        return 1024
    if "bge-base" in name:
        return 768
    if "nomic-embed" in name:
        return 768
    return 1536


def default_database_id(project_name: str = "default") -> str:
    sanitized = "".join(ch.lower() if ch.isalnum() else "-" for ch in project_name.strip())
    sanitized = "-".join(part for part in sanitized.split("-") if part)
    return sanitized or "default"


def build_env_contents(values: Dict[str, str]) -> str:
    sections = [
        (
            "# Shared BRING configuration",
            [],
        ),
        (
            "# LLM gateway",
            [
                "LLM_PROVIDER",
                "LLM_PROVIDER_TYPE",
                "LLM_MODEL",
                "LLM_API_KEY",
                "LLM_BASE_URL",
                "LLM_TEMPERATURE",
                "LLM_MAX_TOKENS",
            ],
        ),
        (
            "# Embeddings",
            [
                "LLM_EMBEDDING_PROVIDER",
                "LLM_EMBEDDING_PROVIDER_TYPE",
                "LLM_EMBEDDING_MODEL",
                "LLM_EMBEDDING_API_KEY",
                "LLM_EMBEDDING_BASE_URL",
                "LLM_EMBEDDING_DIM",
            ],
        ),
        (
            "# Memory",
            [
                "MEMORY_DATABASE_ROOT",
                "MEMORY_DATABASE_ID",
                "MEMORY_GRAPHITI_MAX_COROUTINES",
                "MEMORY_GRAPHITI_STORE_RAW_EPISODES",
                "MEMORY_STRUCTURED_EXTRACTION",
                "MEMORY_BULK_BATCH",
                "MEMORY_SEARCH_RESULT_LIMIT",
                "MEMORY_TIMELINE_WINDOW",
                "MEMORY_SEARCH_CACHE_TTL_SECONDS",
                "MEMORY_SEARCH_CACHE_MAXSIZE",
            ],
        ),
    ]

    lines: list[str] = []
    for header, keys in sections:
        lines.append(header)
        for key in keys:
            value = values.get(key, "")
            lines.append(f"{key}={value}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def merge_env_file(
    updates: Dict[str, str],
    path: str | Path = DEFAULT_SETTINGS_FILE,
) -> Path:
    env_path = Path(path)
    current = parse_env_file(env_path) if env_path.exists() else {}
    current.update({key: value for key, value in updates.items() if value is not None})
    env_path.write_text(build_env_contents(current), encoding="utf-8")
    return env_path
