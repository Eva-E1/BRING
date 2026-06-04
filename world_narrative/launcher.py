"""Professional game launcher – system check, world preparation, birth, post‑creation tasks."""
from __future__ import annotations

import asyncio
import json
import pickle
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.text import Text
from rich.columns import Columns

from world_builder.graph_manager import GraphManager
from world_builder.builder import WorldBuilder
from world_builder.llm import LLMClient
from world_builder.config import get_world_frame_path, get_entity_store_path
from world_explorer.config import DEFAULT_DB_PATH
from world_narrative.context import NarrativeContext
from world_narrative.birth import BirthScenario, BirthGenerator, BirthApplier
from world_narrative.memory_optimized import OptimizedMemoryStore
from world_narrative.story_engine import StoryEngine
from world_narrative.director import DirectorConfig
from world_narrative.quest_manager import Quest
from world_core.llm_queue import GlobalLLMQueue

console = Console()


def system_check() -> Tuple[bool, str]:
    """Check LLM connectivity, FAISS, disk space, etc."""
    # LLM check
    try:
        llm = LLMClient()
        # Quick test - try a simple embedding (use sync method if available)
        try:
            # Try sync embed first
            if hasattr(llm, 'embed_sync'):
                llm.embed_sync("test")
            elif hasattr(llm, 'embed'):
                # For async embed, check if we're in an async context
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    # No running loop, safe to use asyncio.run()
                    asyncio.run(llm.embed("test"))
                else:
                    # We're in an async context, skip the test
                    pass
        except AttributeError:
            # LLMClient might not have embed method, try generate
            pass
    except Exception as e:
        return False, f"LLM connection failed: {e}"

    # FAISS check
    try:
        import faiss
        try:
            faiss.IndexFlatIP(384)
        except Exception:
            # Try float32 index
            faiss.IndexFlatL2(384)
    except ImportError:
        return False, "FAISS not installed. Run: pip install faiss-cpu"

    # Disk space (need at least 500MB free)
    db_path = DEFAULT_DB_PATH
    try:
        free = shutil.disk_usage(db_path).free
        if free < 500 * 1024 * 1024:
            return False, f"Low disk space: {free // (1024*1024)}MB free, need 500MB"
    except Exception:
        pass  # Skip disk check if it fails

    return True, "All systems operational."


async def prepare_world(db_path: Path) -> None:
    """Create or update the world frame and all entity layers."""
    frame_path = get_world_frame_path(db_path)
    if frame_path.exists():
        console.print("[yellow]World already exists. Loading...[/]")
        return

    console.print("[cyan]Generating new world...[/]")
    llm = LLMClient()
    gm = GraphManager(entity_store_path=get_entity_store_path(db_path))
    builder = WorldBuilder(llm, gm, num_episodes=0, world_frame_path=frame_path)

    with console.status("[bold green]Building world foundation...[/]"):
        await builder.create_world()

    with console.status("[bold green]Building L2 entities...[/]"):
        await builder.build_L2()

    with console.status("[bold green]Building L3 details...[/]"):
        await builder.build_L3()

    console.print("[green]World created and fully layered.[/]")


async def run_birth_wizard(
    ctx: NarrativeContext,
    hints: str,
    isekai: bool,
    starting_age: int,
    display_probabilities: bool = True
) -> Tuple[str, str]:
    """Run the birth wizard with live probability display."""
    # Create a custom progress display for probabilities
    prob_table = Table(title="Birth Probabilities", box=None)
    prob_table.add_column("Attribute", style="cyan")
    prob_table.add_column("Probability", style="green")
    prob_table.add_column("Roll", style="yellow")
    prob_table.add_column("Result", style="white")

    generator = BirthGenerator(
        ctx,
        user_hints=hints,
        isekai=isekai,
        starting_age=starting_age,
        display_probabilities=display_probabilities
    )

    # Run generation with status
    with console.status("[bold green]✨ Conjuring your birth...[/]"):
        params = await generator.generate()

    # Show probability results if available
    if hasattr(params, 'probability_rolls') and params.probability_rolls:
        for roll in params.probability_rolls:
            prob_table.add_row(
                roll.attribute,
                f"{roll.probability:.0%}",
                f"{roll.roll_result:.2f}",
                "✓" if roll.success else "✗"
            )
        console.print(prob_table)

    # Show opening narrative
    console.print(Panel(params.opening_narrative, title="🌅 Your Birth", border_style="magenta"))

    # Apply birth to the world
    applier = BirthApplier(ctx, params)
    opening = await applier.apply()

    return params.character_name, opening


async def post_birth_tasks(ctx: NarrativeContext, character_name: str) -> None:
    """Run relationship repair, initial story beats, childhood milestones."""
    console.print("[cyan]Tuning the world for your arrival...[/]")

    # Repair relationships for the new character
    try:
        await ctx.gm.repair_all_relationships(intelligent=True)
    except Exception as e:
        console.print(f"[yellow]Relationship repair skipped: {e}[/]")

    # Schedule initial director beats
    director = ctx.director

    # Force a story beat in 2 story hours
    try:
        await director.clock.schedule_relative(120, "generate_event", {
            "category": "discovery",
            "severity": 0.6,
            "involved_entities": [character_name]
        })
    except Exception as e:
        console.print(f"[yellow]Could not schedule initial beat: {e}[/]")

    # Set initial global luck
    try:
        ctx.clock.set_global_luck(0.55)
    except Exception:
        pass

    # Add a welcome quest
    try:
        quest = Quest(
            id="birth_quest",
            title="Awakening",
            description=f"As {character_name}, explore your surroundings and find a worthy goal.",
            giver="The World",
            objectives=[{"type": "explore", "target": "any", "completed": False}]
        )
        ctx.quest_mgr.add_quest(quest)
    except Exception as e:
        console.print(f"[yellow]Could not add welcome quest: {e}[/]")

    console.print("[green]World tuned and initial story beats scheduled.[/]")


async def memory_health_check(ctx: NarrativeContext) -> None:
    """Run quick memory maintenance before starting."""
    console.print("[cyan]Running memory health check...[/]")
    try:
        await ctx.world_memory.optimizer.run_manual()
        await ctx.world_memory.trigger_consolidation()
        console.print("[green]Memory system optimized.[/]")
    except Exception as e:
        console.print(f"[yellow]Memory optimization skipped: {e}[/]")


async def save_game_snapshot(ctx: NarrativeContext, session_id: str) -> Path:
    """Save entire context (excluding live connections) to a compressed snapshot."""
    snapshot_dir = ctx.db_path / "snapshots"
    snapshot_dir.mkdir(exist_ok=True)
    snapshot_path = snapshot_dir / f"{session_id}.pkl"

    # Gather serializable state
    npc_profiles = {}
    try:
        # Copy profiles without embeddings (they can be recomputed)
        for name, profile in ctx.npc_mgr._npcs.items():
            npc_profiles[name] = {
                "name": profile.name,
                "uid": profile.uid,
                "location": profile.location,
                "health": getattr(profile, 'health', 100),
                "mood": getattr(profile, 'mood', 'neutral'),
            }
    except Exception:
        pass

    state = {
        "db_path": str(ctx.db_path),
        "world_frame": ctx.world_frame,
        "clock": str(ctx.clock.current_time) if ctx.clock.current_time else None,
        "global_luck": getattr(ctx.clock, 'global_luck', 0.5),
        "npc_profiles": npc_profiles,
        "active_session_id": session_id,
    }

    with open(snapshot_path, "wb") as f:
        pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)

    console.print(f"[dim]Snapshot saved to {snapshot_path}[/]")
    return snapshot_path


async def load_game_snapshot(db_path: Path, session_id: str) -> Optional[NarrativeContext]:
    """Restore a full game state from snapshot."""
    snapshot_path = db_path / "snapshots" / f"{session_id}.pkl"
    if not snapshot_path.exists():
        return None

    with open(snapshot_path, "rb") as f:
        state = pickle.load(f)

    # Create new context
    ctx = NarrativeContext(db_path)

    # Restore clock time if available
    if state.get("clock"):
        try:
            ctx.clock.current_time = datetime.fromisoformat(state["clock"])
        except Exception:
            pass

    # Restore global luck
    luck = state.get("global_luck", 0.5)
    try:
        ctx.clock.set_global_luck(luck)
    except Exception:
        pass

    # Restore NPC profiles
    if state.get("npc_profiles"):
        try:
            for name, profile_data in state["npc_profiles"].items():
                if name in ctx.npc_mgr._npcs:
                    profile = ctx.npc_mgr._npcs[name]
                    if "location" in profile_data:
                        profile.location = profile_data["location"]
                    if "health" in profile_data:
                        profile.health = profile_data["health"]
                    if "mood" in profile_data:
                        profile.mood = profile_data["mood"]
            ctx.npc_mgr._save()
        except Exception as e:
            console.print(f"[yellow]Could not restore NPC profiles: {e}[/]")

    console.print("[green]Game state restored from snapshot.[/]")
    return ctx


async def launch_game(
    ctx: NarrativeContext,
    session_id: str,
    character_name: str = None,
    open_browser: bool = True,
    port: int = 8000
):
    """Start the web UI and optionally open browser."""
    # Get character name if not provided
    if not character_name:
        try:
            engine = ctx.create_roleplay_engine()
            character_name = getattr(engine, 'active_character', 'Unknown')
        except Exception:
            character_name = 'Unknown'

    # Check if server already running
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()

    server_started = False
    if result != 0:
        # Start API server in background thread
        def run_server():
            subprocess.run([
                sys.executable, "-m", "uvicorn",
                "world_explorer.api:app",
                "--host", "127.0.0.1",
                "--port", str(port)
            ])

        threading.Thread(target=run_server, daemon=True).start()
        time.sleep(2)
        server_started = True

    url = f"http://localhost:{port}/?session={session_id}&character={character_name}"

    if open_browser:
        webbrowser.open(url)

    status_msg = f"[green]Web UI ready at {url}[/]"
    if server_started:
        status_msg += " (server started)"

    console.print(status_msg)


async def launch_new_game(
    hints: str = "",
    isekai: bool = False,
    starting_age: int = 5,
    db_path: Path = DEFAULT_DB_PATH,
    open_browser: bool = True,
    port: int = 8000
) -> Tuple[str, str, str]:
    """
    Complete new game launch sequence.

    Returns: (session_id, character_name, opening_narrative)
    """
    # System check
    ok, msg = system_check()
    if not ok:
        raise RuntimeError(msg)
    console.print("[green]✓ System check passed[/]")

    # Prepare world
    await prepare_world(db_path)

    # Create context and start background services
    ctx = NarrativeContext(db_path)
    await ctx.start_background_services()

    # Run memory health check
    await memory_health_check(ctx)

    # Run birth wizard
    character_name, opening = await run_birth_wizard(ctx, hints, isekai, starting_age)

    # Post-birth tasks
    await post_birth_tasks(ctx, character_name)

    # Save snapshot
    session_id = f"newgame_{character_name.lower().replace(' ', '_')}"
    await save_game_snapshot(ctx, session_id)

    # Launch web UI
    await launch_game(ctx, session_id, character_name, open_browser, port)

    return session_id, character_name, opening


async def continue_game(
    session_id: str,
    db_path: Path = DEFAULT_DB_PATH,
    open_browser: bool = True,
    port: int = 8000
) -> NarrativeContext:
    """Continue an existing game from snapshot or session."""
    # Try snapshot first
    ctx = await load_game_snapshot(db_path, session_id)

    if ctx is None:
        # Fallback to normal session load
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()

        engine = ctx.create_roleplay_engine()
        if not engine.load_session(session_id):
            raise ValueError(f"Session '{session_id}' not found.")

        console.print(f"[green]Loaded session {session_id}[/]")
    else:
        await ctx.start_background_services()

    # Get character name
    try:
        engine = ctx.create_roleplay_engine()
        character_name = getattr(engine, 'active_character', 'Unknown')
    except Exception:
        character_name = 'Unknown'

    await launch_game(ctx, session_id, character_name, open_browser, port)

    return ctx


def list_sessions(db_path: Path = DEFAULT_DB_PATH) -> list[str]:
    """List all available game sessions."""
    sessions = []

    # Check snapshots
    snapshot_dir = db_path / "snapshots"
    if snapshot_dir.exists():
        for p in snapshot_dir.glob("*.pkl"):
            sessions.append(p.stem)

    # Check session files
    sessions_dir = db_path / "sessions"
    if sessions_dir.exists():
        for p in sessions_dir.glob("*.json"):
            sid = p.stem
            if sid not in sessions:
                sessions.append(sid)

    return sorted(sessions)
