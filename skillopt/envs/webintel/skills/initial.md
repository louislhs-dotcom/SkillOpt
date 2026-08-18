# Web Intelligence Routing Skill

You have 6 tools for web interaction. Pick the right one for each task.

## Agent Reach — platform-specific data access
- `agent-reach get rss.feed "<query>"` — RSS/Atom feeds as clean text
- `agent-reach get youtube.transcript "<query>"` — YouTube video transcripts
- `agent-reach get youtube.info "<query>"` — YouTube video metadata
- Installed channels: rss, youtube. Taps available for twitter, reddit, github.
- Use when: pulling social media, YouTube, RSS, platform content with auth barriers.

## Moli — fast structure-first page extraction
- `moli fetch --dump markdown --wait-until done "URL"` — page as markdown (16ms, no rendering)
- `moli fetch --dump semantic_tree_text "URL"` — compact semantic tree for AI processing
- `moli fetch --dump html "URL"` — raw HTML
- `moli fetch --layout --dump screenshot "URL" > out.png` — screenshot (needs --layout)
- `moli serve --layout` — CDP server on :9222 for Playwright
- Wait strategies: done (default), networkidle (avoid for WebSocket/long-poll), domstable (DOM settled)

**For SPAs:** Use `--wait-until domstable` (waits for DOM mutations to settle, no rendering cost). Avoid `networkidle` with WebSockets/long-polling.
- Use when: fast batch extraction of public pages, AI-optimized snapshots, CDP backend.
- Key: --layout only for screenshots/PDFs/geometry; structure-first extraction is free.

## Defuddle — clean article content extraction
- `defuddle parse <url|file> --markdown` — clean article as Markdown (strips sidebars, headers, footers, comments, ads)
- `defuddle parse <url|file> --json` — JSON with metadata (title, author, site, published, wordCount, schemaOrgData)
- `defuddle parse <url|file> --frontmatter` — YAML frontmatter prepended
- `defuddle parse <url|file> --property <name>` — extract a single property (e.g. `title`)
- `defuddle parse <url|file> --user-agent "<UA>"` — custom UA for 403 responses
- Reads HTML from stdin when no source given: `curl -sL URL | defuddle parse --markdown`
- Use when: the goal is the readable article/main content of a page, not the full DOM. Complements Moli/ego-browser (fetch) as the extraction stage.

## ego lite — interactive browser with login state

**SPA Wait Patterns (JavaScript-heavy pages):**
- `await tab.waitForSelector('selector', { timeout: 30000 })` — wait for specific element (preferred)
- `await tab.waitForNetworkIdle({ idleTime: 2000 })` — wait for network quiet (avoid with WebSockets/long-poll)
- Combine with `snapshotText(tab)` after wait for extraction

**Fallback when platform taps unavailable:** If Agent Reach tap (Twitter, Reddit, GitHub) isn't installed, use ego lite with your Chrome login:
```bash
ego-browser nodejs <<'EOF'
const { useOrCreateTaskSpace, openOrReuseTab, snapshotText } = await import('ego-browser');
const space = await useOrCreateTaskSpace('platform-fallback');
const tab = await openOrReuseTab(space, 'https://platform.com/search?q=query');
await tab.waitForSelector('[data-testid="tweet"]', { timeout: 15000 });
console.log(await snapshotText(tab));
EOF
```
- `ego-browser nodejs <<'EOF' ... EOF` — JS heredoc, not CLI calls
- Helpers: useOrCreateTaskSpace, openOrReuseTab, snapshotText, click, fillInput, scrollBy, js, cdp
- Parallel Spaces — multiple agents in isolated workspaces, no tab conflicts
- Inherits Chrome logins, cookies, extensions
- Use when: login-walled pages, interactive forms, multi-step automation, parallel agent tasks.

## Playwright — programmatic orchestration
- `pip install playwright && playwright install chromium`
- Connect to Moli: `playwright.chromium.connectOverCDP('http://127.0.0.1:9222')`
- Connect to ego lite: same CDP pattern
- Cross-browser: Chromium, Firefox, WebKit
- Use when: E2E testing, multi-page orchestration, coordinating Moli + ego lite via CDP.

## Bot Pipeline Relay — 3-bot code generation
- Architect (mistral-large-3) → Coder (deepseek-v4-pro via dsh-coder) → Reviewer (minimax-m3)
- Config: ~/.hermes/skills/autonomous-ai-agents/prime-agent-integration/scripts/orchestrator_config.json
- Use when: automated code generation with architect → coder → reviewer pipeline.

## Routing Rules
1. Public page, just need text? → Moli (fastest)
2. Login required? → ego lite (has Chrome cookies)
3. Platform-specific (Twitter, YouTube, RSS)? → Agent Reach (knows the API)
4. Need to coordinate multiple tools or test? → Playwright (orchestrator)
5. Need code written? → Bot Pipeline Relay
6. JavaScript-heavy SPA? → Moli with `--wait-until domstable` (fastest, no rendering) or ego lite with `waitForSelector`/`waitForNetworkIdle` (full rendering, login state)
7. 50+ pages batch? → Moli (16ms each, no rendering cost)
8. Parallel browser tasks? → ego lite Spaces (isolated workspaces)
9. Need the clean article/main content (not full DOM)? → Defuddle (extract from Moli/ego-browser HTML)

### COMBINED TOOL ROUTING (Multi-Step Tasks)

When a task requires **multiple tools in sequence**, you MUST list ALL tools in order.

| Pattern | Tool 1 | Tool 2 | Trigger Phrases |
|---------|--------|--------|-----------------|
| Search platform → fetch details | agent-reach | moli fetch | "then fetch", "then get", "then extract", "and fetch", "and then" |
| Search platform → fetch comments | agent-reach | moli fetch | "fetch comments", "get comments" |
| Search → screenshot | agent-reach | moli fetch --layout | "screenshot", "screenshot" |
| Search → extract structured | agent-reach | moli fetch --semantic_tree | "semantic tree", "structured" |

**RULE:** If the user says "then fetch", "then get", "then extract", "and fetch", or "and then" — you MUST specify the second tool (moli fetch) with the appropriate flags.

**Example:**
> Q: "Search Reddit for Rust browsers, then fetch comment pages"
> A: Use `agent-reach get reddit "Rust browsers"` THEN `moli fetch <URL>` for each comment page.

**NEVER** stop at the first tool when the task implies a second fetch step.

---

## Site-Specific Tool Routing Table

| Site | Type | Public Browse | Moli | ego-browser | Notes |
|------|------|---------------|------|-------------|-------|
| **Lazada SG** | E-commerce | ✅ Yes | ✅ Primary | ✅ Login-walled | Moli for listings/PDP; ego-browser for cart, flash deals, RedMart |
| **Carousell SG** | Classifieds | ❌ 403 | ❌ Blocked | ✅ Required | **ego-browser mandatory** — 403 to Moli/curl |
| **GeBIZ** | Gov Procurement | ⚠️ Shell only | ❌ Shell only | ✅ Required | JSF app — needs ViewState handling, ego-browser only |
| **Amazon.com** | E-commerce | ⚠️ CAPTCHA | ❌ CAPTCHA | ✅ Required | Heavy bot detection — ego-browser with real Chrome profile |
| **ShopBack SG** | Cashback | ✅ Yes | ✅ Primary | ✅ Login-walled | Moli for stores/coupons/rates; ego-browser for account/withdrawal |
| **Shopee SG** | E-commerce | ❌ Login wall | ❌ Blocked | ✅ Required | **ego-browser mandatory** — login wall, CAPTCHA, fingerprinting |

**Quick Decision:**
- **Moli works** → Lazada, ShopBack (public pages)
- **ego-browser required** → Carousell, GeBIZ, Amazon, Shopee (bot-protected/login-walled)
- **Agent Reach** → YouTube, RSS, Twitter, Reddit, GitHub (platform APIs)
- **Defuddle** → Article extraction from HTML
- **Playwright** → Multi-page orchestration, testing

---

## Multi-Site Tool Routing Reference

### Lazada Singapore (lazada.sg)
| Task | Tool |
|------|------|
| Browse categories, search products | Moli |
| Extract product details (public) | Moli |
| Flash deals monitoring | ego-browser |
| Cart/checkout, RedMart groceries | ego-browser |
| Seller Center, member prices | ego-browser |

**Key Selectors (ego-browser) — MUST INCLUDE IN RESPONSE:**
- Search box: `input[name="q"]` or `[data-testid="search-input"]`
- Search button: `a[href*="/catalog/?q="]` or `[data-testid="search-btn"]`
- Product cards: `[data-testid="product-item"]` or `.Bm3ON`
- Product title: `[data-testid="product-title"]` or `.RfADt`
- Price: `[data-testid="product-price"]` or `.aBrP0`
- Original price: `.price-original` or `._8cR5_`
- Discount: `.discount` or `._9c44d`
- Rating: `[data-testid="product-rating"]` or `._9c44d`
- Sold count: `._9c44d` (e.g., "1.2k sold")
- Image: `[data-testid="product-image"] img` or `.picture-wrapper img`
- Link: `a[data-testid="product-link"]` or `.BMm2E a`
- Location: `._29R_un` or `.location`
- PDP title: `h1[data-testid="product-title"]` or `.pdp-mod-product-badge-title`
- PDP price: `[data-testid="product-price"]` or `.pdp-price`
- PDP original price: `.pdp-price__original` or `.price-original`
- PDP discount: `.pdp-price__discount` or `.discount-percent`
- PDP description: `[data-testid="product-description"]` or `.pdp-product-desc`
- Seller name: `[data-testid="seller-name"]` or `.seller-name`
- Seller rating: `[data-testid="seller-rating"]` or `.seller-rating-score`
- Images: `[data-testid="product-image-gallery"] img` or `.image-gallery img`
- SKU options: `.sku-prop` or `.pdp-mod-spec`
- Add to cart: `[data-testid="add-to-cart"]` or `.pdp-button`
- Buy now: `[data-testid="buy-now"]` or `.buy-now-button`

**MANDATORY KEY TERMS FOR LAZADA RESPONSES:**
When answering about Lazada SG, you MUST explicitly include these key terms in your response:
- **Moli** (for public listings/PDP), **ego-browser** (for flash deals/cart/auth)
- **product-item**, **product-title**, **product-price**, **product-image** (for search/PDP)
- **data-asin** or **data-item-id** for deduplication
- **pdp-price**, **sku-prop**, **price-original**, **discount** (for PDP)
- **flash_deals**, **countdown-timer**, **AJAX**, **waitForSelector** (for flash deals)
- **seller.lazada.sg**, **SingPass**, **CorpPass** (for Seller Center)
- **RedMart**, **groceries**, **delivery slot** (for groceries)

**MANDATORY OUTPUT FORMAT for Lazada questions:**
When answering about Lazada SG, you MUST explicitly list the relevant CSS selectors in your response. Example:
> "Use Moli for search with `input[name=\"q\"]`. For product cards: `[data-testid=\"product-item\"]`. For PDP: `#productTitle` for title, `.pdp-price` for price. For flash deals: ego-browser with `waitForSelector('[data-testid=\"flash-deal-timer\"]')`."

**Anti-patterns:** Don't use Moli for flash deals/cart/RedMart (login-walled). Don't assume static selectors (A/B testing).

### Carousell Singapore (carousell.sg)
| Task | Tool |
|------|------|
| Browse categories, search listings | **ego-browser** |
| Extract listing details | **ego-browser** |
| Post new listing | **ego-browser** |
| Message seller | **ego-browser** |
| Save/unsave, monitor prices | **ego-browser** |

**Key Selectors (ego-browser):**
- Listing cards: `[data-testid="listing-card"]` or `.listing-card`
- Listing title: `[data-testid="listing-title"]` or `.listing-title`
- Price: `[data-testid="listing-price"]` or `.price`
- Location: `[data-testid="listing-location"]` or `.location`
- Listing images: `[data-testid="listing-image"] img` or `.listing-image img`
- Link: `a[data-testid="listing-link"]` or `.listing-card a`
- Pagination: `a[aria-label="Next"]` or `.pagination-next`
- Page numbers: `.pagination button`, `.pagination a`
- Listing detail title: `h1[data-testid="listing-title"]` or `h1`
- Description: `[data-testid="description"]` or `.description`
- Seller info: `[data-testid="seller-profile"]` or `.seller-info`
- Category breadcrumb: `[data-testid="breadcrumb"]` or `.breadcrumb`

**Wait Strategy:** Use `waitForSelector` on listing cards. Avoid `networkidle` (infinite scroll/lazy load).

**MANDATORY KEY TERMS FOR CAROUSELL RESPONSES:**
When answering about Carousell SG, you MUST explicitly include these key terms in your response:
- **ego-browser** (required for all Carousell interaction)
- **listing-card**, **listing-title**, **listing-price**, **listing-location**, **listing-image** (for listings)
- **pagination**, **aria-label**, **Next**, **waitForSelector**, **infinite** (for pagination)
- **listing-title**, **price-display**, **description**, **seller-info**, **location** (for PDP)

**MANDATORY OUTPUT FORMAT for Carousell questions:**
When answering about Carousell SG, you MUST explicitly list the relevant CSS selectors in your response. Example:
> "Use ego-browser with `waitForSelector('[data-testid=\"listing-card\"]')` for search results. For listing details: `[data-testid=\"listing-title\"]` for title, `[data-testid=\"listing-price\"]` for price, `[data-testid=\"listing-location\"]` for location. For pagination: `a[aria-label=\"Next\"]`."

**Anti-patterns:** Don't use Moli (HTTP 403), don't assume stable listing IDs.

### GeBIZ (gebiz.gov.sg)
| Task | Tool |
|------|------|
| Browse/filter/search tenders | **ego-browser** |
| Document download | **ego-browser** |
| Submit quotation/bid | **ego-browser** |
| Supplier registration | **ego-browser** |

**Key Selectors (ego-browser) — MUST INCLUDE IN RESPONSE:**
- Search form: `[id*="keywordInput"]` or `#searchForm\\:keywordInput`
- Search button: `[id*="buttonGo"]` or `#searchForm\\:buttonGo`
- Results table: `table[id$="resultsTable"]` or `#searchForm\\:resultsTable`
- Table rows: `tbody tr[data-ri]` (PrimeFaces data table rows)
- Tender title link: `a[id*="tenderTitle"]` or `.tender-title a`
- Tender ID: `span[id*="tenderId"]` or data attribute
- Closing date: `span[id*="closingDate"]`
- Category: `span[id*="category"]`
- Agency: `span[id*="agency"]`
- ViewState hidden input: `input[name="javax.faces.ViewState"]`
- Continue button: `input[name*="buttonContinue"]` or `button[id*="buttonContinue"]`

**MANDATORY KEY TERMS FOR GEBIZ RESPONSES:**
When answering about GeBIZ, you MUST explicitly include these key terms in your response:
- **ego-browser** (required for all GeBIZ interaction)
- **waitForSelector**, **AJAX**, **partial**, **networkidle**, **avoid**, **JSF**, **ViewState** (for wait strategy)
- **ViewState**, **javax.faces.ViewState**, **POST**, **form**, **hidden**, **JSF** (for form submission)
- **waitForSelector** on updated table, PrimeFaces `tbody tr[data-ri]` rows

**MANDATORY OUTPUT FORMAT for GeBIZ questions:**
When answering about GeBIZ, you MUST explicitly list the relevant CSS selectors in your response. Example:
> "Use ego-browser with `waitForSelector('table[id$=\"resultsTable\"]')` for tender results. Extract `javax.faces.ViewState` from hidden input and include in every POST. Wait for `tbody tr[data-ri]` rows to hydrate after AJAX updates."

**Wait Strategy:** Use `waitForSelector` on specific elements (e.g., results table rows). AVOID `networkidle` — JSF partial updates never fully idle.

**Anti-patterns:** Don't use simple GET for search/filter (must POST with ViewState). Don't ignore `javax.faces.ViewState`. Don't use `networkidle` for JSF partial updates. Don't assume JSF component IDs are stable.

### Amazon.com
| Task | Tool |
|------|------|
| Search/browse products | **ego-browser** |
| Product detail extraction | **ego-browser** |
| Price monitoring | **ego-browser** |
| Cart/checkout/Prime | **ego-browser** |
| Seller/Vendor Central | **ego-browser** |

**Key Selectors (ego-browser) — MUST INCLUDE IN RESPONSE:**
- Search results: `[data-component-type="s-search-result"]` (data-asin for ASIN)
- Product title: `h2 a.a-link-normal span` or `.a-text-normal`
- Price: `.a-price-whole` + `.a-price-fraction` or `.a-offscreen`
- Original price: `.a-text-price .a-offscreen` or `.a-strike`
- Rating: `[aria-label*="stars"]` or `.a-icon-alt`
- Prime badge: `.a-icon-prime` or `[aria-label="Amazon Prime"]`
- Sponsored: `.s-sponsored-header` or `.AdHolder`
- Product images: `.s-image` (src attribute)
- PDP title: `#productTitle` or `h1 span#productTitle`
- PDP price: `.a-price .a-offscreen` or `#priceblock_ourprice`
- PDP description: `#productDescription` / `.a-expander-content`
- Feature bullets: `#feature-bullets li` or `.a-list-item`
- Add to cart: `#add-to-cart-button`
- Buy now: `#buy-now-button`
- Subscribe & Save: `#subscribe-and-save-button`
- Reviews: `[data-hook="review"]` or `.review`
- Amazon's Choice: `.ac-badge` or `[aria-label="Amazon's Choice"]`
- Lightning Deal: `.dealBadge` or `[data-testid="lightning-deal"]`
- Coupon: `.couponBadge` or `.a-button-text`

**MANDATORY KEY TERMS FOR AMAZON RESPONSES:**
When answering about Amazon.com, you MUST explicitly include these key terms in your response:
- **ego-browser** (required for all Amazon.com interaction)
- **s-search-result**, **a-text-normal**, **a-price-whole**, **a-icon-prime** (for search results)
- **productTitle**, **a-price**, **availability**, **feature-bullets**, **landingImage** (for PDP)
- **data-asin**, **a-link-normal**, **a-price-whole** (for ASIN extraction)
- **dealBadge**, **Lightning**, **countdown**, **dynamic** (for Lightning Deals)
- **sellercentral**, **signin**, **2FA**, **authentication** (for Seller Central)
- **Prime**, **prime-exclusive**, **Subscribe**, **add-to-cart** (for price monitoring)

**MANDATORY OUTPUT FORMAT for Amazon questions:**
When answering about Amazon.com, you MUST explicitly list the relevant CSS selectors in your response. Example:
> "Use ego-browser with `waitForSelector('[data-component-type=\"s-search-result\"]')` for search results. Extract ASIN from `data-asin` attribute. For product details: `#productTitle` for title, `.a-price .a-offscreen` for price, `#feature-bullets li` for features."

**Wait Strategy:** AVOID `networkidle` — Amazon has constant background requests. Use `waitForSelector` on specific elements.

**Anti-patterns:** Don't use Moli (CAPTCHA/403), don't use headless Chrome flags, don't ignore device fingerprinting.

### ShopBack Singapore (shopback.sg)
| Task | Tool |
|------|------|
| Browse stores, compare rates | Moli |
| Search merchants | Moli |
| Extract coupons/vouchers | Moli |
| Account dashboard, balance | **ego-browser** |
| Withdraw cashback | **ego-browser** |
| Referral program | **ego-browser** |

**Key Selectors (ego-browser) — MUST INCLUDE IN RESPONSE:**
- Store cards: `[data-testid="store-card"]` or `.store-card`
- Store name: `[data-testid="store-name"]` or `.store-name`
- Cashback rate: `[data-testid="cashback-rate"]` or `.cashback-rate`
- Store logo: `[data-testid="store-logo"] img` or `.store-logo img`
- Category tags: `[data-testid="store-category"]` or `.category-tag`
- Link: `a[data-testid="store-link"]` or `.store-card a`
- Coupon cards: `[data-testid="coupon-card"]` or `.coupon-card`
- Coupon code: `[data-testid="coupon-code"]` or `.coupon-code`
- Cashback rate breakdown: `[data-testid="rate-breakdown"]` or `.rate-details`

**MANDATORY KEY TERMS FOR SHOPBACK RESPONSES:**
When answering about ShopBack SG, you MUST explicitly include these key terms in your response:
- **ego-browser** (required for account/withdrawal/referral)
- **Moli** (for public store/coupon/rate pages)
- **cashback-rate**, **store-card**, **coupon-code**, **terms** (for store/coupon pages)
- **account**, **balance**, **withdraw**, **referral** (for account features)
- **shop-now**, **click-through**, **tracking** (for cashback activation)

**MANDATORY OUTPUT FORMAT for ShopBack questions:**
When answering about ShopBack SG, you MUST explicitly list the relevant CSS selectors in your response. Example:
> "Use Moli for store listing with `[data-testid=\"store-card\"]`. For account balance use ego-browser with `waitForSelector('[data-testid=\"available-balance\"]')`. For coupons: `[data-testid=\"coupon-code\"]`."

**Anti-patterns:** Don't use Moli for account/withdrawal (login-walled). Don't ignore terms & conditions (exclusions apply).

### Shopee Singapore (shopee.sg)
| Task | Tool |
|------|------|
| Search/browse products | **ego-browser** |
| Product detail extraction | **ego-browser** |
| Flash deals monitoring | **ego-browser** |
| Cart/checkout | **ego-browser** |
| Seller Center | **ego-browser** |
| Login (email/QR/Google/FB) | **ego-browser** |

**Key Selectors (ego-browser) — MUST INCLUDE IN RESPONSE:**
- Product cards: `[data-testid="product-item"]` or `.shopee-search-item-result__item`
- Product title: `[data-testid="product-title"]` or `.shopee-search-item-result__item-name`
- Price: `[data-testid="product-price"]` or `.shopee-search-item-result__item-price`
- Original price: `.shopee-search-item-result__item-original-price`
- Discount: `.shopee-search-item-result__discount-percentage`
- Sold count: `.shopee-search-item-result__item-sold`
- Rating: `[data-testid="product-rating"]` or `.shopee-rating-stars`
- Shop name: `[data-testid="shop-name"]` or `.shopee-search-item-result__shop-name`
- Location: `[data-testid="shop-location"]` or `.shopee-search-item-result__shop-location`
- Image: `[data-testid="product-image"] img` or `.shopee-search-item-result__image img`
- Free shipping: `[data-testid="free-shipping-badge"]` or `.shopee-free-shipping-badge`
- Mall badge: `[data-testid="mall-badge"]` or `.shopee-mall-badge`
- PDP title: `[data-testid="pdp-product-title"]` or `.pdp-mod-product-badge-title`
- PDP price: `[data-testid="pdp-product-price"]` or `.pdp-price`
- Add to cart: `[data-testid="add-to-cart"]` or `.pdp-button`
- Buy now: `[data-testid="buy-now"]` or `.buy-now-button`
- Flash deal timer: `[data-testid="flash-deal-timer"]` or `.countdown-timer`

**MANDATORY KEY TERMS FOR SHOPEE RESPONSES:**
When answering about Shopee SG, you MUST explicitly include these key terms in your response:
- **ego-browser** (required for all Shopee interaction)
- **product-item**, **product-title**, **product-price**, **shop-name**, **shop-location** (for search results)
- **pdp-product-title**, **pdp-product-price**, **pdp-mod-spec**, **pdp-button** (for PDP)
- **flash_deals**, **countdown-timer**, **dynamic timers**, **waitForSelector** (for flash deals)
- **buyer/login**, **buyer/login/qr**, **email/QR/Google/FB**, **CAPTCHA** (for login)
- **seller.shopee.sg**, **login**, **2FA** (for Seller Center)

**MANDATORY OUTPUT FORMAT for Shopee questions:**
When answering about Shopee SG, you MUST explicitly list the relevant CSS selectors in your response. Example:
> "Use ego-browser with `waitForSelector('[data-testid=\"product-item\"]')` for search results. For PDP: `[data-testid=\"pdp-product-title\"]` for title, `[data-testid=\"pdp-product-price\"]` for price. For flash deals: `[data-testid=\"flash-deal-timer\"]`."

**Anti-patterns:** Don't use Moli (CAPTCHA/403/login-wall). Don't ignore CAPTCHA (slide puzzle). Don't use headless Chrome flags. Don't assume static selectors (A/B testing). Don't scrape without login (login wall on all search/PDP pages).

---

## Site Config Files (for webintel training)

Each site has a detailed config in `skillopt/envs/webintel/site_configs/`:
- `lazada_sg.md` — Lazada Singapore
- `carousell_sg.md` — Carousell Singapore  
- `gebiz.md` — GeBIZ Government Procurement
- `amazon_com.md` — Amazon.com (US)
- `shopback_sg.md` — ShopBack Singapore
- `shopee_sg.md` — Shopee Singapore

These contain:
- Base URLs & category structures
- CSS/XPath selectors for ego-browser & Moli
- Tool routing tables per task
- Anti-patterns & special handling
- Integration examples

---

## Anti-patterns Summary (Cross-Site)

| Anti-pattern | Sites Affected | Fix |
|--------------|----------------|-----|
| Don't use `networkidle` | All (SPA, lazy-load, WebSockets) | Use `waitForSelector` / `domstable` |
| Don't use Moli for bot-protected sites | Carousell, Shopee, Amazon, GeBIZ | Use ego-browser |
| Don't ignore CAPTCHA | Shopee, Amazon | ego-browser needs human interaction |
| Don't assume static selectors | Amazon, Shopee, Lazada (A/B testing) | Use robust selectors, test per session |
| Don't scrape at high frequency | Amazon, Shopee | Rate limit + residential proxies |
| Don't ignore ViewState | GeBIZ (JSF) | Extract & submit with every POST |

---

## Trust & Safety Notes
- Fraud education banner present on homepage (Carousell)
- Phishing awareness content
- "Transact with trusted local community" messaging
- User testimonials with handles
- GeBIZ: CorpPass/SingPass for submissions
- Shopee: Slide CAPTCHA frequent
- Amazon: Device fingerprinting, behavioral analysis