import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from pydantic import BaseModel, Field


DEFAULT_SETTINGS_FILE = ".llm_gateway.env"


def _parse_env_file(path: Path) -> Dict[str, str]:
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


def _merge_settings_sources(
    file_values: Mapping[str, str],
    env_values: Mapping[str, str],
) -> Dict[str, str]:
    merged = dict(file_values)
    for key, value in env_values.items():
        if value:
            merged[key] = value
    return merged


class GatewaySettings(BaseModel):
    provider: str = "openai"
    provider_type: Optional[str] = None
    model_provider: Optional[str] = None
    model: str = "gpt-3.5-turbo"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    api_version: Optional[str] = None
    organization: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 1024
    default_headers: Dict[str, str] = Field(default_factory=dict)
    client_kwargs: Dict[str, Any] = Field(default_factory=dict)
    request_kwargs: Dict[str, Any] = Field(default_factory=dict)
    any_llm_kwargs: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_file(
        cls,
        path: Optional[str | Path] = None,
        *,
        env: Optional[Mapping[str, str]] = None,
    ) -> "GatewaySettings":
        settings_path = Path(path or os.getenv("LLM_GATEWAY_SETTINGS_FILE", DEFAULT_SETTINGS_FILE))
        file_values = _parse_env_file(settings_path)
        runtime_env = env if env is not None else os.environ
        merged = _merge_settings_sources(file_values, runtime_env)

        return cls(
            provider=merged.get("LLM_PROVIDER", cls.model_fields["provider"].default),
            provider_type=merged.get("LLM_PROVIDER_TYPE"),
            model_provider=merged.get("LLM_MODEL_PROVIDER"),
            model=merged.get("LLM_MODEL", cls.model_fields["model"].default),
            api_key=merged.get("LLM_API_KEY"),
            base_url=merged.get("LLM_BASE_URL"),
            api_version=merged.get("LLM_API_VERSION"),
            organization=merged.get("LLM_ORGANIZATION"),
            temperature=float(merged.get("LLM_TEMPERATURE", cls.model_fields["temperature"].default)),
            max_tokens=int(merged.get("LLM_MAX_TOKENS", cls.model_fields["max_tokens"].default)),
        )

    def masked_dict(self) -> Dict[str, Any]:
        data = self.model_dump()
        if data.get("api_key"):
            data["api_key"] = "***"
        return data
