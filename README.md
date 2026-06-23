<p align="center">
  <img src="presentation/logo/megamind-logo-512.png" width="200" alt="Megamind Ultra — a mafioso-brain logo" />
</p>

<h1 align="center">🧠⚡ Megamind Ultra</h1>

> **One Claude Code skill that does both: cross-session memory _and_ hard token discipline. Local, zero-dependency, automatic in every session.**

Claude Code forgets everything between sessions, and quietly burns your token budget on things you never see — always-loaded skill descriptions, a 1M context that re-sends every turn, raw transcript noise re-ingested after each compaction. **Megamind Ultra attacks all of these at once.** It runs invisibly through four hooks — nothing to invoke, nothing to remember. Install it once and every new session starts with your project context loaded and the noise stripped out.

- 🧠 **Remembers** your project across sessions — auto-loaded at start, keyword-recalled per prompt.
- ✂️ **Keeps junk out of context** — clean structured resumes instead of raw transcript dumps; no base64 or tool-JSON ever re-ingested.
- 💸 **Saves a large chunk of tokens every session, before you even type** — plus the structural win on long sessions (see the measured numbers below).
- 🔌 **Zero external deps** — Python 3 stdlib + the `git` CLI. Windows, macOS, and Linux.

---

## What it is

Megamind Ultra is a single Claude Code **skill** that installs **four lifecycle hooks** into `~/.claude/settings.json`. Once installed there is nothing to call — the hooks fire automatically on every session, on every machine you sync your config to.

It is built on a simple, honest realization: **memory was never the token sink.** The memory hooks cost roughly 1–2k tokens per session. The real drains are elsewhere — and Megamind attacks all of them: it preserves your context (a full memory map plus a clean resume are always injected) while cutting out the noise and the structural bloat that most memory tools ignore.

---

## How it works

### The 4 hooks (automatic, no invocation)

| Hook | Fires | What it injects | Cost |
|------|-------|-----------------|------|
| **SessionStart** | new / resume / clear | a line-clipped `MEMORY.md` map + the newest **clean** session note + a ~50-token lean directive | **~550 tok once** |
| **UserPromptSubmit** | every message | top-3 keyword-matched memory files, noise-filtered + deduped | **≤400 tok** (silent if no hit) |
| **PreCompact** | before compaction | **nothing to context** — writes a clean structured resume (intent / decisions / files / commands / open questions), base64 + tool-JSON stripped at write time | **0 tok** |
| **Stop** | response ends | **nothing to context** — stamps `.last-active` + an optional debounced, secret-scanned memory backup | **0 tok** |

> The critical difference from a naive memory hook: PreCompact never writes the **raw** transcript. It parses the JSONL, drops image blobs and tool noise, and writes a small structured resume. A single base64 image blob can be ~25k tokens of pure garbage — Megamind makes sure that can never re-enter your context.

### The 3 pillars

**1 · Memory** — remembers your project across sessions. Smart recall uses a float relevance scorer (term-frequency cap + keyword coverage + title/proximity/freshness), skips transcript-dump noise files entirely, and maps `cwd → slug` correctly even for paths with spaces (so `D:\dev\my project` resolves to **its own** memory, not the parent folder's).

**2 · Context discipline** — Megamind knows where tokens actually go and gives you the levers:
- **`opus[1m]` (1M context)** re-sends the whole growing session every turn → default to `opus` (200K).
- **`xhigh` effort** → `high` for routine work.
- **Always-on MCP servers** inject tool schemas into _every_ request → move rarely-used ones to a per-project `.mcp.json`.
- **Session bloat** → `/clear` on an unrelated task switch; route big reads (>~400 lines / >3 files) to a subagent and keep only the conclusion.

**3 · Lazy skills + lean mode**
- **Lazy skills** (`/megamind skills`) disable any skill unused in the last 30 days by moving it out of the scanned path, so its description stops loading. Re-enable any in one command. The hard-protected default is **just `megamind` itself**; if you want to keep specific other skills always-enabled, list their names (one per line) in `~/.claude/megamind-keep.txt`.
- **Lean directive** — a ~50-token SessionStart line (use subagents for big reads, `/clear` between tasks, recall before re-asking). Default ON; opt out by creating `~/.claude/megamind-lean.off`.
- **`/megamind lean apply`** — a fully reversible flip of `opus[1m]→opus` and `xhigh→high` (it backs up `settings.json` to `settings.json.megamind-bak` first; `lean restore` reverts). Model/effort changes apply to **new** sessions only.

---

## Measured token savings

These numbers come from one real setup — 175 installed skills, Max plan, `opus[1m]` + `xhigh`, with a large live transcript. Your savings scale with how many skills you have installed and how long your sessions run.

| Sink | Before | After | Saved / session |
|------|--------|-------|-----------------|
| **Skill descriptions** loaded at startup | ~18,800 tok (175 skills) | ~5,300 tok (only the skills you actually use) | **~13,500** |
| **SessionStart memory injection** | ~1,500 tok | ~550 tok (line-clipped index) | **~950** |
| **Transcript-noise injection** | up to ~400/prompt, spiking to **~25,000** when an image blob was eligible | 0 (noise can't enter context) | **hundreds → thousands** |
| **1M-context re-send** | grows toward 1M × every turn | capped at 200K (`opus`) | **dominant on long sessions** |

**On that setup, roughly 14–18k tokens were saved every session before typing a word**, plus the structural `opus[1m]→opus` win that compounds across a long session. Break-even is immediate. And crucially — **context is preserved.** The full memory map and a clean resume are always injected; it's the _noise_ that's gone, not the memory.

---

## Why it's different from most memory / token skills

Honestly and specifically:

- **Most memory skills only do memory.** Megamind also attacks the _real_ token sinks they ignore — the always-loaded skill descriptions (lazy skills), the model-tier / effort re-send, and the raw transcript noise re-injected after compaction. Memory is the small part; the big savings are there.
- **No LLM calls from hooks.** Several memory tools make an LLM / Agent-SDK call _from inside a hook_ to summarize or embed — that costs extra tokens, adds latency, and needs an API key on every session. Megamind's hooks are **pure `grep` and string ops**: zero model calls, zero added latency.
- **No cloud, no vector DB, no GPU, no account.** No external index to rebuild, nothing to host, nothing to log into. Just files on disk and the `git` CLI you already have.
- **Noise is stopped at the source.** Instead of re-ingesting a raw transcript and hoping the model ignores the junk, Megamind strips base64 and tool-JSON _at write time_ — so a garbage compaction file can never hijack your next SessionStart.
- **It runs invisibly.** No command to remember, no ritual at the start of a session. Install once; the four hooks do the rest on every machine you sync to.

---

## Commands

```
/megamind status                                   # memory stats for the current project
/megamind recall <query>                           # search project memory, print top matches
/megamind list                                     # list memory files
/megamind lean status | on | off | apply | restore # token-discipline / model flip (reversible)
/megamind skills audit | disable --unused | enable <name> | restore | list
/megamind vault sync | mirror | prune [--force]    # optional memory backup (opt-in)
```

Run directly after install: `python ~/.claude/skills/megamind/scripts/cli.py <args>`

> On macOS/Linux, if the `python` command isn't available (only `python3`), create a `python` shim or alias — the hooks invoke `python` by name.

---

## Optional: memory backup (off by default)

The `Stop` hook can mirror your project memory into a git "memory-vault" repo — **disabled by default**. Enable it with `MEGAMIND_AUTOSYNC=1`; point it anywhere with `MEGAMIND_VAULT_DIR` (default: `~/Documents/GitHub/memory-vault`). Because the sync commits directly (it doesn't pass through Claude's Bash tooling), a stdlib secret scanner runs over the staged diff first and **aborts the commit on any key-shaped token** — important **if your memory-vault repo is public**. Nothing is ever pushed for a fresh install until you opt in.

---

## Files

```
megamind/
├── SKILL.md            # skill doc (memory + discipline + lean)
├── README.md           # this file
├── TOKEN-SAVINGS.md    # measured before/after numbers
├── CHANGELOG.md
├── LICENSE             # MIT
└── scripts/
    ├── lib.py              # core: slug, noise detection, resume builder, scoring, budgets, lean/vault primitives
    ├── hook_session_start.py / hook_user_prompt.py / hook_pre_compact.py / hook_stop.py
    ├── cli.py              # status / recall / list / lean / vault / skills
    ├── skills.py           # lazy-skill manager (audit / disable / enable / restore / list)
    ├── vault.py            # optional memory backup (debounced, secret-scanned)
    └── install.py          # idempotent hook registrator (backs up settings.json)
```

Per-project memory lives at `~/.claude/projects/<slug>/memory/{MEMORY.md, facts/, sessions/, .last-active}`.

---

## Install

One command — idempotent, backs up your `settings.json`, registers the four hooks:

```bash
python megamind/scripts/install.py
```

(Or, once it's in place, `python ~/.claude/skills/megamind/scripts/install.py`.)

Then **restart Claude Code or open a new session** so the hooks take effect. To remove: `python megamind/scripts/install.py --uninstall`.

Zero external dependencies (Python 3.7+ stdlib + the `git` CLI). Works on Windows, macOS, and Linux. If an `INSTALL.md` is included in the package, see it for the full step-by-step plus a paste-into-Claude install prompt.

---

*Megamind Ultra · v0.2.0 "Ultra" · MIT-licensed · shared with the Claude Code community.*
