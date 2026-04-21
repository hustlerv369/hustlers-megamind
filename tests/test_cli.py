"""
Smoke tests for CLI mutating + inspection commands.

Uses a temporary CLAUDE_HOME (monkeypatched) so tests never touch the
real user memory. No external deps — stdlib + pytest only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import lib  # noqa: E402


def _setup_fake_home(tmp_path, monkeypatch):
    """Return a fake cwd whose memory dir will exist under tmp_path."""
    fake_home = tmp_path
    fake_projects = fake_home / ".claude" / "projects"
    monkeypatch.setattr(lib, "CLAUDE_HOME", fake_home / ".claude")
    monkeypatch.setattr(lib, "PROJECTS_ROOT", fake_projects)
    return "/tmp/fake-project-xyz"


def test_ensure_memory_dir_creates_index(tmp_path, monkeypatch):
    cwd = _setup_fake_home(tmp_path, monkeypatch)
    mem = lib.ensure_memory_dir(cwd)
    assert mem.exists()
    idx = mem / "MEMORY.md"
    assert idx.exists()
    assert "memory index" in idx.read_text(encoding="utf-8").lower()


def test_append_memory_line_adds_once(tmp_path, monkeypatch):
    cwd = _setup_fake_home(tmp_path, monkeypatch)
    mem = lib.ensure_memory_dir(cwd)
    lib.append_memory_line(mem, "user prefers terse Czech replies")
    lib.append_memory_line(mem, "user prefers terse Czech replies")  # dedupe
    text = (mem / "MEMORY.md").read_text(encoding="utf-8")
    assert text.count("user prefers terse Czech replies") == 1


def test_forget_removes_matching_lines(tmp_path, monkeypatch):
    cwd = _setup_fake_home(tmp_path, monkeypatch)
    mem = lib.ensure_memory_dir(cwd)
    lib.append_memory_line(mem, "payment webhook HMAC issue")
    lib.append_memory_line(mem, "user prefers dark mode")

    removed = lib.forget_memory_line(mem, "HMAC")
    assert len(removed) == 1
    text = (mem / "MEMORY.md").read_text(encoding="utf-8")
    assert "HMAC" not in text
    assert "dark mode" in text


def test_forget_no_match_returns_empty(tmp_path, monkeypatch):
    cwd = _setup_fake_home(tmp_path, monkeypatch)
    mem = lib.ensure_memory_dir(cwd)
    lib.append_memory_line(mem, "dark mode preferred")
    assert lib.forget_memory_line(mem, "stripe") == []


def test_bump_stat_and_estimate(tmp_path, monkeypatch):
    cwd = _setup_fake_home(tmp_path, monkeypatch)
    mem = lib.ensure_memory_dir(cwd)
    lib.bump_stat(mem, "session_start")
    lib.bump_stat(mem, "session_start")
    lib.bump_stat(mem, "prompt_hit")
    stats = lib.load_stats(mem)
    assert stats["session_start"] == 2
    assert stats["prompt_hit"] == 1
    saved = lib.estimate_tokens_saved(stats)
    assert saved == 2 * lib.TOKENS_SAVED_PER_SESSION_START + lib.TOKENS_SAVED_PER_PROMPT_HIT


# ────────────────────────────────────────────────────────────────────
# secret scanner
# ────────────────────────────────────────────────────────────────────

# Test fixtures are built at runtime via string concatenation so the
# source files never contain a contiguous literal that a third-party
# secret scanner (e.g. GitHub push protection) would flag as a real key.
_FAKE_BODY = "FIXTURE" + "ZZ" + ("A" * 36)

STRIPE_FIXTURE = "sk" + "_live_" + _FAKE_BODY
OPENAI_FIXTURE = "sk" + "-" + _FAKE_BODY
ANTHROPIC_FIXTURE = "sk" + "-ant-" + _FAKE_BODY


def test_audit_catches_stripe_live_key(tmp_path, monkeypatch):
    cwd = _setup_fake_home(tmp_path, monkeypatch)
    mem = lib.ensure_memory_dir(cwd)
    (mem / "leaky.md").write_text(f"Fixture: {STRIPE_FIXTURE}\n", encoding="utf-8")
    hits = lib.scan_secrets(mem)
    names = {name for _, name, _, _ in hits}
    assert "stripe-live" in names


def test_audit_catches_openai_and_anthropic(tmp_path, monkeypatch):
    cwd = _setup_fake_home(tmp_path, monkeypatch)
    mem = lib.ensure_memory_dir(cwd)
    (mem / "ai.md").write_text(
        f"OPENAI_API_KEY={OPENAI_FIXTURE}\nANTHROPIC_API_KEY={ANTHROPIC_FIXTURE}\n",
        encoding="utf-8",
    )
    names = {name for _, name, _, _ in lib.scan_secrets(mem)}
    assert "openai" in names
    assert "anthropic" in names


def test_audit_clean_file_returns_empty(tmp_path, monkeypatch):
    cwd = _setup_fake_home(tmp_path, monkeypatch)
    mem = lib.ensure_memory_dir(cwd)
    (mem / "ok.md").write_text(
        "Plan: PRO at $9/mo, 7-day trial. No secrets here.\n",
        encoding="utf-8",
    )
    assert lib.scan_secrets(mem) == []


# ────────────────────────────────────────────────────────────────────
# templates
# ────────────────────────────────────────────────────────────────────

def test_list_templates_finds_bundled():
    names = lib.list_templates()
    # At least the five bundled ones should be present
    expected = {"nextjs-saas", "python-api", "react-native", "data-pipeline", "seo-site"}
    assert expected.issubset(set(names))


def test_copy_template_seeds_files(tmp_path, monkeypatch):
    cwd = _setup_fake_home(tmp_path, monkeypatch)
    mem = lib.ensure_memory_dir(cwd)
    # Remove the auto-created MEMORY.md so copy_template installs the template's
    (mem / "MEMORY.md").unlink()
    n = lib.copy_template("nextjs-saas", mem)
    assert n >= 2  # MEMORY.md + at least one fact
    assert (mem / "MEMORY.md").exists()
    assert (mem / "facts" / "stack.md").exists()


def test_copy_template_unknown_raises(tmp_path, monkeypatch):
    cwd = _setup_fake_home(tmp_path, monkeypatch)
    mem = lib.ensure_memory_dir(cwd)
    try:
        lib.copy_template("no-such-template", mem)
    except FileNotFoundError:
        return
    assert False, "expected FileNotFoundError"
