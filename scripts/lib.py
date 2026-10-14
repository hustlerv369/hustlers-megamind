"""
MegaMind — shared utilities for memory hooks.

Design goals:
  1. Zero external dependencies (stdlib only).
  2. Complete relevant context; excerpts are explicitly requested and labeled.
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

# Budgets (characters, ~4 chars per token).
#
# These were squeezed hard for a "lean everywhere" default, which turned out to
# be a bad trade: on projects with a large memory dir the index got clipped and
# per-turn snippets were too small to carry a decision, so the model worked from
# a partial picture and produced confidently wrong output. Recall quality is the
# entire point of this tool — a few hundred tokens per turn is cheaper than one
# wrong answer. Raised back above the pre-lean values.
BUDGET_SESSION_START = 131072       # ~2000 tokens (was 4500, originally 6000)
BUDGET_USER_PROMPT = 131072         # ~750 tokens (was 1600)
BUDGET_SNIPPET = 32768             # ~250 tokens per file (was 600)
BUDGET_INDEX_LINES = 120          # max lines of MEMORY.md to include (was 60)
MIN_KEYWORDS = 1                  # min keywords to trigger inject
MIN_KEYWORD_LEN = 4
MAX_SCAN_FILES = 400              # cap files scanned per grep_memory() call — bounds
                                   # per-turn cost as a project's memory grows unbounded
RESUME_NOTE_KEEP = 30             # cap auto-generated PreCompact resume snapshots kept

# ── Ultra: token-saving constants ──
BUDGET_PRECOMPACT = 131072          # ~600 tokens — cap for a clean resume snapshot
TOOL_RESULT_MAX_CHARS = 240       # per tool_result, first line clipped
RESUME_TAIL_MESSAGES = None        # retain all safe transcript records by default
TF_CAP = 5                        # cap a single keyword's term-frequency contribution
NOISE_LINE_RATIO = 0.30           # frac of noisy lines that marks a file as garbage
NOISE_MIN_NOISY_LINES = 6         # absolute floor so a tiny note isn't nuked

# ── Ultra v2: relevance gating + per-session inject ledger ──
# These ONLY affect the per-turn inject path (grep_memory(..., inject=True) used
# by the UserPromptSubmit hook). Recall / other callers are unchanged.
# Relaxed after the gates proved too aggressive in practice: a follow-up like
# "co jsme dělali s tím videem" carries few distinct keywords, so the coverage
# gate + 50 % relative floor dropped the very notes that answered it and the hook
# injected nothing at all. Silence here is indistinguishable from "no memory
# exists", which is exactly how the amnesia looked from the outside. Prefer one
# extra ~250-token snippet over a confidently wrong answer.
MIN_SCORE_ABS = 1.5               # absolute score floor (was 3.0)
MIN_SCORE_REL_FRAC = 0.25         # keep files >= this fraction of top score (was 0.5)
INJECT_MIN_COVERAGE = 1           # distinct keyword hits required (was 2)
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
    """Read UTF-8 hook JSON independently of the Windows console code page.

    Invalid transport must be visible; returning {} would silently turn a real
    memory lookup into an empty successful result.
    """
    try:
        stream = getattr(sys.stdin, 'buffer', None)
        raw = stream.read().decode('utf-8-sig') if stream is not None else sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            raise ValueError('Hook payload is not an object')
        return payload
    except (UnicodeError, ValueError, OSError):
        sys.stderr.write('MegaMind: invalid UTF-8/JSON hook input; memory lookup was not performed.\n')
        raise SystemExit(2)


def project_slug_from_cwd(cwd: str | None) -> str | None:
    """
    Claude Code stores per-project data under ~/.claude/projects/<slug>/.
    The slug is the full cwd with every `:`, `/`, `\\`, `.`, AND whitespace
    mapped to `-`, then leading dashes stripped. The whitespace mapping is
    essential: a path like "D:\\CLAUDE\\CLAUDE OS" becomes "D--CLAUDE-CLAUDE-OS"
    (matching Claude Code's own slug) — without it the space survived and the
    memory lookup silently fell back to the PARENT project's memory. Examples:
        D:\\CLAUDE\\seokrates-web                 → D--CLAUDE-seokrates-web
        D:\\CLAUDE\\CLAUDE OS                     → D--CLAUDE-CLAUDE-OS
        D:\\CLAUDE\\seokrates-web\\.claude\\w\\x  → D--CLAUDE-seokrates-web--claude-w-x
    """
    if not cwd:
        return None
    # The leading dash is part of the slug on Unix: Claude Code maps an absolute
    # path's leading `/` to `-` (/Users/ann/app → -Users-ann-app). Stripping it
    # made every macOS/Linux lookup miss and the hooks exit silently.
    return re.sub(r"[:\\/.\s]", "-", cwd)


def find_memory_dir(cwd: str | None) -> Path | None:
    """Resolve exact project or a verified repository boundary, never drive/home memory."""
    if not cwd:
        return None
    requested = PROJECTS_ROOT / project_slug_from_cwd(cwd) / "memory"
    if requested.is_dir():
        return requested
    project=Path(os.path.abspath(cwd))
    exact=PROJECTS_ROOT / project_slug_from_cwd(str(project)) / "memory"
    if exact.is_dir():
        return exact
    for ancestor in [project, *project.parents]:
        git=ancestor / ".git"
        if git.is_file():
            try:
                value=git.read_text(encoding="utf-8").strip()
                if value.startswith("gitdir:"):
                    gitdir=(ancestor / value.split(":",1)[1].strip()).resolve()
                    common=gitdir.parent.parent
                    if gitdir.parent.name == "worktrees" and common.name == ".git":
                        shared=PROJECTS_ROOT / project_slug_from_cwd(str(common.parent)) / "memory"
                        if shared.is_dir(): return shared
            except OSError:
                pass
        boundary=git.exists() or (ancestor / "AGENTS.md").is_file() or (ancestor / "CLAUDE.md").is_file()
        if ancestor != Path(ancestor.anchor) and ancestor != Path.home() and boundary:
            candidate=PROJECTS_ROOT / project_slug_from_cwd(str(ancestor)) / "memory"
            if candidate.is_dir(): return candidate
            # A repository without memory must not inherit another project's state.
            if git.exists(): return None
    return None


def extract_keywords(text: str, min_len: int = MIN_KEYWORD_LEN) -> set[str]:
    """Pull alphanumeric words ≥ min_len, lowercased, deduped.

    Also unions high-signal ALL-CAPS acronyms (KDP, TCG, OG, AWS) of length
    ≥ ACRONYM_MIN_LEN that the length gate would otherwise drop — they carry the
    most query intent, and dropping them was the root cause of weak/irrelevant
    matches (a short acronym query degenerating to leftover generic words)."""
    if not text:
        return set()
    words = re.findall(rf"\w{{{min_len},}}", text, re.UNICODE)
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


def _safe_mtime(path: Path) -> float:
    """mtime, or 0.0 on any error (deleted/locked between listing and stat —
    e.g. a concurrent OneDrive sync or another session's write). Never raises,
    so a transient FS hiccup degrades a sort order instead of crashing the hook."""
    try:
        return path.stat().st_mtime
    except Exception:
        return 0.0


def _word_count(low: str, k: str) -> int:
    """Word-boundary occurrence count of keyword k in already-lowercased text low.
    Plain substring counting (the old behaviour) scored false hits inside unrelated
    words ("note" inside "annotate"/"denote"/"notebook"), inflating both the TF
    term and the coverage gate that decides whether a file gets auto-injected.

    Falls back to a stem match for inflected languages. Czech (and Slavic
    languages generally) decline nouns heavily, so an exact word-boundary match
    silently failed on the most natural way to ask a question: "co jsme dělali
    s tím videem" never matched a note about "video", and the hook injected
    nothing at all. Only applies to words long enough for a trimmed stem to stay
    specific, and only when the exact match found nothing, so English matching is
    unchanged and short words cannot start matching everything.
    """
    exact = len(re.findall(rf"\b{re.escape(k)}\b", low))
    if exact or len(k) < 5:
        return exact
    stem = k[:-2] if len(k) >= 6 else k[:-1]
    if len(stem) < 4:
        return exact
    # allow up to 4 trailing chars: video/videa/videem/videích, práce/pracovat…
    return len(re.findall(rf"\b{re.escape(stem)}\w{{0,4}}\b", low))


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
        c = _word_count(low, k)
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
            (m.start(), k)
            for k in keywords
            for m in [re.search(rf"\b{re.escape(k)}\b", low)]
            if m
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


def grep_memory(mem_dir: Path, keywords: set[str], max_files: int | None = None, inject: bool = False) -> list[Path]:
    """Search all notes. Deduplicate full clean contents, never shared template headers."""
    if not mem_dir.exists() or not keywords:
        return []
    results=[]
    for md in mem_dir.rglob("*.md"):
        if is_noise_file(md) or is_superseded(md): continue
        score,present=score_file_detail(md,keywords)
        if score > 0: results.append((score,_safe_mtime(md),str(md),md))
    results.sort(reverse=True)
    out=[]; seen=set()
    for _,_,_,md in results:
        fp=_prose_fingerprint(md)
        if fp and fp in seen: continue
        if fp:seen.add(fp)
        out.append(md)
        if max_files is not None and len(out)>=max_files:break
    return out


def extract_snippet(path: Path, keywords: set[str], max_chars: int | None = None) -> str:
    """Return complete clean notes by default; explicit excerpts use scored paragraphs."""
    try: text=path.read_text(encoding="utf-8",errors="replace")
    except OSError:return ""
    text="\n".join(line for line in text.splitlines() if not is_noise_line(line)).strip()
    if max_chars is None or len(text)<=max_chars:return text
    paragraphs=re.split(r"\n\s*\n",text)
    ranked=sorted(range(len(paragraphs)),key=lambda i:(sum(_word_count(paragraphs[i].lower(),k) for k in keywords),-i),reverse=True)
    selected=[];used=0
    for i in ranked:
        block=paragraphs[i]
        if used+len(block)+2<=max_chars:
            selected.append(i);used+=len(block)+2
    body="\n\n".join(paragraphs[i] for i in sorted(selected))
    return body+f"\n\n[PARTIAL excerpt; read complete source: {path}]"


def latest_session_note(mem_dir: Path, session_id: str | None = None) -> Path | None:
    """Most recent REAL session note in memory/sessions/ — excludes transcript-noise
    dumps so a fresh auto-compact garbage file can never hijack the SessionStart slot.
    Returns None if only dumps exist."""
    sess_dir = mem_dir / "sessions"
    if not sess_dir.exists():
        return None
    candidates = [p for p in sess_dir.rglob("*.md") if not is_noise_file(p) and not is_superseded(p)]
    if not candidates:
        return None
    if session_id:
        own = []
        for candidate in candidates:
            try:
                if f"Session: {session_id}" in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
                    own.append(candidate)
            except OSError:
                continue
        if own:
            candidates = own
    candidates.sort(key=_safe_mtime, reverse=True)
    return candidates[0]


def memory_index(mem_dir: Path, max_chars: int | None = None, max_line: int | None = None) -> str | None:
    """Return the complete navigation index; any requested excerpt is explicitly labeled."""
    idx=mem_dir / "MEMORY.md"
    try:text=idx.read_text(encoding="utf-8",errors="replace")
    except OSError:return None
    if max_chars is not None and len(text)>max_chars:
        return text[:max_chars]+f"\n[PARTIAL index; complete source: {idx}]"
    return text


def format_budget(text: str, max_chars: int) -> str:
    """Hard-clip to budget with a tail marker."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 15].rstrip() + "\n[...truncated]"


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def write_session_summary(mem_dir: Path, title: str, body: str) -> Path:
    """Append a session note under memory/sessions/. Filename includes seconds,
    a PID component, and a short random suffix so two Claude Code windows on the
    same project — or even two rapid calls in the same process/second — can never
    collide and silently overwrite each other's snapshot (minute-only stamps used
    to). Writes LF line endings explicitly (not the OS default) so the git-tracked
    memory-vault mirror doesn't accumulate CRLF diffs."""
    sess_dir = mem_dir / "sessions"
    sess_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    safe_title = re.sub(r"[^A-Za-z0-9._-]+", "-", title)[:40] or "session"
    unique = f"{os.getpid() % 10000:04d}-{os.urandom(3).hex()}"
    path = sess_dir / f"{stamp}-{unique}-{safe_title}.md"
    path.write_text(body, encoding="utf-8", newline="\n")
    return path


_RE_RESUME_NAME = re.compile(r"-resume-(auto|manual)\.md$")


def prune_old_resume_notes(mem_dir: Path, keep_newest: int = RESUME_NOTE_KEEP) -> int:
    """Move old PreCompact-generated resume snapshots out of the hot scan path
    once a project accumulates more than keep_newest — write_session_summary()
    only ever appends, so without this a long-lived project accumulates one
    file per compaction forever. NEVER deletes anything: archived to
    <project>/memory-archive/sessions/, a sibling directory outside memory/ so
    grep_memory's rglob never re-scans it (bounding per-turn cost) while the
    content stays fully on disk, git-history-recoverable, and trivially
    restorable by moving it back. Matches ONLY the auto-generated
    `*-resume-(auto|manual).md` naming pattern; hand-written session notes never
    match and are never touched. Fully fail-silent; returns the count archived
    (0 on any error, including 'nothing to prune')."""
    try:
        sess_dir = mem_dir / "sessions"
        if not sess_dir.exists():
            return 0
        notes = [p for p in sess_dir.glob("*.md") if _RE_RESUME_NAME.search(p.name)]
        if len(notes) <= keep_newest:
            return 0
        notes.sort(key=_safe_mtime, reverse=True)
        archive_dir = mem_dir.parent / "memory-archive" / "sessions"
        moved = 0
        for p in notes[keep_newest:]:
            try:
                archive_dir.mkdir(parents=True, exist_ok=True)
                dest = archive_dir / p.name
                if dest.exists():  # never clobber; leave it where it is
                    continue
                shutil.move(str(p), str(dest))
                moved += 1
            except Exception:
                pass
        return moved
    except Exception:
        return 0


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


def clear_seen(session_id: str | None) -> None:
    """Drop this session's inject ledger.

    MUST be called on compaction. The ledger's whole premise is "already in the
    context window, re-injecting adds nothing" — compaction destroys that window,
    so a surviving ledger permanently suppresses memory that is no longer present.
    That silently degraded long sessions into amnesia: the model kept working
    without the project facts it had been given hours earlier. Fail-silent.
    """
    if not session_id:
        return
    try:
        _ledger_path(session_id).unlink(missing_ok=True)
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
        for pattern in ("*.json", "*.flag"):
            for f in d.glob(pattern):
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


_RE_SUPERSEDED = re.compile(r"^superseded_by:\s*\S", re.M)


def is_superseded(path: Path) -> bool:
    """Temporal governance: a note whose frontmatter carries a non-empty
    `superseded_by:` is a CLOSED fact — kept on disk for audit, but never
    recalled/injected again (stale advice must not resurface as live)."""
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            head = f.read(600)
    except Exception:
        return False
    return head.lstrip().startswith("---") and bool(_RE_SUPERSEDED.search(head))


def _prose_fingerprint(path: Path) -> str:
    """Content identity across the entire clean note; different facts cannot collapse."""
    try:text=path.read_text(encoding="utf-8",errors="replace")
    except OSError:return ""
    if text.startswith("---"):
        match=re.match(r"^---\s*\n.*?\n---\s*\n",text,re.S)
        if match:text=text[match.end():]
    body="\n".join(line.rstrip() for line in text.splitlines() if not is_noise_line(line)).strip()
    return hashlib.sha256(body.encode("utf-8")).hexdigest() if body else ""


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
    """Keep complete user constraints and actual assistant reports, in any language.

    This is an evidence checkpoint, not an assertion that every reported result is verified.
    Native summaries carry earlier state. Raw image/JSON payloads and secrets stay excluded.
    """
    users=[]; reports=[]; files=[]; cmds=[]; summaries=[]
    def add(target,value):
        if value and value not in target:target.append(value)
    for r in records:
        kind=r.get("kind")
        if kind == "tool_use":
            inp=r.get("input") or {}
            for path in inp.get("paths",[]):add(files,path)
            add(files,inp.get("file_path") or inp.get("notebook_path"))
            if r.get("name") in ("Bash","PowerShell","exec_command"):
                command=inp.get("command") or inp.get("cmd") or ""
                if command and not scan_secrets(command):add(cmds,command)
        elif kind == "summary":
            add(summaries,_strip_noise_prose(r.get("text","")))
        elif kind == "text":
            text=r.get("text","")
            if not isinstance(text,str):continue
            text="\n".join(line for line in text.splitlines() if not is_noise_line(line)).strip()
            if not text or _looks_binary(text) or text.startswith(("<external_","# AGENTS.md instructions","[Request interrupted")):continue
            if r.get("role")=="user":add(users,text)
            elif r.get("role")=="assistant":add(reports,text)
    sections=[("Previous native context summary",summaries),
              ("User requests and constraints (chronological)",users),
              ("Assistant reports (verify against artifacts)",reports),
              ("Files touched",files),("Commands run",cmds)]
    return "\n\n".join("### "+title+"\n"+"\n\n".join("- "+item for item in items) for title,items in sections if items)


# ══════════════════════════════════════════════════════════════════════════
# Explicit memory-vault synchronization; no model or output-style policy
# ══════════════════════════════════════════════════════════════════════════

VAULT_DIR = Path(
    os.environ.get("MEGAMIND_VAULT_DIR") or (Path.home() / "Documents" / "GitHub" / "memory-vault")
)
SYNC_DEBOUNCE_SEC = int(os.environ.get("MEGAMIND_SYNC_DEBOUNCE") or 900)
# Default OFF: vault.sync() calls git directly (bypassing Claude's pre-commit secret
# hook) and the vault repo is public — opt in only after accepting the inline scan.
AUTOSYNC_ON = os.environ.get("MEGAMIND_AUTOSYNC", "0") == "1"

_SECRET_RE = re.compile(
    r"(sk-ant-[A-Za-z0-9_-]{20,}"          # Anthropic API keys (checked before generic sk-)
    r"|sk-[A-Za-z0-9]{16,}"                 # OpenAI-style
    r"|sk_(?:live|test)_[A-Za-z0-9]{16,}"   # Stripe secret/restricted keys
    r"|rk_(?:live|test)_[A-Za-z0-9]{16,}"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|AKIA[0-9A-Z]{12,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|AIza[0-9A-Za-z_\-]{20,}"
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"  # JWT
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)


def scan_secrets(text: str) -> bool:
    """True if the text appears to contain a credential (best-effort, stdlib regex)."""
    return bool(_SECRET_RE.search(text or ""))


def git_quiet(args: list[str], cwd: Path, timeout: int = 10) -> tuple[int, str]:
    """Run a git command; never raises. Returns (returncode, combined stdout+stderr).
    Decodes as UTF-8 (git emits UTF-8 for diffs of UTF-8 files) with errors='replace' —
    NOT the Windows locale (cp1252), which crashed on Czech/emoji memory content and could
    make the secret-scan (which reads this diff) run on garbage / bypass. errors='replace'
    keeps secret patterns intact (they're ASCII) while never raising on odd bytes."""
    try:
        p = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as exc:
        return 1, str(exc)

# Preserve the review branch independent manual CLI APIs. No automatic recall reduction.

STATS_FILE = ".megamind-stats.json"
TOKENS_SAVED_PER_SESSION_START = 1200
TOKENS_SAVED_PER_PROMPT_HIT = 500
TOKENS_SAVED_PER_COMPACT = 800
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
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
    if scan_secrets(text):
        raise ValueError("Secret-looking memory text rejected")
    idx = mem_dir / "MEMORY.md"
    existing = idx.read_text(encoding="utf-8", errors="strict") if idx.exists() else ""
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
    lines = idx.read_text(encoding="utf-8", errors="strict").splitlines(keepends=True)
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
    # Historical compatibility heuristic only; not measured savings or a routing signal.
    s = stats.get("session_start", 0) * TOKENS_SAVED_PER_SESSION_START
    s += stats.get("prompt_hit", 0) * TOKENS_SAVED_PER_PROMPT_HIT
    s += stats.get("compact", 0) * TOKENS_SAVED_PER_COMPACT
    return s

def list_templates() -> list[str]:
    if not TEMPLATES_DIR.exists():
        return []
    return sorted(p.name for p in TEMPLATES_DIR.iterdir() if p.is_dir())

def copy_template(name: str, mem_dir: Path) -> int:
    """
    Copy all files from templates/<name>/ into mem_dir. Does not overwrite
    existing files. Returns number of files created.
    """
    src = (TEMPLATES_DIR / name).resolve()
    if not src.is_relative_to(TEMPLATES_DIR.resolve()):
        raise FileNotFoundError("Template must stay inside the template directory")
    if not src.exists() or not src.is_dir():
        raise FileNotFoundError(f"no such template: {name}")
    created = 0
    for entry in src.rglob("*"):
        if entry.is_dir():
            continue
        rel = entry.relative_to(src)
        dst = mem_dir / rel
        if not dst.resolve().is_relative_to(mem_dir.resolve()):
            raise ValueError("Template destination escaped memory directory")
        if dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(entry.read_bytes())
        created += 1
    return created
_scan_secret_text = scan_secrets

def scan_secrets(value):
    """Keep text safety checks and the review branch's read-only directory audit."""
    if not isinstance(value, Path):
        return _scan_secret_text(value)
    patterns = [('stripe-live', re.compile(r'sk' + r'_live_[A-Za-z0-9]{16,}')),
                ('anthropic', re.compile(r'sk' + r'-ant-[A-Za-z0-9_-]{16,}')),
                ('openai', re.compile(r'sk' + r'-(?!ant-)[A-Za-z0-9_-]{16,}'))]
    hits = []
    for path in value.rglob('*.md'):
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            for name, pattern in patterns:
                if pattern.search(line):
                    hits.append((path, name, number, '[redacted]'))
    return hits
