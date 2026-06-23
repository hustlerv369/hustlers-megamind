#!/usr/bin/env python3
"""
MegaMind installer — registers the four hooks in ~/.claude/settings.json.

Idempotent: running it multiple times leaves exactly one entry per hook.
Does NOT touch any other section of settings.json (MCP servers, permissions, etc.).

Usage:
    python ~/.claude/skills/megamind/scripts/install.py            # install
    python ~/.claude/skills/megamind/scripts/install.py --uninstall # remove
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Windows cp1250 crashes on unicode arrows/emoji by default; force UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

CLAUDE_HOME = Path(os.environ.get("CLAUDE_HOME") or (Path.home() / ".claude"))
SETTINGS = CLAUDE_HOME / "settings.json"
SCRIPTS = CLAUDE_HOME / "skills" / "megamind" / "scripts"

# Marker string used to identify our hook entries on re-install.
MARKER = "megamind/scripts/hook_"

HOOKS_TO_INSTALL = {
    "SessionStart": SCRIPTS / "hook_session_start.py",
    "UserPromptSubmit": SCRIPTS / "hook_user_prompt.py",
    "PreCompact": SCRIPTS / "hook_pre_compact.py",
    "Stop": SCRIPTS / "hook_stop.py",
}


def load_settings() -> dict:
    if not SETTINGS.exists():
        return {}
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Failed to parse {SETTINGS}: {exc}", file=sys.stderr)
        sys.exit(1)


def save_settings(data: dict) -> None:
    # Backup first
    if SETTINGS.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = SETTINGS.with_suffix(f".json.bak-{stamp}")
        shutil.copy2(SETTINGS, backup)
    SETTINGS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_hook_entry(script_path: Path) -> dict:
    # Use `python` explicitly for cross-platform compat. Absolute path to script.
    # Works in Git Bash on Windows, macOS, Linux.
    return {
        "hooks": [
            {
                "type": "command",
                "command": f'python "{script_path.as_posix()}"',
            }
        ]
    }


def strip_existing(entries: list, marker: str) -> list:
    """Drop any entry whose command references our marker — avoids duplicates."""
    out = []
    for entry in entries:
        hooks = entry.get("hooks") or []
        if any(marker in (h.get("command") or "") for h in hooks):
            continue
        out.append(entry)
    return out


def warn_contextmode_global() -> None:
    """Megamind owns all 5 lifecycle hooks. If context-mode is registered GLOBALLY
    it adds 11 tool schemas to every request + duplicate hooks on the same events —
    the worst cost shape on a 1M-context metered plan. Warn so it stays npm-only +
    per-project (.mcp.json) with hooks disabled."""
    try:
        settings = load_settings()
        mcp = settings.get("mcpServers") or {}
        hooks = settings.get("hooks") or {}
        hit = any("context-mode" in k.lower() or k.lower() == "ctx" for k in mcp)
        for entries in hooks.values():
            for e in entries or []:
                for h in e.get("hooks") or []:
                    cmd = (h.get("command") or "").lower()
                    if "context-mode" in cmd:
                        hit = True
        if hit:
            print("\n⚠  context-mode appears registered GLOBALLY in settings.json.")
            print("   Keep it npm-only + per-project (.mcp.json) with hooks disabled —")
            print("   a global install collides with megamind's 5 hooks and bloats every")
            print("   request with 11 tool schemas. See megamind SKILL.md → Lean Mode.")
    except Exception:
        pass


def install() -> None:
    settings = load_settings()
    hooks = settings.setdefault("hooks", {})

    for event, script in HOOKS_TO_INSTALL.items():
        if not script.exists():
            print(f"  SKIP {event}: {script} missing", file=sys.stderr)
            continue
        existing = hooks.get(event) or []
        # Drop any previous megamind entry for this event
        cleaned = strip_existing(existing, MARKER)
        # Append fresh entry
        cleaned.append(build_hook_entry(script))
        hooks[event] = cleaned
        print(f"  + {event} → {script.name}")

    save_settings(settings)
    print(f"\nInstalled. Backup of previous settings saved alongside {SETTINGS}.")
    print("Restart Claude Code (or open a new session) for hooks to take effect.")
    warn_contextmode_global()


def uninstall() -> None:
    settings = load_settings()
    hooks = settings.get("hooks") or {}
    changed = False
    for event in list(hooks.keys()):
        cleaned = strip_existing(hooks[event], MARKER)
        if len(cleaned) != len(hooks[event]):
            hooks[event] = cleaned
            changed = True
            print(f"  - {event}")
        if not cleaned:
            del hooks[event]
    if not hooks:
        settings.pop("hooks", None)
    if changed:
        save_settings(settings)
        print("Uninstalled.")
    else:
        print("No MegaMind hooks found — nothing to do.")


def main() -> None:
    args = sys.argv[1:]
    if "--uninstall" in args or "-u" in args:
        uninstall()
    else:
        install()


if __name__ == "__main__":
    main()
