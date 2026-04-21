"""
Smoke tests for Hustlers MegaMind core library.

Run with:
    python -m pytest tests/ -v

No external deps — uses only stdlib and pytest.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

# Add scripts/ to path so we can import the library directly
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import lib  # noqa: E402


# ────────────────────────────────────────────────────────────────────
# slug resolution
# ────────────────────────────────────────────────────────────────────

def test_slug_windows_repo_root():
    assert lib.project_slug_from_cwd("D:\\projects\\my-app") == "D--projects-my-app"


def test_slug_windows_worktree():
    expected = "D--projects-my-app--claude-worktrees-feature-branch"
    assert lib.project_slug_from_cwd("D:\\projects\\my-app\\.claude\\worktrees\\feature-branch") == expected


def test_slug_posix_repo_root():
    assert lib.project_slug_from_cwd("/home/user/my-project") == "home-user-my-project"


def test_slug_none_input():
    assert lib.project_slug_from_cwd(None) is None
    assert lib.project_slug_from_cwd("") is None


# ────────────────────────────────────────────────────────────────────
# keyword extraction
# ────────────────────────────────────────────────────────────────────

def test_keywords_basic():
    kw = lib.extract_keywords("Fix the payment webhook signature verification")
    assert "payment" in kw
    assert "webhook" in kw
    assert "verification" in kw
    # Short words filtered out by default min_len=4
    assert "fix" not in kw


def test_keywords_stopwords_filtered():
    kw = lib.extract_keywords("this would have been the plan")
    # stopwords "this", "would", "have", "been" dropped
    assert "this" not in kw
    assert "would" not in kw


def test_keywords_empty():
    assert lib.extract_keywords("") == set()
    assert lib.extract_keywords(None) == set()  # type: ignore[arg-type]


# ────────────────────────────────────────────────────────────────────
# budget enforcement
# ────────────────────────────────────────────────────────────────────

def test_budget_under_limit_pass_through():
    text = "short enough"
    assert lib.format_budget(text, 100) == text


def test_budget_over_limit_truncates():
    text = "x" * 1000
    clipped = lib.format_budget(text, 100)
    assert len(clipped) <= 100
    assert "[...truncated]" in clipped


# ────────────────────────────────────────────────────────────────────
# memory dir resolution (with temporary project)
# ────────────────────────────────────────────────────────────────────

def test_find_memory_dir_roundtrip(tmp_path, monkeypatch):
    """Create a fake project memory dir and verify find_memory_dir locates it."""
    fake_home = tmp_path
    fake_projects = fake_home / ".claude" / "projects"
    # Use the slug algo so we create the right dir name
    cwd = "/tmp/my-fake-project"
    slug = lib.project_slug_from_cwd(cwd)
    mem = fake_projects / slug / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("# hi\n")

    monkeypatch.setattr(lib, "CLAUDE_HOME", fake_home / ".claude")
    monkeypatch.setattr(lib, "PROJECTS_ROOT", fake_projects)

    found = lib.find_memory_dir(cwd)
    assert found == mem


def test_find_memory_dir_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "PROJECTS_ROOT", tmp_path / "projects")
    assert lib.find_memory_dir("/nonexistent/path") is None


# ────────────────────────────────────────────────────────────────────
# grep scoring
# ────────────────────────────────────────────────────────────────────

def test_grep_memory_orders_by_relevance(tmp_path):
    d = tmp_path / "memory"
    d.mkdir()
    (d / "a.md").write_text("stripe stripe stripe")
    (d / "b.md").write_text("stripe payment")
    (d / "c.md").write_text("unrelated content")

    results = lib.grep_memory(d, {"stripe"}, max_files=3)
    assert len(results) == 2
    assert results[0].name == "a.md"  # three hits wins
    assert results[1].name == "b.md"


def test_grep_memory_empty_keywords_returns_nothing(tmp_path):
    d = tmp_path / "memory"
    d.mkdir()
    (d / "x.md").write_text("content")
    assert lib.grep_memory(d, set()) == []
