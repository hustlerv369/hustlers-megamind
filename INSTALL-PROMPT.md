# 📋 Install Megamind Ultra — paste-into-Claude prompt

You don't install this by hand. **Download the `megamind` folder, then paste the prompt below into a Claude Code session** — Claude does the whole thing (copy → register hooks → verify → summarize).

> Tip: if you're sharing from a repo instead of a folder, just give Claude the repo URL — the prompt handles both cases.

```
Install the "Megamind Ultra" Claude Code skill for me. It's one skill that adds
cross-session memory + token discipline via 4 hooks (zero deps — Python stdlib + git).
Do this carefully and report each step:

1. Find the source folder. TWO cases:
   • I already have it: I'll tell you the path to the downloaded `megamind` folder
     (a valid one contains scripts/install.py and SKILL.md). If I haven't, ask me.
   • From a repo: if I give you a repo URL, clone it to a temp dir and find the
     directory containing scripts/install.py — treat THAT as the source.
2. Determine my Claude home: $CLAUDE_HOME if set, else ~/.claude (Windows:
   C:\Users\<me>\.claude). Ensure <claude_home>/skills/ exists.
3. Copy the source to exactly  <claude_home>/skills/megamind  (recursive). If one is
   already there, back it up to megamind.bak-<timestamp> first. Then confirm
   <claude_home>/skills/megamind/scripts/install.py exists.
4. Run:  python <claude_home>/skills/megamind/scripts/install.py  (idempotent; it backs
   up settings.json). Show me the output. If only `python3` exists, tell me — the hooks
   call `python`, so I'll need a `python` shim on PATH (do NOT silently rewrite them).
5. VERIFY: read <claude_home>/settings.json and confirm the hooks section now has entries
   for SessionStart, UserPromptSubmit, PreCompact AND Stop, each running a
   megamind/scripts/hook_*.py. List exactly which 4 were registered; re-run if any miss.
6. Tell me to restart Claude Code / open a NEW session (hooks load at startup).
7. Summarize in 4-5 bullets what it now does (memory across sessions, per-prompt recall,
   clean pre-compaction resume, lean token directive, the /megamind command) and note
   the vault backup is OFF by default.

Do NOT enable the optional memory-vault backup, do NOT disable any of my other skills,
and do NOT modify anything in settings.json other than what the installer writes.
```
