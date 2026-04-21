# Contributing to Hustlers MegaMind

Thanks for thinking about contributing. This project is intentionally small
and intentionally boring — the goal is **memory that just works**, not a
framework. Keep that in mind when proposing features.

## Guiding principles

1. **Token-saving, not token-spending.** Every new feature must demonstrate
   a net token win. Features that pad context are rejected.
2. **Zero dependencies.** Python stdlib only. If you want to add `numpy` or
   a sentence-transformer, hide it behind an opt-in flag and document the
   memory/disk cost.
3. **Silent no-op.** Default behavior is to inject nothing when nothing is
   relevant. Never print `"no results found"` into Claude's context.
4. **Under 1000 LOC.** If a PR pushes the codebase over 1000 lines, split
   it or reconsider scope.
5. **Windows + macOS + Linux.** Git Bash must work. No symlinks, no
   POSIX-only assumptions, UTF-8 stdout forced.

## Before you open a PR

1. **Open an issue first** if the change is non-trivial (new hook, new CLI
   command, schema change, new dependency). A five-minute discussion
   saves a one-hour rewrite.
2. **Run the tests.**

   ```bash
   python -m pytest tests/ -v
   ```
3. **Measure the token impact.** If your change affects what a hook
   injects, include a before/after character count in the PR description.
4. **Check cross-platform.** If you can't test on all three OSes, say so in
   the PR. A reviewer will check the rest.

## Style

- Python — follow PEP 8. Use `ruff` or `flake8` locally if you have them;
  they're not enforced in CI but make review faster.
- Type hints welcome but not required. The codebase uses `from __future__
  import annotations` so new-style unions like `str | None` work on 3.7+.
- Keep scripts standalone — each `hook_*.py` should be runnable directly
  and import only `lib.py`.
- Comments explain *why*, not *what*. The code is small enough to read.

## Adding a new hook

1. Create `scripts/hook_<event>.py`.
2. Make sure it reads stdin via `lib.read_hook_input()` and treats missing
   fields as "do nothing".
3. Budget its output in `lib.py` as a module-level constant.
4. Add it to `HOOKS_TO_INSTALL` in `scripts/install.py`.
5. Document it in `README.md` (the table of hooks) and `CHANGELOG.md`.
6. Add a smoke test to `tests/test_hooks.py`.

## Adding a new CLI command

Same pattern: extend `cli.py`, update `README.md`, add a test.

## Issue templates

`.github/ISSUE_TEMPLATE/` has templates for bug reports and feature
requests. Use them — it makes triage 10× faster.

## Code of Conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Be kind, be curious, don't
be a jerk. Maintainer decisions are final on scope disagreements.

## License

By contributing, you agree that your contributions will be licensed under
the project's [MIT License](LICENSE).
