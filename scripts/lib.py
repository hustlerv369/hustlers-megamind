"""
MegaMind — shared utilities for memory hooks.

Design goals:
  1. Zero external dependencies (stdlib only).
  2. Hard token budgets per hook (char-based approximation, 4 chars ≈ 1 token).
  3. Silent no-op when no memory exists or nothing relevant found.
  4. Cross-platform (Windows + mac + linux).
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Force UTF-8 on stdout/stderr so emoji + Czech chars don't crash the hook
# on Windows (default is cp1250). Safe no-op on POSIX. Python 3.7+.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

CLAUDE_HOME = Path(os.environ.get("CLAUDE_HOME") or (Path.home() / ".claude"))
PROJECTS_ROOT = CLAUDE_HOME / "projects"

# Budgets (characters, ~4 chars per token)
BUDGET_SESSION_START = 6000       # ~1500 tokens
BUDGET_USER_PROMPT = 1600         # ~400 tokens
BUDGET_SNIPPET = 600              # ~150 tokens per file
BUDGET_INDEX_LINES = 60           # max lines of MEMORY.md to include
MIN_KEYWORDS = 2                  # min keywords to trigger inject
MIN_KEYWORD_LEN = 4


def read_hook_input() -> dict:
    """Read JSON payload from stdin (Claude Code hook contract)."""
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def project_slug_from_cwd(cwd: str | None) -> str | None:
    """
    Claude Code stores per-project data under ~/.claude/projects/<slug>/.
    The slug is the full cwd with every `:`, `/`, `\\`, and `.` mapped to `-`,
    then leading dashes stripped. Examples:
        D:\\projects\\my-app                  → D--projects-my-app
        D:\\projects\\my-app\\.claude\\w\\x   → D--projects-my-app--claude-w-x
    """
    if not cwd:
        return None
    slug = re.sub(r"[:\\/.]", "-", cwd)
    return slug.lstrip("-")


def find_memory_dir(cwd: str | None) -> Path | None:
    """Return the memory directory for the given cwd, if it exists."""
    slug = project_slug_from_cwd(cwd)
    if not slug:
        return None
    mem = PROJECTS_ROOT / slug / "memory"
    if mem.exists() and mem.is_dir():
        return mem
    # Fallback 1: worktrees share memory with their parent repo
    # e.g. D--projects-my-app--claude-worktrees-lucid-brattain → parent
    parts = slug.split("--claude-worktrees-")
    if len(parts) == 2:
        parent_slug = parts[0]
        mem = PROJECTS_ROOT / parent_slug / "memory"
        if mem.exists():
            return mem
    # Fallback 2: walk up the path, look for a matching project slug. Useful
    # when cwd is a deep subdirectory and only the repo root has memory.
    p = Path(cwd)
    for ancestor in [p.parent, *list(p.parents)]:
        anc_slug = project_slug_from_cwd(str(ancestor))
        if not anc_slug:
            continue
        mem = PROJECTS_ROOT / anc_slug / "memory"
        if mem.exists():
            return mem
    return None


def extract_keywords(text: str, min_len: int = MIN_KEYWORD_LEN) -> set[str]:
    """Pull alphanumeric words ≥ min_len, lowercased, deduped."""
    if not text:
        return set()
    words = re.findall(rf"[A-Za-z0-9_]{{{min_len},}}", text)
    # Drop common English/Czech stopwords (keeps budget clean)
    STOP = {
        "this", "that", "with", "from", "have", "will", "would", "could", "should",
        "what", "when", "where", "which", "there", "about", "been", "were", "they",
        "them", "their", "také", "ktery", "ktera", "ktere", "take", "nebo", "takže",
        "taky", "jestli", "protože", "protoze", "jsem", "jsme", "byla", "byly",
        "ktere", "vsechno", "něco", "něco", "ještě", "jeste", "dnes", "teda", "pořád",
    }
    return {w.lower() for w in words if w.lower() not in STOP}


def score_file(path: Path, keywords: set[str]) -> int:
    """Keyword-hit count for a single file; 0 if unreadable."""
    if not keywords:
        return 0
    try:
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
    except Exception:
        return 0
    score = 0
    for k in keywords:
        score += text.count(k)
    return score


def grep_memory(mem_dir: Path, keywords: set[str], max_files: int = 3) -> list[Path]:
    """Return top-K .md files sorted by keyword relevance."""
    if not mem_dir.exists():
        return []
    results: list[tuple[int, Path]] = []
    for md in mem_dir.rglob("*.md"):
        score = score_file(md, keywords)
        if score > 0:
            results.append((score, md))
    # Sort by score desc, then by mtime desc (newer wins ties)
    results.sort(key=lambda pair: (pair[0], pair[1].stat().st_mtime), reverse=True)
    return [p for _, p in results[:max_files]]


def extract_snippet(path: Path, keywords: set[str], max_chars: int = BUDGET_SNIPPET) -> str:
    """
    Extract a contextual snippet around first keyword hit, within budget.
    Prefers the document title (first H1) + matching lines + tiny context.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

    lines = text.split("\n")
    # Pull title (first H1 line) if present
    title = ""
    for line in lines[:10]:
        if line.startswith("# "):
            title = line.strip()
            break

    # Find first keyword hit; take surrounding 10 lines
    lower_lines = [line.lower() for line in lines]
    match_idx = -1
    for k in keywords:
        for i, line in enumerate(lower_lines):
            if k in line:
                match_idx = i
                break
        if match_idx != -1:
            break

    if match_idx == -1:
        # No hit in file content (keyword might be in path). Take top of file.
        body = "\n".join(lines[:10])
    else:
        start = max(0, match_idx - 2)
        end = min(len(lines), match_idx + 10)
        body = "\n".join(lines[start:end])

    out = (title + "\n\n" + body).strip() if title else body
    if len(out) > max_chars:
        out = out[: max_chars - 15].rstrip() + "\n[...truncated]"
    return out


def latest_session_note(mem_dir: Path) -> Path | None:
    """Find the most recently modified file in memory/sessions/."""
    sess_dir = mem_dir / "sessions"
    if not sess_dir.exists():
        return None
    candidates = list(sess_dir.rglob("*.md"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def memory_index(mem_dir: Path, max_chars: int = 4000) -> str | None:
    """Read MEMORY.md index, clip to budget."""
    idx = mem_dir / "MEMORY.md"
    if not idx.exists():
        return None
    try:
        text = idx.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    if len(text) > max_chars:
        text = text[: max_chars - 15].rstrip() + "\n[...truncated]"
    return text


def format_budget(text: str, max_chars: int) -> str:
    """Hard-clip to budget with a tail marker."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 15].rstrip() + "\n[...truncated]"


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def write_session_summary(mem_dir: Path, title: str, body: str) -> Path:
    """Append a session note under memory/sessions/."""
    sess_dir = mem_dir / "sessions"
    sess_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    safe_title = re.sub(r"[^A-Za-z0-9._-]+", "-", title)[:40] or "session"
    path = sess_dir / f"{stamp}-{safe_title}.md"
    path.write_text(body, encoding="utf-8")
    return path


def log_err(msg: str) -> None:
    """Write to stderr — shown to user by Claude Code if non-empty."""
    sys.stderr.write(f"[megamind] {msg}\n")


# ────────────────────────────────────────────────────────────────────
# CLI helpers — remember / forget / audit / stats / init
# ────────────────────────────────────────────────────────────────────

def ensure_memory_dir(cwd: str | None) -> Path:
    """
    Ensure memory dir exists for this project — create MEMORY.md skeleton
    if missing. Returns the memory dir path. Never raises for permission.
    """
    slug = project_slug_from_cwd(cwd)
    if not slug:
        raise ValueError("cannot derive project slug from cwd")
    mem = PROJECTS_ROOT / slug / "memory"
    mem.mkdir(parents=True, exist_ok=True)
    idx = mem / "MEMORY.md"
    if not idx.exists():
        idx.write_text(
            "# Project memory index\n\n"
            "Newest entries first. One line per fact, tag with emoji.\n\n",
            encoding="utf-8",
        )
    return mem


def append_memory_line(mem_dir: Path, text: str, tag: str = "📦") -> str:
    """
    Append a one-line fact to MEMORY.md. Returns the line written.
    Deduplicates: if the same text is already there, no-op.
    """
    idx = mem_dir / "MEMORY.md"
    existing = idx.read_text(encoding="utf-8", errors="ignore") if idx.exists() else ""
    stamp = datetime.now().strftime("%Y-%m-%d")
    line = f"- {tag} [{stamp}] {text.strip()}\n"
    if line.strip() in existing:
        return line
    with idx.open("a", encoding="utf-8") as f:
        f.write(line)
    return line


def forget_memory_line(mem_dir: Path, query: str) -> list[str]:
    """
    Remove lines from MEMORY.md matching query (case-insensitive).
    Returns the removed lines (may be empty).
    """
    idx = mem_dir / "MEMORY.md"
    if not idx.exists():
        return []
    lines = idx.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
    q = query.lower().strip()
    if not q:
        return []
    kept: list[str] = []
    removed: list[str] = []
    for line in lines:
        if line.strip().startswith("-") and q in line.lower():
            removed.append(line)
        else:
            kept.append(line)
    if removed:
        idx.write_text("".join(kept), encoding="utf-8")
    return removed


# Patterns that strongly suggest a secret has leaked into memory.
# False-positive rate is non-zero; audit output is advisory, not blocking.
SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("stripe-live",        re.compile(r"\bsk_live_[A-Za-z0-9]{16,}")),
    ("stripe-test",        re.compile(r"\bsk_test_[A-Za-z0-9]{16,}")),
    ("stripe-restricted",  re.compile(r"\brk_live_[A-Za-z0-9]{16,}")),
    ("github-pat",         re.compile(r"\bghp_[A-Za-z0-9]{30,}")),
    ("github-oauth",       re.compile(r"\bgho_[A-Za-z0-9]{30,}")),
    ("google-api",         re.compile(r"\bAIza[A-Za-z0-9_-]{30,}")),
    ("openai",             re.compile(r"\bsk-[A-Za-z0-9]{40,}")),
    ("anthropic",          re.compile(r"\bsk-ant-[A-Za-z0-9_-]{40,}")),
    ("aws-access",         re.compile(r"\bAKIA[A-Z0-9]{16}")),
    ("slack-bot",          re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}")),
    ("jwt",                re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}")),
    ("private-key-header", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("password-assign",    re.compile(r"(?i)\bpassword\s*[:=]\s*['\"][^'\"]{6,}['\"]")),
    ("api-key-assign",     re.compile(r"(?i)\b(?:api[_-]?key|secret[_-]?key)\s*[:=]\s*['\"][A-Za-z0-9_-]{16,}['\"]")),
    ("bearer-token",       re.compile(r"\bBearer\s+[A-Za-z0-9_-]{20,}")),
]


def scan_secrets(mem_dir: Path) -> list[tuple[Path, str, int, str]]:
    """
    Walk memory dir, return list of (file, pattern_name, line_no, matched_snippet).
    Advisory — not every match is a real secret, but every real secret matches.
    """
    hits: list[tuple[Path, str, int, str]] = []
    for md in mem_dir.rglob("*.md"):
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            for name, pat in SECRET_PATTERNS:
                m = pat.search(line)
                if m:
                    snippet = m.group(0)
                    if len(snippet) > 40:
                        snippet = snippet[:20] + "…" + snippet[-10:]
                    hits.append((md, name, line_no, snippet))
    return hits


# ────────────────────────────────────────────────────────────────────
# Stats — hook fire counts + token savings estimate
# ────────────────────────────────────────────────────────────────────

STATS_FILE = ".megamind-stats.json"

# Reasonable per-event averages (conservative)
TOKENS_SAVED_PER_SESSION_START = 1200  # typical re-explain avoided
TOKENS_SAVED_PER_PROMPT_HIT = 500      # typical context paste avoided
TOKENS_SAVED_PER_COMPACT = 800         # typical manual tail summary avoided


def stats_file(mem_dir: Path) -> Path:
    return mem_dir / STATS_FILE


def load_stats(mem_dir: Path) -> dict:
    f = stats_file(mem_dir)
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}


def bump_stat(mem_dir: Path, key: str, delta: int = 1) -> None:
    """Increment a counter. Silent on any error (stats are non-critical)."""
    try:
        data = load_stats(mem_dir)
        data[key] = data.get(key, 0) + delta
        data["last_updated"] = now_iso()
        stats_file(mem_dir).write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def estimate_tokens_saved(stats: dict) -> int:
    s = stats.get("session_start", 0) * TOKENS_SAVED_PER_SESSION_START
    s += stats.get("prompt_hit", 0) * TOKENS_SAVED_PER_PROMPT_HIT
    s += stats.get("compact", 0) * TOKENS_SAVED_PER_COMPACT
    return s


# ────────────────────────────────────────────────────────────────────
# Templates — project-type starter kits
# ────────────────────────────────────────────────────────────────────

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def list_templates() -> list[str]:
    if not TEMPLATES_DIR.exists():
        return []
    return sorted(p.name for p in TEMPLATES_DIR.iterdir() if p.is_dir())


def copy_template(name: str, mem_dir: Path) -> int:
    """
    Copy all files from templates/<name>/ into mem_dir. Does not overwrite
    existing files. Returns number of files created.
    """
    src = TEMPLATES_DIR / name
    if not src.exists() or not src.is_dir():
        raise FileNotFoundError(f"no such template: {name}")
    created = 0
    for entry in src.rglob("*"):
        if entry.is_dir():
            continue
        rel = entry.relative_to(src)
        dst = mem_dir / rel
        if dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(entry.read_bytes())
        created += 1
    return created
