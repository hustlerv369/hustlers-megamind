---
name: megamind
description: The single ULTRA memory + token-saving skill for Claude Code. Persistent cross-session memory via 4 hooks (SessionStart loads the MEMORY.md index + newest CLEAN session note; UserPromptSubmit injects keyword-matched snippets; PreCompact writes a clean structured resume — base64/JSONL/tool-noise stripped at write time, never the raw transcript; Stop stamps last-active + debounced memory-vault auto-sync). Also the home of LEAN MODE — token-discipline directives + a reversible `lean apply` that flips opus[1m]→opus and xhigh→high and flags always-on MCP overhead. Zero external deps (Python stdlib + git CLI). Read this when the user asks about memory, context, recall, OR token/context usage, "save tokens", "reduce context", "session cost", "exhausting my limit". CZ: "paměť", "kontext", "šetřit tokeny", "snížit spotřebu", "megamind".
---

# MegaMind Ultra — memory + token discipline, one skill

Claude Code has no memory between sessions and re-sends a growing context every
turn. MegaMind is the single skill that fixes both: it remembers across sessions
**and** keeps junk out of the context window. Three pillars.

## Pillar 1 — MEMORY (4 hooks, registered in `~/.claude/settings.json`)

| Hook | Fires | Injects | Cost |
|------|-------|---------|------|
| **SessionStart** | session open / resume / clear | `MEMORY.md` index + newest **clean** `sessions/*.md` note (transcript-noise dumps are skipped) + the Lean line | ≤1500 tok once |
| **UserPromptSubmit** | every message | top-3 keyword-matched memory files, **noise-filtered + deduped** | ≤400 tok (silent if no hit) |
| **PreCompact** | before auto-compaction | **nothing to context.** Writes a CLEAN structured resume (`sessions/<stamp>-resume-*.md`) — recent intent, decisions, files touched, commands, open questions — with base64 / tool-JSON stripped at write time | 0 tok |
| **Stop** | response ends | **nothing to context.** Stamps `.last-active` + (if `MEGAMIND_AUTOSYNC=1`) a debounced, secret-scanned vault push | 0 tok |

Storage: `~/.claude/projects/<slug>/memory/{MEMORY.md, facts/, sessions/, .last-active}`.
Project isolation: `cwd → slug` (now maps spaces too, so spaced paths like
`D:\CLAUDE\My App` resolve to their own memory, not the parent's). Worktrees fall
back to the parent repo's memory.

**Why this version saves tokens:** the old PreCompact dumped the raw 20KB transcript
tail — base64 image blobs + tool_result JSONL — which then got injected verbatim at
SessionStart (newest-by-mtime) and keyword-matched into the UserPromptSubmit budget.
A single image blob is ~25k tokens of pure noise. Now: noise can never enter context
(write-time stripping + read-time `is_noise_file`/`is_noise_line` filters), and recall
spends its budget only on real prose.

## Pillar 2 — CONTEXT DISCIPLINE (where your tokens actually go)

Memory is ~1900 tok/session — not the sink. The real drivers, in order:

1. **`opus[1m]` (1M context)** — every turn re-sends the whole growing session as input
   tokens; on a token-metered Max plan this burns the cap fastest. Use standard `opus`
   (200K) by default; reserve 1M for genuinely huge-context tasks.
2. **`effortLevel: xhigh`** — max reasoning every turn. `high` for routine work.
3. **Always-on MCP servers** — each injects tool schemas into EVERY request. Move
   rarely-used ones (Apify schemas are large) to a per-project `.mcp.json`.
4. **Session bloat** — `/clear` on an unrelated task switch, `/compact` to continue;
   route big reads (>~400 lines / >3 files) to a subagent and keep only the conclusion.
5. **Headroom proxy** (compresses tool output ~34%) and **claude-code-router** (route
   routine/background work to a free/cheap model) — keep both in play.

## Pillar 3 — LEAN MODE + the in-session engine

- **Lean directive** — SessionStart injects one ~50-token line reminding the model of
  the discipline above. Default ON; opt out with `~/.claude/megamind-lean.off` (or
  `/megamind lean off`). It sits in the trimmable tail, so it can never push out memory.
- **`/megamind lean apply`** — backs up `settings.json` → `settings.json.megamind-bak`,
  flips `opus[1m]→opus` and `xhigh→high`, lists the always-on MCP servers to prune.
  Applies to NEW sessions (run `/clear` or restart). Revert with `lean restore`.
- **context-mode engine (opt-in, OFF by default).** context-mode sandboxes tool output
  (raw data never enters context) and retrieves via FTS5 — a great idea. But a GLOBAL
  install adds ~2000–3500 schema tokens to EVERY request (11 tools) and double-hooks the
  same 5 events MegaMind owns. So: **absorb the discipline** (route big reads/dumps
  through a subagent or a script that returns a summary — "code-first over Read-47-files")
  and only enable the actual engine **per-project** (`.mcp.json`, hooks disabled, tool
  surface trimmed) for genuinely tool-heavy projects. Never global.

## CLI / slash command

```
/megamind status | recall <query> | list
/megamind lean status | on | off | apply | restore
/megamind vault sync | mirror | prune        # MEGAMIND_AUTOSYNC=1 to enable push
```
Direct: `python ~/.claude/skills/megamind/scripts/cli.py <args>`

## Memory-vault auto-sync (opt-in)

`Stop` can mirror project memory to the `memory-vault` git repo, debounced ≥15 min, with
every git call timeboxed. **Default OFF** (`MEGAMIND_AUTOSYNC=0`): the sync runs git
directly (bypassing Claude's pre-commit secret hook) and your memory-vault repo may be public, so a
stdlib secret scan runs over the staged diff and ABORTS the commit on any key-shaped
token. Enable only after making the repo private or accepting that gate.

## Net token math

Per session without MegaMind: re-explaining context wastes ~3000–8000 tokens.
With MegaMind Ultra: ~1500 auto-loaded + ~400 per relevant prompt — and the recurring
garbage-injection (up to 400 tok/prompt + a hijacked ~500-tok SessionStart slot, spiking
to ~25k when an image blob was eligible) is eliminated entirely. `lean apply` then removes
the structural sinks (1M re-send, xhigh, MCP schemas) that dwarf everything else.

## Install

```
python ~/.claude/skills/megamind/scripts/install.py     # idempotent; warns on global context-mode
```

When to read this SKILL.md: only when the user asks about the memory/token system itself.
Normal operation is invisible via hooks.
