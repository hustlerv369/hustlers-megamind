# 🧠⚡ Megamind Ultra — community post (ready to paste/adapt)

> Drop-in copy for a community post / Discord / X thread. Pick the long or short version. All numbers are real (measured on a 175-skill setup).

---

## ⚡ Short version (Discord / X)

**I got tired of Claude Code forgetting everything between sessions — and quietly eating my token budget. So I built Megamind Ultra: one skill, zero dependencies, that does both.**

It runs through 4 hooks (nothing to invoke) and saves **~14–18k tokens every session before you even type** — by:
- 🗂️ loading only the skills you actually use (≈19k tokens of skill descriptions → ≈5k)
- 🧹 never re-injecting raw transcript noise after compaction (a single image blob = ~25k tokens of garbage)
- 🔁 defaulting off the 1M-context re-send

…while still remembering your project across sessions. No LLM calls from hooks, no cloud, no vector DB, no GPU — pure Python stdlib + grep. Free, local, MIT.

Install = paste one prompt into Claude Code and it sets itself up. 👇 [link / folder]

---

## 📜 Long version (forum / README-style post)

### The problem nobody fixes

Two things quietly cost you tokens in Claude Code:

1. **It forgets.** Every new session starts blank — you re-explain your project, your decisions, yesterday's bug. ~2–8k tokens gone before real work begins.
2. **It bloats.** What you *don't* see is worse: ~175 installed skills load their descriptions into context **every session** (~19k tokens before your first word), a 1M-context model re-sends the whole growing conversation on **every turn**, and after each compaction Claude re-ingests **raw transcript noise** — base64 image blobs, tool-call JSON — straight back into your window.

Most "memory" tools only address #1 — and several make it worse by calling an LLM from a hook (more tokens, latency, an API key).

### What Megamind Ultra does

One Claude Code **skill**. Four lifecycle hooks in `~/.claude/settings.json`. Nothing to invoke — it just works, every session, on every machine you sync to.

- 🧠 **Remembers** your project (auto-loaded at start, keyword-recalled per prompt).
- ✂️ **Strips the noise** — PreCompact writes a *clean structured resume* (intent / decisions / files / commands), never the raw transcript. Base64 and tool-JSON can never re-enter context.
- 🗂️ **Lazy skills** — skills unused for 30 days stop loading their descriptions; re-enable any in one command. Only `megamind` is ever hard-protected.
- 🎚️ **Lean mode** — defaults `opus[1m]→opus` (200K) and `xhigh→high`, plus a tiny token-discipline directive. (Reversible.)

### The numbers (measured, real setup)

| Sink | Before | After | Saved / session |
|------|--------|-------|-----------------|
| Skill descriptions loaded | ~18,800 tok | ~5,300 tok | **~13,500** |
| SessionStart memory injection | ~1,500 tok | ~550 tok | **~950** |
| Transcript-noise re-injection | spike ~25,000 tok | 0 | **hundreds → thousands** |
| 1M-context re-send | every turn | 200K cap | **dominant on long sessions** |

**~14–18k tokens saved every session before you type** — and context is *preserved*, only the noise is gone.

### Why it's better than most memory/token skills

- **Zero LLM calls from hooks.** Pure grep + Python stdlib. No extra tokens, no latency, no API key.
- **No cloud, no vector DB, no GPU, no Obsidian lock-in.** ~600 lines you can read in one sitting.
- **It's the only one that also attacks the real token sinks** — skill-description bloat, the model-tier re-send, and post-compaction noise. Memory is the small win; the big savings are there.
- **Free, local, MIT.** Yours to hack.

### Install in 30 seconds

Download the folder, then paste **one prompt** into a Claude Code session — Claude copies the skill, registers the 4 hooks, verifies them, and tells you what it now does. (Manual install is 3 steps; see `INSTALL.md`.) The paste-prompt is in `INSTALL-PROMPT.md`.

> Built for the Claude Code community. Remember more. Spend fewer tokens.
