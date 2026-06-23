#!/usr/bin/env python3
"""
MegaMind skills — lazy-load manager (the biggest per-session token saver).

Claude Code loads EVERY personal skill's `description` into context at session
start so it can match them — even skills you never use this project. With ~175
skills that's ~19k tokens burned every single session before you type anything.

This disables unused skills by MOVING them out of the scanned path
(~/.claude/skills/<name>  →  ~/.claude/skills-disabled/<name>), so their
descriptions stop loading. Re-enable any of them in one command (effective next
session — skills are read at startup). Core daily-drivers and anything wired
into hooks/settings are protected and never disabled.

Usage:
  python skills.py audit [days]            # show cost + disable candidates (unused > days)
  python skills.py disable --unused [days] # disable everything unused > days (default 30)
  python skills.py disable <name...>       # disable specific skills
  python skills.py enable <name...>        # re-enable (effective next session)
  python skills.py restore                 # re-enable ALL disabled skills
  python skills.py list                    # list currently disabled skills
"""
from __future__ import annotations

import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import CLAUDE_HOME, PROJECTS_ROOT

SKILLS_DIR = CLAUDE_HOME / "skills"
# Disabled skills relocate alongside the REAL skills dir (following the symlink),
# so on a setup where ~/.claude/skills → a config repo, disabled skills stay IN
# that repo (preserved + synced, just out of the scanned path) instead of looking
# like 142 deletions.
DISABLED_DIR = SKILLS_DIR.resolve().parent / "skills-disabled"

# megamind itself must NEVER be disabled (its hooks would break). Everything else
# is opt-in via ~/.claude/megamind-keep.txt (one skill name per line, '#' comments).
# _settings_referenced() already auto-protects any skill wired into settings.json.
KEEP_FILE = CLAUDE_HOME / "megamind-keep.txt"


def _user_keep() -> set[str]:
    try:
        return {
            ln.strip()
            for ln in KEEP_FILE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        }
    except Exception:
        return set()


PROTECT = {"megamind"} | _user_keep()

SCAN_FILE_CAP = 300          # most-recent transcripts to scan for usage
RECENT_WINDOW_DAYS = 120     # ignore transcripts older than this for the usage signal


def _desc_chars(skill_md: Path) -> int:
    try:
        t = skill_md.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return 0
    m = re.match(r"^---\s*\n(.*?)\n---", t, re.S)
    if not m:
        return 0
    dm = re.search(r"(?m)^description:\s*(.*(?:\n(?!\w+:).*)*)", m.group(1))
    return len(dm.group(1)) if dm else 0


def _all_skills(base: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    if not base.exists():
        return out
    for d in sorted(base.iterdir()):
        if d.is_dir() and (d / "SKILL.md").exists():
            out[d.name] = _desc_chars(d / "SKILL.md")
    return out


def _settings_referenced() -> set[str]:
    refs: set[str] = set()
    try:
        s = (CLAUDE_HOME / "settings.json").read_text(encoding="utf-8")
        for m in re.finditer(r"/skills/([A-Za-z0-9_.-]+)/", s):
            refs.add(m.group(1))
    except Exception:
        pass
    return refs


def _last_used(names: list[str]) -> dict[str, float]:
    """skill -> last-used epoch (transcript mtime proxy). Scans the most-recent
    transcripts newest-first and stops once every skill is dated."""
    last = {n: 0.0 for n in names}
    if not PROJECTS_ROOT.exists():
        return last
    cutoff = time.time() - RECENT_WINDOW_DAYS * 86400
    files = []
    for f in PROJECTS_ROOT.rglob("*.jsonl"):
        try:
            mt = f.stat().st_mtime
            if mt >= cutoff:
                files.append((mt, f))
        except Exception:
            pass
    files.sort(reverse=True)
    files = files[:SCAN_FILE_CAP]
    remaining = set(names)
    for mt, f in files:
        if not remaining:
            break
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        found = {n for n in remaining if (f"/skills/{n}/" in text or f'"/{n}"' in text or f"/{n} " in text)}
        for n in found:
            if last[n] < mt:
                last[n] = mt
        remaining -= found
    return last


def audit(days: int = 30, quiet: bool = False) -> list[str]:
    enabled = _all_skills(SKILLS_DIR)
    disabled = _all_skills(DISABLED_DIR)
    refs = _settings_referenced()
    last = _last_used(list(enabled))
    cutoff = time.time() - days * 86400
    keep, cand = [], []
    for n, c in enabled.items():
        if n in PROTECT or n in refs or last.get(n, 0) >= cutoff:
            keep.append((c, n))
        else:
            cand.append((c, n))
    cand.sort(reverse=True)
    tot = sum(enabled.values())
    save = sum(c for c, _ in cand)
    if not quiet:
        print(f"Personal skills: {len(enabled)} enabled, {len(disabled)} already disabled")
        print(f"Description tokens loaded now: ~{tot // 4:,} / session")
        print(f"Disable candidates (unused > {days}d, not core): {len(cand)} skills ~ {save // 4:,} tokens")
        print(f"After disable: ~{(tot - save) // 4:,} tokens/session ({len(keep)} kept)")
        print("\nWould disable (top 25 by cost):")
        for c, n in cand[:25]:
            print(f"  ~{c // 4:>4} tok  {n}")
        if len(cand) > 25:
            print(f"  ... +{len(cand) - 25} more")
    return [n for _, n in cand]


def disable(names: list[str]) -> list[str]:
    DISABLED_DIR.mkdir(exist_ok=True)
    moved = []
    for n in names:
        if n in PROTECT:
            continue
        src, dst = SKILLS_DIR / n, DISABLED_DIR / n
        if src.exists() and not dst.exists():
            try:
                shutil.move(str(src), str(dst))
                moved.append(n)
            except Exception as e:
                print(f"  skip {n}: {e}")
    return moved


def disable_unused(days: int = 30) -> list[str]:
    cand = audit(days)
    moved = disable(cand)
    print(f"\n✅ Disabled {len(moved)} skills → {DISABLED_DIR}")
    print("   Effect: NEXT session (skills load at startup). Re-enable: `/megamind skills enable <name>`")
    return moved


def enable(names: list[str]) -> list[str]:
    moved = []
    for n in names:
        src, dst = DISABLED_DIR / n, SKILLS_DIR / n
        if src.exists() and not dst.exists():
            try:
                shutil.move(str(src), str(dst))
                moved.append(n)
            except Exception as e:
                print(f"  skip {n}: {e}")
    print(f"Enabled {len(moved)}: {', '.join(moved) or '(none)'} (effective next session)")
    return moved


def restore() -> None:
    names = [d.name for d in DISABLED_DIR.iterdir() if d.is_dir()] if DISABLED_DIR.exists() else []
    if not names:
        print("nothing disabled")
        return
    enable(names)


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "audit"
    if cmd == "audit":
        audit(int(argv[2]) if len(argv) > 2 else 30)
        return 0
    if cmd == "disable":
        if len(argv) > 2 and argv[2] == "--unused":
            disable_unused(int(argv[3]) if len(argv) > 3 else 30)
        else:
            print("disabled:", ", ".join(disable(argv[2:])) or "(none)")
        return 0
    if cmd == "enable":
        enable(argv[2:])
        return 0
    if cmd == "restore":
        restore()
        return 0
    if cmd == "list":
        d = _all_skills(DISABLED_DIR)
        print(f"DISABLED ({len(d)}):", ", ".join(sorted(d)) or "(none)")
        return 0
    print(__doc__.strip())
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
