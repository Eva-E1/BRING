import asyncio
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mushoku_tensei.graph_builder import build_layered_graph, determine_edge_layer, determine_entity_layer
from mushoku_tensei.extraction_v2 import _build_prompt_context, _split_long_text, _unit_likely_contains_time_cues
from mushoku_tensei.ingest_v2 import reconcile_story_times
from mushoku_tensei.segmentation import _is_japanese_heavy_text, _split_long_paragraph, segment_text
from mushoku_tensei.time_parser import TimelineBuilder, estimate_story_time


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
        self.assertIn("Roxy said", segments[0]["next_excerpt"])
        self.assertIn("practiced water magic", segments[1]["previous_excerpt"])

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

    def test_estimate_story_time_supports_named_relative_markers(self):
        story_time = estimate_story_time(0, ["The next morning, Rudeus resumed practice."])

        self.assertEqual(story_time.day, 2)

    def test_estimate_story_time_supports_word_numbers_and_calendar_shorthand(self):
        age_time = estimate_story_time(0, ["Rudeus was five years old"])
        calendar_time = estimate_story_time(0, ["K423"])

        self.assertEqual(age_time.year, 5)
        self.assertEqual(calendar_time.year, 423)

    def test_timeline_builder_applies_relative_markers_sequentially(self):
        builder = TimelineBuilder()

        first = builder.apply_segment(segment_index=0, markers=["Rudeus was 5 years old"])
        second = builder.apply_segment(segment_index=1, markers=["Two years later"])
        third = builder.apply_segment(segment_index=2, markers=["Later that day"])

        self.assertEqual(first.year, 5)
        self.assertEqual(second.year, 7)
        self.assertGreater(third, second)

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

    def test_unit_likely_contains_time_cues_is_conservative(self):
        self.assertTrue(_unit_likely_contains_time_cues("The next day, Rudeus returned at dawn."))
        self.assertFalse(_unit_likely_contains_time_cues("Rudeus cast Water Ball at the wall."))

    def test_build_prompt_context_includes_neighbor_scene_hints(self):
        context = _build_prompt_context(
            unit="Rudeus practiced.",
            unit_index=1,
            unit_total=2,
            segment_context={
                "heading": "Volume 1\nChapter 1",
                "volume": 1,
                "chapter": 1,
                "scene_index": 0,
                "previous_excerpt": "Paul encouraged him.",
                "next_excerpt": "Roxy arrived the next day.",
            },
        )

        self.assertIn("Previous scene hint", context)
        self.assertIn("Paul encouraged him.", context)
        self.assertIn("Unit position inside segment: 1/2", context)

    def test_japanese_heavy_text_is_detected(self):
        self.assertTrue(_is_japanese_heavy_text("無職転生 ルーデウス の 物語"))
        self.assertFalse(_is_japanese_heavy_text("Rudeus practiced water magic in the yard."))

    def test_reconcile_story_times_keeps_segment_timeline_monotonic(self):
        segments = [
            {"index": 0, "story_time": datetime(5, 1, 1), "time_markers": ["Rudeus was 5 years old"]},
            {"index": 1, "story_time": datetime(1, 1, 2), "time_markers": ["Two years later"]},
            {"index": 2, "story_time": datetime(1, 1, 3), "time_markers": ["Later that day"]},
        ]

        reconcile_story_times(segments)

        self.assertLess(segments[0]["story_time"], segments[1]["story_time"])
        self.assertLess(segments[1]["story_time"], segments[2]["story_time"])
        self.assertEqual(segments[1]["story_time"].year, 7)

    def test_build_layered_graph_matches_edges_case_insensitively_without_mutating_source(self):
        merged = [
            {
                "index": 0,
                "text": "Rudeus uses Water Ball.",
                "story_time": datetime(5, 1, 1),
                "entities": [
                    {"name": "Rudeus", "entity_type": "Character", "attributes": {}},
                    {"name": "Water Ball", "entity_type": "Ability", "attributes": {}},
                ],
                "edges": [
                    {"source_name": "rudeus", "target_name": "water ball", "edge_type": "HasAbility", "attributes": {}},
                ],
            }
        ]

        payload = build_layered_graph(merged)

        self.assertEqual(payload[0]["metadata"]["edges"][0]["attributes"]["layer"], "rule")
        self.assertNotIn("layer", merged[0]["entities"][0]["attributes"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
