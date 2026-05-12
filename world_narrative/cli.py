from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from .context import NarrativeContext
from world_director.newborn_scenario import NewbornScenario
from world_explorer.config import DEFAULT_DB_PATH

app = typer.Typer(help="🎭 Narrative & NPC management")
console = Console()

# Module-level event loop for reuse across commands
_loop: Optional[asyncio.AbstractEventLoop] = None


def get_loop() -> asyncio.AbstractEventLoop:
    """Get or create a shared event loop for the CLI."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


@app.command()
def play(
    session_id: str = typer.Option("default", help="Session identifier"),
    character: Optional[str] = typer.Option(None, help="Active character name"),
    location: Optional[str] = typer.Option(None, help="Starting location"),
    start: Optional[str] = typer.Option(None, help="Starting point (e.g., 'as Kaelen in Silverwood at dawn')"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, help="Path to world_db"),
):
    """Start a rich third-person roleplay session with full background services."""
    async def _run():
        ctx = NarrativeContext(db_path)
        ctx.ensure_booted()

        # Start all background services (LLM queue, director, memory optimizer)
        await ctx.start_background_services()
        console.print("[green]Background services started[/]")

        # Resolve starting location if not provided
        if not location:
            locs = ctx.gm.store.list_by_type("Location")
            location = locs[0].name if locs else "unknown"

        # Create the roleplay engine
        engine = ctx.create_roleplay_engine(character, location)

        # Handle starting point specification
        if start:
            resolver = ctx.create_roleplay_engine(character, location).start_resolver if hasattr(ctx, 'create_roleplay_engine') else None
            if resolver:
                starting_point = await resolver.resolve(start, ctx.world_frame["world_name"], datetime.now())
                await resolver.apply_to_session(engine, starting_point, ctx.world_frame)

        # Try to load existing session
        if engine.load_session(session_id):
            console.print(f"[green]Resumed session {session_id}[/]")
        else:
            console.print(f"[green]New session {session_id} started[/]")

        console.print(f"[italic]World: {ctx.world_frame['world_name']}[/]")
        if engine.active_character:
            console.print(f"[italic]Character: {engine.active_character}[/]")
        console.print(f"[italic]Location: {engine.current_location}[/]")
        console.print("[italic]You control your character. The narrator describes everything else.[/]")
        console.print("[italic]Type /help for commands, /save to persist, /quit to exit.[/]\n")

        try:
            while True:
                user_input = Prompt.ask("[bold cyan]You[/]").strip()
                if not user_input:
                    continue
                if user_input.lower() in {"/quit", "/exit"}:
                    engine.save_session(session_id)
                    console.print("[bold red]Goodbye![/]")
                    break
                if user_input.lower() == "/save":
                    engine.save_session(session_id)
                    console.print("[green]Session saved.[/]")
                    continue
                if user_input.lower() == "/help":
                    console.print("[bold]Commands:[/]")
                    console.print("  /look - Describe your surroundings")
                    console.print("  /inventory - Show your items")
                    console.print("  /status - Show character status")
                    console.print("  /quests - Show active quests")
                    console.print("  /time - Show story time")
                    console.print("  /save - Save session")
                    console.print("  /quit - Save and exit")
                    continue
                response = await engine.process_input(user_input)
                console.print(Panel(response, title="Narrator", border_style="cyan"))
        except KeyboardInterrupt:
            engine.save_session(session_id)
            console.print("\n[red]Session interrupted and saved.[/]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/]")
        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def tick(
    story_time: str = typer.Argument(..., help="ISO datetime like 2025-01-01T12:00:00"),
    involved: str = typer.Option("", help="Comma-separated entities"),
    severity: float = typer.Option(0.5, help="Event severity (0-1)"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Advance the world clock and generate a story event."""
    async def _run():
        ctx = NarrativeContext(db_path)
        ctx.ensure_booted()
        time = datetime.fromisoformat(story_time)
        involved_list = [p.strip() for p in involved.split(",") if p.strip()]
        result = await ctx.story_engine.tick(time, involved_list, severity)
        if result.get("event"):
            event = result["event"]
            console.print(Panel(f"[bold]{event['title']}[/]\n{event['description']}", title="Story Tick"))
        else:
            console.print("[dim]No event generated this tick.[/]")

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def timeline(
    since: Optional[str] = typer.Option(None, help="ISO datetime filter"),
    limit: int = typer.Option(50),
    group: Optional[str] = typer.Option(None, help="Filter by event group"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Show the story timeline."""
    async def _run():
        ctx = NarrativeContext(db_path)
        ctx.ensure_booted()
        since_dt = datetime.fromisoformat(since) if since else None

        if group:
            entries = await ctx.chronicler.get_events_by_group(group, limit=limit)
        else:
            entries = await ctx.chronicler.get_timeline(since=since_dt, limit=limit)

        if not entries:
            console.print("[yellow]No events recorded.[/]")
            return

        for e in entries:
            console.print(f"[dim]{e['timestamp']}[/] | [{e.get('group', 'narrative')}] {e['description']}")

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def schedule(
    callback: str = typer.Argument(..., help="Callback type: villain_event, npc_event, quest_event, random_event"),
    minutes: int = typer.Option(60, help="Minutes from now to schedule event"),
    data: str = typer.Option("{}", help="JSON data for the callback"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Schedule a future event callback."""
    async def _run():
        ctx = NarrativeContext(db_path)
        ctx.ensure_booted()

        try:
            event_data = json.loads(data)
        except json.JSONDecodeError:
            console.print("[red]Invalid JSON data.[/]")
            return

        await ctx.clock.schedule_relative(minutes, callback, event_data)
        console.print(f"[green]Scheduled {callback} event in {minutes} minutes.[/]")

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def scheduled_list(db_path: Path = typer.Option(DEFAULT_DB_PATH)):
    """List all scheduled events."""
    ctx = NarrativeContext(db_path)
    ctx.ensure_booted()

    events = ctx.clock.get_scheduled_events()
    if not events:
        console.print("[yellow]No scheduled events.[/]")
        return

    console.print("[bold]Scheduled Events:[/]")
    for e in events:
        console.print(f"  [dim]{e['time']}[/] | {e['callback']}: {e['data']}")


@app.command()
def npc_status(
    name: str = typer.Argument(..., help="NPC name"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Show NPC status."""
    ctx = NarrativeContext(db_path)
    ctx.ensure_booted()

    state = ctx.npc_mgr.get(name)
    if state:
        console.print(Panel(
            f"[bold]{name}[/]\n"
            f"Location: {state.location}\n"
            f"Health: {state.health}\n"
            f"Mood: {state.mood}\n"
            f"Goals: {', '.join(state.goals) or 'None'}\n"
            f"Inventory: {', '.join(state.inventory) or 'Empty'}",
            title="NPC Status"
        ))
    else:
        console.print(f"[red]NPC '{name}' not found.[/]")


# ------------------------------------------------------------------
# Director commands
# ------------------------------------------------------------------

@app.command()
def director_status(db_path: Path = typer.Option(DEFAULT_DB_PATH)):
    """Show director status (villains, story plan, etc.)."""
    async def _run():
        ctx = NarrativeContext(db_path)
        ctx.ensure_booted()
        status = await ctx.director.get_status()

        console.print("[bold]Director Status:[/]")
        console.print(f"Running: {status['running']}")
        console.print(f"Last major beat: {status['last_major_beat'] or 'None'}")

        console.print("\n[bold]Villain Status:[/]")
        villain_status = status.get("villain_status", {})
        if villain_status:
            for name, info in villain_status.items():
                console.print(f"  {name}: Phase={info['phase']}, Progress={info['progress']}")
        else:
            console.print("  No villains")

        console.print("\n[bold]Story Plan:[/]")
        plan = status.get("story_plan", {})
        current = plan.get("current_chapter", "None")
        console.print(f"  Current chapter: {current}")
        chapters = plan.get("chapters", {})
        for cid, info in chapters.items():
            marker = "→ " if cid == current else "  "
            status_mark = "✓" if info["completed"] else " "
            console.print(f"  {marker}{status_mark} {cid}: {info['title']} ({info['beats_done']}/{info['beats_total']} beats)")

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def force_chance_event(db_path: Path = typer.Option(DEFAULT_DB_PATH)):
    """Manually trigger a chance event."""
    async def _run():
        ctx = NarrativeContext(db_path)
        ctx.ensure_booted()
        event = await ctx.director.force_chance_event()
        if event:
            console.print(f"[yellow]Chance event:[/] {event.get('title')} – {event.get('description')}")
        else:
            console.print("[yellow]No chance event generated.[/]")

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def force_beat(db_path: Path = typer.Option(DEFAULT_DB_PATH)):
    """Force a major story beat."""
    async def _run():
        ctx = NarrativeContext(db_path)
        ctx.ensure_booted()
        event = await ctx.director.force_beat()
        if event:
            console.print(f"[magenta]Major beat:[/] {event.get('title')} – {event.get('description')}")
        else:
            console.print("[yellow]No beat generated (check cooldown or pending beats).[/]")

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def villains(db_path: Path = typer.Option(DEFAULT_DB_PATH)):
    """List all villains and their status."""
    async def _run():
        ctx = NarrativeContext(db_path)
        ctx.ensure_booted()
        status = await ctx.director.villain_mgr.get_status()

        if not status:
            console.print("[yellow]No villains found.[/]")
            return

        for name, info in status.items():
            console.print(Panel(
                f"[bold]{name}[/]\n"
                f"Phase: {info['phase']}\n"
                f"Progress: {info['progress']}\n"
                f"Minions: {', '.join(info.get('minions', [])) or 'None'}\n"
                f"Goal: {info.get('ultimate_goal', 'Unknown')}",
                title="Villain"
            ))

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def story_plan(db_path: Path = typer.Option(DEFAULT_DB_PATH)):
    """Show the current story plan with chapters and beats."""
    async def _run():
        ctx = NarrativeContext(db_path)
        ctx.ensure_booted()
        plan = await ctx.director.story_planner.get_plan_summary()

        console.print(f"[bold]Current Chapter:[/] {plan.get('current_chapter', 'None')}")
        console.print(f"[bold]Pending Beats:[/] {plan.get('pending_beats', 0)}")
        console.print("")

        chapters = plan.get("chapters", {})
        for cid, info in chapters.items():
            marker = "→" if cid == plan.get("current_chapter") else " "
            completed = "✓" if info["completed"] else " "
            console.print(f"[bold]{marker} Chapter {cid}:[/] {info['title']} {completed}")
            console.print(f"   {info['summary']}")
            console.print(f"   Beats: {info['beats_done']}/{info['beats_total']}")
            console.print("")

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def newborn_play(
    character: str = typer.Argument(..., help="Character name (must exist in world)"),
    session_id: str = typer.Option("newborn", help="Session identifier"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Start a session as a newborn character (no memories, no relationships)."""
    async def _run():
        ctx = NarrativeContext(db_path)
        ctx.ensure_booted()
        # Prepare the newborn
        await NewbornScenario.prepare(character, ctx.gm, ctx.builder, ctx.npc_mgr, ctx.chronicler)
        console.print(f"[green]Newborn character '{character}' is ready.[/]")
        console.print("Use 'play' command to start the roleplay session with this character.")
        console.print(f"Run: python -m world_narrative.cli play --character {character} --session-id {session_id}")

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def director_expand(
    center_uid: str = typer.Argument(...),
    depth: int = typer.Option(1),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Manually expand a subgraph around an entity."""
    async def _run():
        ctx = NarrativeContext(db_path)
        ctx.ensure_booted()
        await ctx.director.expand_branch(center_uid, depth)
        console.print(f"[green]Expansion task submitted for {center_uid}[/]")

    loop = get_loop()
    loop.run_until_complete(_run())


if __name__ == "__main__":
    app()
