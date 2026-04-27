import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_gateway.settings import GatewaySettings
from memory.config import MemorySettings
from memory.maintenance import MemoryMaintenance


class SearchEdge:
    def __init__(self, uuid, score, valid_at):
        self.uuid = uuid
        self.source_node_uuid = f"src-{uuid}"
        self.target_node_uuid = f"dst-{uuid}"
        self.name = f"edge-{uuid}"
        self.fact = f"fact-{uuid}"
        self.valid_at = valid_at
        self.invalid_at = None
        self.score = score


class GatewayAndMemorySettingsTests(unittest.IsolatedAsyncioTestCase):
    def write_settings_file(self, contents: str) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        settings_path = Path(temp_dir.name) / ".llm_gateway.env"
        settings_path.write_text(contents, encoding="utf-8")
        return settings_path

    async def test_embedding_settings_live_under_gateway_provider_settings(self):
        settings_path = self.write_settings_file(
            "\n".join(
                [
                    "LLM_PROVIDER=team-gateway",
                    "LLM_PROVIDER_TYPE=openai",
                    "LLM_MODEL=gpt-4o-mini",
                    "LLM_API_KEY=secret",
                    "LLM_EMBEDDING_MODEL=text-embedding-3-large",
                    "LLM_EMBEDDING_DIM=3072",
                ]
            )
        )

        settings = GatewaySettings.from_file(settings_path)

        self.assertEqual(settings.provider, "team-gateway")
        self.assertEqual(settings.provider_settings.embedding.model, "text-embedding-3-large")
        self.assertEqual(settings.provider_settings.embedding.dimensions, 3072)
        self.assertEqual(settings.masked_dict()["provider_settings"]["api_key"], "***")

    async def test_memory_maintenance_deduplicates_and_limits_results(self):
        maintenance = MemoryMaintenance(
            MemorySettings(search_result_limit=2, search_cache_ttl_seconds=60, search_cache_maxsize=16)
        )
        now = datetime.now(UTC)

        episodes = maintenance.prepare_episode_batch(
            [
                {"name": "A", "body": "same", "reference_time": now},
                {"name": "A", "body": "same", "reference_time": now},
                {"name": "B", "body": "other", "reference_time": now + timedelta(seconds=1)},
            ],
            default_group_id="story",
        )
        self.assertEqual([episode.name for episode in episodes], ["A", "B"])

        normalized = maintenance.normalize_search_results(
            [
                SearchEdge("1", 0.3, now),
                SearchEdge("1", 0.1, now),
                SearchEdge("2", 0.9, now + timedelta(seconds=1)),
                SearchEdge("3", 0.5, now + timedelta(seconds=2)),
            ]
        )
        self.assertEqual([item["uuid"] for item in normalized], ["2", "3"])

    async def test_memory_search_cache_generation_invalidates_old_entries(self):
        maintenance = MemoryMaintenance(MemorySettings())
        cache_key = maintenance.build_search_cache_key(
            query="hero",
            group_ids=["story"],
            node_labels=["Character"],
            center_node_uuid=None,
        )

        await maintenance.cache_search(cache_key, [{"uuid": "1"}])
        self.assertEqual((await maintenance.get_cached_search(cache_key))[0]["uuid"], "1")

        maintenance.invalidate_search_cache()
        self.assertIsNone(await maintenance.get_cached_search(cache_key))


if __name__ == "__main__":
    unittest.main(verbosity=2)
