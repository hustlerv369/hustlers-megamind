#!/usr/bin/env python3
"""
SessionStart hook — runs when a new Claude Code session begins.

Injects:
  1. Project memory index (MEMORY.md) — always, if it exists
  2. The single most recent session note — so we resume where we left off

Token budget: ~1500 tokens (6000 chars) total.
Silent no-op if the project has no memory dir yet.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import (
    BUDGET_SESSION_START,
    bump_stat,
    find_memory_dir,
    format_budget,
    latest_session_note,
    memory_index,
    read_hook_input,
)
from sync import autopull_if_due


def main() -> None:
    payload = read_hook_input()
    cwd = payload.get("cwd")

    # Best-effort: if the user has vault sync on, pull fresh memory from
    # other devices before loading. Silent on any failure (offline, auth).
    try:
        autopull_if_due()
    except Exception:
        pass

    mem = find_memory_dir(cwd)
    if not mem:
        # Silent — project has no memory yet, nothing to inject.
        return

    parts: list[str] = []

    idx = memory_index(mem, max_chars=4000)
    if idx:
        parts.append("## 🧠 Project memory index\n" + idx)

    latest = latest_session_note(mem)
    if latest:
        try:
            body = latest.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            body = ""
        if body:
            # Clip to ~2000 chars (~500 tokens)
            if len(body) > 2000:
                body = body[:1985].rstrip() + "\n[...truncated]"
            parts.append(
                f"## 📓 Most recent session note — `{latest.name}`\n{body}"
            )

    if not parts:
        return

    # Preamble gives Claude clear instructions on how to use this context.
    preamble = (
        "The following context is auto-loaded from persistent project memory "
        "(~/.claude/projects/*/memory/). Treat it as background — you already "
        "know these facts. Do NOT re-summarize it to the user unless asked. "
        "If anything here contradicts what the user is saying now, the live "
        "conversation wins, but mention the discrepancy."
    )
    body = "\n\n---\n\n".join(parts)
    full = f"{preamble}\n\n---\n\n{body}"
    full = format_budget(full, BUDGET_SESSION_START)

    # stdout = additionalContext for SessionStart / UserPromptSubmit hooks
    sys.stdout.write(full)
    bump_stat(mem, "session_start")


if __name__ == "__main__":
    main()
