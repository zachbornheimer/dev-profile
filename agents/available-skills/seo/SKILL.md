---
name: seo
disable-model-invocation: true
description: "Full SEO suite — audits, technical, local, GEO/AI search, schema, backlinks, content, sitemaps, images, maps. Invoke with /seo <task>."
user-invokable: true
argument-hint: "[command] [url]"
license: MIT
metadata:
  author: AgriciDaniel
  version: "1.8.1"
  category: seo
---

# SEO: Unified SEO Suite

Comprehensive SEO analysis across all industries. Orchestrates 19 specialised sub-skills.
Before acting on any `/seo` command, **Read the matching reference file listed below** then
follow the instructions inside it. Scripts live at `scripts/`; shared references at `references/`.

## Dispatch Table

| Command                 | Trigger phrases                                                               | Reference file                   |
| ----------------------- | ----------------------------------------------------------------------------- | -------------------------------- |
| `/seo audit <url>`      | audit, full SEO check, analyze my site, website health check                  | `references/audit.md`            |
| `/seo page <url>`       | analyze this page, check page SEO, single URL, on-page analysis               | `references/page.md`             |
| `/seo technical <url>`  | technical SEO, crawl issues, indexability, Core Web Vitals, CWV, robots       | `references/technical.md`        |
| `/seo content <url>`    | content quality, E-E-A-T, readability, thin content, content audit            | `references/content.md`          |
| `/seo schema <url>`     | schema, structured data, rich results, JSON-LD, markup                        | `references/schema.md`           |
| `/seo images <url>`     | image optimization, alt text, image SEO, image audit, convert to webp         | `references/images.md`           |
| `/seo sitemap <url>`    | sitemap, generate sitemap, XML sitemap, sitemap issues                        | `references/sitemap.md`          |
| `/seo geo <url>`        | AI Overviews, SGE, GEO, AI search, LLM optimization, Perplexity, AI citations | `references/geo.md`              |
| `/seo plan <type>`      | SEO plan, SEO strategy, SEO planning, content strategy                        | `references/plan.md`             |
| `/seo programmatic`     | programmatic SEO, pages at scale, template SEO, index bloat                   | `references/programmatic.md`     |
| `/seo competitor-pages` | comparison page, vs page, alternatives page, competitor comparison, X vs Y    | `references/competitor-pages.md` |
| `/seo local <url>`      | local SEO, Google Business Profile, GBP, map pack, citations, NAP             | `references/local.md`            |
| `/seo maps`             | geo-grid, GBP audit, review intelligence, competitor radius                   | `references/maps.md`             |
| `/seo hreflang <url>`   | hreflang, i18n SEO, international SEO, multi-language, language tags          | `references/hreflang.md`         |
| `/seo google <cmd>`     | search console, GSC, PageSpeed, CrUX, field data, GA4, indexing API           | `references/google.md`           |
| `/seo backlinks <url>`  | backlinks, link profile, referring domains, anchor text, toxic links          | `references/backlinks.md`        |
| `/seo firecrawl <url>`  | crawl site, map site, full crawl, discover pages, JS rendering                | `references/firecrawl.md`        |
| `/seo dataforseo <cmd>` | dataforseo, live SERP, keyword volume, backlink data, real search data        | `references/dataforseo.md`       |
| `/seo image-gen <desc>` | generate image, OG image, social preview, hero image, blog image, infographic | `references/image-gen.md`        |

## Orchestration Logic (for /seo audit)

When the user invokes `/seo audit`, Read `references/audit.md` for full delegation
instructions. Summary:

1. Detect business type (SaaS, local, ecommerce, publisher, agency, other)
2. Spawn subagents: seo-technical, seo-content, seo-schema, seo-sitemap, seo-performance, seo-visual, seo-geo
3. If Google API credentials detected (`python scripts/google_auth.py --check`), also spawn seo-google
4. If local business detected, also spawn seo-local
5. If local business detected AND DataForSEO MCP available, also spawn seo-maps
6. If backlink APIs detected (`python scripts/backlinks_auth.py --check`), also spawn seo-backlinks
7. If Firecrawl MCP available, use `firecrawl_map` to discover all site URLs before analysis
8. Collect results → unified report with SEO Health Score (0-100) and prioritised action plan
9. Offer PDF: "Generate a professional PDF report? Use `/seo google report full`"

## Industry Detection

Detect business type from homepage signals:

- **SaaS**: pricing page, /features, /integrations, /docs, "free trial", "sign up"
- **Local Service**: phone number, address, service area, "serving [city]", Google Maps embed
- **E-commerce**: /products, /collections, /cart, "add to cart", product schema
- **Publisher**: /blog, /articles, /topics, article schema, author pages, publication dates
- **Agency**: /case-studies, /portfolio, /industries, "our work", client logos

## Scoring Methodology

### SEO Health Score (0-100)

| Category                 | Weight |
| ------------------------ | ------ |
| Technical SEO            | 22%    |
| Content Quality          | 23%    |
| On-Page SEO              | 20%    |
| Schema / Structured Data | 10%    |
| Performance (CWV)        | 10%    |
| AI Search Readiness      | 10%    |
| Images                   | 5%     |

### Priority Levels

- **Critical**: Blocks indexing or causes penalties (immediate fix required)
- **High**: Significantly impacts rankings (fix within 1 week)
- **Medium**: Optimization opportunity (fix within 1 month)
- **Low**: Nice to have (backlog)

## Quality Gates (Shared — Always Active)

Load `references/quality-gates.md` for thin content thresholds per page type.

Hard rules:

- WARNING at 30+ location pages (enforce 60%+ unique content)
- HARD STOP at 50+ location pages (require user justification)
- Never recommend HowTo schema (deprecated Sept 2023)
- FAQ schema: only government and healthcare sites get Google rich results (Aug 2023); existing FAQPage on commercial sites → flag Info priority (not Critical), noting AI/LLM citation benefit; adding new FAQPage → not recommended for Google benefit
- All Core Web Vitals references use INP, never FID

## Shared Reference Files

Load on-demand as needed (do NOT load all at startup):

- `references/cwv-thresholds.md` — Core Web Vitals thresholds and measurement details
- `references/schema-types.md` — All supported schema types with deprecation status
- `references/eeat-framework.md` — E-E-A-T evaluation criteria (Sept 2025 QRG update)
- `references/quality-gates.md` — Content length minimums, uniqueness thresholds
- `references/local-seo-signals.md` — Local ranking factors, review benchmarks, citation tiers
- `references/local-schema-types.md` — LocalBusiness subtypes, industry-specific schema
- `references/backlink-quality.md` — Toxic link patterns and scoring methodology
- `references/free-backlink-sources.md` — Source comparison, confidence weighting, setup guides
- `references/maps-geo-grid.md`, `references/maps-gbp-checklist.md`, `references/maps-api-endpoints.md`, `references/maps-free-apis.md` — Maps intelligence references

## Error Handling

| Scenario                     | Action                                                                                                         |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Unrecognized command         | List available commands from the Dispatch Table. Suggest closest match.                                        |
| URL unreachable              | Report the error, suggest user verify URL. Do not guess site content.                                          |
| Sub-skill fails during audit | Report partial results from successful sub-skills. Note which failed and why. Suggest re-running individually. |
| Ambiguous business type      | Present top two detected types with supporting signals. Ask user to confirm before proceeding.                 |
