---
name: megamind
description: Persistent cross-session memory for Claude Code. Installed via hooks in ~/.claude/settings.json — SessionStart auto-loads MEMORY.md index + latest session note, UserPromptSubmit injects relevant memory snippets based on keyword match, PreCompact saves a transcript tail before compaction, Stop stamps a last-active marker. Zero external dependencies (Python stdlib + grep). Hard token budgets per hook (session ≤1500, prompt ≤400). Storage: ~/.claude/projects/<slug>/memory/*.md.
---

# MegaMind — persistent memory for Claude Code

## What it does

Claude Code by default has **no memory between sessions**. Project facts you write in `~/.claude/projects/<slug>/memory/` are just files on disk — Claude never reads them unless explicitly told. MegaMind bridges that gap with four hooks registered in `~/.claude/settings.json`.

| Hook | When it fires | What it injects into context | Token cost |
|------|---------------|------------------------------|-----------|
| **SessionStart** | New session opens / resume / clear | `MEMORY.md` index + the single newest `sessions/*.md` note | ≤1500 tokens once per session |
| **UserPromptSubmit** | Every user message | Top-3 memory files matching keywords in the message | ≤400 tokens per prompt (silent if no hit) |
| **PreCompact** | Auto-compaction kicks in | **Nothing** — writes transcript tail to `sessions/compact-*.md` for future sessions to pick up | 0 tokens |
| **Stop** | Claude finishes responding | **Nothing** — updates `.last-active` marker | 0 tokens |

## Design principles

1. **Token-saving, not token-spending.** Every hook has a hard char budget enforced by `format_budget`. Silent no-op when no relevant match found — never pads the context with filler.
2. **Zero deps.** Python 3 stdlib only (`sqlite3`, `pathlib`, `re`, `json`, `os`, `sys`). No pip install, no venv, runs on Windows / macOS / Linux.
3. **Grep-first.** Search is keyword-based via `re.findall` over `*.md` files. Fast for <1000 files, always fresh, no vector index to rebuild. SQLite FTS can be added later if corpus grows.
4. **Project isolation.** Each project's memory lives under `~/.claude/projects/<slug>/memory/`. The hook resolves `cwd` → slug and loads only that project's memory. Worktrees auto-fall-back to their parent project's memory.
5. **Live wins.** Preamble tells Claude: "If anything here contradicts what the user is saying now, the live conversation wins, but mention the discrepancy." Prevents stale memory from overriding fresh user input.

## Directory layout per project

```
~/.claude/projects/<slug>/memory/
├── MEMORY.md              # index — list of files with one-line descriptions
├── facts/                 # long-lived facts about the project
│   ├── pricing.md
│   ├── tech-stack.md
│   └── …
├── sessions/              # session diaries + pre-compact snapshots
│   ├── 2026-04-17-night-session.md
│   └── auto-2026-04-18-0312-compact-auto.md
└── .last-active           # timestamp file updated by Stop hook
```

## Claude-facing invocation

The skill also exposes an on-demand CLI via:

```
python ~/.claude/skills/megamind/scripts/cli.py status
python ~/.claude/skills/megamind/scripts/cli.py recall "<query>"
python ~/.claude/skills/megamind/scripts/cli.py list
```

Use these when:
- User asks "what did we do last session" → `cli.py recall "<their keywords>"`
- You need to see how big the memory has grown → `cli.py status`
- Before writing a new memory file, check for duplicates → `cli.py list`

## When this skill itself should be invoked

Claude should read this SKILL.md only when the user asks about the memory system itself ("how does MegaMind work", "show me memory status", "does Claude remember things"). Normal memory operations happen **invisibly via hooks** — no skill invocation needed.

## Installation

```bash
python ~/.claude/skills/megamind/scripts/install.py
```

The installer registers the four hooks in `~/.claude/settings.json` and creates `~/.claude/projects/` if missing. Safe to run repeatedly — it's idempotent.

## Instructions for Claude (when the user installs or sets up MegaMind)

When the user asks Claude to install, set up, or activate MegaMind (triggers: "install megamind", "nainstaluj megamind", "set up megamind", "rozjeď mi megamind"), follow this exact order:

1. **Clone + register hooks** — confirm `~/.claude/skills/megamind/` exists; if not, `git clone https://github.com/hustlerv369/hustlers-megamind ~/.claude/skills/megamind`. Then run `python ~/.claude/skills/megamind/scripts/install.py`.
2. **Auto-create the private memory vault** — run `python ~/.claude/skills/megamind/scripts/cli.py sync auto-setup`. This creates a **private** GitHub repo named `memory-vault` on the user's account, links `~/.claude/projects/` to it, pushes initial state, and enables autosync (pull on SessionStart, push on Stop). Requires `gh` CLI authenticated. If `gh` is missing or unauthenticated, tell the user the exact next step (`gh auth login`) and stop — never fall back to a public repo.
3. **Verify** — run `python ~/.claude/skills/megamind/scripts/cli.py status` and `sync auto-status`, report what's wired up.
4. **Bootstrap project memory** — if the current project has no `memory/` dir yet, suggest `cli.py init` or `cli.py init --template <name>` (`nextjs-saas`, `python-api`, `react-native`, `data-pipeline`, `seo-site`).

The vault MUST be private. The vault stores the user's project facts, sessions, and decisions — never push that to a public repo. The installer enforces `--private` by default; do not override.

## Natural-language triggers (during normal use)

Once installed, the user will talk to MegaMind in plain language. Map these to CLI calls so the user never has to learn the API:

| User says (CZ / EN) | What Claude does |
|---------------------|-----------------|
| "ulož to do megamindu" / "remember this" / "zapamatuj si" / "save this to megamind" | `python ~/.claude/skills/megamind/scripts/cli.py remember "<concise one-liner of the fact>"` — autosync pushes to `memory-vault` within 10 min, or run `sync push` for instant sync |
| "co jsme dělali minule" / "what did we do last session" / "recall X" | `cli.py recall "<keywords>"` and summarize results |
| "zapomeň X" / "forget X" | `cli.py forget "<keyword>"` |
| "vypiš paměť" / "list memory" / "show me what's saved" | `cli.py list` |
| "stats" / "kolik tokenů jsem ušetřil" | `cli.py stats` |
| "audit" / "zkontroluj jestli tam neunikla hesla" | `cli.py audit` |
| "synchronizuj" / "push memory" / "ulož na vault" | `cli.py sync push` (immediate) |
| "stáhni nejnovější paměť" / "pull from vault" | `cli.py sync pull` |
| "založ nový projekt v paměti" / "init memory here" | `cli.py init [--template <name>]` |

When in doubt, prefer `remember` for new facts (it dedupes against existing entries) and `recall` for retrieval. For longer notes (a full session summary), create a file directly at `~/.claude/projects/<slug>/memory/sessions/<date>-<title>.md` instead of cramming it into MEMORY.md.

## Budgets (tuned for conservative token usage)

Defined in `scripts/lib.py` as module-level constants:

- `BUDGET_SESSION_START = 6000` chars (~1500 tokens)
- `BUDGET_USER_PROMPT = 1600` chars (~400 tokens)
- `BUDGET_SNIPPET = 600` chars per file (~150 tokens)
- `MIN_KEYWORDS = 2` — fewer keywords in a prompt skips injection entirely
- `MIN_KEYWORD_LEN = 4` — 3-char words filtered out as noise

Override any of them by editing `lib.py` or exporting env vars in the hook script.

## Net token math

Per session without MegaMind: user re-explains context → ~3000–8000 tokens wasted.
Per session with MegaMind: ~1500 auto-loaded + ~400 per relevant-keyword prompt.

Break-even after ~3 user messages. After that, every message is pure savings.
