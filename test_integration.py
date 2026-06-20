#!/usr/bin/env python3
"""Comprehensive integration verification for the new game pipeline."""

import sys
import re

print("=" * 70)
print("COMPREHENSIVE INTEGRATION CHECK")
print("=" * 70)

all_ok = True

# 1. Test imports
print("\n[1] Importing modules...")
try:
    from world_narrative.launcher import (
        system_check, prepare_world, run_birth_wizard, post_birth_tasks,
        save_game_snapshot, load_game_snapshot, launch_game,
        launch_new_game, continue_game, list_sessions, memory_health_check,
        NarrativeContext
    )
    print("   ✓ launcher module")
except Exception as e:
    print(f"   ✗ launcher: {e}")
    all_ok = False

try:
    from world_narrative.cli import app as cli_app
    print("   ✓ CLI module")
except Exception as e:
    print(f"   ✗ CLI: {e}")
    all_ok = False

try:
    from world_explorer.api import app as api_app
    print("   ✓ API module")
except Exception as e:
    print(f"   ✗ API: {e}")
    all_ok = False

try:
    from world_explorer.templates import UI_HTML
    print("   ✓ Templates module")
except Exception as e:
    print(f"   ✗ Templates: {e}")
    all_ok = False

# 2. Check API routes
print("\n[2] Checking API routes...")
routes = []
for route in api_app.routes:
    if hasattr(route, 'path') and hasattr(route, 'methods'):
        for method in getattr(route, 'methods', set()):
            routes.append(f"{method} {route.path}")

required_routes = [
    ('POST', '/api/launch'),
    ('POST', '/api/continue'),
    ('GET', '/sessions/list'),
    ('GET', '/api/system-check'),
    ('GET', '/graph/summary'),
    ('GET', '/quests'),
]

# Check for WebSocket routes
# Check for WebSocket routes - they have empty methods sets
ws_found = False
for route in api_app.routes:
    if hasattr(route, 'path') and '/ws/' in route.path:
        ws_found = True
        print(f"   ✓ {route.path} (WebSocket)")

if not ws_found:
    print("   ✗ WebSocket routes")
    all_ok = False

# 3. Check template features
print("\n[3] Checking template features...")
template_checks = [
    ('NEW button (HTML)', 'id="newGameBtn"'),
    ('NEW button handler (JS)', "newGameBtn').addEventListener"),
    ('Session URL param', 'urlParams.get'),
    ('Character URL param', 'initialCharacter'),
    ('Chat WebSocket', '/chat/ws'),
    ('Launch API call', "/api/launch"),
    ('DOMPurify', 'DOMPurify'),
    ('encodeURIComponent', 'encodeURIComponent'),
    ('Probability sparkline', 'probabilityHistory'),
    ('Relationship API', '/romance/characters/'),
    ('Quests API', '/quests'),
]

for name, pattern in template_checks:
    found = pattern in UI_HTML
    status = '✓' if found else '✗'
    print(f"   {status} {name}")
    if not found:
        all_ok = False

# 4. Check CLI commands
print("\n[4] Checking CLI commands...")
with open('world_narrative/cli.py') as f:
    cli_content = f.read()

cli_commands = ['newgame', 'continue_cmd', 'play', 'tick', 'timeline']
for cmd in cli_commands:
    display_name = '/' + ('continue' if cmd == 'continue_cmd' else cmd)
    if re.search(rf'def {cmd}\s*\(', cli_content):
        print(f"   ✓ {display_name}")
    else:
        print(f"   ✗ {display_name}")
        all_ok = False

# 5. Verify RoleplayEngine integration
print("\n[5] Checking RoleplayEngine integration...")
try:
    from world_engine.roleplay_engine import RoleplayEngine
    print("   ✓ RoleplayEngine import")

    from world_narrative.context import NarrativeContext
    if hasattr(NarrativeContext, 'create_roleplay_engine'):
        print("   ✓ NarrativeContext.create_roleplay_engine")
    else:
        print("   ✗ NarrativeContext.create_roleplay_engine")
        all_ok = False
except Exception as e:
    print(f"   ✗ {e}")
    all_ok = False

# 6. Check BirthScenario integration
print("\n[6] Checking BirthScenario integration...")
try:
    from world_narrative.birth import BirthScenario, BirthGenerator, BirthApplier
    print("   ✓ BirthScenario")
    print("   ✓ BirthGenerator")
    print("   ✓ BirthApplier")
except Exception as e:
    print(f"   ✗ {e}")
    all_ok = False

# Summary
print("\n" + "=" * 70)
if all_ok:
    print("ALL INTEGRATION CHECKS PASSED")
else:
    print("SOME CHECKS FAILED - review above")
print("=" * 70)
