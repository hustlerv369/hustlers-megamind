# Security Policy

## Supported versions

Only the latest `main` branch receives security updates. Tagged releases
are snapshots — if you're running an older tag and hit a security issue,
upgrade first; report only if the issue persists on `main`.

| Version | Supported |
|---------|-----------|
| main    | ✅        |
| v0.1.x  | ✅        |
| < v0.1  | ❌        |

## Reporting a vulnerability

**Do not open a public GitHub issue for security bugs.**

Use GitHub's private advisory flow instead:

1. Go to the repo's **Security** tab → **Report a vulnerability**.
2. Fill in reproduction steps, affected files, and an impact assessment
   (what's the worst an attacker can do with this?).
3. A maintainer will reply within 7 days. Fix lands on `main` before
   public disclosure; CVE + changelog entry follow.

If the GitHub flow is blocked for you, email the repo owner through
their GitHub profile's public contact. Do not include exploit code in
the first message — ask for a private channel first.

## Scope

This project runs Python scripts as Claude Code hooks on the user's
local machine. Issues that qualify:

- **Path traversal / arbitrary write** — a crafted `cwd` or hook input
  that makes MegaMind write outside `~/.claude/projects/<slug>/memory/`.
- **Arbitrary command execution** — any input (session JSON, memory
  filename, MEMORY.md content) that triggers shell execution beyond
  what the hook intends.
- **Sensitive data leakage** — memory files or settings getting
  committed, printed to stdout unintentionally, or sent to a network
  endpoint. This project makes **zero network calls**; any observed
  network activity is a bug.
- **Denial of hook execution** — crafted input that crashes all four
  hooks and breaks the user's Claude Code session.

Out of scope:

- Claude Code core vulnerabilities — report to Anthropic instead.
- Social-engineering attacks on memory content (user writes a lie into
  `MEMORY.md`; Claude acts on it). That's the user's responsibility.
- Token-budget overflow. Hard-clipped by `format_budget()`. Misuse
  beyond the budget is a performance bug, not a security issue.

## Hardening notes (what the code already does)

- Zero external dependencies — no transitive CVEs via pip.
- No `shell=True` in subprocess calls anywhere.
- All file reads scoped to `~/.claude/projects/<slug>/memory/`.
- Settings file is backed up before every installer run
  (`settings.json.bak-<timestamp>`).
- Uninstaller removes only MegaMind entries — leaves unknown keys intact.
