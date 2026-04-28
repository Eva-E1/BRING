import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from memory.config import MemorySettings
from memory.database import MemoryDatabaseManager
from mushoku_tensei.graph_builder import build_layered_graph


class MemoryDatabaseTests(unittest.TestCase):
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

    def test_graph_builder_preserves_original_text_and_precomputed_metadata(self):
        payload = build_layered_graph(
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
