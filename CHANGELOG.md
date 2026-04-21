# Changelog

All notable changes to Hustlers MegaMind are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `cli.py remember <text>` — append a one-line fact to MEMORY.md with
  date stamp + emoji tag, dedupes if the same text exists.
- `cli.py forget <keyword>` — remove matching MEMORY.md line(s),
  prints what was deleted.
- `cli.py stats` — decorated stats box with hook fire counts and
  estimated tokens saved. Uses `.megamind-stats.json` maintained by
  `bump_stat` calls from each hook.
- `cli.py audit` — scans every memory file against 15 secret patterns
  (Stripe live/test/restricted, OpenAI, Anthropic, GitHub PAT/OAuth,
  Google API, AWS access, Slack bot, JWT, private key headers, password
  assignments, API key assignments, Bearer tokens). Advisory only —
  reports file + line + masked snippet.
- `cli.py init [--template <name>]` — create memory dir + MEMORY.md
  skeleton, optionally seed from a bundled template.
- `cli.py templates` — list available templates.
- Five bundled starter templates: `nextjs-saas`, `python-api`,
  `react-native`, `data-pipeline`, `seo-site`. Each ships a MEMORY.md
  index plus 1–3 `facts/*.md` skeletons.
- Token savings tracker: each hook calls `bump_stat()` on a non-blocking
  JSON file so users can see measurable value over time.
- `assets/demo-funny-scenario.svg` — animated 5-day comic showing the
  "re-explain everything three days in a row" pain point.
- `scripts/sync.py` + `cli.py sync ...` — optional git-backed memory
  vault for cross-device sync. Subcommands: `init`, `push`, `pull`,
  `status`, `auto-on`, `auto-off`, `auto-status`, and `auto-setup`
  (one-shot via `gh` CLI — creates private repo, links, first push,
  enables autosync).
- SessionStart hook now auto-pulls from the vault (rate-limited to
  once per 5 min) so a fresh session always sees changes made from
  another device.
- Stop hook now auto-pushes pending memory changes (rate-limited to
  once per 10 min) so other devices see your latest memory.
- `.gitignore` in the vault whitelists **only** `*/memory/` paths —
  stats, auth tokens, settings backups never enter the repo.
- `assets/mobile-preamble.md` — ready-made preamble for Claude mobile
  app and web Claude (iOS Shortcut / Android text expander / browser
  bookmarklet instructions included).
- 7 new tests in `tests/test_sync.py` covering flag round-trip, rate
  limiting, gitignore pattern, and graceful handling of missing `git`
  or `gh` binaries. Total: 31 tests.

### Planned
- SQLite FTS5 backend for multi-project scale (100+ files)
- Drift detection — warn when memory claims diverge from code constants
- Cross-project recall CLI flag
- Consolidation skill — auto-merge duplicate facts, prune stale sessions
- Tiered injection budget (smaller payload for short prompts)
- Optional semantic search hook behind feature flag

## [0.1.0] — 2026-04-17

Initial release. Built in one evening while shipping SEOKRATES.

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
