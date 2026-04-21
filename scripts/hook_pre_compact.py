#!/usr/bin/env python3
"""
PreCompact hook — fires when Claude Code is about to auto-compact the transcript.

Writes a session-summary file to memory/sessions/auto-<stamp>.md so that
nothing of value is lost when older context gets dropped. The file contains
the last N KB of the transcript plus any extractable todo/decisions.

This hook does NOT inject anything back into context (saving tokens); it
only writes to disk. The next SessionStart hook will pick it up naturally.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import bump_stat, find_memory_dir, log_err, now_iso, read_hook_input, write_session_summary

TRANSCRIPT_TAIL_BYTES = 20000  # ~5k tokens — cheap to re-read next session


def main() -> None:
    payload = read_hook_input()
    cwd = payload.get("cwd")
    transcript_path = payload.get("transcript_path")
    trigger = payload.get("trigger") or "unknown"  # 'auto' | 'manual'

    mem = find_memory_dir(cwd)
    if not mem:
        return

    tail = ""
    if transcript_path:
        try:
            p = Path(transcript_path)
            if p.exists():
                size = p.stat().st_size
                with p.open("rb") as f:
                    if size > TRANSCRIPT_TAIL_BYTES:
                        f.seek(size - TRANSCRIPT_TAIL_BYTES)
                    tail = f.read().decode("utf-8", errors="ignore")
        except Exception as exc:
            log_err(f"pre-compact: failed to read transcript: {exc}")

    body_parts = [
        f"# Pre-compact snapshot — {now_iso()}",
        f"",
        f"Trigger: `{trigger}`",
        f"",
        "Auto-saved right before Claude Code compacted older context. The tail of",
        "the transcript is preserved below so facts and decisions discussed in",
        "the first half of the session can still be recovered by future sessions.",
        "",
        "---",
        "",
        "## Transcript tail",
        "",
        "```",
        tail or "(transcript unavailable)",
        "```",
    ]

    try:
        write_session_summary(mem, f"compact-{trigger}", "\n".join(body_parts))
        bump_stat(mem, "compact")
    except Exception as exc:
        log_err(f"pre-compact: write failed: {exc}")


if __name__ == "__main__":
    main()
