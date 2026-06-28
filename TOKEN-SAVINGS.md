# Megamind Ultra — what changed & token savings

A plain-English summary of the v0.2.0 "Ultra" overhaul: what each change does and
roughly how many tokens it saves per session. Measured on a real setup (175 skills,
Max plan, `opus[1m]` + `xhigh`, 8.3 MB live transcript).

## v0.3.0 "Deltas-only" — the per-turn drain nobody had fixed

v0.2.0 found that memory hooks weren't the main sink. But one real per-turn leak
remained: **the UserPromptSubmit hook re-injected the SAME matching note on nearly
every message** — it had no memory of what it had already surfaced. A note Claude
has already seen is carried forward for free in the cached conversation prefix, so
re-injecting it adds zero information and costs tokens.

Why it hurt more than its size suggests — Anthropic prompt cache (verified):
cache **write = 1.25×** base input, cache **read = 0.1×**, **5-min TTL** that
refreshes free on every read. Continuous traffic is cheap; but **bursty usage with
>5-min gaps lets the cache go COLD**, and a cold turn re-charges the ENTIRE
accumulated prefix at full **1×**. With no cross-turn dedup the prefix grows
**O(N²)** in duplicate copies — a 20-turn cold-burst session re-charges ~84k
full-price tokens of pure duplication vs ~8k with dedup (**~10× waste**).

The fix — "load once at SessionStart, inject deltas only":

| Change | Effect |
|--------|--------|
| **Per-session inject ledger** (`~/.claude/.megamind/seen/<session>.json`) | A file is injected **at most once per session**; collapses the O(N²) duplicate cost to O(N) |
| **SessionStart pre-seeds the ledger** with the index + latest resume it loads | The per-turn hook never re-injects working memory already in the cache-stable prefix |
| **Relevance gate** (coverage + score floor) on the inject path | Weak/irrelevant matches inject **nothing** |
| **Acronym keywords** (KDP, TCG…) kept; length-weighted scoring | Short high-signal queries match the RIGHT note or stay silent |

Net: **most turns now inject zero tokens.** Per-turn injection drops from ~400 tok
every turn to ~0 on repeat/irrelevant turns; a genuinely new, relevant note still
surfaces exactly once. Everything from v0.2.0 (and vault sync, lean mode, noise
filtering, PreCompact resume) is preserved untouched. 42 tests pass.

---

## v0.2.0 "Ultra" (below)

## The realization

Memory was **never** the token sink — Megamind's hooks are capped at ~1,900 tokens/
session. The real drains were three things Megamind now controls:

| Sink | Before | After | Saved / session |
|------|--------|-------|-----------------|
| **Skill descriptions** loaded at startup | ~18,800 tok (175 skills) | ~5,300 tok (33 core) | **~13,500 tok** |
| **Transcript-noise injection** (base64/JSONL from raw PreCompact dumps re-read at SessionStart + grep-matched into recall) | up to ~400 tok/prompt + a ~500-tok SessionStart slot, **spiking to ~25,000** when an image blob was eligible | 0 (noise can't enter context) | **hundreds → thousands** (more on compaction-heavy sessions) |
| **1M-context re-send** (`opus[1m]`: the whole growing session is re-sent as input every turn) | grows unbounded toward 1M × every turn | capped at 200K (`opus`) | **the dominant win on long sessions** — millions of input tokens avoided across a long session |

## What changed (per feature)

1. **Clean PreCompact** — instead of dumping the raw 20 KB transcript tail (base64
   images + tool JSON), it parses the transcript and writes a small **structured
   resume** (intent / decisions / files / commands / open questions), noise stripped
   at write time. *Verified: this session's 8.3 MB transcript → 1.5 KB clean resume,
   zero base64.*

2. **Smart, noise-aware recall** — `grep_memory` skips transcript-dump files and
   dedupes; `score_file` is a proper relevance scorer (TF-cap + keyword coverage +
   title/proximity/freshness); `latest_session_note` never injects a garbage dump.

3. **Slug fix (bonus)** — `project_slug_from_cwd` now maps spaces, so a path like
   `D:\CLAUDE\My App` resolves to its **own** memory instead of silently falling
   back to the parent project's. (Your recall was loading the wrong project.)

4. **Lazy skills** (`/megamind skills`) — disables skills unused in the last 30 days
   by moving them out of the scanned path, so their descriptions stop loading.
   Re-enable any in one command. **~13,500 tok/session** reclaimed, persistent.

5. **Lean mode** — a ~50-token SessionStart directive (subagents for big reads,
   `/clear` discipline, recall-before-asking) + `/megamind lean apply`, a reversible
   flip of `opus[1m]→opus` and `xhigh→high` that removes the biggest structural sinks.

6. **Memory-vault auto-sync** — optional (`MEGAMIND_AUTOSYNC=1`), debounced, with a
   secret scan before any commit (the vault is git-pushed directly, bypassing the
   Bash pre-commit hook).

## Bottom line

- **Guaranteed, every session:** ~13,500 tokens from lazy skills + the elimination
  of transcript-noise injection. Call it **~14–18k tokens saved before you type**.
- **On long sessions:** the `opus[1m]→opus` flip is the dominant saving — a long
  session no longer re-sends a 1M-bound context as input on every turn.
- **Net effect:** a heavy day that used to exhaust the Max cap should now sit
  comfortably inside it. The single highest-leverage habit on top of all this is
  `/clear` between unrelated tasks.

## Commands

```
/megamind skills audit            # see the cost + what's disabled
/megamind skills enable <name>    # bring a skill back when you need it
/megamind lean apply | restore    # flip model/effort (reversible)
/megamind recall <query>          # search project memory
```
