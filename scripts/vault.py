#!/usr/bin/env python3
"""
MegaMind vault sync — mirror project memory into the memory-vault git repo.

SAFETY: vault.sync() runs git DIRECTLY (it does not go through Claude's Bash
tool), so it bypasses the pre-commit-secrets.sh hook. Your memory-vault repo may be public,
and hand-written notes can contain keys/PII. Therefore:
  • Auto-sync is OFF unless MEGAMIND_AUTOSYNC=1 (or --force on the CLI).
  • Every push is debounced (≥15 min) and every git call is timeboxed.
  • A stdlib secret scan runs over the staged diff and ABORTS the commit on a hit.

Zero external deps (stdlib + git CLI). Usage:
    python vault.py sync [--force]    # mirror + commit + push (gated/debounced)
    python vault.py mirror            # copy memory → vault working tree only
    python vault.py prune             # drop transcript-noise dumps from index + disk
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import (
    AUTOSYNC_ON,
    PROJECTS_ROOT,
    SYNC_DEBOUNCE_SEC,
    VAULT_DIR,
    git_quiet,
    is_noise_file,
    log_err,
    now_iso,
    project_slug_from_cwd,
    scan_secrets,
)

SKIP_NAMES = {".last-active", ".megamind-stats.json", ".megamind-last-sync"}


def _sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
        return ""


def mirror_project_memory(slug: str) -> int:
    """Copy <projects>/<slug>/memory/**/*.md → <vault>/<slug>/memory/, content-deduped.
    Skips transcript-noise dumps and bookkeeping files. Returns files written."""
    src = PROJECTS_ROOT / slug / "memory"
    if not src.exists():
        return 0
    dst_root = VAULT_DIR / slug / "memory"
    written = 0
    for md in src.rglob("*.md"):
        if md.name in SKIP_NAMES or is_noise_file(md):
            continue
        rel = md.relative_to(src)
        dst = dst_root / rel
        if dst.exists() and _sha(dst) == _sha(md):
            continue  # unchanged — no churn
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            dst.write_bytes(md.read_bytes())
            written += 1
        except Exception as exc:
            log_err(f"vault mirror: {rel}: {exc}")
    return written


def _debounced() -> bool:
    """True if we synced within SYNC_DEBOUNCE_SEC (skip this run)."""
    stamp = VAULT_DIR / ".megamind-last-sync"
    try:
        if stamp.exists():
            import time

            if time.time() - stamp.stat().st_mtime < SYNC_DEBOUNCE_SEC:
                return True
    except Exception:
        pass
    return False


def _touch_stamp() -> None:
    try:
        (VAULT_DIR / ".megamind-last-sync").write_text(now_iso(), encoding="utf-8")
    except Exception:
        pass


def sync(slug: str, force: bool = False) -> str:
    """Mirror + commit + push, gated by AUTOSYNC + debounce + secret scan."""
    if not (AUTOSYNC_ON or force):
        return "skip: MEGAMIND_AUTOSYNC!=1 (use --force to override)"
    if not VAULT_DIR.exists():
        return f"skip: vault dir not found ({VAULT_DIR})"
    if not force and _debounced():
        return "skip: debounced"

    mirror_project_memory(slug)
    git_quiet(["add", "-A"], VAULT_DIR, timeout=15)

    rc, _ = git_quiet(["diff", "--cached", "--quiet"], VAULT_DIR, timeout=10)
    if rc == 0:
        _touch_stamp()
        return "nothing to sync"

    # Secret gate over the staged diff (git path bypasses the Bash pre-commit hook).
    _, diff = git_quiet(["diff", "--cached"], VAULT_DIR, timeout=10)
    if scan_secrets(diff):
        git_quiet(["reset"], VAULT_DIR, timeout=10)
        log_err("vault sync ABORTED: a secret-looking token was found in the staged diff.")
        return "ABORT: secret detected in staged memory — not committed"

    git_quiet(["commit", "-m", f"[megamind] auto-sync {slug} {now_iso()}"], VAULT_DIR, timeout=10)
    prc, pout = git_quiet(["push"], VAULT_DIR, timeout=20)
    _touch_stamp()
    return "synced + pushed" if prc == 0 else f"committed; push failed: {pout.strip()[:120]}"


def prune() -> str:
    """Remove transcript-noise dumps from the vault index + disk AND local projects."""
    pat = re.compile(r"compact-(auto|manual)")
    removed = 0
    # Vault working tree
    if VAULT_DIR.exists():
        for md in VAULT_DIR.rglob("*.md"):
            if md.name.startswith("_compact-") or pat.search(md.name):
                git_quiet(["rm", "--cached", "--ignore-unmatch", str(md)], VAULT_DIR, timeout=10)
                try:
                    md.unlink()
                    removed += 1
                except Exception:
                    pass
        git_quiet(["commit", "-m", "[megamind] prune transcript noise"], VAULT_DIR, timeout=10)
    # Local project memory copies
    if PROJECTS_ROOT.exists():
        for md in PROJECTS_ROOT.rglob("*.md"):
            if md.name.startswith("_compact-") or pat.search(md.name):
                try:
                    md.unlink()
                    removed += 1
                except Exception:
                    pass
    return f"pruned {removed} noise file(s)"


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    slug = project_slug_from_cwd(os.getcwd()) or ""
    if cmd == "sync":
        print(sync(slug, force="--force" in argv))
        return 0
    if cmd == "mirror":
        print(f"mirrored {mirror_project_memory(slug)} file(s) → {VAULT_DIR / slug / 'memory'}")
        return 0
    if cmd == "prune":
        print(prune())
        return 0
    print(__doc__.strip())
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
