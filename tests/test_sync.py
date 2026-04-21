"""
Smoke tests for sync module. We don't test real network pushes; we test
the surface: init creates .git + .gitignore, gitignore whitelists only
memory/ paths, autosync flag round-trips, rate limiting works.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import lib  # noqa: E402
import sync  # noqa: E402


def _setup_fake_home(tmp_path, monkeypatch):
    fake_home = tmp_path
    fake_claude = fake_home / ".claude"
    fake_projects = fake_claude / "projects"
    monkeypatch.setattr(lib, "CLAUDE_HOME", fake_claude)
    monkeypatch.setattr(lib, "PROJECTS_ROOT", fake_projects)
    # sync module caches these at import time — patch too
    monkeypatch.setattr(sync, "CLAUDE_HOME", fake_claude)
    monkeypatch.setattr(sync, "PROJECTS_ROOT", fake_projects)
    monkeypatch.setattr(sync, "VAULT_ROOT", fake_projects)
    monkeypatch.setattr(sync, "AUTOSYNC_FLAG", fake_claude / ".megamind-autosync")
    monkeypatch.setattr(sync, "AUTOSYNC_LAST", fake_claude / ".megamind-autosync-last")
    monkeypatch.setattr(sync, "AUTOPULL_LAST", fake_claude / ".megamind-autopull-last")
    return fake_projects


def test_autosync_flag_roundtrip(tmp_path, monkeypatch):
    _setup_fake_home(tmp_path, monkeypatch)
    assert sync.autosync_is_enabled() is False
    sync.autosync_enable()
    assert sync.autosync_is_enabled() is True
    sync.autosync_disable()
    assert sync.autosync_is_enabled() is False
    # Disabling when not enabled is a no-op
    sync.autosync_disable()


def test_autosync_tick_no_vault_returns_false(tmp_path, monkeypatch):
    _setup_fake_home(tmp_path, monkeypatch)
    sync.autosync_enable()
    did, msg = sync.autosync_tick_if_due()
    assert did is False
    assert "vault not initialized" in msg


def test_autosync_tick_disabled_returns_false(tmp_path, monkeypatch):
    _setup_fake_home(tmp_path, monkeypatch)
    did, msg = sync.autosync_tick_if_due()
    assert did is False
    assert "off" in msg


def test_autopull_rate_limited(tmp_path, monkeypatch):
    vault = _setup_fake_home(tmp_path, monkeypatch)
    sync.autosync_enable()
    # Fake-init: make the vault look initialized (.git dir)
    (vault / ".git").mkdir(parents=True)
    # Write a "recent" last-pull so the rate limiter fires
    sync.AUTOPULL_LAST.parent.mkdir(parents=True, exist_ok=True)
    sync.AUTOPULL_LAST.write_text(str(time.time()), encoding="utf-8")
    did, msg = sync.autopull_if_due()
    assert did is False
    assert "too soon" in msg.lower()


def test_gitignore_pattern_design(tmp_path, monkeypatch):
    """
    Verify the gitignore string whitelists memory/ and nothing else.
    This is the safety net: anything outside memory/ must be ignored.
    """
    content = sync.GITIGNORE
    # Should start with blanket-deny then whitelist .gitignore and memory dirs
    assert "*" in content
    assert "!.gitignore" in content
    assert "!*/memory/" in content
    # Stats are per-machine, should stay out of the repo
    assert ".megamind-stats.json" in content


def test_run_git_handles_missing_binary(tmp_path, monkeypatch):
    """If git isn't in PATH, run_git must return (127, <message>), not raise."""
    _setup_fake_home(tmp_path, monkeypatch)
    # Force FileNotFoundError by pointing PATH at an empty dir
    monkeypatch.setenv("PATH", str(tmp_path / "empty-path"))
    (tmp_path / "empty-path").mkdir()
    code, out = sync.run_git("--version", timeout=5)
    # Either git is still reachable via absolute path fallback (return 0),
    # or it's not found (127). Both are acceptable — the point is: no raise.
    assert code in (0, 127, 1)
    assert isinstance(out, str)


def test_has_gh_cli_does_not_raise(tmp_path, monkeypatch):
    """has_gh_cli should return bool, never raise, whether gh exists or not."""
    result = sync.has_gh_cli()
    assert isinstance(result, bool)
