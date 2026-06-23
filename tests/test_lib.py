"""
Smoke tests for Megamind Ultra core library.

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
    assert lib.project_slug_from_cwd("D:\\CLAUDE\\my-project") == "D--CLAUDE-my-project"


def test_slug_windows_path_with_space():
    # Spaces must map to dashes to match Claude Code's slug (else recall falls
    # back to the parent project's memory).
    assert lib.project_slug_from_cwd("D:\\CLAUDE\\My App") == "D--CLAUDE-My-App"


def test_slug_windows_worktree():
    expected = "D--CLAUDE-my-project--claude-worktrees-lucid-brattain"
    assert lib.project_slug_from_cwd("D:\\CLAUDE\\my-project\\.claude\\worktrees\\lucid-brattain") == expected


def test_slug_posix_repo_root():
    assert lib.project_slug_from_cwd("/home/user/my-project") == "home-user-my-project"


def test_slug_none_input():
    assert lib.project_slug_from_cwd(None) is None
    assert lib.project_slug_from_cwd("") is None


# ────────────────────────────────────────────────────────────────────
# keyword extraction
# ────────────────────────────────────────────────────────────────────

def test_keywords_basic():
    kw = lib.extract_keywords("Fix the shopify webhook HMAC verification")
    assert "shopify" in kw
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


# ════════════════════════════════════════════════════════════════════
# ULTRA: noise detection
# ════════════════════════════════════════════════════════════════════

JSONL_LINE = (
    '{"parentUuid":"abc","sessionId":"x","isSidechain":false,'
    '"message":{"role":"user","content":"hi"}}'
)


def test_is_noise_line_jsonl():
    assert lib.is_noise_line(JSONL_LINE)


def test_is_noise_line_base64():
    assert lib.is_noise_line("/9j/4AAQSkZJRg" + "A" * 200)


def test_is_noise_line_prose_false():
    assert not lib.is_noise_line("We decided to switch to opus for cost.")


def test_is_noise_file_compact_name(tmp_path):
    p = tmp_path / "2026-06-22-1355-compact-auto.md"
    p.write_text("# note\nsome prose\n", encoding="utf-8")
    assert lib.is_noise_file(p)  # filename anchor catches the real dumps


def test_is_noise_file_compact_manual_name(tmp_path):
    p = tmp_path / "2026-05-05-0009-compact-manual.md"
    p.write_text("# note\nprose\n", encoding="utf-8")
    assert lib.is_noise_file(p)  # manual dumps must also be filtered


def test_is_noise_file_dump_content(tmp_path):
    p = tmp_path / "2026-06-22-renamed.md"
    p.write_text("\n".join([JSONL_LINE] * 8), encoding="utf-8")
    assert lib.is_noise_file(p)  # content sniff catches renamed garbage


def test_is_noise_file_real_note_false(tmp_path):
    p = tmp_path / "2026-06-22-feature-work.md"
    p.write_text(
        "# Feature work\n\nWe shipped the operator route and verified it.\n- did X\n- did Y\n",
        encoding="utf-8",
    )
    assert not lib.is_noise_file(p)


def test_is_noise_file_title_autodeploy_false(tmp_path):
    # 'Auto-deploy'/'Compact' in a TITLE-derived filename must NOT be flagged
    p = tmp_path / "2026-01-01-Auto-deploy-pipeline.md"
    p.write_text("# Auto-deploy pipeline\n\nNotes about the deploy pipeline.\n", encoding="utf-8")
    assert not lib.is_noise_file(p)


def test_is_noise_file_small_note_one_jsonl_false(tmp_path):
    # 3-line note quoting ONE jsonl line must survive (absolute-floor regression)
    p = tmp_path / "2026-06-22-bug.md"
    p.write_text("# Bug\nGot this error row:\n" + JSONL_LINE + "\n", encoding="utf-8")
    assert not lib.is_noise_file(p)


# ════════════════════════════════════════════════════════════════════
# ULTRA: clean tool_result + resume builder (zero base64 leak)
# ════════════════════════════════════════════════════════════════════

def test_clean_tool_result_keeps_text_after_image():
    block = {
        "content": [
            {"type": "image", "source": {"data": "/9j/AAAA"}},
            {"type": "text", "text": "Found the file at line 5"},
        ]
    }
    assert "Found the file" in lib.clean_tool_result(block)


def test_clean_tool_result_drops_base64():
    block = {"content": [{"type": "text", "text": "/9j/" + "A" * 300}]}
    assert lib.clean_tool_result(block) == ""


def test_build_resume_no_base64_leak():
    records = [
        {"role": "user", "kind": "text", "text": "Please fix the login bug?"},
        {"role": "assistant", "kind": "tool_use", "name": "Edit", "input": {"file_path": "/app/login.ts"}},
        {"role": "assistant", "kind": "tool_use", "name": "Bash", "input": {"command": "npm test"}},
        {"role": "user", "kind": "tool_result", "block": {"content": [{"type": "image", "source": {"data": "/9j/" + "A" * 5000}}]}},
        {"role": "assistant", "kind": "text", "text": "I decided to switch to a guard clause because it's cleaner."},
    ]
    out = lib.build_resume(records)
    assert "/9j/" not in out and "iVBOR" not in out
    assert len(out) <= lib.BUDGET_PRECOMPACT
    assert "/app/login.ts" in out
    assert "npm test" in out
    assert "login bug" in out  # user intent captured


def test_build_resume_empty():
    assert lib.build_resume([]) == ""


# ════════════════════════════════════════════════════════════════════
# ULTRA: snippet noise-strip + latest note + scoring + secret scan
# ════════════════════════════════════════════════════════════════════

def test_extract_snippet_strips_jsonl(tmp_path):
    p = tmp_path / "n.md"
    p.write_text("# Title\n\nReal line about stripe.\n" + JSONL_LINE + "\n", encoding="utf-8")
    snip = lib.extract_snippet(p, {"stripe"})
    assert "parentUuid" not in snip
    assert "stripe" in snip.lower()


def test_latest_session_note_skips_noise(tmp_path):
    import time as _t

    sess = tmp_path / "sessions"
    sess.mkdir()
    real = sess / "2026-06-20-real.md"
    real.write_text("# Real\nprose here\n", encoding="utf-8")
    _t.sleep(0.02)
    dump = sess / "2026-06-21-compact-auto.md"  # newer, but noise
    dump.write_text("\n".join([JSONL_LINE] * 8), encoding="utf-8")
    assert lib.latest_session_note(tmp_path) == real


def test_latest_session_note_none_when_only_dumps(tmp_path):
    sess = tmp_path / "sessions"
    sess.mkdir()
    (sess / "2026-06-21-compact-auto.md").write_text("\n".join([JSONL_LINE] * 8), encoding="utf-8")
    assert lib.latest_session_note(tmp_path) is None


def test_score_file_returns_float(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("stripe stripe", encoding="utf-8")
    s = lib.score_file(p, {"stripe"})
    assert isinstance(s, float) and s > 0


def test_score_file_noise_excluded_via_grep(tmp_path):
    d = tmp_path / "memory"
    d.mkdir()
    (d / "real.md").write_text("stripe payment flow\n", encoding="utf-8")
    (d / "2026-06-21-compact-auto.md").write_text("\n".join([JSONL_LINE.replace("hi", "stripe")] * 8), encoding="utf-8")
    results = lib.grep_memory(d, {"stripe"}, max_files=5)
    names = [p.name for p in results]
    assert "real.md" in names
    assert "2026-06-21-compact-auto.md" not in names  # noise never injected


def test_secret_scan():
    assert lib.scan_secrets("key sk-abcdefghijklmnop12345xyz")
    assert lib.scan_secrets("-----BEGIN OPENSSH PRIVATE KEY-----")
    assert not lib.scan_secrets("no secrets here, just normal prose about code")
