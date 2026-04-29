import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mushoku_tensei.graph_builder import determine_edge_layer, determine_entity_layer
from mushoku_tensei.extraction_v2 import _split_long_text
from mushoku_tensei.segmentation import _split_long_paragraph, segment_text
from mushoku_tensei.time_parser import estimate_story_time


class MushokuPipelineAccuracyTests(unittest.TestCase):
    def test_segment_text_preserves_heading_and_splits_long_section_semantically(self):
        text = (
            "Volume 1\n\n"
            "Chapter 1\n\n"
            "Rudeus opened the book and practiced water magic. "
            "He repeated the chant until the air shook around him.\n\n"
            "\"Again,\" Roxy said. \"Focus on the image in your mind first.\"\n\n"
            "The next day, he tried the spell outside near the training yard. "
            "Paul watched him from a distance while Zenith carried laundry."
        )

        segments = asyncio.run(segment_text(text, min_chunk_chars=80, max_chunk_chars=150))

        self.assertGreaterEqual(len(segments), 2)
        self.assertTrue(all("Chapter 1" in segment["heading"] for segment in segments))
        self.assertTrue(all(segment["text"].startswith("Volume 1") for segment in segments))
        self.assertEqual(segments[0]["volume"], 1)
        self.assertEqual(segments[0]["chapter"], 1)

    def test_determine_layers_uses_story_rule_and_fact_conservatively(self):
        event = {"name": "Rudeus trains magic", "entity_type": "Event", "attributes": {}}
        character = {"name": "Rudeus", "entity_type": "Character", "attributes": {}}
        concept = {"name": "Family", "entity_type": "Concept", "attributes": {}}
        ability = {"name": "Water Ball", "entity_type": "Ability", "attributes": {"category": "elemental"}}

        self.assertEqual(determine_entity_layer(event), "story")
        self.assertEqual(determine_entity_layer(character), "fact")
        self.assertEqual(determine_entity_layer(concept), "concept")
        self.assertEqual(determine_entity_layer(ability), "rule")

        entity_lookup = {
            "Rudeus": {"attributes": {"layer": "fact"}},
            "Water Ball": {"attributes": {"layer": "rule"}},
            "Rudeus trains magic": {"attributes": {"layer": "story"}},
        }
        self.assertEqual(
            determine_edge_layer(
                {"source_name": "Rudeus", "target_name": "Water Ball", "edge_type": "HasAbility", "attributes": {}},
                entity_lookup,
            ),
            "rule",
        )
        self.assertEqual(
            determine_edge_layer(
                {"source_name": "Rudeus", "target_name": "Rudeus trains magic", "edge_type": "ParticipatedIn", "attributes": {}},
                entity_lookup,
            ),
            "story",
        )

    def test_estimate_story_time_ignores_implausible_large_years(self):
        story_time = estimate_story_time(
            0,
            [
                "Rudeus was 5 years old",
                "Year 6996 of the Armored Dragon Calendar",
            ],
        )
        self.assertEqual(story_time.year, 5)

    def test_split_long_paragraph_hard_wraps_oversized_sentences(self):
        paragraph = ("A" * 950) + ". short."

        chunks = _split_long_paragraph(paragraph, 900)

        self.assertEqual(chunks[-1], "short.")
        self.assertTrue(all(len(chunk) <= 900 for chunk in chunks))

    def test_split_long_text_hard_wraps_oversized_sentences(self):
        text = ("A" * 750) + ". short."

        chunks = _split_long_text(text, 700)

        self.assertEqual(chunks[-1], "short.")
        self.assertTrue(all(len(chunk) <= 700 for chunk in chunks))


if __name__ == "__main__":
    unittest.main(verbosity=2)
