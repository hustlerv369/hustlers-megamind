---
name: Stack overview
type: fact
date: YYYY-MM-DD
---

# Stack

| Layer | Choice | Version | Notes |
|-------|--------|---------|-------|
| Framework | Next.js | | App Router? Pages Router? |
| Runtime | Node | | |
| Language | TypeScript | | |
| ORM | Prisma / Drizzle / ? | | |
| Database | Postgres / MySQL / ? | | |
| Auth | NextAuth / Clerk / ? | | |
| Payments | Stripe | | Subscriptions / one-time / both? |
| Hosting | Vercel / Railway / ? | | |
| Monorepo? | yes / no | | pnpm workspaces? turborepo? |

## Directory layout
- `app/` — routes
- `components/` — reusable UI
- `lib/` — server-side utilities
- `prisma/` — schema + migrations

## Commands
- `pnpm dev` — local dev
- `pnpm test` — run tests
- `pnpm lint` — lint
- `pnpm build` — production build
