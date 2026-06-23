---
name: Product pricing facts
description: Authoritative pricing for the product. Verify against live site or Stripe before citing in external copy.
type: fact
date: 2026-04-17
verify_sources:
  - https://example.com/pricing
  - Stripe Dashboard → Products
---

# Pricing

| Plan | Monthly | Yearly | Trial |
|------|---------|--------|-------|
| FREE | $0 | — | — |
| PRO | $12 | $119 (save 17%) | 3 days on both cycles |
| TEAM | $33 | $330 | none |
| ENTERPRISE | contact | — | — |

## Rules

- Trial captures a payment method but does not charge until day 4.
- Canceling during trial drops back to FREE, no charge.
- Team plan extra seats: $10 / seat / month.
- 100%-off coupon flow: Stripe sets `payment_status = "no_payment_required"`.
  The checkout handler must accept both `"paid"` and `"no_payment_required"`.

## Gotchas

- Pre-2026-04-17: trial was PRO-monthly-only. Extended to yearly after
  conversion tests showed asymmetry was hurting yearly adoption.
- Stripe minimum charge is $0.50 — true 100% lifetime discounts can edge-case
  on one-off invoices; use 99% if nervous.
