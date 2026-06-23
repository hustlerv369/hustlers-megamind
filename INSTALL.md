# 🧠⚡ Megamind Ultra — Install Guide

> One Claude Code skill that does cross-session **memory** + hard **token discipline**. Zero external deps (Python stdlib + git CLI). Cross-platform (Windows / macOS / Linux). It runs invisibly via **4 hooks** registered in `~/.claude/settings.json` — nothing to invoke, automatic on every session.

This guide has two parts:

1. **[Manual install](#1-manual-install-3-steps)** — drop the folder, run the installer, open a new session.
2. **[Let Claude install it for you](#2-let-claude-install-it-for-you-paste-this-prompt)** — a ready-to-paste prompt so Claude Code does the whole thing.

Plus: **[Verify](#3-verify-the-4-hooks-registered)**, **[Optional vault backup](#4-optional-memory-vault-backup-off-by-default)**, **[Uninstall](#5-uninstall)**, **[Troubleshooting](#6-troubleshooting)**.

---

## Prerequisites

- **Claude Code** installed and run at least once (so `~/.claude/` exists).
- **Python 3** on your `PATH`, invokable as `python` (`python --version` → 3.8+). No pip packages needed — stdlib only. If your system only has `python3`, see [§6 Troubleshooting](#6-troubleshooting) — the hooks are written to call `python`, so a `python` entry on `PATH` is required for them to fire.
- **git** on your `PATH` (only required if you later enable the optional vault backup; the core memory + token features work without it).

> `~/.claude` is your Claude home. On Windows that's `C:\Users\<you>\.claude`, on macOS/Linux `~/.claude`. If you set the `CLAUDE_HOME` env var, the installer honors it.

---

## 1 · Manual install (3 steps)

### Step 1 — Put the folder in place

Copy the downloaded `megamind` folder so it lives at exactly:

```
~/.claude/skills/megamind/
```

After copying, `~/.claude/skills/megamind/scripts/install.py` must exist. That's how you know the path is right.

**macOS / Linux:**
```bash
mkdir -p ~/.claude/skills
cp -R /path/to/downloaded/megamind ~/.claude/skills/megamind
```

**Windows (PowerShell):**
```powershell
New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null
Copy-Item -Recurse "C:\path\to\downloaded\megamind" "$HOME\.claude\skills\megamind"
```

### Step 2 — Run the installer

```bash
python ~/.claude/skills/megamind/scripts/install.py
```

This is **idempotent** (safe to run again) and:
- backs up your existing `settings.json` to `settings.json.bak-<timestamp>` alongside it,
- registers the 4 hooks (`SessionStart`, `UserPromptSubmit`, `PreCompact`, `Stop`) and **nothing else** — it never touches your MCP servers, permissions, or other settings,
- prints a `+ <Hook> → <script>` line for each hook it wired up.

> The hook command it writes is `python "<absolute path>"`. On Windows, run it from Git Bash, PowerShell, or `cmd` — all work. If `python` is not the name of your interpreter (some systems expose only `python3`), read [§6 Troubleshooting](#6-troubleshooting) **before** relying on the hooks.

### Step 3 — Open a new session

Hooks are read at startup, so **restart Claude Code or open a new session**. From then on Megamind loads your project memory at SessionStart, recalls per prompt, writes a clean resume before compaction, and stamps activity on Stop — all automatically.

That's it. Nothing to invoke. To inspect it any time:

```
/megamind status
```

---

## 2 · Let Claude install it for you (paste this prompt)

If you'd rather have Claude Code do the install, paste the prompt below into a Claude Code session. It handles **both** cases — "I already downloaded the folder" and "clone it from a repo URL first" — and finishes by verifying the 4 hooks and summarizing what the skill does.

> Before pasting, do **one** of:
> - **Case A — you have the folder:** note its current path (e.g. your Downloads folder).
> - **Case B — clone from a repo:** replace `https://github.com/hustlerv369/hustlers-megamind` with the Git URL you were given (placeholder: `https://github.com/hustlerv369/hustlers-megamind` — e.g. `https://github.com/<owner>/megamind.git`).

### The install prompt

```
You are going to install the "Megamind Ultra" Claude Code skill for me. It is a single
skill that adds cross-session memory + token discipline via 4 hooks. Zero external deps
(Python stdlib + git CLI). Do this carefully and report each step:

1. Locate the skill source. TWO cases — figure out which applies:
   • CASE A (I already have the folder): I will tell you the path to the downloaded
     `megamind` folder. If I haven't, ask me for it. A valid folder contains
     `scripts/install.py` and `SKILL.md`.
   • CASE B (clone from a repo): if I gave you a repo URL instead of a local folder,
     clone it to a temp dir:  git clone https://github.com/hustlerv369/hustlers-megamind /tmp/megamind-src
     The skill may be at the repo root or in a subfolder — find the directory that
     contains `scripts/install.py` and treat THAT as the source folder.

2. Determine my Claude home: the `CLAUDE_HOME` env var if set, otherwise `~/.claude`
   (on Windows: `C:\Users\<me>\.claude`). Ensure `<claude_home>/skills/` exists.

3. Copy/move the source folder to EXACTLY `<claude_home>/skills/megamind` (recursive).
   If a `megamind` folder is already there, back it up to `megamind.bak-<timestamp>`
   first, then replace it. Afterward, confirm `<claude_home>/skills/megamind/scripts/
   install.py` exists.

4. Run the installer:  python <claude_home>/skills/megamind/scripts/install.py
   It is idempotent and backs up settings.json automatically. Show me its output.
   If `python` is not found but `python3` is, tell me — the hooks the installer writes
   call `python`, so we will need a `python` shim on PATH (do NOT silently rewrite them).

5. VERIFY: read `<claude_home>/settings.json` and confirm the `hooks` section now has
   entries for SessionStart, UserPromptSubmit, PreCompact, AND Stop, each running a
   `megamind/scripts/hook_*.py` script. List exactly which 4 were registered. If any
   are missing, re-run the installer and re-check.

6. Tell me to restart Claude Code / open a NEW session for the hooks to take effect
   (they load at startup).

7. Summarize in 4-5 bullets what the skill now does for me (memory across sessions,
   per-prompt recall, clean pre-compaction resume, lean token directive, and the
   `/megamind` command), and mention the vault backup is OFF by default.

Do NOT enable the optional memory-vault backup, do NOT disable any of my other skills,
and do NOT modify anything in settings.json other than what the installer writes.
```


---

## 3 · Verify the 4 hooks registered

After installing (either way), confirm all four hooks landed. Open `~/.claude/settings.json` and look under `"hooks"` for these four keys, each running a `megamind/scripts/hook_*.py` script:

| Hook | Script | What it does |
|------|--------|--------------|
| `SessionStart` | `hook_session_start.py` | Injects the line-clipped `MEMORY.md` map + newest **clean** session note + a ~50-token lean directive (~550 tok, once). |
| `UserPromptSubmit` | `hook_user_prompt.py` | Greps project memory for the prompt's keywords, injects top-3 (noise-filtered + deduped), ≤400 tok, silent if no hit. |
| `PreCompact` | `hook_pre_compact.py` | Writes a **clean structured resume** (intent / decisions / files / commands / open questions), base64 + tool-JSON stripped. **0 tokens to context.** |
| `Stop` | `hook_stop.py` | Stamps `.last-active` + optional debounced, secret-scanned vault push. **0 tokens to context.** |

**Quick CLI check** (works on all platforms):

```bash
python ~/.claude/skills/megamind/scripts/cli.py status
```

It prints the current project's memory stats, the lean directive state, and your model/effort — proof the skill code runs. If you see memory stats, you're good. (The hooks themselves only fire in a *new* session, so don't worry if the current session predates the install.)

---

## 4 · Optional: memory-vault backup (OFF by default)

The `Stop` hook can mirror your project memory into a git **`memory-vault`** repo so your notes survive across machines. It is **disabled by default** and never pushes anything for a fresh user. Enable it only if you want it.

**Why it's opt-in:** the sync runs `git` directly (bypassing Claude's pre-commit secret hook), so if your memory-vault repo is **public**, hand-written notes could leak keys/PII. As a backstop, a stdlib regex secret scan runs over the staged diff and **aborts the commit** if it spots a key-shaped token — but treat that as a safety net, not a guarantee, since a regex can't catch every secret. The real protection is to use a **private** repo. Pushes are also debounced (≥15 min) and every git call is timeboxed.

### Enable it

1. Create a git repo for your memory and clone it locally. By default Megamind looks for it at `~/Documents/GitHub/memory-vault`. To point elsewhere, set `MEGAMIND_VAULT_DIR`.
2. Turn auto-sync on with the env var `MEGAMIND_AUTOSYNC=1`.

**macOS / Linux** (add to your shell profile, e.g. `~/.zshrc` / `~/.bashrc`):
```bash
export MEGAMIND_AUTOSYNC=1
export MEGAMIND_VAULT_DIR="$HOME/Documents/GitHub/memory-vault"   # optional override
# export MEGAMIND_SYNC_DEBOUNCE=900                               # optional, seconds (default 900 = 15 min)
```

**Windows** (persist for your user):
```powershell
[Environment]::SetEnvironmentVariable("MEGAMIND_AUTOSYNC", "1", "User")
[Environment]::SetEnvironmentVariable("MEGAMIND_VAULT_DIR", "$HOME\Documents\GitHub\memory-vault", "User")
```

### Use it manually any time

```
/megamind vault sync      # mirror + commit + push (gated by AUTOSYNC + debounce + secret scan)
/megamind vault mirror    # copy memory → vault working tree only (no commit)
/megamind vault prune     # drop transcript-noise dumps from the vault index + disk
```

Force a one-off push regardless of the env gate: `python ~/.claude/skills/megamind/scripts/vault.py sync --force`.

---

## 5 · Uninstall

Remove the 4 hooks from `settings.json` (everything else is left untouched). It also writes a fresh timestamped backup before editing:

```bash
python ~/.claude/skills/megamind/scripts/install.py --uninstall
```

(If your interpreter is `python3`, use `python3` for that command.)

Then, if you also want the code gone, delete the folder.

**macOS / Linux:**
```bash
rm -rf ~/.claude/skills/megamind
```

**Windows (PowerShell):**
```powershell
Remove-Item -Recurse -Force "$HOME\.claude\skills\megamind"
```

Your stored memory under `~/.claude/projects/<slug>/memory/` is left in place — delete those folders too if you want a clean wipe. A timestamped `settings.json.bak-*` from install time is also kept alongside `settings.json` if you ever need to roll back.

---

## 6 · Troubleshooting

- **`python: command not found` (you only have `python3`)** → The installer is invoked as `python …`, **and** the hooks it writes call `python "<path>"`. Two fixes, pick one:
  1. **Recommended — add a `python` shim/alias on `PATH`** so both the installer and the hooks resolve. On macOS/Linux this is often `ln -s "$(command -v python3)" ~/.local/bin/python` (ensure `~/.local/bin` is on `PATH`); on Windows the official python.org installer registers `python`.
  2. **Manual — after running the installer via `python3 …install.py`, hand-edit `~/.claude/settings.json`** and change each of the four hook commands from `python "…"` to `python3 "…"`, then re-verify per [§3](#3-verify-the-4-hooks-registered). (There is no installer flag to emit `python3` automatically.)
  Confirm your interpreter with `python --version` / `python3 --version`.
- **Installer says `SKIP <Hook>: ... missing`** → the folder isn't at `~/.claude/skills/megamind/`, or it's incomplete. Re-check that `~/.claude/skills/megamind/scripts/install.py` and the four `hook_*.py` files exist, then re-run.
- **Hooks don't fire** → they load at startup. Restart Claude Code / open a **new** session. Re-verify the `hooks` block in `settings.json` per [§3](#3-verify-the-4-hooks-registered). If the block looks right but nothing happens, confirm `python` actually resolves on your `PATH` (see the first item above).
- **`settings.json` failed to parse** → the installer refuses to touch a broken file and exits. Fix the JSON (the installer never wrote it broken — restore a `settings.json.bak-*` if needed), then re-run.
- **Worried about overwriting settings** → the installer backs up `settings.json` to `settings.json.bak-<timestamp>` before every write, and only edits the `hooks` section.

---

## What you just installed (the 30-second version)

- **Memory across sessions** — your project context is auto-loaded at start and keyword-recalled per prompt. Project isolation via a `cwd → slug` mapper (handles spaces in paths).
- **No noise in context** — PreCompact writes a *clean structured resume*, never the raw transcript; base64 image blobs and tool-JSON are stripped at write time.
- **Lean token discipline** — a one-line SessionStart directive + a reversible `/megamind lean apply` that flips `opus[1m]→opus` and `xhigh→high`.
- **Lazy skills** — `/megamind skills` disables skills you haven't used in 30+ days (moving them out of the scanned path so their descriptions stop loading); re-enable on demand.
- **Zero LLM calls from hooks** — pure grep, no cloud, no vector DB, no GPU, no API key.

Full reference: see `README.md`, `SKILL.md`, and `TOKEN-SAVINGS.md` in the skill folder.

