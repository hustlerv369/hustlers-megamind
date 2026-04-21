"""
MegaMind sync — optional Git-backed memory vault.

Makes your ~/.claude/projects/*/memory/ folders portable across machines:
laptop, work computer, dev box via Dispatch, anywhere git is available.

Design:
  - Vault root = ~/.claude/projects/ (the standard Claude Code layout).
  - .gitignore whitelists only `<slug>/memory/` paths — stats, logs, and
    any other Claude Code per-project artifacts are never committed.
  - Zero new deps: shells out to the system `git` binary.
  - All operations are no-ops if git isn't installed or vault isn't
    initialized — sync is strictly opt-in.
"""
from __future__ import annotations

import subprocess
import time
from datetime import datetime
from pathlib import Path

from lib import CLAUDE_HOME, PROJECTS_ROOT

VAULT_ROOT = PROJECTS_ROOT
AUTOSYNC_FLAG = CLAUDE_HOME / ".megamind-autosync"
AUTOSYNC_LAST = CLAUDE_HOME / ".megamind-autosync-last"
AUTOSYNC_INTERVAL_SEC = 600  # rate-limit auto-commits to once per 10 min

# Only track memory/ subdirs — never settings.json, stats, backups, etc.
GITIGNORE = """# Managed by `megamind sync init` — do not edit casually.
# Ignore everything, then whitelist only each project's memory/ tree.
*
!.gitignore
!*/
!*/memory/
!*/memory/**

# Never commit the stats counter — it's per-machine.
*/memory/.megamind-stats.json
"""


def run_git(*args: str, cwd: Path = VAULT_ROOT, timeout: int = 30) -> tuple[int, str]:
    """Run git, return (exit_code, combined stdout+stderr trimmed)."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except FileNotFoundError:
        return 127, "git not found — install git first"
    except subprocess.TimeoutExpired:
        return 124, "git command timed out"
    except Exception as exc:
        return 1, f"git failed: {exc}"


def is_initialized() -> bool:
    return (VAULT_ROOT / ".git").is_dir()


def sync_init(remote_url: str, branch: str = "main") -> tuple[int, str]:
    """
    Initialize a git repo at the vault root and wire up `origin` to a
    remote. Idempotent — safe to re-run to update the remote URL.
    """
    VAULT_ROOT.mkdir(parents=True, exist_ok=True)

    if not is_initialized():
        code, out = run_git("init", "-q")
        if code != 0:
            return code, out
        # Default to main (git may default to master on old installs)
        run_git("checkout", "-q", "-B", branch)

    # Drop gitignore (overwrites safely — it's declarative)
    (VAULT_ROOT / ".gitignore").write_text(GITIGNORE, encoding="utf-8")

    # Ensure remote is set / updated
    code, _ = run_git("remote", "get-url", "origin")
    if code == 0:
        run_git("remote", "set-url", "origin", remote_url)
    else:
        run_git("remote", "add", "origin", remote_url)

    return 0, f"vault initialized at {VAULT_ROOT} · remote: {remote_url}"


def sync_status() -> tuple[int, str]:
    if not is_initialized():
        return 1, "vault not initialized — run `sync init <remote-url>` first"
    return run_git("status", "--short")


def sync_push(message: str | None = None) -> tuple[int, str]:
    """Stage all memory changes, commit if any, push to origin."""
    if not is_initialized():
        return 1, "vault not initialized — run `sync init <remote-url>` first"

    run_git("add", "--all")
    code, out = run_git("diff", "--cached", "--quiet")
    # `git diff --cached --quiet` returns 1 when there ARE staged changes
    if code == 0:
        return 0, "no changes to push"

    msg = message or f"megamind sync {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    code, out = run_git("commit", "-m", msg)
    if code != 0:
        return code, out

    code, push_out = run_git("push", "-u", "origin", "HEAD")
    return code, push_out


def sync_pull() -> tuple[int, str]:
    if not is_initialized():
        return 1, "vault not initialized — run `sync init <remote-url>` first"
    return run_git("pull", "--rebase", "--autostash")


def autosync_enable() -> None:
    CLAUDE_HOME.mkdir(parents=True, exist_ok=True)
    AUTOSYNC_FLAG.write_text(datetime.now().isoformat(), encoding="utf-8")


def autosync_disable() -> None:
    try:
        AUTOSYNC_FLAG.unlink()
    except FileNotFoundError:
        pass


def autosync_is_enabled() -> bool:
    return AUTOSYNC_FLAG.exists()


def autosync_tick_if_due() -> tuple[bool, str]:
    """
    Called by the Stop hook. If autosync is on AND enough time has
    passed since last commit, run sync_push silently. Returns
    (did_run, message). Never raises.
    """
    if not autosync_is_enabled():
        return False, "autosync off"
    if not is_initialized():
        return False, "vault not initialized"

    # Rate-limit — avoid spam commits while user iterates fast.
    try:
        last_ts = float(AUTOSYNC_LAST.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError, OSError):
        last_ts = 0.0
    now = time.time()
    if now - last_ts < AUTOSYNC_INTERVAL_SEC:
        return False, f"too soon ({int(now - last_ts)}s < {AUTOSYNC_INTERVAL_SEC}s)"

    try:
        AUTOSYNC_LAST.write_text(str(now), encoding="utf-8")
    except OSError:
        pass

    code, out = sync_push()
    return (code == 0), out


# ────────────────────────────────────────────────────────────────────
# Auto-pull — called from SessionStart so memory is always fresh.
# Rate-limited separately so we don't hit origin every single session.
# ────────────────────────────────────────────────────────────────────

AUTOPULL_LAST = CLAUDE_HOME / ".megamind-autopull-last"
AUTOPULL_INTERVAL_SEC = 300  # refresh at most every 5 min


def autopull_if_due() -> tuple[bool, str]:
    """
    Called by SessionStart. If autosync is on, pull from origin so this
    session sees changes made on other devices. Rate-limited, silent on
    any failure (offline, auth prompt, conflict — all safe to skip).
    """
    if not autosync_is_enabled():
        return False, "autosync off"
    if not is_initialized():
        return False, "vault not initialized"
    try:
        last_ts = float(AUTOPULL_LAST.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError, OSError):
        last_ts = 0.0
    now = time.time()
    if now - last_ts < AUTOPULL_INTERVAL_SEC:
        return False, f"too soon"
    try:
        AUTOPULL_LAST.write_text(str(now), encoding="utf-8")
    except OSError:
        pass
    # Short timeout — if the network is slow or prompts for auth, bail fast.
    code, out = run_git("pull", "--rebase", "--autostash", "--quiet", timeout=8)
    return (code == 0), out


# ────────────────────────────────────────────────────────────────────
# Fully-automated one-command setup via `gh` CLI if available.
# ────────────────────────────────────────────────────────────────────

def _run_cmd(cmd: list[str], timeout: int = 30) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except FileNotFoundError:
        return 127, f"{cmd[0]} not found"
    except Exception as exc:
        return 1, str(exc)


def has_gh_cli() -> bool:
    code, _ = _run_cmd(["gh", "--version"], timeout=5)
    return code == 0


def gh_is_authed() -> bool:
    code, _ = _run_cmd(["gh", "auth", "status"], timeout=5)
    return code == 0


def auto_setup(repo_name: str = "memory-vault", private: bool = True) -> tuple[int, str]:
    """
    Fully automated setup: create private GitHub repo via `gh`, link it
    as the vault remote, first push, enable autosync. Returns (code, msg).
    """
    if not has_gh_cli():
        return 127, (
            "gh CLI not found. Install from https://cli.github.com/ then rerun, "
            "or fall back to manual: create a private repo on GitHub, then run\n"
            "  python cli.py sync init <remote-url>"
        )
    if not gh_is_authed():
        return 1, (
            "gh is installed but not authenticated. Run `gh auth login` first, "
            "then rerun this command."
        )

    # Try to create the repo. If it already exists on the user's account,
    # we still want to link it — `gh repo view` confirms ownership.
    visibility = "--private" if private else "--public"
    code, out = _run_cmd(
        ["gh", "repo", "create", repo_name, visibility, "--confirm"],
        timeout=20,
    )
    if code != 0 and "already exists" not in out.lower() and "name already exists" not in out.lower():
        return code, f"gh repo create failed: {out}"

    # Get the remote URL for the repo (works whether we just created it or it existed)
    code, view_out = _run_cmd(
        ["gh", "repo", "view", repo_name, "--json", "sshUrl,url", "-q", ".sshUrl"],
        timeout=10,
    )
    remote_url = view_out.strip() if code == 0 and view_out.strip() else None
    if not remote_url:
        # Fallback to HTTPS if SSH isn't parseable
        code, view_out = _run_cmd(
            ["gh", "repo", "view", repo_name, "--json", "url", "-q", ".url"],
            timeout=10,
        )
        if code == 0 and view_out.strip():
            remote_url = view_out.strip() + ".git"
    if not remote_url:
        return 1, "could not determine remote URL from gh — try manual `sync init`"

    # Wire up vault
    code, msg = sync_init(remote_url)
    if code != 0:
        return code, msg

    # First push (ignore "nothing to commit" as success)
    push_code, push_msg = sync_push("megamind: initial vault sync")
    autosync_enable()

    return 0, (
        f"✅  vault live at {remote_url}\n"
        f"✅  autosync enabled (pull on session start, push after Claude responses)\n"
        f"first-push: {push_msg or '(nothing to push yet)'}"
    )
