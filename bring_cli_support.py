"""Helper utilities for the BRING CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

from bring_settings import DEFAULT_SETTINGS_FILE, parse_env_file


@dataclass(slots=True)
class StartupProfile:
    provider: str
    provider_type: str
    model_provider: Optional[str]
    startup_parallelism: int
    startup_parallelism_max: int
    request_timeout_seconds: float
    structured_output_mode: str
    memory_bulk_batch: int
    graphiti_max_coroutines: int
    notes: list[str] = field(default_factory=list)


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


def assess_startup_profile(
    *,
    base_url: Optional[str],
    model: str,
    provider: str,
    provider_type: str,
) -> StartupProfile:
    model_lower = model.strip().lower()
    hostname = (urlparse(base_url).hostname or "").lower() if base_url else ""
    is_custom_openai = provider_type == "openai" and hostname not in {"", "api.openai.com"}
    is_local = hostname in {"127.0.0.1", "localhost", "0.0.0.0"}
    is_nonstandard_openai = provider_type == "openai" and not model_lower.startswith(
        ("gpt-", "o1", "o3", "o4", "text-embedding-", "omni-")
    )

    structured_output_mode = "auto"
    startup_parallelism = 4
    startup_parallelism_max = 8
    request_timeout_seconds = 90.0
    memory_bulk_batch = 5
    graphiti_max_coroutines = 10
    model_provider = None
    notes: list[str] = []

    if provider_type in {"anthropic", "cohere", "google"}:
        startup_parallelism = 2
        startup_parallelism_max = 4
        request_timeout_seconds = 120.0
        memory_bulk_batch = 3
        graphiti_max_coroutines = 6
        notes.append(f"{provider_type} startup profile favors lower concurrency and longer request timeouts.")

    if provider_type == "azure":
        startup_parallelism = 3
        startup_parallelism_max = 6
        request_timeout_seconds = 90.0
        notes.append("Azure-compatible startup profile uses moderate concurrency to absorb deployment variance.")

    if provider_type == "ollama" or is_local:
        startup_parallelism = 2
        startup_parallelism_max = 3
        request_timeout_seconds = 180.0
        structured_output_mode = "schema"
        memory_bulk_batch = 2
        graphiti_max_coroutines = 4
        notes.append("Local or Ollama-style providers default to schema-guided structured output for stability.")

    if is_custom_openai or is_nonstandard_openai:
        startup_parallelism = min(startup_parallelism, 3)
        startup_parallelism_max = min(startup_parallelism_max, 4)
        request_timeout_seconds = max(request_timeout_seconds, 120.0)
        structured_output_mode = "schema"
        model_provider = provider
        notes.append("Custom OpenAI-compatible models start in compatibility mode until they are calibrated.")

    memory_bulk_batch = max(2, min(startup_parallelism, memory_bulk_batch))
    graphiti_max_coroutines = max(memory_bulk_batch, graphiti_max_coroutines)
    return StartupProfile(
        provider=provider,
        provider_type=provider_type,
        model_provider=model_provider,
        startup_parallelism=startup_parallelism,
        startup_parallelism_max=max(startup_parallelism, startup_parallelism_max),
        request_timeout_seconds=request_timeout_seconds,
        structured_output_mode=structured_output_mode,
        memory_bulk_batch=memory_bulk_batch,
        graphiti_max_coroutines=graphiti_max_coroutines,
        notes=notes,
    )


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
                "LLM_MODEL_PROVIDER",
                "LLM_MODEL",
                "LLM_API_KEY",
                "LLM_BASE_URL",
                "LLM_TEMPERATURE",
                "LLM_MAX_TOKENS",
                "LLM_PARALLELISM",
                "LLM_MAX_PARALLELISM",
                "LLM_TIMEOUT_SECONDS",
                "LLM_STRUCTURED_OUTPUT_MODE",
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
