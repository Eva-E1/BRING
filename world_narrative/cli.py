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
from rich.table import Table
from rich.markdown import Markdown
from rich import box

from .context import NarrativeContext
from .birth import BirthScenario
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


# ------------------------------------------------------------------
# Helper to show a compact status table
# ------------------------------------------------------------------
def _display_status(engine, ctx, console: Console) -> None:
    """Show current character and world status in a neat panel."""
    status_table = Table.grid(padding=(0, 1))
    status_table.add_column(style="bold cyan", justify="right")
    status_table.add_column(style="white")

    # Character info
    if engine.active_character:
        npc_state = ctx.npc_mgr.get(engine.active_character)
        health = npc_state.health if npc_state else "?"
        mood = npc_state.mood if npc_state else "?"
        status_table.add_row("Character:", engine.active_character)
        status_table.add_row("❤️ Health:", f"{health}%")
        status_table.add_row("😊 Mood:", mood.capitalize())
    else:
        status_table.add_row("Character:", "None (observer)")

    # Location and time
    status_table.add_row("📍 Location:", engine.current_location)
    status_table.add_row("⏱️ Time:", engine.current_time.strftime("%H:%M"))

    console.print(Panel(status_table, title="Status", border_style="cyan", padding=(0, 1)))


@app.command()
def play(
    session_id: str = typer.Option("default", help="Session identifier"),
    character: Optional[str] = typer.Option(None, help="Active character name"),
    location: Optional[str] = typer.Option(None, help="Starting location"),
    start: Optional[str] = typer.Option(None, help="Starting point (e.g., 'as Kaelen in Silverwood at dawn')"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, help="Path to world_db"),
):
    """Start a rich, modern roleplay session with a beautiful terminal interface."""
    async def _run():
        ctx = NarrativeContext(db_path)
        ctx.ensure_booted()

        # Start background services (LLM queue, director, memory optimizer)
        await ctx.start_background_services()
        console.print("[green]Background services started[/]")

        # Resolve starting location if not provided
        resolved_location = location
        if not resolved_location:
            locs = ctx.gm.store.list_by_type("Location")
            resolved_location = locs[0].name if locs else "unknown"

        # Create the roleplay engine
        engine = ctx.create_roleplay_engine(character, resolved_location)

        # Handle starting point specification
        if start:
            resolver = engine.start_resolver
            if resolver:
                starting_point = await resolver.resolve(start, ctx.world_frame["world_name"], datetime.now())
                await resolver.apply_to_session(engine, starting_point, ctx.world_frame)

        # Load or create session
        if engine.load_session(session_id):
            console.print(f"[green]📖 Resumed session '{session_id}'[/]")
        else:
            console.print(f"[green]✨ New session '{session_id}' started[/]")

        # Welcome header and help hint
        console.clear()
        console.rule(f"[bold heading]🎭 {ctx.world_frame['world_name']}[/]")
        _display_status(engine, ctx, console)
        console.print("[dim]Type /help for commands, /save to persist, /quit to exit.[/]\n")

        # Main interactive loop
        try:
            while True:
                # Refresh status before each prompt
                console.rule(style="dim")
                _display_status(engine, ctx, console)

                # Get user input with a stylish prompt
                user_input = Prompt.ask("[bold cyan]You[/]").strip()
                if not user_input:
                    continue

                # Handle built‑in commands
                cmd = user_input.lower()
                if cmd in {"/quit", "/exit"}:
                    engine.save_session(session_id)
                    console.print("[bold red]Goodbye![/]")
                    break
                if cmd == "/save":
                    engine.save_session(session_id)
                    console.print("[green]Session saved.[/]")
                    continue
                if cmd == "/help":
                    help_text = (
                        "**Commands**\n\n"
                        "/look – Describe your surroundings\n"
                        "/inventory – Show your items\n"
                        "/status – Show character status\n"
                        "/quests – Show active quests\n"
                        "/time – Show story time\n"
                        "/save – Save session\n"
                        "/quit – Exit"
                    )
                    console.print(Panel(Markdown(help_text), title="Help", border_style="cyan"))
                    continue

                # Display user input in a left‑aligned panel (message bubble)
                console.print(Panel(
                    Markdown(f"> {user_input}"),
                    style="dim cyan",
                    border_style="cyan",
                    title="You",
                    title_align="left"
                ))

                # Get narrative response from the engine
                response = await engine.process_input(user_input)

                # Display narrator response in a right‑aligned panel (message bubble)
                console.print(Panel(
                    Markdown(response),
                    style="italic white",
                    border_style="magenta",
                    title="Narrator",
                    title_align="right"
                ))

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
        await BirthScenario.prepare(character, ctx.gm, ctx.builder, ctx.npc_mgr, ctx.chronicler)
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


@app.command()
def newborn(
    session_id: str = typer.Option("newborn", help="Session identifier for the new game"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, help="Path to world_db"),
):
    """Create a brand‑new character from scratch and start a roleplay session."""
    async def _run():
        ctx = NarrativeContext(db_path)
        ctx.ensure_booted()

        console.print("[bold cyan]🌟 Newborn Character Creation[/]")
        user_spec = typer.prompt(
            "Enter any specifics about your character (name, race, family, etc.)\n"
            "or press Enter for a completely random creation",
            default=""
        )

        console.print("[cyan]Generating your character and birth scenario...[/]")
        try:
            char_name, opening_narrative = await BirthScenario.generate_and_prepare(
                user_spec,
                ctx.gm,
                ctx.builder,
                ctx.npc_mgr,
                ctx.chronicler,
                ctx.llm,
            )
        except Exception as e:
            console.print(f"[red]Creation failed: {e}[/]")
            raise typer.Exit(1)

        console.print(f"[green]✓ Character '{char_name}' created.[/]")
        console.print(Panel(opening_narrative, title="Your Birth", border_style="magenta"))

        # Start background services
        await ctx.start_background_services()

        engine = ctx.create_roleplay_engine(char_name, location=None)

        # Determine starting location from the character's L2
        node = ctx.gm.store.get_by_name_and_type(char_name, "Character")
        if node and node.profile.l2.get("current_location"):
            start_loc = node.profile.l2["current_location"]
        else:
            locs = ctx.gm.store.list_by_type("Location")
            start_loc = locs[0].name if locs else "unknown"

        engine.set_session(
            character=char_name,
            location=start_loc,
            story_time=datetime.now(),
            role="protagonist",
        )

        # Inject the opening narrative into the engine's memory
        engine.memory.add_entry("(birth)", opening_narrative)

        console.print(f"[italic]You are {char_name}.[/]")
        console.print(f"[italic]Location: {start_loc}[/]")
        console.print("[italic]Type /help for commands, /save to persist, /quit to exit.[/]\n")

        # Start the interactive loop
        try:
            while True:
                user_input = typer.prompt("[bold cyan]You[/]").strip()
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
        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def memory_maintenance(
    full: bool = typer.Option(True, "--full/--quick", help="Run full maintenance or only essential"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Run memory maintenance: repair, deduplicate, consolidate, clean."""
    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()
        try:
            if full:
                report = await ctx.world_memory.optimizer.run_full_maintenance()
                console.print(Panel(
                    f"[bold green]Full maintenance complete![/bold green]\n\n" +
                    "\n".join(f"{k}: {v}" for k, v in report.items()),
                    title="Maintenance Report"
                ))
                # Quick: only consolidation and cleanup
                await ctx.world_memory.trigger_consolidation()
                removed = await ctx.world_memory.clear_old_entries()
                console.print(f"[green]Consolidated, removed {removed} old entries.[/green]")
        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def memory_status(db_path: Path = typer.Option(DEFAULT_DB_PATH)):
    """Get current memory and maintenance statistics."""
    ctx = NarrativeContext(db_path)
    stats = ctx.world_memory.get_stats()

    # Add optimizer status
    opt_status = ctx.world_memory.optimizer.get_stats()
    stats["optimizer_status"] = opt_status

    console.print(Panel(
        "\n".join(f"[bold]{k}:[/] {v}" for k, v in stats.items()),
        title="World Memory Status"
    ))


@app.command()
def memory_forget(
    older_than: int = typer.Option(30, help="Days"),
    min_importance: float = typer.Option(0.2, help="Minimum importance"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Forget old, low-importance memories."""
    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()
        try:
            removed = await ctx.world_memory.forget_old_entries(older_than, min_importance)
            console.print(f"Removed {removed} old memories.")
        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def memory_summarise(
    tag: str = typer.Option(None, help="Tag to summarise"),
    node: str = typer.Option(None, help="Node UID"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Summarise memories with a given tag or node UID."""
    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()
        try:
            if tag:
                consolidated = await ctx.world_memory.consolidate_cluster(tag=tag)
            elif node:
                consolidated = await ctx.world_memory.consolidate_cluster(node_uid=node)
            else:
                console.print("Provide either --tag or --node")
                return
            console.print(f"Consolidated {consolidated} memories into a summary.")
        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def memory_export(
    output: Path = typer.Argument(..., help="Output file"),
    fmt: str = typer.Option("json", help="json or parquet"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Export all memories to a file."""
    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()
        try:
            data = await ctx.world_memory.export_memories(fmt)
            if fmt == "parquet":
                output.write_bytes(data)
            else:
                output.write_text(data)
            console.print(f"Exported to {output}")
        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def memory_import(
    input: Path = typer.Argument(..., help="Input file"),
    merge: bool = typer.Option(True, help="Merge with existing"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Import memories from a file."""
    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()
        try:
            fmt = "parquet" if input.suffix == ".parquet" else "json"
            data = input.read_bytes() if fmt == "parquet" else input.read_text()
            await ctx.world_memory.import_memories(data, fmt, merge)
            console.print("Import completed.")
        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


# ─────────────────────────────────────────────────────────────────
# New Enhanced Memory System CLI Commands
# ─────────────────────────────────────────────────────────────────

@app.command()
def memory_stats(db_path: Path = typer.Option(DEFAULT_DB_PATH)):
    """Show detailed memory statistics including cognitive features."""
    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()
        try:
            stats = await ctx.get_memory_stats()

            # Display in a nice table
            table = Table(title="Memory System Statistics", box=box.ROUNDED)
            table.add_column("Component", style="cyan")
            table.add_column("Value", style="white")

            # Basic stats
            table.add_row("Active Entries", str(stats.get("total_active_entries", 0)))
            table.add_row("FAISS Entries", str(stats.get("faiss_entries", 0)))
            table.add_row("FAISS Fragmentation", f"{stats.get('faiss_fragmentation', 0):.1%}")
            table.add_row("Embedding Queue Size", str(stats.get("embedding_queue_size", 0)))
            table.add_row("Write Buffer Size", str(stats.get("write_buffer_size", 0)))

            # Optimizer stats
            opt_stats = stats.get("optimizer_stats", {})
            table.add_row("Pruned Count", str(opt_stats.get("pruned_count", 0)))
            table.add_row("Merged Count", str(opt_stats.get("merged_count", 0)))
            table.add_row("Archived Count", str(opt_stats.get("archived_count", 0)))

            console.print(table)

            # Cognitive pipeline stats
            cog_stats = stats.get("cognitive_pipeline", {})
            if cog_stats:
                console.print(f"\n[cyan]Cognitive Pipeline:[/]")
                console.print(f"  Turns processed: {cog_stats.get('turns_processed', 0)}")
                console.print(f"  Facts extracted: {cog_stats.get('facts_extracted', 0)}")
                console.print(f"  Entities extracted: {cog_stats.get('entities_extracted', 0)}")
                console.print(f"  Contradictions found: {cog_stats.get('contradictions_found', 0)}")
                console.print(f"  Warnings raised: {cog_stats.get('warnings_raised', 0)}")

            # Pain signals
            pain_stats = stats.get("pain_signals", {})
            if pain_stats:
                console.print(f"\n[red]Pain Signals:[/]")
                console.print(f"  Total pain signals: {pain_stats.get('total_pain_signals', 0)}")
                console.print(f"  Cached keywords: {pain_stats.get('cached_keywords', 0)}")

        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def memory_optimize(db_path: Path = typer.Option(DEFAULT_DB_PATH)):
    """Manually trigger memory optimization (pruning, clustering, archiving)."""
    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()
        try:
            console.print("[cyan]Starting memory optimization...[/]")
            await ctx.trigger_memory_optimization()
            console.print("[green]Memory optimization complete![/]")
        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def memory_pain_warnings(
    context: str = typer.Argument(..., help="Context text to check for pain keywords"),
    top_k: int = typer.Option(3, "--top", "-t", help="Number of warnings to show"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Check for pain signal warnings in the given context."""
    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()
        try:
            warnings = await ctx.get_pain_warnings(context, top_k)
            if not warnings:
                console.print("[green]No pain warnings found.[/]")
            else:
                table = Table(title="Pain Warnings", box=box.ROUNDED)
                table.add_column("Match Score", style="yellow")
                table.add_column("Content", style="white")
                table.add_column("Importance", style="red")

                for w in warnings:
                    table.add_row(
                        f"{w['match_score']:.1%}",
                        w['content'][:60] + "..." if len(w['content']) > 60 else w['content'],
                        f"{w['importance']:.1f}"
                    )
                console.print(table)
        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def memory_partitions(db_path: Path = typer.Option(DEFAULT_DB_PATH)):
    """Show memory partition information."""
    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()
        try:
            info = await ctx.world_memory.partition_mgr.get_partition_info()
            if not info:
                console.print("[yellow]No partitions found.[/]")
                return

            table = Table(title="Memory Partitions", box=box.ROUNDED)
            table.add_column("Partition", style="cyan")
            table.add_column("Entries", style="white")
            table.add_column("Size (KB)", style="yellow")
            table.add_column("Modified", style="green")

            for key, data in sorted(info.items()):
                table.add_row(
                    key,
                    str(data.get("entry_count", 0)),
                    f"{data.get('size_bytes', 0) / 1024:.1f}",
                    data.get("modified", "unknown")[:19]
                )
            console.print(table)
        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def memory_clear_pain(
    older_than: int = typer.Option(30, "--days", "-d", help="Clear pain signals older than N days"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Clear old pain signal memories."""
    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()
        try:
            removed = await ctx.pain_signal_manager.clear_old_pain_signals(older_than)
            console.print(f"[green]Cleared {removed} old pain signals.[/]")
        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def memory_migrate_timeline(
    limit: int = typer.Option(100, "--limit", "-n", help="Maximum events to import"),
    group: str = typer.Option(None, "--group", "-g", help="Filter by group (narrative, director, villain, etc.)"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Import events from timeline.jsonl into memory system."""
    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()
        try:
            timeline_path = db_path / "timeline.jsonl"
            if not timeline_path.exists():
                console.print("[red]timeline.jsonl not found[/]")
                return

            # Read timeline events
            events = []
            with open(timeline_path, 'r') as f:
                import json
                for line in f:
                    try:
                        events.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue

            # Filter by group if specified
            if group:
                events = [e for e in events if e.get('group') == group]

            # Limit
            events = events[:limit]

            if not events:
                console.print("[yellow]No events to import[/]")
                return

            console.print(f"[cyan]Importing {len(events)} timeline events...[/]")

            # Import each event as a memory
            from datetime import datetime
            from uuid import uuid4
            from world_core.memory import WorldMemoryEntry, MemoryMetadata

            imported = 0
            for event in events:
                try:
                    ts = datetime.fromisoformat(event.get('timestamp', datetime.now().isoformat()))
                    entry = WorldMemoryEntry(
                        id=str(uuid4()),
                        content=event.get('description', ''),
                        timestamp=ts,
                        source_type='timeline',
                        source_id=event.get('group', 'timeline'),
                        importance=0.5,
                        tags=[event.get('group', 'timeline')],
                        metadata=MemoryMetadata(
                            story_relevance=0.6,
                        ),
                    )
                    await ctx.world_memory.add_memory(entry)
                    imported += 1
                except Exception as e:
                    console.print(f"[yellow]Warning: Failed to import event: {e}[/]")

            console.print(f"[green]Successfully imported {imported} events to memory[/]")

            # Show updated stats
            stats = await ctx.world_memory.get_stats()
            console.print(f"\nTotal active entries: {stats['total_active_entries']}")

        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


# ─────────────────────────────────────────────────────────────────
# Probability CLI Commands
# ─────────────────────────────────────────────────────────────────

prob_app = typer.Typer(help="🎲 Probability system commands")
app.add_typer(prob_app, name="prob")


@prob_app.command("show")
def prob_show(
    profile: str = typer.Argument(..., help="Profile name: combat, persuasion, stealth, intimidation, deception, athletics, investigation, romance, generic"),
    character: str = typer.Option(..., "--character", "-c", help="Character name"),
    target: str = typer.Option(None, "--target", "-t", help="Optional target character"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Show success probability for an action."""
    from world_core.probability.profiles import get_profile, PROFILES

    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()
        try:
            profile_obj = get_profile(profile)
            if not profile_obj:
                console.print(f"[red]Unknown profile: {profile}[/]")
                console.print(f"Available: {', '.join(PROFILES.keys())}")
                raise typer.Exit(1)

            context = await ctx.prob_resolver.build_context(
                actor=character,
                target=target,
                action_type=profile,
                location=None,
            )

            probability = ctx.prob_engine.get_success_chance(profile_obj, context, character)

            # Get character's relevant skill
            char_profile = ctx.npc_mgr.get(character)
            skill_value = 0.5
            if char_profile and char_profile.skills:
                skill_value = char_profile.skills.get(profile, 0.5)

            console.print(Panel(
                f"[bold]{character}[/] attempting [bold]{profile}[/]\n"
                f"Success probability: [green]{probability:.0%}[/]\n"
                f"Relevant skill: {skill_value:.0%}",
                title="Probability Check"
            ))
        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


@prob_app.command("list")
def prob_list(
    character: str = typer.Option(..., "--character", "-c", help="Character name"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """List active probability modifiers for a character."""
    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()
        try:
            uid = f"Character:{character}"
            summary = ctx.prob_engine.get_modifier_summary(uid)

            if not summary["total_modifiers"]:
                console.print(f"[yellow]No active modifiers for {character}.[/]")
                return

            table = Table(title=f"Active Modifiers for {character}")
            table.add_column("Parameter")
            table.add_column("Value")
            table.add_column("Type")
            table.add_column("Source")

            for param, mods in summary["by_parameter"].items():
                for m in mods:
                    table.add_row(
                        param,
                        f"{m['value']:+.2f}",
                        m.get("type", "add"),
                        m.get("source", "unknown")
                    )

            console.print(table)
            console.print(f"\n[bold]Total modifiers:[/] {summary['total_modifiers']}")
        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


@prob_app.command("modify")
def prob_modify(
    entity: str = typer.Argument(..., help="Entity name (character)"),
    parameter: str = typer.Argument(..., help="Parameter to modify (e.g., strength, charisma)"),
    value: float = typer.Argument(..., help="Modifier value (e.g., 0.2 or -0.1)"),
    duration: int = typer.Option(None, "--duration", "-d", help="Duration in seconds (omit for permanent)"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Apply a temporary probability modifier to a character."""
    from world_core.probability import ProbabilityModifier, ModifierType

    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()
        try:
            uid = f"Character:{entity}"
            modifier = ProbabilityModifier(
                parameter_name=parameter,
                value=value,
                modifier_type=ModifierType.ADD,
                duration_seconds=duration,
                source="cli_command"
            )
            ctx.prob_engine.apply_modifier(uid, modifier)

            dur_text = f" for {duration} seconds" if duration else " permanently"
            console.print(f"[green]Applied {parameter} {value:+.2f} to {entity}{dur_text}.[/]")

            # Save modifiers
            mod_path = db_path / "probability_modifiers.json"
            ctx.prob_engine.save_modifiers(mod_path)
        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


@prob_app.command("skills")
def prob_skills(
    character: str = typer.Option(..., "--character", "-c", help="Character name"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Show skills for a character."""
    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()
        try:
            char_profile = ctx.npc_mgr.get(character)
            if not char_profile:
                console.print(f"[red]Character {character} not found.[/]")
                raise typer.Exit(1)

            skills = char_profile.skills or {}
            if not skills:
                console.print(f"[yellow]No skills defined for {character}.[/]")
                return

            table = Table(title=f"Skills for {character}")
            table.add_column("Skill", style="cyan")
            table.add_column("Value", justify="right")
            table.add_column("Bar")

            for skill, value in sorted(skills.items()):
                bar_len = int(value * 20)
                bar = "█" * bar_len + "░" * (20 - bar_len)
                table.add_row(skill, f"{value:.2f}", bar)

            console.print(table)
        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


# ─────────────────────────────────────────────────────────────────
# System Info Command
# ─────────────────────────────────────────────────────────────────

@app.command()
def info(db_path: Path = typer.Option(DEFAULT_DB_PATH)):
    """Display system information and status."""
    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()
        try:
            # World info
            world_name = ctx.world_frame.get("world_name", "Unknown")
            console.print(Panel(f"[bold cyan]{world_name}[/]", title="🌍 World"))

            # LLM info
            llm_info = f"[bold]URL:[/] {ctx.llm.base_url}\n[bold]Model:[/] {ctx.llm.default_model}"
            console.print(Panel(llm_info, title="🤖 LLM"))

            # Memory stats
            mem_stats = ctx.world_memory.get_stats()
            memory_info = (
                f"[bold]Entries:[/] {mem_stats.get('total_entries', 0)}\n"
                f"[bold]Global Facts:[/] {mem_stats.get('global_facts', 0)}\n"
                f"[bold]FAISS Index:[/] {mem_stats.get('faiss_index_size', 0)}\n"
                f"[bold]Pending Consolidation:[/] {mem_stats.get('pending_consolidation', 0)}\n"
                f"[bold]Last Consolidation:[/] {mem_stats.get('last_consolidation', 'Never')[:19]}"
            )
            console.print(Panel(memory_info, title="💾 Memory"))

            # Maintenance status
            opt_status = ctx.world_memory.optimizer.get_stats()
            maint_info = (
                f"[bold]Running:[/] {opt_status.get('running', False)}\n"
                f"[bold]Last Run:[/] {opt_status.get('last_run', 'Never') or 'Never'}\n"
                f"[bold]Interval:[/] {opt_status.get('interval_minutes', 'N/A')} hours"
            )
            console.print(Panel(maint_info, title="🔧 Maintenance"))

            # Director status (get_status is async)
            director_status = await ctx.director.get_status()
            director_info = (
                f"[bold]Running:[/] {director_status.get('running', False)}\n"
                f"[bold]Active Events:[/] {len(director_status.get('active_events', []))}\n"
                f"[bold]Story Chapter:[/] {director_status.get('current_chapter', 1)}"
            )
            console.print(Panel(director_info, title="🎬 Director"))

            # Entity counts
            store = ctx.graph_store
            G = store.get_active_graph() if store else None
            if G:
                entity_counts = {}
                for node, attrs in G.nodes(data=True):
                    etype = attrs.get("type", "?")
                    entity_counts[etype] = entity_counts.get(etype, 0) + 1

                counts_info = "\n".join(f"[bold]{k}:[/] {v}" for k, v in sorted(entity_counts.items()))
                console.print(Panel(counts_info or "No entities", title="📊 Entities"))

        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


# ─────────────────────────────────────────────────────────────────
# Advanced Birth Command
# ─────────────────────────────────────────────────────────────────

@app.command()
def birth(
    hints: str = typer.Option("", help="Optional hints for character creation (e.g., 'noble mage half-elf')"),
    session_id: str = typer.Option("birth_session", help="Session identifier for the new game"),
    isekai: bool = typer.Option(False, "--isekai", help="Enable isekai/reincarnation mode"),
    starting_age: int = typer.Option(5, help="Starting age (in years)"),
    display_probabilities: bool = typer.Option(False, "--display-probabilities", help="Show each roll's probability"),
    verbose: bool = typer.Option(False, "--verbose", help="Show LLM prompts and responses"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Create a brand-new character through birth/reincarnation, with rich narrative."""
    from .birth import BirthScenario

    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()

        try:
            console.print("[bold cyan]🌟 Birth System – Advanced Reincarnation Narrative[/]")
            console.print("Generating your new life...\n")

            # Generate and apply birth
            scenario = BirthScenario(ctx)
            opening_narrative, params = await scenario.generate_and_apply(
                user_hints=hints,
                isekai=isekai,
                starting_age=starting_age,
                display_probabilities=display_probabilities,
            )

            # Display generated info
            console.print(f"[green]✓ Character:[/] {params.character_name}")
            console.print(f"[green]✓ Race:[/] {params.race}")
            console.print(f"[green]✓ Social class:[/] {params.social_class.value}")
            console.print(f"[green]✓ Gender:[/] {params.gender.value}")
            if params.magic_affinity:
                console.print(f"[green]✓ Magic affinity:[/] {params.magic_affinity}")
            console.print(f"[green]✓ Birthplace:[/] {params.birthplace}")
            console.print(f"[green]✓ Birth circumstance:[/] {params.birth_circumstance.value}")
            console.print(f"[green]✓ Starting age:[/] {params.starting_age_years} years")
            console.print(f"[green]✓ Innate traits:[/] {', '.join(params.innate_traits) or 'None'}")
            console.print(f"[green]✓ Innate skills:[/] {len(params.innate_skills)}")

            if params.family_secret:
                console.print(f"[yellow]⚠ Family secret:[/] {params.family_secret}")

            if params.reincarnation:
                console.print(f"\n[bold magenta]✨ Isekai Mode Enabled[/]")
                console.print(f"[magenta]✓ Past life:[/] {params.reincarnation.past_name} from {params.reincarnation.past_world}")
                console.print(f"[magenta]✓ Death cause:[/] {params.reincarnation.death_cause}")
                console.print(f"[magenta]✓ Cheat ability:[/] {params.reincarnation.cheat_ability}")

            # Display opening narrative
            console.print()
            console.print(Panel(opening_narrative, title="🌅 Your Birth", border_style="magenta", expand=False))

            # Create roleplay engine and start session
            engine = ctx.create_roleplay_engine(params.character_name, params.initial_location)
            engine.set_session(
                character=params.character_name,
                location=params.initial_location,
                story_time=datetime.now(),
                role="protagonist"
            )
            engine.save_session(session_id)

            console.print(f"\n[green]Session '{session_id}' saved.[/]")
            console.print("[dim]You can continue playing with:[/]")
            console.print(f"[dim]  world narrative play --session-id {session_id}[/]")

        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


# ─────────────────────────────────────────────────────────────────
# Romance Commands
# ─────────────────────────────────────────────────────────────────

@app.command()
def romance_status(
    character: str = typer.Option(..., "--character", "-c", help="First character"),
    target: str = typer.Option(..., "--target", "-t", help="Second character"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Show romantic relationship status between two characters."""
    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()
        try:
            rel = await ctx.romance_engine.get_relationship(character, target)
            if not rel:
                console.print(f"[yellow]No romantic history between {character} and {target}.[/]")
            else:
                console.print(Panel(
                    f"[bold]Status:[/] {rel.status.value}\n"
                    f"[bold]Affection:[/] {rel.affection:.0%}\n"
                    f"[bold]Compatibility:[/] {rel.compatibility:.0%}\n"
                    f"[bold]Stage:[/] {rel.progression_stage.value}\n"
                    f"[bold]Last Interaction:[/] {rel.last_interaction.strftime('%Y-%m-%d %H:%M')}",
                    title=f"💖 {character} & {target}"
                ))
        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def romance_attempt(
    action: str = typer.Argument(..., help="Action: attraction, flirt, confess, date, kiss, propose, breakup"),
    character: str = typer.Option(..., "--character", "-c", help="Initiating character"),
    target: str = typer.Option(..., "--target", "-t", help="Target character"),
    location: str = typer.Option("unknown", "--location", "-l", help="Location of the action"),
    message: str = typer.Option("", "--message", "-m", help="Optional message for confession"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Attempt a romantic action (attraction, flirt, confess, date, kiss, propose, breakup)."""
    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()
        try:
            action_lower = action.lower()

            if action_lower in ("attraction", "flirt"):
                success, narrative, new_aff = await ctx.romance_engine.attempt_attraction(
                    character, target, location
                )
            elif action_lower == "confess":
                success, narrative, new_aff = await ctx.romance_engine.attempt_confession(
                    character, target, location, message
                )
            elif action_lower == "date":
                success, narrative, aff_change = await ctx.romance_engine.attempt_date(
                    character, target, location
                )
                new_aff = aff_change
            elif action_lower == "kiss":
                success, narrative, new_aff = await ctx.romance_engine.attempt_kiss(
                    character, target, location
                )
            elif action_lower == "propose":
                success, narrative, new_aff = await ctx.romance_engine.attempt_proposal(
                    character, target, location
                )
            elif action_lower == "breakup":
                success, narrative, new_aff = await ctx.romance_engine.attempt_breakup(
                    character, target, message
                )
            else:
                console.print(f"[red]Unknown action: {action}[/]")
                console.print("[yellow]Valid actions: attraction, flirt, confess, date, kiss, propose, breakup[/]")
                return

            # Display results
            status_icon = "✅" if success else "❌"
            console.print(f"\n{status_icon} [bold]{action.capitalize()}[/] result:")
            console.print(f"  {narrative}")
            console.print(f"  [dim]Affection change: {new_aff:+.0%}[/]" if isinstance(new_aff, float) else "")

        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def romance_list(
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status (dating, crush, etc.)"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """List all romantic relationships."""
    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()
        try:
            from world_core.romance import RomanceStatus

            if status:
                try:
                    status_enum = RomanceStatus(status.lower())
                    relationships = await ctx.romance_engine.get_relationships_by_status(status_enum)
                except ValueError:
                    console.print(f"[red]Invalid status: {status}[/]")
                    console.print(f"[yellow]Valid statuses: {[s.value for s in RomanceStatus]}[/]")
                    return
            else:
                relationships = list(ctx.romance_engine._relationships.values())

            if not relationships:
                console.print("[yellow]No romantic relationships found.[/]")
                return

            console.print(f"[bold]Romantic Relationships ({len(relationships)})[/]")
            console.print("-" * 60)

            for rel in relationships:
                names = rel.pair_id.split("_")
                if len(names) == 2:
                    console.print(f"  💕 {names[0]} & {names[1]}")
                    console.print(f"     Status: {rel.status.value} | Affection: {rel.affection:.0%} | Stage: {rel.progression_stage.value}")

        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def romance_gift(
    character: str = typer.Option(..., "--character", "-c", help="Giver"),
    target: str = typer.Option(..., "--target", "-t", help="Receiver"),
    gift: str = typer.Argument(..., help="Gift name"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Give a gift to increase affection."""
    async def _run():
        ctx = NarrativeContext(db_path)
        await ctx.start_background_services()
        try:
            success, narrative, aff_change = await ctx.romance_engine.give_gift(
                character, target, gift
            )
            console.print(f"  {narrative}")
            console.print(f"  [dim]Affection change: {aff_change:+.0%}[/]")
        finally:
            await ctx.stop_background_services()

    loop = get_loop()
    loop.run_until_complete(_run())




@app.command()
def newgame(
    hints: str = typer.Option("", help="Character creation hints (e.g., 'noble mage half-elf')"),
    isekai: bool = typer.Option(False, "--isekai", help="Enable isekai/reincarnation mode"),
    starting_age: int = typer.Option(5, help="Starting age in years"),
    port: int = typer.Option(8000, help="Port for web UI"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open browser automatically"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Start a completely new game: creates world (if needed), generates a character, and launches the UI."""
    from rich.console import Console
    from rich.rule import Rule
    from world_narrative.launcher import (
        system_check, prepare_world, run_birth_wizard, post_birth_tasks,
        save_game_snapshot, launch_game, memory_health_check, NarrativeContext
    )
    from world_narrative.context import NarrativeContext as NC

    console = Console()

    async def _run():
        console.print(Rule("[bold cyan]✨ WORLD ENGINE – NEW GAME ✨[/]"))

        # System check
        ok, msg = system_check()
        if not ok:
            console.print(f"[red]{msg}[/]")
            raise typer.Exit(1)
        console.print(f"[green]✓ {msg}[/]")

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
        await launch_game(ctx, session_id, character_name, open_browser=not no_browser, port=port)

        console.print(f"\n[bold green]✓ Game ready! Session ID: {session_id}[/]")
        console.print("[dim]Use 'world continue --session-id {0}' to resume later.[/]".format(session_id))

    from asyncio import get_event_loop as get_loop
    loop = get_loop()
    loop.run_until_complete(_run())


@app.command()
def continue_cmd(
    session_id: Optional[str] = typer.Option(None, help="Session ID to resume (omit to list)"),
    port: int = typer.Option(8000, help="Web UI port"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open browser"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH),
):
    """Resume an existing game from snapshot or session file."""
    from world_narrative.launcher import load_game_snapshot, continue_game, list_sessions
    from world_narrative.context import NarrativeContext
    from world_explorer.config import DEFAULT_DB_PATH as EXPLORER_DB_PATH

    console = Console()

    if not session_id:
        # List available sessions
        sessions = list_sessions(db_path)
        if not sessions:
            console.print("[yellow]No saved games found. Start a new game with 'newgame'.[/]")
            return

        console.print("[bold]Available sessions:[/]")
        for sid in sessions:
            console.print(f"  [cyan]{sid}[/]")

        console.print("\n[dim]Resume with: world continue --session-id <id>[/]")
        return

    async def _run():
        # Try snapshot first
        ctx = await load_game_snapshot(db_path, session_id)

        if ctx is None:
            # Fallback to normal session load
            ctx = NarrativeContext(db_path)
            await ctx.start_background_services()

            engine = ctx.create_roleplay_engine()
            if not engine.load_session(session_id):
                console.print(f"[red]Session '{session_id}' not found.[/]")
                raise typer.Exit(1)

            console.print(f"[green]Loaded session {session_id}[/]")
        else:
            await ctx.start_background_services()

        # Get character name
        try:
            engine = ctx.create_roleplay_engine()
            character_name = getattr(engine, 'active_character', 'Unknown')
        except Exception:
            character_name = 'Unknown'

        await launch_game(ctx, session_id, character_name, open_browser=not no_browser, port=port)
        console.print(f"[green]Resumed session {session_id}[/]")

    from asyncio import get_event_loop as get_loop
    loop = get_loop()
    loop.run_until_complete(_run())


if __name__ == "__main__":
    app()
