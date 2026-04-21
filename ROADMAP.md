# Roadmap

Public direction for Hustlers MegaMind. Priorities can shift based on
issues and PRs.

## v0.1 — current (April 2026)

- [x] Four core hooks (SessionStart, UserPromptSubmit, PreCompact, Stop)
- [x] Grep-first keyword search with BM25-like scoring
- [x] Hard token budgets per hook
- [x] Idempotent installer / uninstaller
- [x] CLI: `status`, `recall`, `list`, `remember`, `forget`, `stats`,
      `audit`, `init --template`, `templates`
- [x] `bump_stat()` token-savings tracker plumbed through all hooks
- [x] Secrets scanner — 15 credential patterns
- [x] Five bundled templates: `nextjs-saas`, `python-api`, `react-native`,
      `data-pipeline`, `seo-site`
- [x] `cli.py sync auto-setup / push / pull / auto-on` — git-backed
      cross-device memory vault with autosync on SessionStart (pull)
      and Stop (push)
- [x] Mobile preamble + browser bookmarklet for web/app Claude
- [x] 31 smoke tests
- [x] Cross-platform (Windows Git Bash, macOS, Linux)
- [x] Full README, LICENSE, CONTRIBUTING, SECURITY

## v0.2 — next

- [ ] **SQLite FTS5 backend** — swap linear grep for FTS5 index. Triggered
  only when project has > 50 `.md` files. Keeps grep path as default so
  small projects have zero sqlite overhead.
- [ ] **Drift detection** — a SessionStart sub-check that reads certain
  tagged facts (e.g. `verify_sources:` in frontmatter) and warns if the
  referenced code constant differs. Catches the real-world bug class:
  "memory claims 5 languages but code has 12."
- [ ] **Tiered injection** — short prompts (< 8 words) skip
  UserPromptSubmit injection entirely. Pure token saver.

## v0.3 — expansion

- [ ] **Cross-project recall** — `cli.py recall --all "query"` searches
  across every project's memory, ranked globally.
- [ ] **Consolidation skill** — reflective pass that merges duplicate
  facts, prunes session notes older than 30 days, rebuilds MEMORY.md
  index. Runs manually via CLI, optionally weekly cron.
- [ ] **More templates** — Rails, Go API, SvelteKit, Nuxt, Laravel.

## v0.4 — optional semantic

- [ ] **Local sentence-transformer** behind a feature flag. Adds
  `sentence-transformers` as an optional dep. Off by default to preserve
  zero-dep promise.
- [ ] **Hybrid ranking** — combine FTS5 BM25 + embedding cosine for best
  precision. Still local, still no external API calls.

## Non-goals (probably forever)

- ❌ Cloud sync / remote storage. Memory stays on your disk.
- ❌ Third-party service dependencies (Supermemory, Pinecone, etc.).
- ❌ Claude API calls from hooks (adds latency + tokens + requires auth).
- ❌ Automatic LLM-based summarization on every save (expensive, flaky).
- ❌ Framework / plugin registry. One project, one purpose, one file tree.

## How priorities are set

1. **Real bugs** (reproducible, has a clear fix) jump the queue.
2. **Token savings** — features that measurably save tokens land before
   features that add sugar.
3. **Maintainer's own pain** — the author uses this daily on real work.
   Friction that hits that workflow gets fixed fastest.
4. **Community feedback** via GitHub issues shapes order of v0.3+ items.
