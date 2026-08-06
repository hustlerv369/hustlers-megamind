#!/usr/bin/env bash
# Megamind — cross-platform fix for macOS / Linux.
#
# Two bugs made every hook a silent no-op on Unix:
#   1. project_slug_from_cwd() stripped the leading dash → memory dir never found
#   2. hooks hardcoded `python` → macOS only ships `python3` → command not found
#
# Both are fixed upstream (hustlerv369/hustlers-megamind). This script pulls the
# fix, re-runs the installer so settings.json gets the right interpreter, and
# verifies the result. Safe to run repeatedly.

set -uo pipefail

REPO="https://github.com/hustlerv369/hustlers-megamind.git"
SKILL_DIR="$HOME/.claude/skills/megamind"
SETTINGS="$HOME/.claude/settings.json"

say() { printf '%s\n' "$*"; }
ok()  { printf '  OK   %s\n' "$*"; }
bad() { printf '  FAIL %s\n' "$*"; }

say "=============================================="
say " Megamind fix — $(uname -s) $(uname -m)"
say "=============================================="

# ---- 1. Python -------------------------------------------------------------
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  bad "Python nenalezen — nainstaluj Python 3 a spusť znovu."
  exit 1
fi
ok "Python: $PY ($("$PY" --version 2>&1))"

# ---- 2. Get / update the skill --------------------------------------------
if [ -d "$SKILL_DIR/.git" ]; then
  say ""
  say "-> git klon nalezen, aktualizuji…"
  git -C "$SKILL_DIR" pull --ff-only 2>&1 | tail -2
elif [ -d "$SKILL_DIR" ]; then
  say ""
  say "-> složka existuje, ale není to git klon → zálohuji a klonuji čistě"
  BAK="$SKILL_DIR.bak-$(date +%Y%m%d-%H%M%S)"
  mv "$SKILL_DIR" "$BAK" && ok "záloha: $BAK"
  git clone --quiet "$REPO" "$SKILL_DIR" && ok "naklonováno"
else
  say ""
  say "-> Megamind není nainstalovaný, klonuji…"
  mkdir -p "$(dirname "$SKILL_DIR")"
  git clone --quiet "$REPO" "$SKILL_DIR" && ok "naklonováno"
fi

# ---- 3. Verify the slug fix is actually present ----------------------------
say ""
say "-> ověřuji opravu slugu"
SLUG_OUT="$("$PY" - "$SKILL_DIR" <<'PYEOF'
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(sys.argv[1]) / "scripts"))
try:
    from lib import project_slug_from_cwd as slug
except Exception as e:
    print("IMPORT_ERROR", e); raise SystemExit(1)
got = slug("/Users/test/my project")
print("OK" if got == "-Users-test-my-project" else "WRONG", got)
PYEOF
)"
case "$SLUG_OUT" in
  OK*)   ok "slug: /Users/test/my project -> ${SLUG_OUT#OK }" ;;
  *)     bad "slug vrací špatnou hodnotu: $SLUG_OUT"; exit 1 ;;
esac

# ---- 4. Re-run the installer (rewrites hook commands) ----------------------
say ""
say "-> spouštím install.py (přepíše hooky v settings.json)"
"$PY" "$SKILL_DIR/scripts/install.py" 2>&1 | tail -8

# ---- 5. Verify hooks point at a real interpreter ---------------------------
say ""
say "-> kontroluji settings.json"
if [ -f "$SETTINGS" ]; then
  "$PY" - "$SETTINGS" <<'PYEOF'
import json, shutil, sys, re
p = sys.argv[1]
try:
    data = json.load(open(p, encoding="utf-8"))
except Exception as e:
    print("  FAIL settings.json nelze načíst:", e); raise SystemExit(1)

cmds = []
def walk(node):
    if isinstance(node, dict):
        c = node.get("command")
        if isinstance(c, str) and "megamind" in c:
            cmds.append(c)
        for v in node.values():
            walk(v)
    elif isinstance(node, list):
        for v in node:
            walk(v)
walk(data.get("hooks", {}))

if not cmds:
    print("  FAIL v settings.json nejsou žádné megamind hooky")
    raise SystemExit(1)

print(f"  OK   megamind hooků: {len(cmds)}")
bad = 0
for c in cmds:
    interp = c.split()[0].strip('"')
    exists = bool(shutil.which(interp)) or interp.startswith("/")
    name = re.search(r"hook_\w+", c)
    print(f"       {'ok ' if exists else 'X  '} {interp:<10} {name.group(0) if name else ''}")
    if not exists:
        bad += 1
raise SystemExit(1 if bad else 0)
PYEOF
  HOOKS_RC=$?
else
  bad "settings.json neexistuje"; HOOKS_RC=1
fi

# ---- 6. Result -------------------------------------------------------------
say ""
say "=============================================="
if [ "$HOOKS_RC" -eq 0 ]; then
  say " HOTOVO — restartuj Claude Code."
  say ""
  say " Ověření po restartu (v nové session):"
  say "   ls -la ~/.claude/projects/*/memory/.last-active"
  say " Když soubor existuje a má dnešní datum, Megamind píše."
else
  say " NĚCO NESEDÍ — pošli tento výstup zpátky."
fi
say "=============================================="
