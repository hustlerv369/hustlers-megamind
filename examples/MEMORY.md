# Project memory index

Place this file at `~/.claude/projects/<your-project-slug>/memory/MEMORY.md`.
Megamind Ultra auto-loads it at every session start (budget ≤ 1500 tokens).

Convention: one line per entry with an emoji tag for priority, a linked
filename, and a one-sentence description. Claude learns to treat the
emoji as a priority signal.

## Tags

- 🔴 **urgent / pending next session** — bring up proactively
- 🟡 **active** — under current work
- ✅ **resolved / reference** — past fix worth remembering
- 📓 **session note** — diary entry from a working session
- 📦 **fact** — stable project fact (pricing, stack, conventions)
- ⚠️ **watch out** — known gotcha or subtle bug

## Example entries

- 🔴 [TOMORROW: deploy v2 to prod](tomorrow-deploy-v2.md) — waiting on final QA, scheduled morning
- ✅ [Webhook HMAC fix](fixes/webhook-hmac-2026-04.md) — root cause + resolution
- 📓 [Session 2026-04-17 evening](sessions/2026-04-17-evening.md) — added Stripe coupons
- 📦 [Pricing facts](facts/pricing.md) — plans, trial rules, currencies
- 📦 [Architecture overview](facts/architecture.md) — services, data flow, auth model
- ⚠️ [Known Firebase quirks](facts/firebase-gotchas.md) — req.body vs req.rawBody, regional timeouts

## What NOT to put here

- Generic Claude Code docs (`/docs` lives in Anthropic's docs, not your memory)
- API keys, passwords, tokens — use Firebase Secret Manager, Vault, or `.env`
- Files larger than a few KB — split into multiple files, index points to them
