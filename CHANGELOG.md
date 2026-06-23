# Changelog

All notable changes to Megamind Ultra are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-06-22 — "Ultra"

The token-saving overhaul. Memory was never the token sink — raw transcript noise
and context bloat were. This release stops both and folds in lean-mode discipline.

### Changed
- **PreCompact no longer dumps the raw transcript.** It now parses the JSONL,
  strips base64 image blobs + tool_use/tool_result noise, and writes a CLEAN
  structured resume (`<stamp>-resume-*.md`: recent intent, decisions, files,
  commands, open questions), budget-capped. Filename prefix `compact-` → `resume-`.
- **Recall is noise-aware.** `grep_memory` skips transcript-dump files and dedupes
  near-identical notes; `score_file` is now a float scorer (TF-cap + keyword
  coverage + title/proximity boosts + freshness); `extract_snippet` drops noise
  lines; `latest_session_note` skips dumps (returns None if only dumps exist) so a
  fresh auto-compact garbage file can never hijack the SessionStart slot.
- **Slug now maps whitespace.** `project_slug_from_cwd` maps spaces (and other
  whitespace) to `-`, matching Claude Code's own slug — fixes spaced paths like
  `D:\CLAUDE\My App` silently resolving to the PARENT project's memory.

### Added
- `lib.py`: `is_noise_line`/`is_noise_file`, `iter_transcript_blocks`,
  `clean_tool_result`, `build_resume`, `_looks_binary`, `_strip_noise_prose`,
  `_prose_fingerprint`; lean (`LEAN_LINE`, `lean_on`) + vault (`git_quiet`,
  `scan_secrets`, `VAULT_DIR`, `AUTOSYNC_ON`) primitives.
- **Lean mode** — SessionStart injects a ~50-token token-discipline line (default
  ON, opt out via `~/.claude/megamind-lean.off`), placed in the trimmable tail.
- `scripts/vault.py` — debounced, secret-scanned memory-vault auto-sync (default
  OFF via `MEGAMIND_AUTOSYNC`). `Stop` hook calls it; 25s Stop timeout added.
- `cli.py`: `lean status|on|off|apply|restore` (reversible `opus[1m]→opus` +
  `xhigh→high` flip with backup) and `vault sync|mirror|prune`.
- `/megamind` slash command (`~/.claude/commands/megamind.md`).
- `install.py` warns if context-mode is registered globally (it must stay
  per-project to avoid an 11-tool + 5-hook collision with MegaMind).
- 18 new tests in `tests/test_lib.py` (noise detection, resume builder, slug,
  scoring, secret scan) — all green.

## [Unreleased]

### Planned
- SQLite FTS5 backend for multi-project scale (100+ files)
- Drift detection — warn when memory claims diverge from code constants
- Cross-project recall CLI flag
- Consolidation skill — auto-merge duplicate facts, prune stale sessions
- Slash commands (`/remember`, `/forget`, `/recall`) registered as Claude Code commands
- Tiered injection budget (smaller payload for short prompts)
- Optional semantic search hook behind feature flag

## [0.1.0] — 2026-04-17

Initial release. Built in one evening while shipping a real project.

### Added
- `scripts/lib.py` — shared utilities: slug resolution, keyword grep,
  token budget enforcement, snippet extraction.
- `scripts/hook_session_start.py` — SessionStart hook. Injects `MEMORY.md`
  index + the newest `sessions/*.md` note at every new session. Budget:
  ≤ 1500 tokens (6000 chars).
- `scripts/hook_user_prompt.py` — UserPromptSubmit hook. Extracts
  keywords from the user message, greps memory files, injects top-3 matching
  snippets. Budget: ≤ 400 tokens per prompt. Silent no-op when no relevant
  match found.
- `scripts/hook_pre_compact.py` — PreCompact hook. Before Claude Code
  auto-compacts, saves the transcript tail to `sessions/compact-*.md`.
  No context injection.
- `scripts/hook_stop.py` — Stop hook. Updates `.last-active` marker on
  every response completion. No context injection.
- `scripts/cli.py` — on-demand operations: `status`, `recall <query>`,
  `list`.
- `scripts/install.py` — idempotent hook registrator for
  `~/.claude/settings.json`. Supports `--uninstall`.
- `SKILL.md` — metadata for Claude Code Skill tool discoverability.
- `README.md` — full docs, design principles, competitive positioning.
- `.gitignore` — Python, OS, and backup artifacts.

### Design contract
- **Zero external dependencies** — Python 3.7+ stdlib only.
- **Hard token budgets** enforced by `format_budget()` in `lib.py`.
- **Silent no-op** when no relevant match — never pads context with filler.
- **Live conversation wins** over stale memory — preamble instructs
  Claude to treat memory as background only.
- **UTF-8 stdout/stderr** forced at lib load — emoji and non-ASCII
  (Czech, etc.) don't crash Windows cp1250.
- **Cross-platform** — Git Bash on Windows, macOS, Linux.

[Unreleased]: https://github.com/hustlerv369/hustlers-megamind/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/hustlerv369/hustlers-megamind/releases/tag/v0.1.0
