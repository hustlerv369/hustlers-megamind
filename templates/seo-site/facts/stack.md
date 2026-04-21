---
name: Stack overview
type: fact
date: YYYY-MM-DD
---

# Stack

| Layer | Choice | Version | Notes |
|-------|--------|---------|-------|
| Framework | Next.js / Astro / Hugo / Eleventy | | |
| CMS | headless / flat files / Sanity / Contentful | | |
| Hosting | Vercel / Netlify / Cloudflare | | |
| Search Console | connected? | | |
| Analytics | GA4 / Plausible / ? | | |
| Schema markup | JSON-LD generators | | |

## Build
- `pnpm build` — generate static output
- Deploy preview on PR
- Sitemap auto-generated at `/sitemap.xml`

## SEO checklist
- [ ] Every page has unique `<title>` and `meta description`
- [ ] Canonical tags on every indexable URL
- [ ] Schema.org JSON-LD on articles / products / breadcrumbs
- [ ] hreflang if multi-lang
- [ ] CWV green in field data (CrUX)
