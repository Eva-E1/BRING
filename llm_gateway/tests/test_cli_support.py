import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bring_cli_support import (
    build_env_contents,
    default_database_id,
    infer_provider,
    merge_env_file,
    suggest_embedding_dimensions,
)


class CliSupportTests(unittest.TestCase):
    def test_infer_provider_from_model_and_url(self):
        self.assertEqual(infer_provider("https://api.openai.com/v1", "gpt-4o-mini"), ("openai", "openai"))
        self.assertEqual(infer_provider("https://my-azure.example.com", "gpt-4o"), ("azure", "azure"))
        self.assertEqual(infer_provider(None, "claude-3-5-sonnet"), ("anthropic", "anthropic"))

    def test_suggest_embedding_dimensions(self):
        self.assertEqual(suggest_embedding_dimensions("text-embedding-3-large"), 3072)
        self.assertEqual(suggest_embedding_dimensions("text-embedding-3-small"), 1536)
        self.assertEqual(suggest_embedding_dimensions("unknown-model"), 1536)

    def test_default_database_id(self):
        self.assertEqual(default_database_id("Mushoku Tensei V2"), "mushoku-tensei-v2")
        self.assertEqual(default_database_id("  "), "default")

    def test_merge_env_file_writes_clean_root_config(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / ".bring.env"
            merge_env_file(
                {
                    "LLM_PROVIDER": "openai",
                    "LLM_MODEL": "gpt-4o-mini",
                    "LLM_API_KEY": "secret",
                    "MEMORY_DATABASE_ID": "default",
                },
                path,
            )
            contents = path.read_text(encoding="utf-8")
            self.assertIn("# LLM gateway", contents)
            self.assertIn("LLM_PROVIDER=openai", contents)
            self.assertIn("MEMORY_DATABASE_ID=default", contents)

    def test_build_env_contents_keeps_sections(self):
        contents = build_env_contents({"LLM_PROVIDER": "openai"})
        self.assertIn("# Shared BRING configuration", contents)
        self.assertIn("# Embeddings", contents)
        self.assertIn("LLM_PROVIDER=openai", contents)


if __name__ == "__main__":
    unittest.main(verbosity=2)
