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


# ════════════════════════════════════════════════════════════════════
# ULTRA v2: acronym keywords + relevance floor + per-session inject ledger
# ════════════════════════════════════════════════════════════════════

def test_keywords_keep_acronyms():
    # Short ALL-CAPS acronyms (the most salient token) must survive the length gate.
    kw = lib.extract_keywords("what is the KDP export")
    assert "kdp" in kw  # was previously dropped (3 chars) → root cause of weak matches
    kw2 = lib.extract_keywords("how does the TCG OG image work")
    assert "tcg" in kw2 and "og" in kw2


def test_keywords_lowercase_short_words_still_dropped():
    # The acronym pass must NOT resurrect lowercase short words.
    kw = lib.extract_keywords("fix the cat dog")
    assert "fix" not in kw and "cat" not in kw and "dog" not in kw


def test_score_file_detail_returns_present_count(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("stripe webhook stripe", encoding="utf-8")
    score, present = lib.score_file_detail(p, {"stripe", "webhook"})
    assert score > 0 and present == 2
    score0, present0 = lib.score_file_detail(p, {"unrelated"})
    assert score0 == 0.0 and present0 == 0


def test_grep_inject_relevance_floor_rejects_weak_match(tmp_path):
    d = tmp_path / "memory"
    d.mkdir()
    # A billing note shares only ONE generic word with a book-formatting query → no inject.
    (d / "billing.md").write_text("# Billing\nstripe webhook payment flow\n", encoding="utf-8")
    kws = lib.extract_keywords("how do I format a KDP book manuscript for kindle publishing")
    inject = lib.grep_memory(d, kws, max_files=3, inject=True)
    assert inject == []  # weak/irrelevant → silent (kills the wrong-note-injection class)


def test_grep_inject_coverage_gate(tmp_path):
    d = tmp_path / "memory"
    d.mkdir()
    (d / "one.md").write_text("stripe stripe stripe", encoding="utf-8")   # 1 keyword only
    (d / "two.md").write_text("stripe webhook payment stripe", encoding="utf-8")  # 2 keywords
    kws = {"stripe", "webhook"}
    inject = lib.grep_memory(d, kws, max_files=5, inject=True)
    names = [p.name for p in inject]
    assert "two.md" in names          # clears coverage (2 distinct hits)
    assert "one.md" not in names      # single-keyword coincidence rejected
    # Non-inject path is unchanged: both still returned.
    plain = [p.name for p in lib.grep_memory(d, kws, max_files=5)]
    assert "one.md" in plain and "two.md" in plain


def test_ledger_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "CLAUDE_HOME", tmp_path / ".claude")
    sid = "sess-abc-123"
    assert lib.load_seen(sid) == set()          # nothing yet
    lib.save_seen(sid, {"sessions/note.md", "MEMORY.md"})
    assert lib.load_seen(sid) == {"sessions/note.md", "MEMORY.md"}
    # Missing session id → always empty, never crashes.
    assert lib.load_seen(None) == set()
    lib.save_seen(None, {"x"})  # no-op, must not raise


def test_ledger_prune_old(tmp_path, monkeypatch):
    import os as _os, time as _time
    monkeypatch.setattr(lib, "CLAUDE_HOME", tmp_path / ".claude")
    lib.save_seen("fresh", {"a.md"})
    lib.save_seen("stale", {"b.md"})
    stale = lib._ledger_path("stale")
    old = _time.time() - (lib.LEDGER_MAX_AGE_SEC + 3600)
    _os.utime(stale, (old, old))
    lib.prune_old_ledgers()
    assert lib._ledger_path("fresh").exists()
    assert not stale.exists()


def test_session_key_prefers_id_then_transcript():
    assert lib.session_key({"session_id": "S1"}) == "S1"
    assert lib.session_key({"transcript_path": "/x/y/UUID-9.jsonl"}) == "UUID-9"
    assert lib.session_key({}) is None


def test_norm_relpath_forward_slashes():
    assert lib.norm_relpath("sessions\\note.md") == "sessions/note.md"
    assert lib.norm_relpath("MEMORY.md") == "MEMORY.md"


# ════════════════════════════════════════════════════════════════════
# FIXES: Unicode keyword extraction, word-boundary scoring, guarded
# .stat(), filename collisions, resume-note pruning, bounded scan
# ════════════════════════════════════════════════════════════════════

def test_keywords_diacritics_survive():
    # Previously the ASCII-only regex fragmented every diacritic word (e.g.
    # "pokracuj"/"uj"), so common non-English words never became keywords.
    kw = lib.extract_keywords("Prosím pokračuj a zkontroluj paměť před commitem")
    assert "pokračuj" in kw
    assert "paměť" in kw
    assert "commitem" in kw


def test_score_word_boundary_no_false_positive(tmp_path):
    # "note" must not score a hit inside "annotate"/"notebook"/"denote".
    p = tmp_path / "a.md"
    p.write_text("Please annotate the notebook and denote the changes.", encoding="utf-8")
    score, present = lib.score_file_detail(p, {"note"})
    assert score == 0.0 and present == 0


def test_score_word_boundary_real_hit_still_counts(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("Wrote a note. Left another note for later.", encoding="utf-8")
    score, present = lib.score_file_detail(p, {"note"})
    assert score > 0 and present == 1


def test_safe_mtime_missing_file_returns_zero(tmp_path):
    ghost = tmp_path / "does-not-exist.md"
    assert lib._safe_mtime(ghost) == 0.0


def test_write_session_summary_no_filename_collision(tmp_path):
    p1 = lib.write_session_summary(tmp_path, "resume-auto", "first")
    p2 = lib.write_session_summary(tmp_path, "resume-auto", "second")
    assert p1 != p2
    assert p1.read_text(encoding="utf-8") == "first"
    assert p2.read_text(encoding="utf-8") == "second"


def test_write_session_summary_uses_lf_not_crlf(tmp_path):
    p = lib.write_session_summary(tmp_path, "resume-manual", "line one\nline two\n")
    assert b"\r\n" not in p.read_bytes()


def test_prune_old_resume_notes_keeps_newest_only(tmp_path):
    sess = tmp_path / "sessions"
    sess.mkdir()
    import time as _t

    for i in range(5):
        (sess / f"2026-07-{10+i:02d}-000000-0000-resume-auto.md").write_text(f"note {i}", encoding="utf-8")
        _t.sleep(0.01)
    removed = lib.prune_old_resume_notes(tmp_path, keep_newest=2)
    remaining = sorted(sess.glob("*.md"))
    assert removed == 3
    assert len(remaining) == 2


def test_prune_old_resume_notes_ignores_hand_written_notes(tmp_path):
    sess = tmp_path / "sessions"
    sess.mkdir()
    (sess / "2026-07-01-hand-written-decision.md").write_text("important", encoding="utf-8")
    for i in range(40):
        (sess / f"2026-07-{i+1:02d}-resume-auto.md").write_text("x", encoding="utf-8")
    lib.prune_old_resume_notes(tmp_path, keep_newest=5)
    assert (sess / "2026-07-01-hand-written-decision.md").exists()
    assert len(list(sess.glob("*resume-auto.md"))) == 5


def test_secret_scan_widened_patterns():
    assert lib.scan_secrets("STRIPE_KEY=sk_live_abcdefghijklmnop1234")
    assert lib.scan_secrets("ANTHROPIC_API_KEY=sk-ant-api03-abcdefghijklmnopqrstuvwx")
    assert lib.scan_secrets("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dQw4w9WgXcQ")
    assert not lib.scan_secrets("no secrets here, just normal prose about code")


def test_grep_memory_respects_max_scan_files_cap(tmp_path, monkeypatch):
    d = tmp_path / "memory"
    d.mkdir()
    import time as _t

    old = d / "old.md"
    old.write_text("relevant content here", encoding="utf-8")
    _t.sleep(0.02)
    for i in range(4):
        (d / f"filler{i}.md").write_text("irrelevant filler text", encoding="utf-8")
    monkeypatch.setattr(lib, "MAX_SCAN_FILES", 2)
    results = lib.grep_memory(d, {"relevant", "content"}, max_files=5)
    assert old not in results
