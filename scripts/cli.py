#!/usr/bin/env python3
"""
MegaMind CLI — manual operations on project memory + lean/vault control.

Usage:
  python cli.py status               # show memory stats for current project
  python cli.py recall <query>       # search memory, print top matches
  python cli.py list                 # list all memory files
  python cli.py lean status|on|off|apply|restore
                                     # token-discipline: view/flip settings (reversible)
  python cli.py caveman status|on|off|lite|full|ultra|wenyan-*|never|always
                                     # OUTPUT-token compression: terse caveman replies
  python cli.py vault sync|mirror|prune [--force]
                                     # mirror project memory to the memory-vault repo
  python cli.py reconcile            # memory governance report: duplicates,
                                     # orphans (not in MEMORY.md), stale, superseded
  python cli.py skills audit|disable --unused|enable <name>|restore|list
                                     # lazy-load: disable unused skills so their
                                     # descriptions stop loading (~19k tok/session)
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import (
    CAVEMAN_DEFAULT_MODE,
    CAVEMAN_FLAG,
    CAVEMAN_MODES,
    CAVEMAN_OFF_FLAG,
    CLAUDE_HOME,
    caveman_active_mode,
    caveman_globally_off,
    extract_keywords,
    extract_snippet,
    find_memory_dir,
    grep_memory,
    lean_on,
    memory_index,
    normalize_caveman_mode,
    project_slug_from_cwd,
    write_caveman_flag,
)


def cmd_status() -> int:
    cwd = os.getcwd()
    slug = project_slug_from_cwd(cwd)
    mem = find_memory_dir(cwd)
    print(f"Project slug: {slug}")
    print(f"Memory dir:   {mem if mem else '(not found)'}")
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


def cmd_recall(query: str) -> int:
    cwd = os.getcwd()
    mem = find_memory_dir(cwd)
    if not mem:
        print(f"No memory dir for {cwd}", file=sys.stderr)
        return 1
    kw = extract_keywords(query)
    if not kw:
        print("(no useful keywords in query)", file=sys.stderr)
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


def cmd_list() -> int:
    cwd = os.getcwd()
    mem = find_memory_dir(cwd)
    if not mem:
        print(f"No memory dir for {cwd}", file=sys.stderr)
        return 1
    for md in sorted(mem.rglob("*.md")):
        rel = md.relative_to(mem)
        size = md.stat().st_size
        print(f"{size:>8}  {rel}")
    return 0


def cmd_lean(args: list[str]) -> int:
    action = args[0] if args else "status"
    settings_path = CLAUDE_HOME / "settings.json"
    off_flag = CLAUDE_HOME / "megamind-lean.off"
    bak = settings_path.parent / (settings_path.name + ".megamind-bak")

    if action == "status":
        model = effort = "?"
        mcp = 0
        try:
            s = json.loads(settings_path.read_text(encoding="utf-8"))
            model = s.get("model", "?")
            effort = s.get("effortLevel", "?")
            mcp = len(s.get("mcpServers") or {})
        except Exception:
            pass
        print(f"lean directive: {'ON' if lean_on() else 'OFF (megamind-lean.off present)'}")
        print(f"model:          {model}")
        print(f"effortLevel:    {effort}")
        print(f"MCP servers:    {mcp} (loaded every request)")
        if model == "opus[1m]" or effort == "xhigh":
            print("\n→ `python cli.py lean apply` would flip opus[1m]->opus and/or xhigh->high.")
        return 0

    if action == "on":
        if off_flag.exists():
            off_flag.unlink()
        print("lean directive ON (SessionStart will inject the token-discipline line).")
        return 0

    if action == "off":
        off_flag.write_text("", encoding="utf-8")
        print("lean directive OFF (created ~/.claude/megamind-lean.off).")
        return 0

    if action == "apply":
        try:
            s = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"cannot read settings.json: {exc}", file=sys.stderr)
            return 1
        shutil.copy2(settings_path, bak)
        changes = []
        if s.get("model") == "opus[1m]":
            s["model"] = "opus"
            changes.append("model: opus[1m] -> opus (200K context — stops re-sending a 1M-growing session every turn)")
        if s.get("effortLevel") == "xhigh":
            s["effortLevel"] = "high"
            changes.append("effortLevel: xhigh -> high (less reasoning per turn)")
        settings_path.write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if changes:
            print("Applied lean settings:")
            for c in changes:
                print("  • " + c)
        else:
            print("Already lean (model not opus[1m], effort not xhigh) — no change.")
        mcp = s.get("mcpServers") or {}
        if mcp:
            print(f"\nMCP servers loaded on EVERY request ({len(mcp)}): " + ", ".join(mcp.keys()))
            print("  → move rarely-used ones to a per-project .mcp.json (Apify schemas are large).")
        print("\nAlso: keep the Headroom proxy running (compresses tool output ~34%); route")
        print("routine/background tasks via claude-code-router to a free/cheap model.")
        print(f"\nBackup: {bak.name}. NOTE: model/effort apply to NEW sessions only — run /clear or restart.")
        print("Revert: python cli.py lean restore")
        return 0

    if action == "restore":
        if not bak.exists():
            print("no megamind backup found (run `lean apply` first)", file=sys.stderr)
            return 1
        shutil.copy2(bak, settings_path)
        print("settings.json restored from megamind backup (new sessions only).")
        return 0

    print("usage: lean status|on|off|apply|restore")
    return 1


def cmd_vault(args: list[str]) -> int:
    try:
        import vault
    except Exception as exc:
        print(f"vault module unavailable: {exc}", file=sys.stderr)
        return 1
    sub = args[0] if args else ""
    slug = project_slug_from_cwd(os.getcwd()) or ""
    if sub == "sync":
        print(vault.sync(slug, force="--force" in args))
        return 0
    if sub == "mirror":
        print(f"mirrored {vault.mirror_project_memory(slug)} file(s) → {vault.VAULT_DIR / slug / 'memory'}")
        return 0
    if sub == "prune":
        print(vault.prune())
        return 0
    print("usage: vault sync|mirror|prune [--force]")
    return 1


def cmd_reconcile() -> int:
    """Memory governance (deterministic, žádný LLM): najdi duplicity, sirotky mimo
    index, stale kandidáty a superseded poznámky. NIC nemaže — report pro
    rozhodnutí (Claude/uživatel označí `superseded_by:` ve frontmatter)."""
    import time as _time

    from lib import _prose_fingerprint, is_noise_file, is_superseded

    cwd = os.getcwd()
    mem = find_memory_dir(cwd)
    if not mem:
        print(f"No memory dir for {cwd}", file=sys.stderr)
        return 1
    notes = [p for p in mem.rglob("*.md") if p.name != "MEMORY.md" and not is_noise_file(p)]
    idx_text = ""
    try:
        idx_text = (mem / "MEMORY.md").read_text(encoding="utf-8", errors="ignore")
    except Exception:
        pass

    superseded = [p for p in notes if is_superseded(p)]
    live = [p for p in notes if p not in superseded]

    # 1) duplicity podle prose fingerprintu (stejné první 3 řádky prózy)
    groups: dict[str, list] = {}
    for p in live:
        fp = _prose_fingerprint(p)
        if fp:
            groups.setdefault(fp, []).append(p)
    dupes = {fp: ps for fp, ps in groups.items() if len(ps) > 1}

    # 2) sirotci: top-level poznámky (mimo sessions/), na které index neodkazuje
    orphans = [
        p for p in live
        if p.parent == mem and p.name not in idx_text
    ]

    # 3) stale kandidáti: >90 dní nedotčené top-level poznámky
    cut = _time.time() - 90 * 86400
    stale = [p for p in live if p.parent == mem and p.stat().st_mtime < cut]

    print(f"Memory reconcile — {mem}")
    print(f"  poznámek: {len(notes)} (live {len(live)}, superseded {len(superseded)})")
    if dupes:
        print(f"\n⚠️ DUPLICITY ({len(dupes)} skupin) — slouč / označ superseded_by:")
        for ps in dupes.values():
            print("   • " + "  ×  ".join(str(x.relative_to(mem)) for x in ps))
    if orphans:
        print(f"\n⚠️ SIROTCI mimo MEMORY.md index ({len(orphans)}) — přidej řádek do indexu, nebo smaž:")
        for p in orphans:
            print(f"   • {p.name}")
    if stale:
        print(f"\nℹ️ STALE >90 dní ({len(stale)}) — zvaž superseded_by / aktualizaci:")
        for p in stale:
            age = int((_time.time() - p.stat().st_mtime) / 86400)
            print(f"   • {p.name}  ({age} dní)")
    if superseded:
        print(f"\n📁 superseded (archiv, z recall vyfiltrováno): "
              + ", ".join(p.name for p in superseded))
    if not (dupes or orphans or stale):
        print("\n✅ čisto — žádné duplicity, sirotci ani stale kandidáti.")
    print("\nJak uzavřít fakt: do frontmatter přidej `superseded_by: <name-nové-poznámky>`"
          "\n— zůstane na disku (audit), ale recall/inject ho už nikdy nevytáhne.")
    return 0


def cmd_caveman(args: list[str]) -> int:
    action = (args[0] if args else "status").lower()

    if action == "status":
        if caveman_globally_off():
            print("caveman:   DISABLED globally (megamind-caveman.off present)")
            print("           re-enable → python cli.py caveman always")
            return 0
        mode = caveman_active_mode()
        print(f"caveman:   {'ON — level ' + mode if mode else 'off (this session only)'}")
        print(f"default:   {CAVEMAN_DEFAULT_MODE}  (always-on; 'off' never persists across sessions)")
        print(f"levels:    {', '.join(CAVEMAN_MODES)}")
        print(f"flag:      {CAVEMAN_FLAG}")
        return 0

    if action == "never":      # permanent global kill switch
        try:
            CAVEMAN_OFF_FLAG.write_text("", encoding="utf-8")
        except Exception as exc:
            print(f"cannot write kill switch: {exc}", file=sys.stderr)
            return 1
        print("caveman DISABLED globally (created megamind-caveman.off). Affects NEW sessions.")
        return 0

    if action == "always":     # remove kill switch + re-arm default
        if CAVEMAN_OFF_FLAG.exists():
            CAVEMAN_OFF_FLAG.unlink()
        write_caveman_flag(CAVEMAN_DEFAULT_MODE)
        print(f"caveman always-on re-enabled (default {CAVEMAN_DEFAULT_MODE}).")
        return 0

    norm = normalize_caveman_mode(action)
    if norm == "off":
        write_caveman_flag("off")
        print("caveman off for THIS session (always-on re-arms next session; `never` = permanent).")
        return 0
    if norm:
        write_caveman_flag(norm)
        print(f"caveman level → {norm} (applies to your next message / new sessions).")
        return 0

    print("usage: caveman status|on|off|lite|full|ultra|wenyan-lite|wenyan-full|wenyan-ultra|never|always")
    return 1


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip())
        return 1
    cmd = argv[1]
    if cmd == "status":
        return cmd_status()
    if cmd == "recall":
        return cmd_recall(" ".join(argv[2:]))
    if cmd == "list":
        return cmd_list()
    if cmd == "lean":
        return cmd_lean(argv[2:])
    if cmd == "caveman":
        return cmd_caveman(argv[2:])
    if cmd == "vault":
        return cmd_vault(argv[2:])
    if cmd == "reconcile":
        return cmd_reconcile()
    if cmd == "skills":
        import skills
        return skills.main(["skills"] + argv[2:])
    print(f"Unknown command: {cmd}")
    print(__doc__.strip())
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
