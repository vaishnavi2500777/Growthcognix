# CrawlMonk vs Firecrawl: feature parity

Studied from https://docs.firecrawl.dev/llms-full.txt (v2 API: scrape, crawl, map, search, batch scrape, extract, agent, interact, parse, monitor, team usage) and the open-source repo (apps/api: scrapeURL engines such as fetch, Playwright service and the proprietary fire-engine; a BullMQ/Redis queue with workers; the html-to-markdown service; `removeUnwantedElements` for onlyMainContent; map via sitemap plus a search index; signed webhooks).

Status key: **Yes** means implemented and tested live. **Partial** means implemented with a limit, explained in the row. **No** means not done.

| Firecrawl feature | CrawlMonk | Notes |
|---|---|---|
| POST /scrape: markdown, html, rawHtml, links, images | Yes | BeautifulSoup + markdownify. Relative URLs are made absolute. |
| onlyMainContent | Yes | Uses Firecrawl's own non-main selector list (header, footer, nav, .sidebar, .cookie…) and keeps main/article. |
| includeTags / excludeTags | Yes | CSS selectors. |
| timeout, headers, mobile (UA and viewport) | Yes | |
| maxAge cache | Yes | Postgres page cache, 7-day retention. |
| PDF / DOCX / XLSX URLs | Yes | pypdf, python-docx, openpyxl. No OCR for scanned PDFs (Partial). |
| screenshot (viewport or fullPage) | Yes* | Headless Chromium through Playwright, stored and served at /files/{id}. *Depends on the browser fitting in Render free's 512 MB. |
| waitFor, actions (wait, click, write, press, scroll, screenshot, scrape, executeJavascript) | Yes* | Same browser dependency. |
| json format (prompt/schema) | Yes | Gemini (gemini-3.5-flash-lite). Returns a clear 503 AI_UNAVAILABLE error when no key is set. |
| summary format | Yes | Gemini. |
| changeTracking format (git-diff) | Yes | Per-user snapshots with a unified diff. |
| contacts format (emails, phones, socials) | Extra | Not in Firecrawl. Indian phone parsing uses libphonenumber. |
| branding, audio, attributes formats | No | Out of scope. |
| Proxy tiers (basic, stealth), fire-engine anti-bot, captcha handling | No | Firecrawl's proprietary paid infrastructure. CrawlMonk uses one datacenter IP with no residential proxies. Expect 403s on Cloudflare-protected sites. |
| robots.txt | Yes (always respected) | Firecrawl can ignore it. CrawlMonk does not. |
| POST /crawl (async) + GET status + DELETE cancel + /errors | Yes | includePaths, excludePaths, maxDiscoveryDepth, limit (≤200), allowExternalLinks, allowSubdomains, crawlEntireDomain, ignoreQueryParameters, delay, maxConcurrency (≤5), sitemap include/skip, scrapeOptions, paginated `next`. |
| Webhooks (started, page, completed, failed) with signature | Yes | HMAC-SHA256 in `X-CrawlMonk-Signature`, using a per-user secret. |
| POST /map | Yes | sitemap.xml (with indexes and gzip) + robots sitemaps + homepage links + search-engine `site:` results. Options: search filter, includeSubdomains, limit, sitemap only/skip. |
| POST /search (web + news, scrapeOptions) | Partial | No paid search API. Web search scrapes Yahoo, then DuckDuckGo HTML, then DDG Lite, then Bing, with a relevance check. News comes from Google News RSS. Free engines rate-limit datacenter IPs, so search can fail under load. No images/categories sources. |
| POST /batch/scrape (async) | Yes | Up to 500 URLs, webhooks, cancel. |
| POST /extract | Yes | URLs, `/*` wildcards (via map), prompt, schema, enableWebSearch. Uses one Gemini call over ≤10 pages, so it is not Firecrawl's multi-step extraction at scale. |
| POST /agent | Partial | Gemini plans queries, then search, scrape, and answer with sources. Simpler than Firecrawl's FIRE-1 agent: no autonomous browsing or clicking. |
| POST /parse (file upload) | Yes | PDF, DOCX, XLSX, HTML, TXT. |
| Monitors / change tracking on a schedule | Partial | Interval ≥15 min, stores diffs, sends a webhook on change. Render free sleeps after 15 idle minutes, so checks only run while the service is awake. Fixing this needs a paid instance or an external pinger. |
| /interact (live browser session) | Partial | Max 2 sessions, closed after 5 idle minutes, in-memory (lost on restart). Same browser memory caveat. |
| API keys, usage/credits, rate limits | Yes | Multiple keys per user (SHA-256 hashed). Daily credit cap (3000/24h), 120 req/min per user. Signup is limited to 5/hour per IP. |
| SDKs | Partial | Python, JS and curl snippets on the API page. Request shapes mirror Firecrawl v1/v2 (`/v1` and `/v2` both mounted). Official Firecrawl SDKs are untested against it. |
| MCP server | Yes (basic) | POST /mcp (JSON-RPC: initialize, tools/list, tools/call) with tools for scrape, map, search, find_leads, crawl and job_status. |
| Queue | Yes | Postgres `FOR UPDATE SKIP LOCKED` queue with 2 in-process workers. Jobs left running are requeued on restart. No Redis. |
| Scale | No | Firecrawl runs fleets of workers. CrawlMonk is one free 512 MB instance. |

## Where CrawlMonk is better for Devi's use case (finding Indian business leads)
- City-wise Lead Finder, which Firecrawl does not have. It geocodes the city (Nominatim, or Photon as a fallback), pulls real businesses from OpenStreetMap (name, address, phone, website, category, lat/lon) and finds more companies through web search. Directory sites like IndiaMART, Justdial and TradeIndia are excluded, and each company must prove it fits on its own website (keyword plus a mention of the city).
- Each lead is enriched from its own site: emails (including [at]/[dot] de-obfuscation), Indian phone numbers normalised to E.164, social profiles, and quality signals for agency sales (no HTTPS, not mobile-friendly, old copyright year, no Instagram).
- Every lead gets an explainable 0–100 score. Two modes: `agency` (scores weak online presence) and `buyer` (scores relevance). Optional Gemini fit reasons are tailored to "what you sell".
- Dedupe by domain, phone and name. Multi-city jobs, CSV export, history stored in Postgres.
