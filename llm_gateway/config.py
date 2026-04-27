from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from .settings import GatewaySettings, ProviderSettings


class ProviderConfig(ProviderSettings):
    api_key: Optional[str] = Field(default=None, env="LLM_API_KEY")
    base_url: Optional[str] = Field(default=None, env="LLM_BASE_URL")
    api_version: Optional[str] = Field(default=None, env="LLM_API_VERSION")
    organization: Optional[str] = Field(default=None, env="LLM_ORGANIZATION")


class AnyLLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-3.5-turbo"
    api_key: Optional[str] = Field(default=None, env="LLM_API_KEY")
    base_url: Optional[str] = Field(default=None, env="LLM_BASE_URL")
    api_version: Optional[str] = Field(default=None, env="LLM_API_VERSION")
    organization: Optional[str] = Field(default=None, env="LLM_ORGANIZATION")
    provider_type: Optional[str] = None
    model_provider: Optional[str] = None
    default_headers: Dict[str, str] = Field(default_factory=dict)
    client_kwargs: Dict[str, Any] = Field(default_factory=dict)
    request_kwargs: Dict[str, Any] = Field(default_factory=dict)
    temperature: float = 0.7
    max_tokens: int = 1024
    extra_kwargs: Dict[str, Any] = Field(default_factory=dict)
    provider_config: Optional[ProviderConfig] = None

    @classmethod
    def from_settings(
        cls,
        settings: Optional[GatewaySettings] = None,
        *,
        settings_file: Optional[str | Path] = None,
        **overrides: Any,
    ) -> "AnyLLMConfig":
        resolved_settings = settings or GatewaySettings.from_file(settings_file)
        payload: Dict[str, Any] = {
            "provider": resolved_settings.provider,
            "provider_type": resolved_settings.provider_type,
            "model_provider": resolved_settings.model_provider,
            "model": resolved_settings.model,
            "api_key": resolved_settings.api_key,
            "base_url": resolved_settings.base_url,
            "api_version": resolved_settings.api_version,
            "organization": resolved_settings.organization,
            "temperature": resolved_settings.temperature,
            "max_tokens": resolved_settings.max_tokens,
            "default_headers": dict(resolved_settings.default_headers),
            "client_kwargs": dict(resolved_settings.client_kwargs),
            "request_kwargs": dict(resolved_settings.request_kwargs),
            "extra_kwargs": dict(resolved_settings.any_llm_kwargs),
            "provider_config": ProviderConfig.model_validate(
                resolved_settings.provider_settings.model_dump()
            ),
        }
        payload.update(overrides)
        return cls(**payload)

    @property
    def provider_settings(self) -> ProviderConfig:
        if self.provider_config is not None:
            return self.provider_config

        legacy_client_kwargs = dict(self.extra_kwargs.get("client_kwargs", {}))
        legacy_request_kwargs = dict(self.extra_kwargs.get("request_kwargs", {}))
        legacy_any_llm_kwargs = {
            key: value
            for key, value in self.extra_kwargs.items()
            if key not in {"client_kwargs", "request_kwargs"}
        }
        return ProviderConfig(
            name=self.provider,
            api_type=self.provider_type,
            model_provider=self.model_provider,
            api_key=self.api_key,
            base_url=self.base_url,
            api_version=self.api_version,
            organization=self.organization,
            default_headers=dict(self.default_headers),
            client_kwargs={**legacy_client_kwargs, **self.client_kwargs},
            request_kwargs={**legacy_request_kwargs, **self.request_kwargs},
            any_llm_kwargs=legacy_any_llm_kwargs,
        )

    @property
    def runtime_provider(self) -> str:
        return self.provider_settings.runtime_type

    @property
    def model_id(self) -> str:
        return f"{self.provider_settings.any_llm_provider}/{self.model}"
