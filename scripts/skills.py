#!/usr/bin/env python3
"""Read-only skill inventory. Automatic hiding for token savings is retired."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
from lib import CLAUDE_HOME

SKILLS_DIR = CLAUDE_HOME / "skills"
DISABLED_DIR = SKILLS_DIR.resolve().parent / "skills-disabled"

def inventory(base):
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())

def main(argv):
    operation = argv[1] if len(argv) > 1 else "audit"
    if operation not in ("audit", "list"):
        print("Skill relocation is retired. Inventory is read-only; use audit or list.", file=sys.stderr)
        return 2
    for label, base in (("available", SKILLS_DIR), ("historically disabled", DISABLED_DIR)):
        names = inventory(base)
        print(f"{label}: {len(names)}")
        for name in names:
            print(f"  {name}")
    print("No skills moved, disabled or removed. Historical disabled sources remain available for explicit retrieval.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
