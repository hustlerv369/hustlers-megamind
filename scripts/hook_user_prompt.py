#!/usr/bin/env python3
"""
UserPromptSubmit hook — runs on every user message.

Strategy: extract keywords (≥4 chars) from the user's message, grep the
project memory dir for relevance, inject top 3 matching snippets.

Silent no-op when:
  - No memory dir for this project
  - <2 keywords in user message (low signal → skip injection)
  - No file scores >0

Token budget: ~400 tokens (1600 chars) total.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import (
    BUDGET_SNIPPET,
    BUDGET_USER_PROMPT,
    MIN_KEYWORDS,
    bump_stat,
    extract_keywords,
    extract_snippet,
    find_memory_dir,
    format_budget,
    grep_memory,
    read_hook_input,
)


def main() -> None:
    payload = read_hook_input()
    cwd = payload.get("cwd")
    prompt = payload.get("prompt") or payload.get("user_prompt_text") or ""

    mem = find_memory_dir(cwd)
    if not mem:
        return

    keywords = extract_keywords(prompt)
    if len(keywords) < MIN_KEYWORDS:
        bump_stat(mem, "prompt_miss")
        return

    matches = grep_memory(mem, keywords, max_files=3)
    if not matches:
        bump_stat(mem, "prompt_miss")
        return

    lines: list[str] = ["## 🧠 Memory hits for this message"]
    used = len(lines[0])
    for md in matches:
        rel = md.relative_to(mem)
        snip = extract_snippet(md, keywords, max_chars=BUDGET_SNIPPET)
        block = f"\n\n**{rel}**\n\n{snip}"
        if used + len(block) > BUDGET_USER_PROMPT:
            break
        lines.append(block)
        used += len(block)

    out = format_budget("".join(lines), BUDGET_USER_PROMPT)
    sys.stdout.write(out)
    bump_stat(mem, "prompt_hit")


if __name__ == "__main__":
    main()
