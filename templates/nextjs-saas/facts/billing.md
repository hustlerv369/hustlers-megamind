---
name: Billing + Stripe
type: fact
date: YYYY-MM-DD
verify_sources:
  - Stripe Dashboard → Products
  - /pricing page
---

# Billing

## Plans
| Plan | Monthly | Yearly | Trial |
|------|---------|--------|-------|
| FREE | $0 | — | — |
| PRO | $ | $ | days |
| TEAM | $ | $ | days |

## Stripe webhook events we handle
- `checkout.session.completed`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.payment_failed`

## Edge cases
- 100% off coupons → `payment_status = "no_payment_required"` (not `"paid"`)
- Trial cancel before day N → drops to FREE, no charge
- Chargebacks → mark user as banned, invalidate sessions
