# Site: Amazon.com (United States)
**Type:** E-commerce marketplace (B2C + 3P sellers) — everything: electronics, books, fashion, home, groceries, AWS, Prime Video, Prime, etc.
**Auth:** Public browse OK; login required for cart, orders, Prime benefits, subscriptions, seller central
**Bot protection:** Heavy — aggressive bot detection (CAPTCHA, fingerprinting, rate limiting); Moli often blocked; ego-browser with real Chrome profile required for reliable access

---

## Base URLs
- **Root:** `https://www.amazon.com/`
- **Search:** `https://www.amazon.com/s?k=<query>`
- **Categories:** `https://www.amazon.com/b?node=<category_id>`
- **Prime Deals:** `https://www.amazon.com/primeday` / `https://www.amazon.com/deals`
- **Today's Deals:** `https://www.amazon.com/gp/goldbox`
- **Amazon Fresh (Groceries):** `https://www.amazon.com/alm/storefront`
- **Amazon Pharmacy:** `https://www.amazon.com/pharmacy`
- **AWS Console:** `https://console.aws.amazon.com/`
- **Seller Central:** `https://sellercentral.amazon.com/`
- **Vendor Central:** `https://vendorcentral.amazon.com/`

---

## Category Structure (Key Browse Nodes)

### Electronics
- **Computers & Accessories:** `node=565108` (laptops, desktops, monitors, components)
- **Cell Phones & Accessories:** `node=2407749011` (smartphones, cases, chargers)
- **TV & Video:** `node=172659` (TVs, streaming devices, home theater)
- **Camera & Photo:** `node=62390011` (cameras, lenses, drones, audio)
- **Video Games:** `node=468642` (consoles, games, accessories)
- **Wearable Tech:** `node=133141011` (smartwatches, fitness trackers)

### Home & Kitchen
- **Kitchen & Dining:** `node=284507` (appliances, cookware, gadgets)
- **Furniture:** `node=1063386` (living, bedroom, office, outdoor)
- **Home Decor:** `node=1063384` (lighting, bedding, bath, storage)
- **Tools & Home Improvement:** `node=552744` (power tools, hardware, plumbing)

### Fashion
- **Women's Fashion:** `node=7141123011`
- **Men's Fashion:** `node=7147441011`
- **Shoes:** `node=7147442011` (sneakers, boots, dress, sandals)
- **Watches:** `node=3937722011`
- **Jewelry:** `node=6358539011`

### Beauty & Personal Care
- **Skincare:** `node=11057241`
- **Makeup:** `node=11057881`
- **Hair Care:** `node=11057481`
- **Fragrance:** `node=11057561`

### Grocery & Consumables
- **Amazon Fresh:** `node=16310101` (fresh, perishable - login required)
- **Pantry Staples:** `node=16310091`
- **Household Essentials:** `node=16310211`

### Books & Media
- **Books:** `node=283155` (physical, Kindle, Audible)
- **Movies & TV:** `node=2625373011` (Prime Video, DVD/Blu-ray)
- **Music:** `node=165793011` (CDs, vinyl, digital)
- **Video Games:** `node=468642`

### Automotive & Industrial
- **Automotive:** `node=15684181` (parts, accessories, tools)
- **Industrial & Scientific:** `node=8387476011`

---

## Selectors (ego-browser / Moli extraction)

### Search Results (Grid/List View)
- **Container:** `[data-component-type="s-search-result"]` or `.s-result-item`
- **ASIN:** `data-asin` attribute on container
- **Title:** `h2 a.a-link-normal span` or `.a-text-normal`
- **Price (whole):** `.a-price-whole` or `.a-offscreen`
- **Price (fraction):** `.a-price-fraction`
- **Original Price:** `.a-text-price .a-offscreen` or `.a-strike`
- **Rating:** `[aria-label*="stars"]` or `.a-icon-alt`
- **Review Count:** `[aria-label*="reviews"]` or `.a-size-base`
- **Prime Badge:** `.a-icon-prime` or `[aria-label="Amazon Prime"]`
- **Sponsored Badge:** `.s-sponsored-header` or `.AdHolder`
- **Image:** `.s-image` (src attribute)
- **Link:** `h2 a.a-link-normal` (href)
- **Delivery:** `.a-color-base` (e.g., "FREE delivery Tomorrow")

### Pagination
- **Next Page:** `.s-pagination-next` or `a[aria-label="Go to next page"]`
- **Page Numbers:** `.s-pagination-item`
- **Current Page:** `.s-pagination-selected`

### Product Detail Page (PDP)
- **Title:** `#productTitle` or `h1 span#productTitle`
- **Price:** `.a-price .a-offscreen` or `#priceblock_ourprice` / `#priceblock_dealprice`
- **Original Price:** `.a-text-price .a-offscreen` or `.a-strike`
- **Availability:** `#availability` or `#ddmDeliveryMessage`
- **Brand:** `#bylineInfo` or `.a-link-normal` (brand link)
- **Description:** `#productDescription` / `.a-expander-content`
- **Feature Bullets:** `#feature-bullets li` or `.a-list-item`
- **Images:** `#landingImage` / `#imgBlkFront` / `#main-image` (data-a-dynamic-image JSON)
- **Variations:** `#variation_color_name` / `#variation_size_name` / `twister-js-init-dp`
- **Add to Cart:** `#add-to-cart-button` / `#submit.add-to-cart`
- **Buy Now:** `#buy-now-button` / `#buybox-see-all-buying-choices`
- **Subscribe & Save:** `#subscribe-and-save-button` / `#sns-accordion`

### Reviews
- **Review Container:** `[data-hook="review"]` or `.review`
- **Rating:** `[data-hook="review-star-rating"]` or `.a-icon-alt`
- **Title:** `[data-hook="review-title"]` or `.review-title`
- **Body:** `[data-hook="review-body"]` or `.review-text`
- **Verified Purchase:** `[data-hook="avp-badge"]` or `.a-color-state`
- **Date:** `[data-hook="review-date"]` or `.review-date`
- **Helpful Votes:** `[data-hook="helpful-vote-statement"]`

### Amazon's Choice / Best Seller Badges
- **Amazon's Choice:** `.ac-badge` or `[aria-label="Amazon's Choice"]`
- **Best Seller:** `#SalesRank` or `.zg-badge-text`

### Deals / Coupons
- **Lightning Deal:** `.dealBadge` or `[data-testid="lightning-deal"]`
- **Coupon Badge:** `.couponBadge` or `.a-button-text` (clip coupon)
- **Deal Price:** `.dealPriceText` or `.a-price .a-offscreen`

### Auth-Required Elements
- **Sign In:** `#nav-link-accountList` / `a[href*="signin"]`
- **Cart:** `#nav-cart` / `a[href*="/gp/cart"]`
- **Checkout:** `#proceed-to-checkout-button` / `#hlb-ptc-btn`
- **Prime Membership:** `#prime-link` / `a[href*="/prime"]`
- **Subscribe & Save:** `#sns-accordion` / `a[href*="sns"]`

---

## Tool Routing for Amazon.com

| Task | Tool | Rationale |
|------|------|-----------|
| Browse/search public listings | **ego-browser** (primary) | Heavy bot protection; Moli often gets CAPTCHA/403 |
| Extract product details | **ego-browser** | PDP renders dynamically; anti-scraping measures |
| Price monitoring | **ego-browser** (scheduled) | Price changes via AJAX; login for Prime prices |
| Cart/checkout automation | **ego-browser** | Requires login, 2FA, address/payment selection |
| Subscribe & Save management | **ego-browser** | Login-walled, recurring orders |
| Seller Central operations | **ego-browser** | Login + 2FA, complex dashboards |
| Vendor Central | **ego-browser** | Enterprise login, complex forms |
| AWS Console | **ego-browser** | Separate domain, MFA required |
| Product review scraping | **ego-browser** | Infinite scroll, login for verified filter |
| Deal monitoring (Lightning/Prime Day) | **ego-browser** | Dynamic timers, limited quantity |

**Key Rule:** Amazon's bot detection is among the most aggressive. **Always use ego-browser** with a real Chrome profile that has:
- Existing Amazon login cookies
- Real user agent
- No headless flags
- Residential IP preferred

Moli will almost always hit CAPTCHA or 403 on Amazon.

---

## Anti-patterns to Avoid
- **Don't use Moli for Amazon** — will hit CAPTCHA/Challenge within 1-2 requests
- **Don't use `networkidle`** — Amazon has constant background requests (analytics, ads, recommendations)
- **Don't scrape at high frequency** — aggressive rate limiting (IP + fingerprint)
- **Don't ignore ASIN** — canonical identifier; use for dedup across regions
- **Don't assume static selectors** — Amazon A/B tests heavily; selectors change by user cohort
- **Don't use headless Chrome flags** — `--headless` is detected; use `--disable-blink-features=AutomationControlled`
- **Don't scrape reviews without login** — verified purchase filter requires auth
- **Don't ignore variation data** — color/size/bundle changes price & availability

---

## Special Considerations

### Regional Variants
- **Amazon.com** (US) — this config
- **Amazon.ca** (Canada) — similar structure, different ASINs sometimes
- **Amazon.co.uk** (UK) — similar, different browse nodes
- **Amazon.de** (Germany) — similar, GDPR consent banners
- **Amazon.co.jp** (Japan) — different layout, Japanese selectors

### Prime / Membership Tiers
- **Prime:** Free 1-2 day, Prime Video, Prime Reading, Prime Gaming
- **Prime Student:** Discounted Prime
- **Amazon Fresh/Whole Foods:** Separate grocery fulfillment
- **Prime Pantry:** Discontinued (merged into Fresh)

### Advertising / Sponsored Products
- **Sponsored Products:** `spc` / `sponsored` in URL, `AdHolder` class
- **Sponsored Brands:** Header banner with brand logo + multiple products
- **Sponsored Display:** Retargeting ads on/off Amazon
- Filter out via `.sponsored` / `.AdHolder` / `data-component-type="sp-sponsored-result"`

### Amazon Business (B2B)
- **Business pricing:** Quantity discounts, tax exemption
- **Separate checkout:** `business.amazon.com`
- **Analytics:** Purchase reporting, approval workflows

### FBA / Seller Metrics
- **Buy Box:** Algorithmic; price + shipping + seller rating + Prime
- **FBA vs FBM:** Fulfilled by Amazon vs Merchant fulfilled
- **Seller rating:** `% positive feedback last 12 months`
- **Account health:** ODR, late shipment, cancellation rate

### Amazon Vine / Early Reviewer
- **Vine Voices:** Invite-only, free products for reviews
- **Early Reviewer Program:** Incentivized reviews for new products
- Badge: `Vine Customer Review of Free Product`

### Anti-Scraping Measures
- **CAPTCHA:** Image/audio puzzle, triggered by rate/fingerprint
- **Device Fingerprinting:** Canvas, WebGL, fonts, audio context
- **Behavioral Analysis:** Mouse movements, scroll patterns, click timing
- **IP Reputation:** Datacenter IPs flagged; residential proxies needed
- **Header Analysis:** Missing/incorrect headers trigger blocks
- **Cookie Validation:** Valid session cookies required for PDP

---

## Quick Reference: Key ASINs for Testing

| Product | ASIN | Category |
|---------|------|----------|
| iPhone 15 Pro | B0CHX1W1XY | Electronics |
| Kindle Paperwhite | B09V45Y1JC | Electronics |
| Instant Pot Duo | B00FLYWNYQ | Kitchen |
| Fire TV Stick 4K | B079QHML21 | Streaming |
| Echo Dot (5th Gen) | B09B8V1LZ3 | Smart Home |

---

## Environment Variables for Testing

```bash
# Use a real Chrome profile with Amazon login
export CHROME_USER_DATA_DIR="/path/to/chrome-profile-with-amazon-login"
export CHROME_PROFILE_DIR="Profile 1"

# Or launch ego-browser with existing profile
ego-browser nodejs --user-data-dir="$CHROME_USER_DATA_DIR" --profile-directory="$CHROME_PROFILE_DIR"
```

---

## Integration with SkillOpt

Add to webintel config:
```yaml
env:
  site_config: skillopt/envs/webintel/site_configs/amazon_com.md
  skill_template: skillopt/envs/webintel/skills/initial.md
```