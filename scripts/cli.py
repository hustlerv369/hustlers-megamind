#!/usr/bin/env python3
"""
MegaMind CLI — manual operations on project memory.

Usage:
  python cli.py status                      show memory stats for current project
  python cli.py stats                       detailed stats + token savings estimate
  python cli.py recall <query>              search memory, print top matches
  python cli.py remember <text>             append a one-line fact to MEMORY.md
  python cli.py forget <keyword>            remove matching line(s) from MEMORY.md
  python cli.py list                        list all memory files
  python cli.py audit                       scan memory files for leaked secrets
  python cli.py init [--template <name>]    bootstrap memory (optionally from template)
  python cli.py templates                   list available templates

Cross-device sync (optional):
  python cli.py sync auto-setup             one-shot: create private GitHub repo, link, push, enable autosync (needs `gh` CLI)
  python cli.py sync init <git-remote>      manual alt: link memory to an existing private git repo
  python cli.py sync push                   push memory changes
  python cli.py sync pull                   pull memory from other machines
  python cli.py sync status                 show pending changes
  python cli.py sync auto-on | auto-off     toggle background autosync
  python cli.py sync auto-status            show autosync + vault state

Examples:
  python cli.py remember "user prefers terse Czech replies"
  python cli.py init --template nextjs-saas
  python cli.py sync init git@github.com:hustlerv369/memory-vault.git
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import (
    append_memory_line,
    copy_template,
    ensure_memory_dir,
    estimate_tokens_saved,
    extract_keywords,
    extract_snippet,
    find_memory_dir,
    forget_memory_line,
    grep_memory,
    list_templates,
    load_stats,
    memory_index,
    project_slug_from_cwd,
    scan_secrets,
)
import sync as sync_mod


# ────────────────────────────────────────────────────────────────────
# read-only inspection
# ────────────────────────────────────────────────────────────────────

def cmd_status(args) -> int:
    cwd = os.getcwd()
    slug = project_slug_from_cwd(cwd)
    mem = find_memory_dir(cwd)
    print(f"Project slug: {slug}")
    print(f"Memory dir:   {mem if mem else '(not found — run `init`)'}")
    if not mem:
        return 1
    files = list(mem.rglob("*.md"))
    total_bytes = sum(f.stat().st_size for f in files)
    print(f"Files:        {len(files)}")
    print(f"Total size:   {total_bytes:,} bytes (~{total_bytes // 4:,} tokens)")
    idx = memory_index(mem, max_chars=99999)
    if idx:
        lines = idx.count("\n") + 1
        print(f"Index:        MEMORY.md — {lines} lines")
    return 0


def cmd_stats(args) -> int:
    cwd = os.getcwd()
    mem = find_memory_dir(cwd)
    if not mem:
        print(f"No memory dir for {cwd} — run `init` first", file=sys.stderr)
        return 1
    stats = load_stats(mem)
    sess = stats.get("session_start", 0)
    prompt_hits = stats.get("prompt_hit", 0)
    prompt_misses = stats.get("prompt_miss", 0)
    compacts = stats.get("compact", 0)
    saved = estimate_tokens_saved(stats)
    last = stats.get("last_updated", "(never)")
    files = list(mem.rglob("*.md"))
    total_bytes = sum(f.stat().st_size for f in files)

    print("┌──────────────────────────────────────────────────────┐")
    print("│  🧠  MegaMind stats                                   │")
    print("├──────────────────────────────────────────────────────┤")
    print(f"│  Project: {project_slug_from_cwd(cwd) or '?':<43}│")
    print(f"│  Files in memory: {len(files):<36}│")
    print(f"│  Memory size:     {total_bytes:>6,} bytes (~{total_bytes // 4:,} tok){' ' * max(0, 18 - len(f'{total_bytes // 4:,}'))}│")
    print("├──────────────────────────────────────────────────────┤")
    print(f"│  SessionStart fires:    {sess:<28}│")
    print(f"│  UserPrompt — hit:      {prompt_hits:<28}│")
    print(f"│  UserPrompt — silent:   {prompt_misses:<28}│")
    print(f"│  PreCompact saves:      {compacts:<28}│")
    print("├──────────────────────────────────────────────────────┤")
    print(f"│  💾  Tokens saved (est): {saved:>8,} tokens         │")
    print(f"│  💰  @ $0.003/1k out:    ${saved * 0.003 / 1000:>7.2f}                │")
    print(f"│  Last updated:           {last:<26}│")
    print("└──────────────────────────────────────────────────────┘")
    return 0


def cmd_recall(args) -> int:
    cwd = os.getcwd()
    mem = find_memory_dir(cwd)
    if not mem:
        print(f"No memory dir for {cwd}", file=sys.stderr)
        return 1
    query = " ".join(args.query) if args.query else ""
    kw = extract_keywords(query)
    if not kw:
        print("(no useful keywords in query — try ≥4 char words)", file=sys.stderr)
        return 1
    matches = grep_memory(mem, kw, max_files=5)
    if not matches:
        print("(no matches)")
        return 0
    for md in matches:
        rel = md.relative_to(mem)
        snip = extract_snippet(md, kw, max_chars=400)
        print(f"\n=== {rel} ===\n{snip}")
    return 0


def cmd_list(args) -> int:
    cwd = os.getcwd()
    mem = find_memory_dir(cwd)
    if not mem:
        print(f"No memory dir for {cwd}", file=sys.stderr)
        return 1
    for md in sorted(mem.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        rel = md.relative_to(mem)
        size = md.stat().st_size
        print(f"{size:>8}  {rel}")
    return 0


# ────────────────────────────────────────────────────────────────────
# mutating commands
# ────────────────────────────────────────────────────────────────────

def cmd_remember(args) -> int:
    text = " ".join(args.text).strip()
    if not text:
        print("remember: missing text", file=sys.stderr)
        return 2
    cwd = os.getcwd()
    try:
        mem = ensure_memory_dir(cwd)
    except ValueError as e:
        print(f"remember: {e}", file=sys.stderr)
        return 1
    line = append_memory_line(mem, text, tag=args.tag)
    print(f"✅  remembered: {line.strip()}")
    return 0


def cmd_forget(args) -> int:
    keyword = " ".join(args.keyword).strip()
    if not keyword:
        print("forget: missing keyword", file=sys.stderr)
        return 2
    cwd = os.getcwd()
    mem = find_memory_dir(cwd)
    if not mem:
        print(f"No memory dir for {cwd}", file=sys.stderr)
        return 1
    removed = forget_memory_line(mem, keyword)
    if not removed:
        print(f"(no MEMORY.md lines matched '{keyword}')")
        return 0
    print(f"🗑️   forgot {len(removed)} line(s):")
    for line in removed:
        print(f"    {line.strip()}")
    return 0


def cmd_audit(args) -> int:
    cwd = os.getcwd()
    mem = find_memory_dir(cwd)
    if not mem:
        print(f"No memory dir for {cwd}", file=sys.stderr)
        return 1
    hits = scan_secrets(mem)
    if not hits:
        print("🟢  audit clean — no secret-looking patterns in memory")
        return 0
    print(f"🔴  audit — {len(hits)} potential secret pattern(s) found:\n")
    for path, pattern, line_no, snippet in hits:
        rel = path.relative_to(mem)
        print(f"  {rel}:{line_no}  [{pattern}]  {snippet}")
    print("\nReview each match. Remove from the file if it's a real secret,")
    print("then rotate the credential. Audit only flags patterns — verify context.")
    return 1


def cmd_init(args) -> int:
    cwd = os.getcwd()
    try:
        mem = ensure_memory_dir(cwd)
    except ValueError as e:
        print(f"init: {e}", file=sys.stderr)
        return 1
    print(f"✅  memory dir ready: {mem}")
    if args.template:
        try:
            n = copy_template(args.template, mem)
        except FileNotFoundError as e:
            print(f"init: {e}", file=sys.stderr)
            print(f"Available templates: {', '.join(list_templates()) or '(none)'}", file=sys.stderr)
            return 1
        print(f"✅  seeded {n} file(s) from template '{args.template}'")
    print("\nNext: open memory files, fill in the blanks. Claude will auto-load them.")
    return 0


def cmd_templates(args) -> int:
    names = list_templates()
    if not names:
        print("(no templates bundled)")
        return 0
    print("Available templates:")
    for name in names:
        print(f"  • {name}")
    return 0


# ────────────────────────────────────────────────────────────────────
# sync — git-backed memory vault
# ────────────────────────────────────────────────────────────────────

def cmd_sync(args) -> int:
    action = args.action
    if action == "init":
        if not args.remote:
            print("sync init: missing remote URL", file=sys.stderr)
            print("example: python cli.py sync init git@github.com:you/memory-vault.git", file=sys.stderr)
            return 2
        code, msg = sync_mod.sync_init(args.remote, branch=args.branch)
        print(msg)
        if code != 0:
            return code
        # Autosync on by default after init — matches "always fresh" expectation.
        if not args.no_autosync:
            sync_mod.autosync_enable()
            print("✅  autosync enabled — memory will push every ~10 min after a Claude response")
        print("\nNext: `python cli.py sync push` to do the first push.")
        return 0

    if action == "push":
        code, msg = sync_mod.sync_push(message=args.message)
        print(msg or "(no output)")
        return code

    if action == "pull":
        code, msg = sync_mod.sync_pull()
        print(msg or "(no output)")
        return code

    if action == "status":
        code, msg = sync_mod.sync_status()
        if msg:
            print(msg)
        else:
            print("(nothing pending)")
        return code

    if action == "auto-on":
        sync_mod.autosync_enable()
        print("✅  autosync enabled")
        return 0

    if action == "auto-off":
        sync_mod.autosync_disable()
        print("🔕  autosync disabled")
        return 0

    if action == "auto-status":
        state = "ON" if sync_mod.autosync_is_enabled() else "OFF"
        init = "initialized" if sync_mod.is_initialized() else "not initialized"
        print(f"autosync: {state} · vault: {init}")
        return 0

    if action == "auto-setup":
        code, msg = sync_mod.auto_setup(repo_name=args.repo_name, private=not args.public)
        print(msg)
        return code

    print(f"sync: unknown action '{action}'", file=sys.stderr)
    return 1


# ────────────────────────────────────────────────────────────────────
# arg parser
# ────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="megamind", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="show memory stats").set_defaults(func=cmd_status)
    sub.add_parser("stats", help="detailed stats + token savings").set_defaults(func=cmd_stats)
    sub.add_parser("list", help="list all memory files").set_defaults(func=cmd_list)
    sub.add_parser("audit", help="scan for leaked secrets").set_defaults(func=cmd_audit)
    sub.add_parser("templates", help="list available templates").set_defaults(func=cmd_templates)

    r = sub.add_parser("recall", help="search memory")
    r.add_argument("query", nargs="+")
    r.set_defaults(func=cmd_recall)

    rem = sub.add_parser("remember", help="append a one-line fact")
    rem.add_argument("text", nargs="+")
    rem.add_argument("--tag", default="📦", help="emoji tag (default: 📦)")
    rem.set_defaults(func=cmd_remember)

    fgt = sub.add_parser("forget", help="remove matching line(s) from MEMORY.md")
    fgt.add_argument("keyword", nargs="+")
    fgt.set_defaults(func=cmd_forget)

    ini = sub.add_parser("init", help="bootstrap memory dir")
    ini.add_argument("--template", help="seed with template (see `templates`)")
    ini.set_defaults(func=cmd_init)

    syn = sub.add_parser("sync", help="git-backed memory vault (cross-device sync)")
    syn.add_argument(
        "action",
        choices=["init", "push", "pull", "status", "auto-on", "auto-off", "auto-status", "auto-setup"],
        help="sub-action",
    )
    syn.add_argument("remote", nargs="?", help="remote URL (for `init`)")
    syn.add_argument("--branch", default="main", help="branch name (for `init`, default: main)")
    syn.add_argument("--no-autosync", action="store_true", help="don't enable autosync at init")
    syn.add_argument("-m", "--message", help="commit message (for `push`)")
    syn.add_argument("--repo-name", default="memory-vault", help="repo name for auto-setup (default: memory-vault)")
    syn.add_argument("--public", action="store_true", help="auto-setup: make repo public (default is private)")
    syn.set_defaults(func=cmd_sync)

    return p


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip())
        return 1
    parser = build_parser()
    args = parser.parse_args(argv[1:])
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
