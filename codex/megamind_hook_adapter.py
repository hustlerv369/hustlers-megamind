#!/usr/bin/env python3
"""Codex <-> Megamind hook adapter (14. 9. 2026).

Codex vyzaduje, aby hook zapsal na stdout JSON podle sveho schematu
(`{"continue": bool, "hookSpecificOutput": {...}}`). Megamind hooky psane pro
Claude Code emituji holy markdown, takze je Codex odmital s
"hook returned invalid JSON output" a hlasil `UserPromptSubmit Failed` —
tise tim zahazoval injektovanou pamet.

Tenhle adapter spusti puvodni Megamind hook beze zmeny, vezme jeho stdout
a zabali ho do `additionalContext`. Kdyz hook nic nevrati, posle prazdny
(ale platny) objekt. Chybu hooku nikdy neeskaluje — pamet nesmi blokovat turn.

Pouziti (v ~/.codex/hooks.json):
    python "<...>/megamind_hook_adapter.py" <EventName> "<cesta k hooku>"
"""
import json
import subprocess
import sys
from megamind_delivery import prepare_delivery

# The adapter runs in a separate process from the UTF-8 shared hook. Windows
# pipes otherwise retain CP1250 and reject valid Unicode before emitting JSON.
for _stream in (sys.stdin, sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        _stream.reconfigure(encoding='utf-8', errors='replace')


def main() -> int:
    if len(sys.argv) < 3:
        sys.stdout.write(json.dumps({"continue": True}))
        return 0

    event, target = sys.argv[1], sys.argv[2]
    payload = sys.stdin.read()

    context = ""
    try:
        proc = subprocess.run(
            [sys.executable, target],
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=55,
        )
        if proc.returncode != 0:
            context = f"MegaMind {event} failed (exit {proc.returncode}). Memory was not loaded; retrieve project history explicitly."
            sys.stderr.write(context + "\n")
        else:
            context = (proc.stdout or "").strip()
    except Exception:
        # Pamet je best-effort: selhani hooku nesmi shodit ani zablokovat turn.
        context = f"MegaMind {event} could not run. Memory was not loaded; retrieve it explicitly."
        sys.stderr.write(context + "\n")

    out = {"continue": True}
    if context:
        context, delivery_status = prepare_delivery(context, event)
        if delivery_status == 'failed':
            sys.stderr.write('MegaMind: complete delivery artifact could not be saved.\n')
        out["hookSpecificOutput"] = {
            "hookEventName": event,
            "additionalContext": context,
        }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
