import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from memory.config import MemorySettings
from memory.database import MemoryDatabaseManager
from memory.ontology import ENTITY_TYPES


class MemoryDatabaseTests(unittest.TestCase):
    def _build_episode_payload(self, segments: list[dict], group_id: str = "default") -> list[dict]:
        payload = []
        for index, segment in enumerate(segments):
            entities = []
            for entity in segment.get("entities", []):
                entity_copy = dict(entity)
                entity_copy["attributes"] = dict(entity.get("attributes", {}))
                entity_copy["attributes"].setdefault("layer", "fact")
                entities.append(entity_copy)
            payload.append(
                {
                    "name": f"segment_{index + 1:04d}",
                    "body": segment["text"],
                    "reference_time": segment.get("story_time", datetime(1, 1, 1) + timedelta(days=index)),
                    "group_id": group_id,
                    "metadata": {
                        "volume": segment.get("volume"),
                        "chapter": segment.get("chapter"),
                        "time_markers": list(segment.get("time_markers", [])),
                        "entities": entities,
                        "edges": list(segment.get("edges", [])),
                    },
                }
            )
        return payload

    def test_memory_settings_build_isolated_database_path_from_database_id(self):
        settings = MemorySettings(database_root=Path("/tmp/bring-dbs"), database_id="Mushoku Tensei / V2")

        self.assertEqual(settings.normalized_database_id, "mushoku-tensei-v2")
        self.assertEqual(
            settings.database_path,
            Path("/tmp/bring-dbs/mushoku-tensei-v2/kuzu"),
        )

    def test_database_manager_can_export_import_and_clone_database(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "databases"
            settings = MemorySettings(database_root=root, database_id="source-db")
            manager = MemoryDatabaseManager(settings)
            manager.ensure_layout()
            (manager.kuzu_path / "data.bin").write_text("graph-data", encoding="utf-8")
            manifest = manager.write_manifest(
                label="Source DB",
                source="tests",
                metadata={"group_id": "story"},
            )

            archive_path = manager.export_archive(root / "source-db.zip")
            self.assertTrue(archive_path.exists())
            self.assertEqual(manifest.database_id, "source-db")

            imported = MemoryDatabaseManager.import_archive(
                archive_path,
                MemorySettings(database_root=root, database_id="import-target"),
                database_id="import-target",
            )
            self.assertTrue((imported.kuzu_path / "data.bin").exists())
            self.assertEqual(imported.load_manifest().database_id, "import-target")

            clone = imported.clone_database("clone-db")
            self.assertTrue((clone.kuzu_path / "data.bin").exists())
            self.assertEqual(clone.load_manifest().database_id, "clone-db")

    def test_episode_payload_preserves_original_text_and_precomputed_metadata(self):
        payload = self._build_episode_payload(
            [
                {
                    "index": 0,
                    "text": "Volume 1\nChapter 1\nRudeus studies magic.",
                    "volume": 1,
                    "chapter": 1,
                    "time_markers": ["Rudeus is 5 years old"],
                    "entities": [
                        {
                            "name": "Rudeus",
                            "entity_type": "Character",
                            "attributes": {"role": "protagonist"},
                        }
                    ],
                    "edges": [],
                }
            ],
            group_id="Mushoku-Tensei",
        )

        self.assertEqual(payload[0]["body"], "Volume 1\nChapter 1\nRudeus studies magic.")
        self.assertEqual(payload[0]["metadata"]["volume"], 1)
        self.assertEqual(payload[0]["metadata"]["chapter"], 1)
        self.assertEqual(payload[0]["metadata"]["time_markers"], ["Rudeus is 5 years old"])
        self.assertEqual(payload[0]["metadata"]["entities"][0]["attributes"]["layer"], "fact")

    def test_entity_type_models_do_not_use_graphiti_reserved_fields(self):
        reserved = {"uuid", "name", "group_id", "labels", "created_at", "name_embedding", "summary", "attributes"}

        for entity_name, entity_model in ENTITY_TYPES.items():
            self.assertTrue(
                reserved.isdisjoint(entity_model.model_fields.keys()),
                msg=f"{entity_name} uses reserved Graphiti fields",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
