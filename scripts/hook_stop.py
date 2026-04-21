#!/usr/bin/env python3
"""
Stop hook — fires when Claude finishes responding to a user message.

Refreshes a `.last-active` marker in memory/ and — if autosync is on —
pushes any pending memory changes to the vault remote (rate-limited to
one commit per 10 minutes, so a fast-iterating session doesn't spam the
log).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import find_memory_dir, now_iso, read_hook_input
from sync import autosync_tick_if_due


def main() -> None:
    payload = read_hook_input()
    cwd = payload.get("cwd")
    mem = find_memory_dir(cwd)
    if mem:
        try:
            (mem / ".last-active").write_text(now_iso(), encoding="utf-8")
        except Exception:
            pass

    # Fire autosync if enabled. Runs silently, never raises, never writes to
    # stdout (which would end up in Claude's context for this hook event).
    try:
        autosync_tick_if_due()
    except Exception:
        pass


if __name__ == "__main__":
    main()
