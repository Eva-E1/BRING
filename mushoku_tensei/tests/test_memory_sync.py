import asyncio
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from memory.config import MemorySettings
from memory.engine import MemoryEngine
from mushoku_tensei.graph_builder import build_layered_graph
from mushoku_tensei.ingest_v2 import validate_gateway_configuration
from mushoku_tensei.ingest_v2 import (
    load_segment_checkpoint,
    mark_segment_extracted,
    resume_or_initialize_state,
    save_segment_checkpoint,
)
from mushoku_tensei.ontology_extended import ENTITY_TYPES_EXTENDED


class MemorySyncTests(unittest.TestCase):
    def test_validate_gateway_configuration_requires_llm_and_embedding_keys(self):
        client = MagicMock()
        client.config.provider_settings.api_key = None
        client.config.provider_settings.embedding.api_key = None

        with self.assertRaisesRegex(RuntimeError, "LLM provider API key is missing"):
            validate_gateway_configuration(client)

        client.config.provider_settings.api_key = "secret"
        with self.assertRaisesRegex(RuntimeError, "Embedding provider API key is missing"):
            validate_gateway_configuration(client)

        client.config.provider_settings.embedding.api_key = "embed-secret"
        validate_gateway_configuration(client)

    def test_graph_payload_preserves_mushoku_metadata_for_memory_ingestion(self):
        payload = build_layered_graph(
            [
                {
                    "index": 0,
                    "text": "Volume 1\n\nChapter 1\n\nRudeus studies magic.",
                    "volume": 1,
                    "chapter": 1,
                    "heading": "Volume 1\nChapter 1",
                    "scene_index": 0,
                    "segment_kind": "chapter_scene",
                    "time_markers": ["Rudeus was 5 years old"],
                    "story_time": datetime(5, 1, 1),
                    "entities": [
                        {
                            "name": "Rudeus",
                            "entity_type": "Character",
                            "attributes": {"role": "protagonist"},
                        },
                        {
                            "name": "Water Ball",
                            "entity_type": "Ability",
                            "attributes": {"category": "elemental"},
                        },
                    ],
                    "edges": [
                        {
                            "source_name": "Rudeus",
                            "target_name": "Water Ball",
                            "edge_type": "HasAbility",
                            "attributes": {},
                        }
                    ],
                }
            ],
            group_id="Mushoku-Tensei",
        )

        episode = payload[0]
        self.assertEqual(episode["metadata"]["volume"], 1)
        self.assertEqual(episode["metadata"]["chapter"], 1)
        self.assertEqual(episode["metadata"]["heading"], "Volume 1\nChapter 1")
        self.assertEqual(episode["metadata"]["scene_index"], 0)
        self.assertEqual(episode["metadata"]["segment_kind"], "chapter_scene")
        self.assertEqual(episode["metadata"]["entities"][0]["attributes"]["layer"], "fact")
        self.assertEqual(episode["metadata"]["entities"][1]["attributes"]["layer"], "rule")
        self.assertEqual(episode["metadata"]["edges"][0]["attributes"]["layer"], "rule")

    def test_memory_engine_ingests_mushoku_payload_sequentially_with_metadata(self):
        settings = MemorySettings(database_id="mushoku-test-sync")
        engine = MemoryEngine(settings, entity_types=ENTITY_TYPES_EXTENDED)
        engine._graph = MagicMock()
        engine._graph.graphiti = MagicMock()
        engine._graph.graphiti.add_episode = AsyncMock()

        episodes = [
            {
                "name": "segment_0002",
                "body": "second",
                "reference_time": datetime(5, 1, 2),
                "group_id": "Mushoku-Tensei",
                "uuid": "2",
                "metadata": {"volume": 1, "chapter": 2},
            },
            {
                "name": "segment_0001",
                "body": "first",
                "reference_time": datetime(5, 1, 1),
                "group_id": "Mushoku-Tensei",
                "uuid": "1",
                "metadata": {"volume": 1, "chapter": 1},
            },
        ]

        asyncio.run(engine.add_episodes_bulk(episodes, group_id="Mushoku-Tensei"))

        calls = engine._graph.graphiti.add_episode.await_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].kwargs["name"], "segment_0001")
        self.assertEqual(calls[1].kwargs["name"], "segment_0002")
        self.assertEqual(calls[0].kwargs["group_id"], "Mushoku-Tensei")
        self.assertIn("volume=1", calls[0].kwargs["source_description"])
        self.assertIn("chapter=1", calls[0].kwargs["source_description"])

    def test_ingestion_checkpoint_state_can_resume_segment_results(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = MemorySettings(database_root=Path(tmp_dir), database_id="mushoku-resume")
            full_text = "Volume 1\n\nChapter 1\n\nRudeus studies magic."
            segments = [{"index": 0, "text": full_text}]

            state = resume_or_initialize_state(settings, full_text, segments)
            self.assertEqual(state["status"], "extracting")

            payload = {
                "index": 0,
                "text": full_text,
                "entities": [],
                "edges": [],
                "time_markers": ["Rudeus was 5 years old"],
                "story_time": datetime(5, 1, 1),
            }
            save_segment_checkpoint(settings, 0, payload)
            mark_segment_extracted(settings, state, 0)

            restored = load_segment_checkpoint(settings, 0)
            self.assertEqual(restored["index"], 0)
            self.assertEqual(restored["story_time"], datetime(5, 1, 1))

            resumed_state = resume_or_initialize_state(settings, full_text, segments)
            self.assertEqual(resumed_state["completed_extraction_indices"], [0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
