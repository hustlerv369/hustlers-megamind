#!/usr/bin/env python3
"""
Stop hook — fires when Claude finishes responding to a user message.

Used lightly: only refreshes a `last-active.md` marker in memory/ so the
next session's SessionStart hook knows this project was recently touched.
Does NOT inject anything into context.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import find_memory_dir, now_iso, project_slug_from_cwd, read_hook_input


def main() -> None:
    payload = read_hook_input()
    cwd = payload.get("cwd")
    mem = find_memory_dir(cwd)
    if not mem:
        return
    # 1) Instant last-active stamp (unchanged 0-token contract, runs first).
    try:
        marker = mem / ".last-active"
        marker.write_text(now_iso(), encoding="utf-8")
    except Exception:
        pass
    # 2) Memory-vault auto-sync — debounced (≥15min) + AUTOSYNC-gated + every git
    # call timeboxed, so this is effectively free and never blocks turn-end. Fully
    # swallowed: a missing/broken vault.py can never break the Stop hook.
    try:
        import vault  # local module

        slug = project_slug_from_cwd(cwd)
        if slug:
            vault.sync(slug)
    except Exception:
        pass
    # 3) Refresh the OpenCode brain bridge so MiniMax/Kimi in the OpenCode panel
    # share the same Megamind memory as Claude — scoped to THIS project's cwd
    # (previously hardcoded to one fixed project, so every other project's Stop
    # event silently overwrote the bridge file with the wrong project's memory).
    # Best-effort, timeboxed, fully swallowed — never blocks turn-end.
    try:
        import subprocess  # stdlib

        bridge = Path(__file__).parent / "opencode_bridge.py"
        if bridge.exists() and cwd:
            subprocess.run(
                [sys.executable, str(bridge), cwd],
                timeout=15,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass


if __name__ == "__main__":
    main()
