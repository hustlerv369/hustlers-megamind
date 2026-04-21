---
name: Product pricing facts
description: Authoritative pricing for the product. Verify against live site or billing provider before citing in external copy.
type: fact
date: 2026-04-17
verify_sources:
  - https://example.com/pricing
  - Billing provider dashboard → Products
---

# Pricing

| Plan | Monthly | Yearly | Trial |
|------|---------|--------|-------|
| FREE | $0 | — | — |
| PRO | $9 | $89 (save 18%) | 7 days on both cycles |
| TEAM | $29 | $290 | none |
| ENTERPRISE | contact | — | — |

## Rules

- Trial captures a payment method but does not charge until day 8.
- Canceling during trial drops back to FREE, no charge.
- Team plan extra seats: $8 / seat / month.
- 100%-off coupon flow: billing provider sets `payment_status = "no_payment_required"`.
  The checkout handler must accept both `"paid"` and `"no_payment_required"`.

## Gotchas

- Pre-2026-04-17: trial was PRO-monthly-only. Extended to yearly after
  conversion tests showed asymmetry was hurting yearly adoption.
- Many payment processors enforce a minimum charge of $0.50 — true 100%
  lifetime discounts can edge-case on one-off invoices; use 99% if nervous.
