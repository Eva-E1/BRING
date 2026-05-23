"""Deterministic memory scoring engine - no LLM involvement."""
import math
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .world_memory import WorldMemoryEntry

class MemoryScoringEngine:
    """Deterministic scoring for memory retention decisions."""

    def __init__(self, weights: dict, half_life_days: float):
        self.weights = weights
        self.half_life = half_life_days

    def compute_score(self, entry: "WorldMemoryEntry", current_time: datetime) -> float:
        """
        Compute a deterministic retention score for a memory entry.

        Score is a weighted combination of:
        - importance: Base importance of the memory (0-1)
        - recency: Exponential decay based on age
        - access: Number of times accessed (boosts retention)
        - emotion: Emotional valence magnitude
        - relevance: Story relevance score
        """
        # Calculate recency with exponential decay (half-life based)
        days = (current_time - entry.timestamp).days
        recency = math.exp(-days / self.half_life)

        # Get memory attributes
        imp = entry.metadata.get("importance", entry.importance)
        accesses = min(entry.metadata.get("access_count", 0) / 10.0, 1.0)
        emotion = abs(entry.metadata.get("emotional_valence", 0.0))
        relevance = entry.metadata.get("story_relevance", 0.5)

        # Compute weighted score
        score = (
            self.weights["importance"] * imp +
            self.weights["recency"] * recency +
            self.weights["access"] * accesses +
            self.weights["emotion"] * emotion +
            self.weights["relevance"] * relevance
        )

        return min(1.0, max(0.0, score))

    def compute_salience(self, entry: "WorldMemoryEntry", current_time: datetime) -> float:
        """
        Compute salience score with access boost and decay.

        Salience determines how prominent a memory is in attention.
        It combines base importance with recency decay and access frequency.
        """
        days = (current_time - entry.timestamp).days
        base_importance = entry.metadata.get("importance", entry.importance)

        # Exponential decay based on half-life
        decay = 2 ** (-days / self.half_life)

        # Access count provides a logarithmic boost
        access_count = entry.metadata.get("access_count", 0)
        access_boost = math.log1p(access_count) * 0.1

        # Calculate final salience
        salience = base_importance * decay + access_boost

        return min(1.0, max(0.0, salience))

