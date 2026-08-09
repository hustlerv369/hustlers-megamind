#!/usr/bin/env python3
"""
PreCompact hook — fires when Claude Code is about to compact the transcript.

ULTRA: instead of dumping the last 20KB of the RAW transcript (which carried
base64 image blobs + tool_use/tool_result JSONL that later polluted recall and
the SessionStart slot), this parses the transcript and writes a CLEAN, bounded,
structured resume — recent intent, decisions, files touched, commands, open
questions — with all binary/JSON noise stripped at write time.

Writes to disk only (0 tokens at write time). Writes NO file if there's nothing
clean to save, so it never seeds a garbage note. Never crashes compaction.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import (
    build_resume,
    clear_seen,
    find_memory_dir,
    iter_transcript_blocks,
    log_err,
    now_iso,
    prune_old_resume_notes,
    read_hook_input,
    session_key,
    write_session_summary,
)


def main() -> None:
    payload = read_hook_input()
    cwd = payload.get("cwd")
    transcript_path = payload.get("transcript_path")
    trigger = payload.get("trigger") or "unknown"  # 'auto' | 'manual'

    # Compaction throws away the context window, so everything the inject ledger
    # marked as "already delivered" is gone. Clear it FIRST — before any early
    # return below — otherwise memory stays permanently suppressed for the rest
    # of the session and the model silently loses the project's facts.
    clear_seen(session_key(payload))

    mem = find_memory_dir(cwd)
    if not mem:
        return

    try:
        records = iter_transcript_blocks(transcript_path) if transcript_path else []
        resume = build_resume(records)
        if not resume:
            # Nothing clean worth saving — write NO garbage file.
            return
        body = "\n".join(
            [
                f"# Resume snapshot — {now_iso()}",
                "",
                f"Trigger: `{trigger}`",
                "",
                "Clean structured resume written right before compaction. The raw transcript,",
                "base64 blobs, and tool JSON were stripped at write time so future sessions",
                "recall signal, not noise.",
                "",
                "---",
                "",
                resume,
            ]
        )
        write_session_summary(mem, f"resume-{trigger}", body)
        prune_old_resume_notes(mem)
    except Exception as exc:
        # Only truly unexpected failures get logged; the expected
        # empty/absent-transcript path is silent to keep PreCompact at 0 tokens.
        log_err(f"pre-compact: {exc}")


if __name__ == "__main__":
    main()
