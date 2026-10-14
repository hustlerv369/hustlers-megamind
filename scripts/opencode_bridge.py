#!/usr/bin/env python3
"""Compatibility entry point: project memory is retrieved explicitly, never written globally."""
import sys
def main(argv):
    print("Global project-memory mirroring was removed. Use D:/AI/harness-memory.py recall/read --project <absolute project>.")
    return 0
if __name__ == "__main__":raise SystemExit(main(sys.argv))
