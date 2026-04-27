import asyncio
import logging
import os
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pydantic import BaseModel

from llm_gateway.client import LLMClient
from llm_gateway.config import AnyLLMConfig, ProviderConfig
from llm_gateway.settings import GatewaySettings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("llm_gateway.tests")


class Person(BaseModel):
    name: str
    age: int


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().slow_callback_duration = 1.0

    @contextmanager
    def log_timing(self, label: str):
        start = time.perf_counter()
        yield
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info("%s completed in %.2f ms", label, elapsed_ms)

    def build_client(self, **config_kwargs) -> LLMClient:
        default_config = {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "enable_cache": False,
        }
        default_config.update(config_kwargs)
        enable_cache = default_config.pop("enable_cache")
        return LLMClient(AnyLLMConfig(**default_config), enable_cache=enable_cache)

    def write_settings_file(self, contents: str) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        settings_path = Path(temp_dir.name) / ".llm_gateway.env"
        settings_path.write_text(contents, encoding="utf-8")
        return settings_path

    async def test_settings_can_be_loaded_from_separate_secure_file(self):
        settings_path = self.write_settings_file(
            "\n".join(
                [
                    "LLM_PROVIDER=secure-gateway",
                    "LLM_PROVIDER_TYPE=openai",
                    "LLM_MODEL=gpt-4o-mini",
                    "LLM_API_KEY=super-secret",
                    "LLM_BASE_URL=https://gateway.internal/v1",
                    "LLM_MAX_TOKENS=2048",
                ]
            )
        )

        settings = GatewaySettings.from_file(settings_path)

        self.assertEqual(settings.provider, "secure-gateway")
        self.assertEqual(settings.provider_type, "openai")
        self.assertEqual(settings.model, "gpt-4o-mini")
        self.assertEqual(settings.base_url, "https://gateway.internal/v1")
        self.assertEqual(settings.max_tokens, 2048)
        self.assertEqual(settings.masked_dict()["api_key"], "***")

    async def test_anyllm_config_uses_separate_settings_file_by_default(self):
        settings_path = self.write_settings_file(
            "\n".join(
                [
                    "LLM_PROVIDER=company-proxy",
                    "LLM_PROVIDER_TYPE=openai",
                    "LLM_MODEL=gpt-4.1-mini",
                    "LLM_API_KEY=secret",
                    "LLM_BASE_URL=https://proxy.internal/v1",
                ]
            )
        )

        config = AnyLLMConfig.from_settings(settings_file=settings_path)

        self.assertEqual(config.provider, "company-proxy")
        self.assertEqual(config.runtime_provider, "openai")
        self.assertEqual(config.model, "gpt-4.1-mini")
        self.assertEqual(config.provider_settings.api_key, "secret")
        self.assertEqual(config.provider_settings.build_client_kwargs()["base_url"], "https://proxy.internal/v1")

    async def test_client_from_settings_builds_project_wide_configuration(self):
        settings_path = self.write_settings_file(
            "\n".join(
                [
                    "LLM_PROVIDER=team-gateway",
                    "LLM_PROVIDER_TYPE=openai",
                    "LLM_MODEL=gpt-4o-mini",
                    "LLM_API_KEY=secret",
                    "LLM_BASE_URL=https://team-gateway.internal/v1",
                ]
            )
        )

        client = LLMClient.from_settings(settings_file=settings_path, enable_cache=False)

        self.assertEqual(client.config.provider, "team-gateway")
        self.assertEqual(client.config.runtime_provider, "openai")
        self.assertEqual(client.config.provider_settings.api_key, "secret")
        self.assertEqual(
            client.config.provider_settings.build_client_kwargs()["base_url"],
            "https://team-gateway.internal/v1",
        )

    async def test_default_client_init_reads_shared_settings_file(self):
        settings_path = self.write_settings_file(
            "\n".join(
                [
                    "LLM_PROVIDER=default-shared-gateway",
                    "LLM_PROVIDER_TYPE=openai",
                    "LLM_MODEL=gpt-4o-mini",
                    "LLM_API_KEY=secret",
                    "LLM_BASE_URL=https://default-shared.internal/v1",
                ]
            )
        )

        with patch.dict(os.environ, {"LLM_GATEWAY_SETTINGS_FILE": str(settings_path)}, clear=False):
            client = LLMClient()

        self.assertEqual(client.config.provider, "default-shared-gateway")
        self.assertEqual(client.config.provider_settings.api_key, "secret")

    async def test_provider_settings_expose_custom_provider_configuration(self):
        config = AnyLLMConfig(
            provider="internal-gateway",
            provider_type="openai",
            model="meta-llama-3.1-70b-instruct",
            base_url="https://llm.internal.example/v1",
            api_key="secret",
            default_headers={"x-team": "bring"},
            client_kwargs={"timeout": 30},
            request_kwargs={"top_p": 0.2},
            extra_kwargs={"api_version": "2024-06-01", "custom_flag": True},
        )

        settings = config.provider_settings

        self.assertEqual(config.model_id, "internal-gateway/meta-llama-3.1-70b-instruct")
        self.assertEqual(config.runtime_provider, "openai")
        self.assertEqual(settings.build_client_kwargs()["base_url"], "https://llm.internal.example/v1")
        self.assertEqual(settings.build_client_kwargs()["timeout"], 30)
        self.assertEqual(settings.request_kwargs["top_p"], 0.2)
        self.assertTrue(settings.build_any_llm_kwargs()["custom_flag"])

    async def test_provider_config_can_override_runtime_and_model_routing(self):
        config = AnyLLMConfig(
            provider="friendly-name",
            model="claude-3-5-sonnet",
            provider_config=ProviderConfig(
                name="company-gateway",
                api_type="anthropic",
                model_provider="anthropic",
                api_key="secret",
                base_url="https://anthropic-proxy.internal",
                request_kwargs={"top_k": 3},
            ),
        )

        self.assertEqual(config.runtime_provider, "anthropic")
        self.assertEqual(config.model_id, "anthropic/claude-3-5-sonnet")
        self.assertEqual(config.provider_settings.build_client_kwargs()["base_url"], "https://anthropic-proxy.internal")
        self.assertEqual(config.provider_settings.request_kwargs["top_k"], 3)

    async def test_full_gateway_execution_paths_have_clear_logs(self):
        with self.log_timing("gateway execution smoke test"):
            client = self.build_client(enable_cache=True)
            text_calls = []
            structured_calls = []

            async def fake_text_call(prompt: str) -> str:
                text_calls.append(prompt)
                return "plain response"

            async def fake_structured_call(prompt: str, response_model):
                structured_calls.append((prompt, response_model))
                return '{"name":"Jane","age":28}'

            client._text_call = fake_text_call
            client._structured_call = fake_structured_call

            first = await client.generate("Summarize the request")
            second = await client.generate("Summarize the request")
            third = await client.generate("Extract Jane, 28", response_model=Person)
            fourth = await client.generate("Extract Jane, 28", response_model=Person)

        logger.info(
            "smoke results | first=%s second_provider=%s third=%s fourth_provider=%s",
            first.text,
            second.provider,
            third.text,
            fourth.provider,
        )
        self.assertEqual(first.text, "plain response")
        self.assertEqual(second.provider, "cache")
        self.assertEqual(third.text, '{"name":"Jane","age":28}')
        self.assertEqual(fourth.provider, "cache")
        self.assertEqual(text_calls, ["Summarize the request"])
        self.assertEqual(structured_calls, [("Extract Jane, 28", Person)])

    async def test_structured_generation_falls_back_to_schema_prompt_for_custom_provider(self):
        with self.log_timing("schema fallback path"):
            client = self.build_client(
                provider="custom-ollama",
                provider_type="ollama",
                model="llama3",
            )
            calls = []

            async def fake_text_call(prompt: str) -> str:
                calls.append(prompt)
                return '{"name":"John","age":30}'

            client._text_call = fake_text_call

            response = await client.generate("Extract John, 30", response_model=Person)

        self.assertEqual(response.text, '{"name":"John","age":30}')
        self.assertEqual(response.provider, "custom-ollama")
        self.assertIn("Please respond with JSON that matches this schema", calls[0])
        self.assertIn('"name"', calls[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
