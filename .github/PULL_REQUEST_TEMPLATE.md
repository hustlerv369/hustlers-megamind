<!-- Thanks for contributing! Please fill out each section. Empty PRs are closed. -->

## Summary

<!-- One sentence: what does this PR change? -->

## Motivation

<!-- Why is this worth adding? Link to the relevant issue if one exists. -->

Fixes #

## Changes

-
-
-

## Token impact

<!-- Required section. Measure before/after. -->

| Metric | Before | After |
|--------|--------|-------|
| SessionStart typical output | _____ chars | _____ chars |
| UserPromptSubmit average output | _____ chars | _____ chars |
| Scripts total LOC | _____ | _____ |

## Testing

- [ ] `python -m pytest tests/ -v` passes locally
- [ ] Manually exercised the affected hook with sample stdin
- [ ] Tested on Windows Git Bash (if touched path/slug logic)
- [ ] Tested on macOS / Linux (if possible)

## Docs

- [ ] Updated `README.md` if user-visible
- [ ] Updated `CHANGELOG.md` under `[Unreleased]`
- [ ] Updated `SKILL.md` if the invocation pattern changed

## Checklist

- [ ] Zero new external dependencies (stdlib only), or justified exception
- [ ] Silent no-op path still works when nothing is relevant
- [ ] Hard budget still enforced by `format_budget()`
- [ ] No secrets or personal data in diff
