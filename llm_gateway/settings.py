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


def _read_str(merged: Mapping[str, str], *keys: str, default: Optional[str] = None) -> Optional[str]:
    for key in keys:
        value = merged.get(key)
        if value not in (None, ""):
            return value
    return default


def _read_int(merged: Mapping[str, str], *keys: str, default: int) -> int:
    value = _read_str(merged, *keys)
    return int(value) if value is not None else default


def _read_float(merged: Mapping[str, str], *keys: str, default: float) -> float:
    value = _read_str(merged, *keys)
    return float(value) if value is not None else default


class EmbeddingSettings(BaseModel):
    model: str = "text-embedding-3-small"
    dimensions: int = 1536


class ProviderSettings(BaseModel):
    name: str = "openai"
    api_type: Optional[str] = None
    model_provider: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    api_version: Optional[str] = None
    organization: Optional[str] = None
    default_headers: Dict[str, str] = Field(default_factory=dict)
    client_kwargs: Dict[str, Any] = Field(default_factory=dict)
    request_kwargs: Dict[str, Any] = Field(default_factory=dict)
    any_llm_kwargs: Dict[str, Any] = Field(default_factory=dict)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)

    @property
    def runtime_type(self) -> str:
        return (self.api_type or self.name).lower()

    @property
    def any_llm_provider(self) -> str:
        return self.model_provider or self.name

    def build_any_llm_kwargs(self) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = dict(self.any_llm_kwargs)
        if self.api_key is not None:
            kwargs.setdefault("api_key", self.api_key)
        if self.base_url is not None:
            kwargs.setdefault("base_url", self.base_url)
        if self.api_version is not None:
            kwargs.setdefault("api_version", self.api_version)
        if self.organization is not None:
            kwargs.setdefault("organization", self.organization)
        if self.default_headers:
            kwargs.setdefault("default_headers", dict(self.default_headers))
        return kwargs

    def build_client_kwargs(self) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = dict(self.client_kwargs)
        if self.base_url is not None:
            kwargs.setdefault("base_url", self.base_url)
        if self.api_version is not None:
            kwargs.setdefault("api_version", self.api_version)
        if self.organization is not None:
            kwargs.setdefault("organization", self.organization)
        if self.default_headers:
            kwargs.setdefault("default_headers", dict(self.default_headers))
        return kwargs


class GatewaySettings(BaseModel):
    provider_settings: ProviderSettings = Field(default_factory=ProviderSettings)
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7
    max_tokens: int = 1024

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

        provider_settings = ProviderSettings(
            name=_read_str(merged, "LLM_PROVIDER", default=ProviderSettings.model_fields["name"].default),
            api_type=_read_str(merged, "LLM_PROVIDER_TYPE"),
            model_provider=_read_str(merged, "LLM_MODEL_PROVIDER"),
            api_key=_read_str(merged, "LLM_API_KEY"),
            base_url=_read_str(merged, "LLM_BASE_URL"),
            api_version=_read_str(merged, "LLM_API_VERSION"),
            organization=_read_str(merged, "LLM_ORGANIZATION"),
            embedding=EmbeddingSettings(
                model=_read_str(
                    merged,
                    "LLM_EMBEDDING_MODEL",
                    "MEMORY_EMBEDDING_MODEL",
                    default=EmbeddingSettings.model_fields["model"].default,
                ),
                dimensions=_read_int(
                    merged,
                    "LLM_EMBEDDING_DIM",
                    "MEMORY_EMBEDDING_DIM",
                    default=EmbeddingSettings.model_fields["dimensions"].default,
                ),
            ),
        )

        return cls(
            provider_settings=provider_settings,
            model=_read_str(merged, "LLM_MODEL", default=cls.model_fields["model"].default),
            temperature=_read_float(
                merged,
                "LLM_TEMPERATURE",
                default=cls.model_fields["temperature"].default,
            ),
            max_tokens=_read_int(
                merged,
                "LLM_MAX_TOKENS",
                default=cls.model_fields["max_tokens"].default,
            ),
        )

    @property
    def provider(self) -> str:
        return self.provider_settings.name

    @property
    def provider_type(self) -> Optional[str]:
        return self.provider_settings.api_type

    @property
    def model_provider(self) -> Optional[str]:
        return self.provider_settings.model_provider

    @property
    def api_key(self) -> Optional[str]:
        return self.provider_settings.api_key

    @property
    def base_url(self) -> Optional[str]:
        return self.provider_settings.base_url

    @property
    def api_version(self) -> Optional[str]:
        return self.provider_settings.api_version

    @property
    def organization(self) -> Optional[str]:
        return self.provider_settings.organization

    @property
    def default_headers(self) -> Dict[str, str]:
        return dict(self.provider_settings.default_headers)

    @property
    def client_kwargs(self) -> Dict[str, Any]:
        return dict(self.provider_settings.client_kwargs)

    @property
    def request_kwargs(self) -> Dict[str, Any]:
        return dict(self.provider_settings.request_kwargs)

    @property
    def any_llm_kwargs(self) -> Dict[str, Any]:
        return dict(self.provider_settings.any_llm_kwargs)

    def masked_dict(self) -> Dict[str, Any]:
        data = self.model_dump()
        provider_settings = data.get("provider_settings", {})
        if provider_settings.get("api_key"):
            provider_settings["api_key"] = "***"
        data.update(
            {
                "provider": self.provider,
                "provider_type": self.provider_type,
                "model_provider": self.model_provider,
                "api_key": provider_settings.get("api_key"),
                "base_url": self.base_url,
                "api_version": self.api_version,
                "organization": self.organization,
            }
        )
        return data
