"""
MegaMind — shared utilities for memory hooks.

Design goals:
  1. Zero external dependencies (stdlib only).
  2. Hard token budgets per hook (char-based approximation, 4 chars ≈ 1 token).
  3. Silent no-op when no memory exists or nothing relevant found.
  4. Cross-platform (Windows + mac + linux).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import deque
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

# Budgets (characters, ~4 chars per token). Tightened for the "lean everywhere"
# default: the index is line-clipped + the PreCompact resume is already small, so
# the whole SessionStart payload stays well under this cap without losing the map.
BUDGET_SESSION_START = 4500       # ~1125 tokens (was 6000)
BUDGET_USER_PROMPT = 1600         # ~400 tokens
BUDGET_SNIPPET = 600              # ~150 tokens per file
BUDGET_INDEX_LINES = 60           # max lines of MEMORY.md to include
MIN_KEYWORDS = 2                  # min keywords to trigger inject
MIN_KEYWORD_LEN = 4

# ── Ultra: token-saving constants ──
BUDGET_PRECOMPACT = 2400          # ~600 tokens — cap for a clean resume snapshot
TOOL_RESULT_MAX_CHARS = 240       # per tool_result, first line clipped
RESUME_TAIL_MESSAGES = 120        # only keep last N content blocks (recency, bounded)
TF_CAP = 5                        # cap a single keyword's term-frequency contribution
NOISE_LINE_RATIO = 0.30           # frac of noisy lines that marks a file as garbage
NOISE_MIN_NOISY_LINES = 6         # absolute floor so a tiny note isn't nuked

# ── Ultra v2: relevance gating + per-session inject ledger ──
# These ONLY affect the per-turn inject path (grep_memory(..., inject=True) used
# by the UserPromptSubmit hook). Recall / other callers are unchanged.
MIN_SCORE_ABS = 3.0               # absolute score floor — below this, never inject
MIN_SCORE_REL_FRAC = 0.5          # keep only files >= this fraction of the top score
INJECT_MIN_COVERAGE = 2           # require >= min(this, #keywords) distinct keyword hits
ACRONYM_MIN_LEN = 2               # keep high-signal ALL-CAPS acronyms (KDP, TCG, OG, AWS)
LEDGER_DIRNAME = "seen"           # under CLAUDE_HOME/.megamind/<LEDGER_DIRNAME>/
LEDGER_MAX_AGE_SEC = 86400        # prune per-session inject ledgers older than 24h

# Noise signatures. RE_JSONL = Claude Code transcript rows; RE_SELFINJECT =
# megamind's own injected blocks (never re-ingest); RE_BASE64RUN = image/blob runs.
RE_JSONL = re.compile(
    r'"(parentUuid|sessionId|toolUseResult|requestId|isSidechain|toolUseID|promptId|leafUuid)"\s*:'
)
RE_SELFINJECT = re.compile(r"Memory hits for this message|Pre-compact snapshot|## Transcript tail")
RE_BASE64RUN = re.compile(r"[A-Za-z0-9+/]{120,}={0,2}")
RE_H1 = re.compile(r"^#\s+(.+)$")
RE_DECISION = re.compile(
    r"\b(decided|will|chose|switched|because|instead|plan|approach|root cause|fix(ed)?)\b", re.I
)


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
    The slug is the full cwd with every `:`, `/`, `\\`, `.`, AND whitespace
    mapped to `-`, then leading dashes stripped. The whitespace mapping is
    essential: a path like "D:\\CLAUDE\\My App" becomes "D--CLAUDE-My-App"
    (matching Claude Code's own slug) — without it the space survived and the
    memory lookup silently fell back to the PARENT project's memory. Examples:
        D:\\CLAUDE\\my-project                 → D--CLAUDE-my-project
        D:\\CLAUDE\\My App                     → D--CLAUDE-My-App
        D:\\CLAUDE\\my-project\\.claude\\w\\x  → D--CLAUDE-my-project--claude-w-x
    """
    if not cwd:
        return None
    slug = re.sub(r"[:\\/.\s]", "-", cwd)
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
    # e.g. D--CLAUDE-my-project--claude-worktrees-lucid-brattain → parent
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
    """Pull alphanumeric words ≥ min_len, lowercased, deduped.

    Also unions high-signal ALL-CAPS acronyms (KDP, TCG, OG, AWS) of length
    ≥ ACRONYM_MIN_LEN that the length gate would otherwise drop — they carry the
    most query intent, and dropping them was the root cause of weak/irrelevant
    matches (a short acronym query degenerating to leftover generic words)."""
    if not text:
        return set()
    words = re.findall(rf"[A-Za-z0-9_]{{{min_len},}}", text)
    acronyms = re.findall(rf"\b[A-Z0-9]{{{ACRONYM_MIN_LEN},}}\b", text)
    # Drop common English/Czech stopwords (keeps budget clean)
    STOP = {
        "this", "that", "with", "from", "have", "will", "would", "could", "should",
        "what", "when", "where", "which", "there", "about", "been", "were", "they",
        "them", "their", "také", "ktery", "ktera", "ktere", "take", "nebo", "takže",
        "taky", "jestli", "protože", "protoze", "jsem", "jsme", "byla", "byly",
        "ktere", "vsechno", "něco", "něco", "ještě", "jeste", "dnes", "teda", "pořád",
    }
    out = {w.lower() for w in words} | {a.lower() for a in acronyms}
    return {w for w in out if w not in STOP}


def score_file_detail(path: Path, keywords: set[str]) -> tuple[float, int]:
    """
    Relevance score for one file plus the distinct-keyword 'present' count.
    base = Σ min(count(k), TF_CAP) × length_weight(k)  — caps keyword spam, and
           length-weights so longer/rarer terms dominate (a cheap stdlib IDF proxy:
           generic 4-char words contribute ~1×, a 10-char project term ~1.9×)
    × coverage (distinct keywords present ^1.5) — rewards files covering more of the query
    × title_boost (1.5 if a keyword is in the H1)
    × proximity_boost (1.3 if ≥2 distinct keywords co-occur within 200 chars)
    × freshness (0.6–1.0 by mtime age)
    Returns (score, present). The inject path uses 'present' to enforce a coverage gate.
    """
    if not keywords:
        return (0.0, 0)
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return (0.0, 0)
    low = text.lower()
    base = 0.0
    present = 0
    for k in keywords:
        c = low.count(k)
        if c:
            present += 1
            base += min(c, TF_CAP) * (1.0 + 0.15 * max(0, len(k) - 4))
    if base == 0:
        return (0.0, 0)

    coverage = present ** 1.5

    title_boost = 1.0
    for line in text.split("\n")[:12]:
        m = RE_H1.match(line)
        if m and any(k in m.group(1).lower() for k in keywords):
            title_boost = 1.5
            break

    prox_boost = 1.0
    if present >= 2:
        positions = sorted(
            (low.find(k), k) for k in keywords if low.find(k) >= 0
        )
        for i in range(len(positions)):
            window = {positions[i][1]}
            for j in range(i + 1, len(positions)):
                if positions[j][0] - positions[i][0] <= 200:
                    window.add(positions[j][1])
                else:
                    break
            if len(window) >= 2:
                prox_boost = 1.3
                break

    try:
        age_days = max(0.0, (time.time() - path.stat().st_mtime) / 86400.0)
    except Exception:
        age_days = 0.0
    freshness = 0.6 + 0.4 / (1 + age_days / 14.0)

    return (base * coverage * title_boost * prox_boost * freshness, present)


def score_file(path: Path, keywords: set[str]) -> float:
    """Relevance score for one file (0.0 if unreadable / no hit). Thin wrapper over
    score_file_detail — kept for non-inject callers (recall, tests) so their
    single-float contract is unchanged."""
    return score_file_detail(path, keywords)[0]


def grep_memory(
    mem_dir: Path, keywords: set[str], max_files: int = 3, inject: bool = False
) -> list[Path]:
    """Return top-K .md files by relevance, skipping transcript-noise dumps and
    de-duplicating near-identical notes (same prose fingerprint).

    inject=False (default): every file with score>0 is eligible — used by recall
    and any caller that wants best-effort matches. Behaviour unchanged.

    inject=True: the strict per-turn path used by the UserPromptSubmit hook. Adds
    a coverage gate (a file must contain ≥ min(INJECT_MIN_COVERAGE, #keywords)
    distinct keywords) and a relevance floor (score ≥ max(MIN_SCORE_ABS,
    MIN_SCORE_REL_FRAC × top_score)). Weak/coincidental matches return [] (silent),
    so a vague prompt injects nothing instead of unrelated noise."""
    if not mem_dir.exists():
        return []
    need = min(INJECT_MIN_COVERAGE, len(keywords)) if inject else 0
    results: list[tuple[float, Path]] = []
    for md in mem_dir.rglob("*.md"):
        if is_noise_file(md):  # never inject base64/JSONL garbage
            continue
        score, present = score_file_detail(md, keywords)
        if score <= 0:
            continue
        if inject and present < need:  # coverage gate — kill single-keyword coincidences
            continue
        results.append((score, md))
    if not results:
        return []
    # Sort by score desc, then by mtime desc (newer wins ties)
    results.sort(key=lambda pair: (pair[0], pair[1].stat().st_mtime), reverse=True)
    if inject:
        top = results[0][0]
        floor = max(MIN_SCORE_ABS, MIN_SCORE_REL_FRAC * top)
        results = [r for r in results if r[0] >= floor]
        if not results:
            return []
    out: list[Path] = []
    seen: set[str] = set()
    for _, p in results:
        fp = _prose_fingerprint(p)
        if fp and fp in seen:
            continue
        if fp:
            seen.add(fp)
        out.append(p)
        if len(out) >= max_files:
            break
    return out


def extract_snippet(path: Path, keywords: set[str], max_chars: int = BUDGET_SNIPPET) -> str:
    """
    Extract a contextual snippet around first keyword hit, within budget.
    Prefers the document title (first H1) + matching lines + tiny context.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

    raw = text.split("\n")
    # Pull title (first H1 line) if present
    title = ""
    for line in raw[:10]:
        if line.startswith("# "):
            title = line.strip()
            break

    # Drop transcript-noise lines (base64/JSONL/self-injected blocks) so a snippet
    # never spends the budget on garbage.
    lines = [line for line in raw if not is_noise_line(line)]
    if not lines:
        return ""

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
    """Most recent REAL session note in memory/sessions/ — excludes transcript-noise
    dumps so a fresh auto-compact garbage file can never hijack the SessionStart slot.
    Returns None if only dumps exist."""
    sess_dir = mem_dir / "sessions"
    if not sess_dir.exists():
        return None
    candidates = [p for p in sess_dir.rglob("*.md") if not is_noise_file(p)]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def memory_index(mem_dir: Path, max_chars: int = 3000, max_line: int = 160) -> str | None:
    """Read MEMORY.md index and return a LEAN, scannable version: each line is
    clipped to max_line chars so long session bullets become titles+hooks rather
    than paragraphs (the full detail lives in the session files, loaded only on
    recall). Keeps the whole map (every entry) while spending far fewer tokens —
    'see it faster, burn less'."""
    idx = mem_dir / "MEMORY.md"
    if not idx.exists():
        return None
    try:
        text = idx.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    out: list[str] = []
    for line in text.split("\n"):
        if len(line) > max_line:
            line = line[: max_line - 1].rstrip() + "…"
        out.append(line)
    text = "\n".join(out)
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


# ══════════════════════════════════════════════════════════════════════════
# ULTRA v2: per-session inject ledger — "load once, inject deltas only"
#
# The UserPromptSubmit hook used to re-inject the SAME matching note on EVERY
# turn (no memory of what it already surfaced). Once a note is in the
# conversation it is carried forward for free in the cached prefix, so
# re-injecting it adds zero information and — under the 5-min cache TTL and
# bursty usage — gets re-charged at full price every time the cache goes cold.
#
# The ledger records, per session, the set of memory files already injected
# (relpaths, forward-slash normalized). SessionStart pre-seeds it with what it
# loads (index + latest resume), so the per-turn hook injects ONLY genuinely new
# files. Stored OUTSIDE any project memory dir (CLAUDE_HOME/.megamind/seen/) so
# it can never be picked up by grep_memory's *.md scan, recall, or vault sync.
# Every function is fully fail-silent: any IO error or a missing session id
# degrades to "dedup disabled" (i.e. exactly today's behaviour), never a crash.
# ══════════════════════════════════════════════════════════════════════════

def session_key(payload: dict) -> str | None:
    """Stable per-session id from the hook payload. Prefer the explicit
    session_id; fall back to the transcript filename stem (the session UUID) so
    dedup still works even if the key is ever renamed. None if neither is present
    (→ dedup silently disabled)."""
    if not isinstance(payload, dict):
        return None
    sid = payload.get("session_id")
    if not sid:
        tp = payload.get("transcript_path")
        if tp:
            try:
                sid = Path(tp).stem
            except Exception:
                sid = None
    return sid or None


def _safe_session_id(sid: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", sid or "")[:80] or "nosession"


def _seen_dir() -> Path:
    return CLAUDE_HOME / ".megamind" / LEDGER_DIRNAME


def _ledger_path(session_id: str | None) -> Path:
    return _seen_dir() / f"{_safe_session_id(session_id)}.json"


def norm_relpath(rel) -> str:
    """Forward-slash relpath string so SessionStart (seeding) and UserPromptSubmit
    (checking) always agree regardless of OS separator."""
    return str(rel).replace("\\", "/")


def load_seen(session_id: str | None) -> set[str]:
    """Set of relpaths already injected this session. Empty on missing id / any error."""
    if not session_id:
        return set()
    try:
        p = _ledger_path(session_id)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return set(data)
    except Exception:
        pass
    return set()


def save_seen(session_id: str | None, relpaths: set[str]) -> None:
    """Atomically persist the seen-set (tmp write + os.replace). No-op on missing
    id or any IO error — never raises, never leaves a partial file."""
    if not session_id:
        return
    try:
        d = _seen_dir()
        d.mkdir(parents=True, exist_ok=True)
        p = _ledger_path(session_id)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(sorted(relpaths)), encoding="utf-8")
        os.replace(tmp, p)
    except Exception:
        pass


def prune_old_ledgers(max_age_sec: int = LEDGER_MAX_AGE_SEC) -> None:
    """Unlink per-session ledgers older than max_age_sec. Bounds the dir even
    though Claude Code never signals session end. Fully fail-silent."""
    try:
        d = _seen_dir()
        if not d.exists():
            return
        cut = time.time() - max_age_sec
        for f in d.glob("*.json"):
            try:
                if f.stat().st_mtime < cut:
                    f.unlink()
            except Exception:
                pass
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════
# ULTRA: noise detection — keep base64 / JSONL transcript garbage out of recall
# ══════════════════════════════════════════════════════════════════════════

def is_noise_line(line: str) -> bool:
    """A single line that is transcript noise (JSONL row, self-injected block,
    or a long base64 run with no spaces)."""
    if RE_JSONL.search(line) or RE_SELFINJECT.search(line):
        return True
    if RE_BASE64RUN.search(line) and " " not in line.strip():
        return True
    return False


def is_noise_file(path: Path) -> bool:
    """Whether a memory file is a raw transcript dump (so recall/SessionStart skip it).
    Filename match is anchored to PreCompact's real stems ONLY (never loose substrings
    like 'auto-' that would false-positive on titles like 'Auto-deploy'); otherwise a
    content sniff over the first 4KB with an absolute noisy-line floor."""
    name = path.name
    if name.startswith("_compact-") or re.search(r"compact-(auto|manual)", name):
        return True
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            head = f.read(4096)
    except Exception:
        return False  # transient Windows/OneDrive lock — never silently drop a note
    lines = [ln for ln in head.split("\n") if ln.strip()]
    if len(lines) < NOISE_MIN_NOISY_LINES:
        return False
    noisy = sum(1 for ln in lines if is_noise_line(ln))
    return noisy >= NOISE_MIN_NOISY_LINES and (noisy / len(lines)) >= NOISE_LINE_RATIO


def _prose_fingerprint(path: Path) -> str:
    """First 3 clean, non-heading lines, lowercased — for dedup of near-identical notes."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    picked: list[str] = []
    for line in text.split("\n"):
        s = line.strip()
        if not s or s.startswith("#") or is_noise_line(s):
            continue
        picked.append(s)
        if len(picked) >= 3:
            break
    return " ".join(picked).lower()[:160]


# ══════════════════════════════════════════════════════════════════════════
# ULTRA: PreCompact clean resume — parse the transcript, strip base64/tool JSON,
# emit a small structured snapshot instead of dumping a raw 20KB byte-tail.
# ══════════════════════════════════════════════════════════════════════════

def _looks_binary(s: str) -> bool:
    head = s[:24]
    if head.startswith(("/9j/", "iVBOR", "H4sI", "data:image")):
        return True
    sample = s[:400]
    if len(sample) >= 200:
        b64 = sum(1 for c in sample if c.isalnum() or c in "+/=")
        if b64 / len(sample) > 0.97 and " " not in sample:
            return True
    return False


def clean_tool_result(block: dict) -> str:
    """First useful line of a tool_result, or '' — DROPS image blocks and base64
    blobs. On an image block it CONTINUES (so a mixed image+text result keeps its text)."""
    rc = block.get("content")
    parts = rc if isinstance(rc, list) else [rc]
    for x in parts:
        if isinstance(x, dict):
            if x.get("type") == "image":
                continue
            if x.get("type") == "text":
                t = x.get("text", "")
            else:
                continue
        elif isinstance(x, str):
            t = x
        else:
            continue
        t = (t or "").strip()
        if not t or _looks_binary(t):
            continue
        return t.splitlines()[0][:TOOL_RESULT_MAX_CHARS]
    return ""


def _strip_noise_prose(s: str) -> str:
    s = re.sub(r"```.*?```", "[code]", s, flags=re.S)
    s = re.sub(r"<system-reminder>.*?</system-reminder>", "", s, flags=re.S)
    return re.sub(r"\s+", " ", s).strip()


def iter_transcript_blocks(transcript_path: str) -> list[dict]:
    """Stream the JSONL transcript line-by-line into a bounded deque of normalized
    content blocks (text / thinking / tool_use / tool_result). [] on any IOError."""
    dq: deque = deque(maxlen=RESUME_TAIL_MESSAGES)
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:  # lazy — bounded memory even on multi-MB transcripts
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                msg = obj.get("message")
                if not isinstance(msg, dict):
                    continue
                role = msg.get("role")
                content = msg.get("content")
                if isinstance(content, str):
                    dq.append({"role": role, "kind": "text", "text": content})
                elif isinstance(content, list):
                    for b in content:
                        if not isinstance(b, dict):
                            continue
                        bt = b.get("type")
                        if bt == "text":
                            dq.append({"role": role, "kind": "text", "text": b.get("text", "")})
                        elif bt == "thinking":
                            dq.append({"role": role, "kind": "thinking", "text": b.get("thinking", "")})
                        elif bt == "tool_use":
                            dq.append({"role": role, "kind": "tool_use", "name": b.get("name", ""), "input": b.get("input") or {}})
                        elif bt == "tool_result":
                            dq.append({"role": role, "kind": "tool_result", "block": b})
    except Exception:
        return []
    return list(dq)


def build_resume(records: list[dict]) -> str:
    """Bucket transcript blocks into a clean structured resume (≤BUDGET_PRECOMPACT)."""
    decisions: list[str] = []
    files: list[str] = []
    cmds: list[str] = []
    intents: list[str] = []
    questions: list[str] = []

    def add(lst: list[str], v) -> None:
        if v and v not in lst:
            lst.append(v)

    for r in records:
        k = r.get("kind")
        if k == "tool_use":
            n = r.get("name")
            inp = r.get("input") or {}
            if n in ("Edit", "Write", "NotebookEdit"):
                add(files, inp.get("file_path") or inp.get("notebook_path"))
            elif n == "Read":
                add(files, inp.get("file_path"))
            elif n in ("Bash", "PowerShell"):
                add(cmds, (inp.get("command") or "")[:120])
        elif k == "text" and r.get("role") == "user":
            t = _strip_noise_prose(r.get("text", ""))
            if t and not t.startswith("[Request interrupted") and not t.startswith("<"):
                intents.append(t[:200])
                if "?" in t:
                    questions.append(t[:200])
        elif k == "text" and r.get("role") == "assistant":
            t = _strip_noise_prose(r.get("text", ""))
            if t and RE_DECISION.search(t):
                decisions.append(t[:200])

    def tail_uniq(xs: list[str], n: int) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for x in reversed(xs):
            if x and x not in seen:
                seen.add(x)
                out.append(x)
        return list(reversed(out))[-n:]

    sections = [
        ("Recent intent", tail_uniq(intents, 4)),
        ("Decisions / rationale", tail_uniq(decisions, 6)),
        ("Files touched", tail_uniq(files, 12)),
        ("Commands run", tail_uniq(cmds, 8)),
        ("Open questions", tail_uniq(questions, 4)),
    ]
    out: list[str] = []
    for nm, items in sections:
        if items:
            out.append(f"### {nm}\n" + "\n".join(f"- {i}" for i in items))
    body = "\n\n".join(out)
    return format_budget(body, BUDGET_PRECOMPACT) if body else ""


# ══════════════════════════════════════════════════════════════════════════
# ULTRA: lean mode (token-discipline directive, opt-out) + memory-vault sync
# ══════════════════════════════════════════════════════════════════════════

LEAN_LINE = (
    "Lean mode — to save tokens: route big reads (>~400 lines or >3 files) to a "
    "subagent and keep only the conclusion; `/clear` on an unrelated task switch; "
    "recall from memory before asking the user to re-explain; load MCP/skill tools "
    "only when the task needs them."
)


def lean_on() -> bool:
    """Lean directive is default-ON; opt out by creating ~/.claude/megamind-lean.off."""
    return not (CLAUDE_HOME / "megamind-lean.off").exists()


VAULT_DIR = Path(
    os.environ.get("MEGAMIND_VAULT_DIR") or (Path.home() / "Documents" / "GitHub" / "memory-vault")
)
SYNC_DEBOUNCE_SEC = int(os.environ.get("MEGAMIND_SYNC_DEBOUNCE") or 900)
# Default OFF: vault.sync() calls git directly (bypassing Claude's pre-commit secret
# hook) and your memory-vault repo may be public — opt in only after accepting the inline scan.
AUTOSYNC_ON = os.environ.get("MEGAMIND_AUTOSYNC", "0") == "1"

_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9]{16,}"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|AKIA[0-9A-Z]{12,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|AIza[0-9A-Za-z_\-]{20,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)


def scan_secrets(text: str) -> bool:
    """True if the text appears to contain a credential (best-effort, stdlib regex)."""
    return bool(_SECRET_RE.search(text or ""))


def git_quiet(args: list[str], cwd: Path, timeout: int = 10) -> tuple[int, str]:
    """Run a git command; never raises. Returns (returncode, combined stdout+stderr)."""
    try:
        p = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=timeout
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as exc:
        return 1, str(exc)
