"""Core module tests for BRING v2."""

import pytest
from pathlib import Path
import tempfile
import os


class TestNameIndex:
    """Tests for the NameIndex class in world_core.store."""
    
    def test_exact_match(self):
        """Test exact name matching."""
        from world_core.store import NameIndex
        
        index = NameIndex()
        index.add("char:kaelen-001", "Kaelen", "character")
        
        result = index.resolve("Kaelen")
        assert result == "char:kaelen-001"
    
    def test_case_insensitive(self):
        """Test case-insensitive matching."""
        from world_core.store import NameIndex
        
        index = NameIndex()
        index.add("char:kaelen-001", "Kaelen", "character")
        
        result = index.resolve("kaelen")
        assert result == "char:kaelen-001"
        
        result = index.resolve("KAELEN")
        assert result == "char:kaelen-001"
    
    def test_uid_direct(self):
        """Test direct UID resolution."""
        from world_core.store import NameIndex
        
        index = NameIndex()
        index.add("char:kaelen-001", "Kaelen", "character")
        
        result = index.resolve("char:kaelen-001")
        assert result == "char:kaelen-001"
    
    def test_not_found(self):
        """Test resolution of non-existent names."""
        from world_core.store import NameIndex
        
        index = NameIndex()
        index.add("char:kaelen-001", "Kaelen", "character")
        
        result = index.resolve("NonExistent")
        assert result is None
    
    def test_remove(self):
        """Test entity removal from index."""
        from world_core.store import NameIndex
        
        index = NameIndex()
        index.add("char:kaelen-001", "Kaelen", "character")
        index.remove("char:kaelen-001", "Kaelen", "character")
        
        result = index.resolve("Kaelen")
        assert result is None
    
    def test_list_by_type(self):
        """Test listing entities by type."""
        from world_core.store import NameIndex
        
        index = NameIndex()
        index.add("char:kaelen-001", "Kaelen", "character")
        index.add("char:elara-002", "Elara", "character")
        index.add("loc:silverwood-001", "Silverwood", "location")
        
        chars = index.list_by_type("character")
        assert len(chars) == 2
        assert "char:kaelen-001" in chars
        assert "char:elara-002" in chars
        
        locs = index.list_by_type("location")
        assert len(locs) == 1
        assert "loc:silverwood-001" in locs


class TestEntityNode:
    """Tests for EntityNode model."""
    
    def test_create_entity(self):
        """Test creating an entity node."""
        from world_core.models import EntityNode, EntityType
        
        node = EntityNode(
            uid="char:test-001",
            name="Test Character",
            entity_type="character",
            l1_profile={"race": "human", "class": "warrior"},
            l2_description="A brave warrior.",
            l3_secrets=["Secret past"]
        )
        
        assert node.uid == "char:test-001"
        assert node.name == "Test Character"
        assert node.entity_type == "character"
    
    def test_entity_serialization(self):
        """Test entity to_dict and from_dict."""
        from world_core.models import EntityNode
        
        original = EntityNode(
            uid="char:test-001",
            name="Test Character",
            entity_type="character",
            l1_profile={"race": "human"},
            l2_description="Description",
            relationships=["rel:001"]
        )
        
        data = original.to_dict()
        restored = EntityNode.from_dict(data)
        
        assert restored.uid == original.uid
        assert restored.name == original.name
        assert restored.l1_profile == original.l1_profile


class TestProbabilityEngine:
    """Tests for the probability engine."""
    
    def test_basic_roll(self):
        """Test basic probability roll."""
        from world_core.probability.engine import ProbabilityEngine
        
        engine = ProbabilityEngine()
        result = engine.roll("combat", 0.5)
        
        assert isinstance(result, dict)
        assert "success" in result
        assert "quality" in result
        assert "roll_value" in result
    
    def test_deterministic_seed(self):
        """Test that same seed produces same result."""
        from world_core.probability.engine import ProbabilityEngine
        
        engine1 = ProbabilityEngine(seed=42)
        engine2 = ProbabilityEngine(seed=42)
        
        result1 = engine1.roll("combat", 0.5)
        result2 = engine2.roll("combat", 0.5)
        
        assert result1["roll_value"] == result2["roll_value"]
        assert result1["success"] == result2["success"]


class TestRomanceEngine:
    """Tests for the romance engine."""
    
    def test_create_relationship(self):
        """Test creating a romance relationship."""
        from world_core.romance.engine import RomanceEngine
        
        engine = RomanceEngine()
        engine.create_relationship("char:A", "char:B")
        
        status = engine.get_status("char:A", "char:B")
        assert status is not None
        assert status.actor == "char:A"
        assert status.partner == "char:B"
    
    def test_affection_update(self):
        """Test updating affection level."""
        from world_core.romance.engine import RomanceEngine
        
        engine = RomanceEngine()
        engine.create_relationship("char:A", "char:B")
        
        engine.update_affection("char:A", "char:B", 0.75)
        status = engine.get_status("char:A", "char:B")
        
        assert abs(status.affection - 0.75) < 0.01


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
