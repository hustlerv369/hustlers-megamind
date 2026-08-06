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
    LEAN_LINE,
    caveman_session_block,
    find_memory_dir,
    format_budget,
    latest_session_note,
    lean_on,
    load_seen,
    memory_index,
    norm_relpath,
    prune_old_ledgers,
    read_hook_input,
    save_seen,
    session_key,
)


def main() -> None:
    payload = read_hook_input()
    cwd = payload.get("cwd")
    sid = session_key(payload)
    mem = find_memory_dir(cwd)
    if not mem:
        # Silent — project has no memory yet, nothing to inject.
        return

    parts: list[str] = []

    idx = memory_index(mem, max_chars=3000)
    if idx:
        parts.append("## 🧠 Project memory index\n" + idx)

    latest = latest_session_note(mem)
    if latest:
        try:
            body = latest.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            body = ""
        if body:
            # Clip to ~1300 chars (~325 tokens). The new PreCompact resumes are
            # already small + clean, so this rarely truncates — it just caps the
            # latest-note slot so a long hand-written note can't bloat startup.
            if len(body) > 1300:
                body = body[:1285].rstrip() + "\n[...truncated]"
            parts.append(
                f"## 📓 Most recent session note — `{latest.name}`\n{body}"
            )

    # Lean directive last → it lands in the trimmable tail, so under budget
    # pressure the real memory body is kept and this ~50-token line is dropped
    # first (format_budget clips the END). Opt out via ~/.claude/megamind-lean.off.
    if lean_on():
        parts.append("## ⚡ Lean mode\n" + LEAN_LINE)

    # Caveman ruleset (output-token compression). Built separately so it lives in its
    # OWN slot — memory budget pressure can never clip it, and it never pushes memory
    # out. '' when the permanent kill switch (megamind-caveman.off) is set.
    caveman_block = caveman_session_block(sid)

    if not parts and not caveman_block:
        return

    # Pre-seed the per-session inject ledger with what we load HERE (index + latest
    # resume note), so the per-turn UserPromptSubmit hook never re-injects this
    # working-memory content — it already lives in this cache-stable SessionStart
    # prefix. Disk-only (0 tokens added to the payload), fully fail-silent.
    try:
        prune_old_ledgers()
        if sid:
            seed: set[str] = set()
            if idx:
                seed.add("MEMORY.md")
            if latest is not None and body:
                seed.add(norm_relpath(latest.relative_to(mem)))
            if seed:
                save_seen(sid, load_seen(sid) | seed)
    except Exception:
        pass

    # Assemble: caveman ruleset first (its own slot), then the budgeted memory body.
    out_chunks: list[str] = []
    if caveman_block:
        out_chunks.append(caveman_block)

    if parts:
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
        out_chunks.append(format_budget(full, BUDGET_SESSION_START))

    # stdout = additionalContext for SessionStart / UserPromptSubmit hooks
    sys.stdout.write("\n\n---\n\n".join(out_chunks))


if __name__ == "__main__":
    main()
