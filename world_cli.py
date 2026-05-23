"""
Unified CLI entry point for the World Engine.

This module provides a single entry point that routes commands to the appropriate
sub-CLI modules (world_builder, world_explorer, world_intelligence, world_narrative).

Usage:
    python world_cli.py builder build --force
    python world_cli.py explore show Character:Kaelen
    python world_cli.py intel analyze
    python world_cli.py narrative play --character Kaelen
    python world_cli.py info
    python world_cli.py prob show combat --character Kaelen
"""
import sys
import subprocess
import warnings
from pathlib import Path

# Suppress FAISS warning
warnings.filterwarnings("ignore", message=".*FAISS.*")

# Module mapping: subcommand -> (module, default_command)
MODULES = {
    "builder": "world_builder.cli",
    "explore": "world_explorer.cli",
    "intel": "world_intelligence.cli",
    "narrative": "world_narrative.cli",
    # Aliases
    "add": ("world_builder.cli", None),
    "search": ("world_explorer.cli", "search"),
    "build": ("world_builder.cli", "build"),
    "show": ("world_explorer.cli", "show"),
    "neighbors": ("world_explorer.cli", "neighbors"),
    "path": ("world_explorer.cli", "path"),
    "layer": ("world_explorer.cli", "layer"),
    "visualize": ("world_explorer.cli", "visualize"),
    "branch": ("world_explorer.cli", "branch"),
    "analyze": ("world_intelligence.cli", "analyze"),
    "recommend": ("world_intelligence.cli", "recommend"),
    "expand": ("world_intelligence.cli", "expand"),
    "enrich": ("world_intelligence.cli", "enrich"),
    "check-rules": ("world_intelligence.cli", "check-rules"),
    "deduplicate": ("world_intelligence.cli", "deduplicate"),
    "play": ("world_narrative.cli", "play"),
    "tick": ("world_narrative.cli", "tick"),
    "timeline": ("world_narrative.cli", "timeline"),
    "schedule": ("world_narrative.cli", "schedule"),
    "npc-status": ("world_narrative.cli", "npc-status"),
    "director-status": ("world_narrative.cli", "director-status"),
    "memory-maintenance": ("world_narrative.cli", "memory-maintenance"),
    "memory-status": ("world_narrative.cli", "memory-status"),
    "memory-forget": ("world_narrative.cli", "memory-forget"),
    "memory-summarise": ("world_narrative.cli", "memory-summarise"),
    "memory-export": ("world_narrative.cli", "memory-export"),
    "memory-import": ("world_narrative.cli", "memory-import"),
    "info": ("world_narrative.cli", "info"),
    "prob": ("world_narrative.cli", "prob"),
    "birth": ("world_narrative.cli", "birth"),
    "romance": ("world_narrative.cli", "romance"),
    "romance-status": ("world_narrative.cli", "romance_status"),
    "romance-attempt": ("world_narrative.cli", "romance_attempt"),
    "romance-list": ("world_narrative.cli", "romance_list"),
    "romance-gift": ("world_narrative.cli", "romance_gift"),
    "serve": ("world_cli", "serve"),
}


# Direct command implementations for commands not in sub-CLIs
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
    db_path: Path = None,
):
    """Start the Web API server (REST + WebSocket)."""
    import uvicorn
    from world_explorer.api import app as fastapi_app
    from world_explorer.config import DEFAULT_DB_PATH

    effective_db_path = db_path or DEFAULT_DB_PATH
    print(f"Starting API server at http://{host}:{port}")
    print(f"Using database: {effective_db_path}")
    print(f"WebSocket endpoint: ws://{host}:{port}/ws/roleplay/{{session_id}}")

    uvicorn.run(
        fastapi_app,
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )


def get_module_and_command(subcommand: str):
    """Get the module and default command for a subcommand."""
    if subcommand in MODULES:
        mapping = MODULES[subcommand]
        if isinstance(mapping, tuple):
            return mapping[0], mapping[1]
        return mapping, None
    return None, None


def print_help():
    """Print the main help message."""
    print("""🌍 World Engine – Complete narrative system

Usage: python world_cli.py <command> [options] [arguments]

Main Commands:
  builder    World creation and entity management
  explore    Graph navigation and visualization
  intel      Analysis, recommendations, and enrichment
  narrative  Story simulation, roleplay, and memory

Common Aliases:
  build              -> builder build
  add                -> builder add
  search             -> explore search
  show               -> explore show
  neighbors          -> explore neighbors
  path               -> explore path
  layer              -> explore layer
  analyze            -> intel analyze
  recommend          -> intel recommend
  expand             -> intel expand
  enrich             -> intel enrich
  play               -> narrative play
  tick               -> narrative tick
  timeline           -> narrative timeline
  info               -> narrative info
  prob               -> narrative prob
  birth              -> narrative birth (character creation with family & lineage)
  romance            -> narrative romance (relationship commands)
  romance-status     -> Check relationship status between two characters
  romance-attempt    -> Attempt romantic action (confess, date, propose, etc.)
  romance-list       -> List all romantic relationships
  romance-gift       -> Give a gift to increase affection

Memory Commands:
  memory-maintenance -> Run memory maintenance
  memory-status      -> Show memory status
  memory-forget      -> Forget old memories
  memory-export      -> Export memories to file
  memory-import      -> Import memories from file

Examples:
  python world_cli.py builder build --force
  python world_cli.py explore show Character:Kaelen -l l2
  python world_cli.py explore search "sword" --semantic
  python world_cli.py intel analyze
  python world_cli.py narrative play --character Kaelen
  python world_cli.py narrative info
  python world_cli.py prob show combat --character Kaelen --target Goblin
  python world_cli.py memory-export memories.json
  python world_cli.py birth --hints "noble mage" --isekai
  python world_cli.py romance-status --character Kaelen --target Elara
  python world_cli.py romance-attempt confess --character Kaelen --target Elara --location "Moonlight Garden"
  python world_cli.py romance-list --status dating
  python world_cli.py romance-gift Kaelen --target Elira --message "A rose"

For more information on a command, run:
  python world_cli.py <command> --help
""")


def main():
    """Main entry point for the unified CLI."""
    if len(sys.argv) < 2:
        print_help()
        sys.exit(0)

    subcommand = sys.argv[1]

    # Handle --help on the main command
    if subcommand in ("--help", "-h"):
        print_help()
        sys.exit(0)

    # Check if it's a known subcommand
    if subcommand not in MODULES:
        print(f"Unknown command: {subcommand}")
        print("\nRun 'python world_cli.py --help' for usage information.")
        sys.exit(1)

    # Get module and default command
    module, default_cmd = get_module_and_command(subcommand)

    # Build the command
    cmd = [sys.executable, "-m", module]

    # Add default command if this is an alias
    if default_cmd:
        cmd.append(default_cmd)

    # Add remaining arguments (filter out the subcommand itself)
    remaining = sys.argv[2:]
    cmd.extend(remaining)

    # Run the subcommand
    try:
        result = subprocess.run(cmd)
        sys.exit(result.returncode)
    except Exception as e:
        print(f"Error running command: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
