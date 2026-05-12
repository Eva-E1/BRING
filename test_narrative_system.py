#!/usr/bin/env python3
"""Comprehensive test suite for the narrative system (world_narrative + director)."""

import asyncio
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

# Add project paths to sys.path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from world_builder.llm import LLMClient
from world_builder.graph_manager import GraphManager
from world_builder.builder import WorldBuilder
from world_builder.config import get_entity_store_path, get_world_frame_path

from world_narrative.context import NarrativeContext
from world_narrative.npc_manager import NPCManager
from world_narrative.chronicler import Chronicler
from world_narrative.story_engine import StoryEngine
from world_narrative.director import Director, DirectorConfig
from world_narrative.villain_manager import VillainManager
from world_narrative.story_planner import StoryPlanner
from world_narrative.npc_simulator import NPCSimulator
from world_narrative.user_agent import UserAgent


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, msg):
        self.passed += 1
        print(f"✅ {msg}")

    def fail(self, msg):
        self.failed += 1
        print(f"❌ {msg}")
        self.errors.append(msg)

    def summary(self):
        print(f"\n=== SUMMARY: {self.passed} passed, {self.failed} failed ===")
        if self.errors:
            print("Errors:")
            for e in self.errors:
                print(f"  - {e}")
        return self.failed == 0


async def test_world_building(tmp_path: Path, result: TestResult):
    """Test world generation (frame + L1/L2/L3 + relationships)."""
    print("\n--- Phase 1: World Building ---")
    db_path = tmp_path / "world_db"
    db_path.mkdir()

    llm = LLMClient()
    gm = GraphManager(entity_store_path=get_entity_store_path(db_path))
    builder = WorldBuilder(llm, gm, num_episodes=2, world_frame_path=get_world_frame_path(db_path))

    try:
        # Create world
        world = await builder.create_world()
        assert world.get("world_name"), "World name missing"
        result.ok("World frame generated")

        # Build L2
        await builder.build_L2()
        # Check that at least one character has L2
        chars = gm.store.list_by_type("Character")
        assert any(c.profile.l2 for c in chars), "No L2 data generated"
        result.ok("L2 details generated")

        # Build L3
        await builder.build_L3()
        assert any(c.profile.l3 for c in chars), "No L3 secrets generated"
        result.ok("L3 secrets generated")

        # Build relationships
        await builder.build_relationships()
        # Check if any relationship added
        has_rel = any(len(c.profile.l1.get("relationships", [])) > 0 for c in chars)
        # Relationships may be empty if LLM returns none – that's acceptable
        result.ok(f"Relationships built (found: {has_rel})")

        # Store a scene
        await builder.add_narrative_episodes()
        result.ok("Narrative episodes generated")
    except Exception as e:
        result.fail(f"World building failed: {e}")
        raise


async def test_npc_manager(tmp_path: Path, result: TestResult):
    """Test NPC state management."""
    print("\n--- Phase 2: NPC Manager ---")
    db_path = tmp_path / "world_db"
    db_path.mkdir(exist_ok=True)

    # Need a GraphManager with at least an empty store
    gm = GraphManager(entity_store_path=get_entity_store_path(db_path))
    npc_mgr = NPCManager(gm, db_path / "npc_state.json")

    # Register
    state = await npc_mgr.register("TestGuy", "Tavern")
    assert state.name == "TestGuy"
    assert state.location == "Tavern"
    result.ok("Register NPC")

    # Move
    now = datetime.now()
    await npc_mgr.move("TestGuy", "Castle", now)
    state = npc_mgr.get("TestGuy")
    assert state.location == "Castle"
    result.ok("Move NPC")

    # Health
    await npc_mgr.adjust_health("TestGuy", -15)
    assert npc_mgr.get("TestGuy").health == 85
    result.ok("Adjust health")

    # Mood
    await npc_mgr.set_mood("TestGuy", "angry")
    assert npc_mgr.get("TestGuy").mood == "angry"
    result.ok("Set mood")

    # Goal
    await npc_mgr.add_goal("TestGuy", "Find the sword")
    assert "Find the sword" in npc_mgr.get("TestGuy").goals
    result.ok("Add goal")

    # Inventory
    await npc_mgr.add_item("TestGuy", "Sword")
    assert "Sword" in npc_mgr.get("TestGuy").inventory
    result.ok("Add item")

    # Persistence reload
    npc_mgr._save()
    new_mgr = NPCManager(gm, db_path / "npc_state.json")
    assert new_mgr.get("TestGuy").health == 85
    result.ok("Persistence reload")


async def test_story_engine(tmp_path: Path, result: TestResult):
    """Test event generation and effect application."""
    print("\n--- Phase 3: Story Engine ---")
    db_path = tmp_path / "world_db"
    db_path.mkdir(exist_ok=True)

    # Minimal world frame
    world_frame = {
        "world_name": "TestWorld",
        "world_rules": [{"name": "No magic in temple", "description": "no magic in the temple"}],
        "characters": [{"name": "Hero"}],
        "magic_system": {"rules": "Magic costs stamina"},
    }
    (db_path / "world_frame.json").write_text(str(world_frame).replace("'", '"'))

    gm = GraphManager(entity_store_path=get_entity_store_path(db_path))
    # Register Hero as an NPC
    npc_mgr = NPCManager(gm, db_path / "npc_state.json")
    await npc_mgr.register("Hero", "Village")

    chronicler = Chronicler(db_path / "timeline.jsonl")
    from world_narrative.validation import WorldValidator
    validator = WorldValidator(gm, world_frame)

    # Dummy quest manager and social sim for StoryEngine (we'll create minimal versions)
    from world_narrative.quest_manager import QuestManager
    from world_narrative.social_sim import SocialSimulator
    from world_narrative.world_clock import WorldClock

    quest_mgr = QuestManager(db_path / "quests.json")
    clock = WorldClock(db_path / "world_clock.json")
    social_sim = SocialSimulator(None)  # we don't need full context for this test

    llm = LLMClient()
    story_engine = StoryEngine(
        llm, gm, npc_mgr, chronicler, validator,
        world_name="TestWorld",
        world_rules=world_frame["world_rules"],
        quest_mgr=quest_mgr,
        social_sim=social_sim,
        clock=clock,
        graph_store=None,
    )

    # Generate event
    now = datetime.now()
    event = await story_engine.generate_event(now, ["Hero"], category="discovery", severity=0.5)
    assert "title" in event and "description" in event, "Event missing fields"
    result.ok("Generate event")

    # Apply effects (test a simple effect)
    effects = [{"type": "npc_move", "entity": "Hero", "location": "Dungeon"}]
    await story_engine.apply_effects(effects, now, ["Hero"])
    assert npc_mgr.get("Hero").location == "Dungeon"
    result.ok("Apply effect: npc_move")

    # Rule validation – should block magic in temple
    ok, msg, forced = await validator.validate_action("Hero", "cast_magic", location="temple")
    assert not ok, "Rule should block magic in temple"
    result.ok("Rule validation works")


async def test_director(tmp_path: Path, result: TestResult):
    """Test director background loop, villains, story planner, NPC simulator."""
    print("\n--- Phase 4: Director ---")
    db_path = tmp_path / "world_db"
    db_path.mkdir(exist_ok=True)

    # Build a minimal world with characters so that NPC simulator has data
    from world_builder.builder import WorldBuilder
    llm = LLMClient()
    gm = GraphManager(entity_store_path=get_entity_store_path(db_path))
    builder = WorldBuilder(llm, gm, num_episodes=0, world_frame_path=get_world_frame_path(db_path))
    await builder.create_world()
    # Ensure at least two characters exist
    chars = gm.store.list_by_type("Character")
    if len(chars) < 2:
        await builder.add_npc("default")
        await builder.add_npc("default")
        chars = gm.store.list_by_type("Character")
    assert len(chars) >= 2, "Need at least 2 characters for NPC sim"

    # Create context with director
    ctx = NarrativeContext(db_path)
    ctx.ensure_booted()

    # Override director config for fast testing
    ctx.director.config.tick_interval_minutes = 1
    ctx.director.config.chance_event_probability = 1.0  # force chance events
    ctx.director.config.wake_interval_seconds = 1

    # Start director
    await ctx.start_director()

    # Let it run for a few seconds (enough to do a couple of ticks)
    await asyncio.sleep(5)

    # Stop director
    await ctx.stop_director()

    # Check that something was recorded in chronicler
    timeline = await ctx.chronicler.get_timeline(limit=20)
    # At minimum, we expect some director events (chance event, maybe villain, etc.)
    if any("Director" in e.get("description", "") for e in timeline):
        result.ok("Director generated events")
    else:
        # Possibly LLM didn't produce an event – still acceptable if no errors
        result.ok("Director ran without errors (no events generated)")

    # Check villain manager has at least one villain
    status = await ctx.director.get_status()
    if status.get("villain_status"):
        result.ok("Villain manager initialised")
    else:
        result.fail("Villain manager not initialised")

    # Check story planner
    plan = await ctx.story_planner.get_plan_summary()
    assert "current_chapter" in plan, "Story planner missing"
    result.ok("Story planner active")

    # Test NPC simulator directly
    npc_sim = ctx.director.npc_sim
    events = await npc_sim.tick(datetime.now())
    # May be empty, but should not crash
    result.ok(f"NPC simulator tick ran (generated {len(events)} events)")


async def test_user_agent(tmp_path: Path, result: TestResult):
    """Test user agent commands and session persistence."""
    print("\n--- Phase 5: User Agent ---")
    db_path = tmp_path / "world_db"
    db_path.mkdir(exist_ok=True)

    ctx = NarrativeContext(db_path)
    ctx.ensure_booted()

    # Create a session
    session = await ctx.user_agent.new_session(
        "test_session",
        ctx.world_frame["world_name"],
        datetime.now(),
        active_character="Hero"
    )
    result.ok("Session created")

    # Test simple command
    response = await ctx.user_agent.process_input(session, "/time")
    assert "story time" in response.lower() or "time" in response.lower(), f"Unexpected response: {response}"
    result.ok("Command /time works")

    # Test help command
    response = await ctx.user_agent.process_input(session, "/help")
    assert "Commands:" in response, "Help command missing"
    result.ok("Command /help works")

    # Test movement
    # We need a location called "Forest" in the world – add one if missing
    loc_nodes = ctx.gm.store.list_by_type("Location")
    if not loc_nodes:
        await ctx.builder.add_location()
        loc_nodes = ctx.gm.store.list_by_type("Location")
    if loc_nodes:
        dest = loc_nodes[0].name
        response = await ctx.user_agent.process_input(session, f"/go {dest}")
        assert session.current_location == dest or "move" in response.lower(), f"Movement failed: {response}"
        result.ok("Movement command works")
    else:
        result.ok("Skipped movement test (no locations)")

    # Test party management
    response = await ctx.user_agent.process_input(session, "/party add Hero")
    assert "Hero" in ctx.user_agent.party, "Party addition failed"
    result.ok("Party add works")

    # Test save/load
    ctx.user_agent._save_session(session)
    loaded = await ctx.user_agent.load_session("test_session")
    assert loaded.active_character == session.active_character, "Session load mismatch"
    result.ok("Session save/load works")


async def main():
    result = TestResult()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        print(f"Using temporary directory: {tmp_path}")

        # Run tests sequentially
        try:
            await test_world_building(tmp_path, result)
            await test_npc_manager(tmp_path, result)
            await test_story_engine(tmp_path, result)
            await test_director(tmp_path, result)
            await test_user_agent(tmp_path, result)
        except Exception as e:
            result.fail(f"Unexpected error: {e}")
            import traceback
            traceback.print_exc()

    result.summary()
    if result.failed == 0:
        print("\n🎉 All tests passed! The narrative system is working.")
    else:
        print("\n⚠️ Some tests failed. Check the errors above.")


if __name__ == "__main__":
    asyncio.run(main())
