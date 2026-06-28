#!/usr/bin/env python3
"""
UserPromptSubmit hook — runs on every user message.

Strategy (Ultra v2 — "inject deltas only"): extract keywords from the user's
message, grep the project memory dir with the STRICT inject gate (coverage +
relevance floor), then inject ONLY files not already surfaced this session. A
note injected once is carried forward for free in the cached conversation
prefix, so re-injecting it every turn is pure waste — the per-session ledger
collapses that O(N²) duplicate cost to O(N).

Silent no-op when:
  - No memory dir for this project
  - <2 keywords in user message (low signal → skip injection)
  - No file clears the coverage gate + relevance floor
  - Every relevant file was already injected this session (nothing NEW)

Token budget: ~400 tokens (1600 chars) total. Most turns now inject NOTHING.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import (
    BUDGET_SNIPPET,
    BUDGET_USER_PROMPT,
    MIN_KEYWORDS,
    extract_keywords,
    extract_snippet,
    find_memory_dir,
    format_budget,
    grep_memory,
    load_seen,
    norm_relpath,
    prune_old_ledgers,
    read_hook_input,
    save_seen,
    session_key,
)

HEADER = "## 🧠 Memory hits for this message"


def main() -> None:
    payload = read_hook_input()
    cwd = payload.get("cwd")
    prompt = payload.get("prompt") or payload.get("user_prompt_text") or ""

    mem = find_memory_dir(cwd)
    if not mem:
        return

    keywords = extract_keywords(prompt)
    if len(keywords) < MIN_KEYWORDS:
        return

    # Strict inject gate: coverage + relevance floor (kills weak/irrelevant hits).
    matches = grep_memory(mem, keywords, max_files=3, inject=True)
    if not matches:
        return

    # Cross-turn dedup: skip any file already injected this session (or pre-seeded
    # by SessionStart). Fail-silent — missing session id → empty set → no dedup.
    sid = session_key(payload)
    seen = load_seen(sid)

    blocks: list[str] = []
    emitted: set[str] = set()
    used = len(HEADER)
    for md in matches:
        rel = md.relative_to(mem)
        key = norm_relpath(rel)
        if key in seen:  # already in context this session — re-injecting is waste
            continue
        snip = extract_snippet(md, keywords, max_chars=BUDGET_SNIPPET)
        block = f"\n\n**{rel}**\n\n{snip}"
        if used + len(block) > BUDGET_USER_PROMPT:
            break
        blocks.append(block)
        emitted.add(key)
        used += len(block)

    if not blocks:  # nothing NEW survived — emit nothing (not even the header)
        return

    out = format_budget(HEADER + "".join(blocks), BUDGET_USER_PROMPT)
    sys.stdout.write(out)

    # Record what we injected so later turns don't repeat it; bound the dir.
    save_seen(sid, seen | emitted)
    prune_old_ledgers()


if __name__ == "__main__":
    main()
