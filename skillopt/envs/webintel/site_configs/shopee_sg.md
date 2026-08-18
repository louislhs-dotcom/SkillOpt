# Site: Shopee Singapore (shopee.sg)
**Type:** E-commerce marketplace (B2C + C2C) — electronics, fashion, home, beauty, groceries
**Auth:** Public browse limited; login required for search results, product details, cart, checkout, flash deals, seller center
**Bot protection:** Heavy — aggressive bot detection (CAPTCHA, fingerprinting, rate limiting); Moli blocked; ego-browser with real Chrome profile required for reliable access

---

## Base URLs
- **Root:** `https://www.shopee.sg/`
- **Search:** `https://shopee.sg/search?keyword=<query>`
- **Categories:** `https://www.shopee.sg/<category-path>/`
- **Flash Deals:** `https://www.shopee.sg/flash_deals/`
- **Mall (Official Brands):** `https://www.shopee.sg/mall/`
- **Supermarket (Groceries):** `https://www.shopee.sg/groceries/`
- **Product Detail:** `https://www.shopee.sg/<product-name>-i.<item_id>.<shop_id>`
- **Seller Center:** `https://seller.shopee.sg/`
- **Login:** `https://shopee.sg/buyer/login`
- **QR Login:** `https://shopee.sg/buyer/login/qr`

---

## Category Structure (Key Categories)

### Electronics
- **Computers & Accessories:** `/Computers-Accessories-cat.15006` (laptops, phones, tablets, accessories)
- **Consumer Electronics:** `/Consumer-Electronics-cat.15007` (audio, cameras, drones, wearables)
- **Gaming:** `/Gaming-cat.15008` (consoles, games, accessories)

### Fashion
- **Women's Fashion:** `/Women's-Fashion-cat.15013` (clothing, shoes, bags, accessories)
- **Men's Fashion:** `/Men's-Fashion-cat.15014` (clothing, shoes, watches)
- **Shoes:** `/Shoes-cat.15015` (sneakers, boots, sandals)
- **Bags & Accessories:** `/Bags-Accessories-cat.15016`

### Home & Living
- **Home & Living:** `/Home-Living-cat.15017` (furniture, decor, kitchen, bedding)
- **Home Appliances:** `/Home-Appliances-cat.15018`
- **Home Improvement:** `/Home-Improvement-cat.15019` (tools, hardware, lighting)

### Beauty & Personal Care
- **Beauty:** `/Beauty-cat.15010` (skincare, makeup, haircare, fragrance)
- **Health:** `/Health-cat.15011` (vitamins, supplements, personal care)

### Groceries & Essentials
- **Supermarket:** `/Supermarket-cat.15012` (fresh food, pantry, beverages, household)

### Toys, Kids & Baby
- **Toys & Games:** `/Toys-Games-cat.15020`
- **Baby & Parenting:** `/Baby-Parenting-cat.15021`

### Sports & Travel
- **Sports & Outdoors:** `/Sports-Outdoors-cat.15022`
- **Travel:** `/Travel-cat.15023`

---

## Selectors (ego-browser only — Moli blocked)

### Search Results / Category Pages
- **Product Container:** `[data-testid="product-item"]` or `.shopee-search-item-result__item`
- **Product Link:** `a[data-testid="product-item-link"]` or `.shopee-search-item-result__item a`
- **Product Title:** `[data-testid="product-title"]` or `.shopee-search-item-result__item-name`
- **Price:** `[data-testid="product-price"]` or `.shopee-search-item-result__item-price`
- **Original Price:** `.shopee-search-item-result__item-original-price`
- **Discount:** `.shopee-search-item-result__discount-percentage`
- **Sold Count:** `.shopee-search-item-result__item-sold`
- **Rating:** `[data-testid="product-rating"]` or `.shopee-rating-stars`
- **Shop Name:** `[data-testid="shop-name"]` or `.shopee-search-item-result__shop-name`
- **Location:** `[data-testid="shop-location"]` or `.shopee-search-item-result__shop-location`
- **Image:** `[data-testid="product-image"] img` or `.shopee-search-item-result__image img`
- **Free Shipping Badge:** `[data-testid="free-shipping-badge"]` or `.shopee-free-shipping-badge`
- **Mall Badge:** `[data-testid="mall-badge"]` or `.shopee-mall-badge`

### Pagination
- **Next Page:** `button.shopee-button-solid.shopee-button-solid--primary` (next button)
- **Page Numbers:** `.shopee-page-controller button`
- **Page Input:** `input.shopee-page-controller-input`

### Product Detail Page (PDP)
- **Title:** `[data-testid="pdp-product-title"]` or `.pdp-mod-product-badge-title`
- **Price:** `[data-testid="pdp-product-price"]` or `.pdp-price`
- **Original Price:** `.pdp-price__original` or `.price-original`
- **Discount Badge:** `.pdp-price__discount` or `.discount-percent`
- **Description:** `[data-testid="pdp-description"]` or `.pdp-product-desc`
- **Seller Name:** `[data-testid="shop-name"]` or `.pdp-mod-shop-name`
- **Seller Rating:** `[data-testid="shop-rating"]` or `.pdp-mod-shop-rating`
- **Location:** `[data-testid="shop-location"]` or `.pdp-mod-shop-location`
- **Images:** `[data-testid="product-image-gallery"] img` or `.image-gallery img`
- **SKU Options:** `.sku-prop` or `.pdp-mod-spec`
- **Add to Cart:** `[data-testid="add-to-cart"]` or `.pdp-button`
- **Buy Now:** `[data-testid="buy-now"]` or `.buy-now-button`

### Reviews
- **Review Container:** `[data-testid="review-item"]` or `.shopee-product-rating`
- **Rating Stars:** `.review-rating` or `.star-rating`
- **Review Text:** `.review-content` or `.review-text`
- **Verified Purchase:** `.verified-purchase`

### Flash Deals
- **Timer:** `[data-testid="flash-deal-timer"]` or `.countdown-timer`
- **Progress Bar:** `.deal-progress` or `.progress-bar`
- **Claim Button:** `[data-testid="claim-deal"]` or `.claim-button`

### Auth-Required Elements
- **Login Button:** `[data-testid="login-btn"]`, `a[href*="/buyer/login"]`
- **Cart:** `[data-testid="cart-btn"]`, `.cart-icon`
- **Checkout:** `[data-testid="checkout-btn"]`, `.checkout-button`
- **Seller Center:** `https://seller.shopee.sg/`
- **Flash Deals Claim:** Requires login

### Login Page
- **Email/Phone Input:** `input[name="loginKey"]`
- **Password Input:** `input[name="password"]`
- **Login Button:** `button[type="submit"]` (text "LOG IN")
- **QR Code Link:** `a[href*="/buyer/login/qr"]`
- **Google Login:** `button[aria-label="Google"]`
- **Facebook Login:** `button[aria-label="Facebook"]`

---

## Tool Routing for Shopee Singapore

| Task | Tool | Rationale |
|------|------|-----------|
| Browse/search public listings | **ego-browser** (primary) | Heavy bot protection; Moli gets CAPTCHA/403 |
| Extract product details | **ego-browser** | PDP renders dynamically; anti-scraping measures |
| Price monitoring | **ego-browser** (scheduled) | Price changes via AJAX; login for member prices |
| Cart/checkout automation | **ego-browser** | Requires login, 2FA, address/payment selection |
| Subscribe & Save management | **ego-browser** | Login-walled, recurring orders |
| Seller Center operations | **ego-browser** | Login + 2FA, complex dashboards |
| Product review scraping | **ego-browser** | Infinite scroll, login for verified filter |
| Deal monitoring (Lightning/Flash) | **ego-browser** | Dynamic timers, limited quantity |
| Login/Account access | **ego-browser** | Requires credentials, CAPTCHA handling |

**Key Rule:** Shopee's bot detection is among the most aggressive in SEA. **Always use ego-browser** with a real Chrome profile that has:
- Existing Shopee login cookies (from your regular Chrome profile)
- Real user agent
- No headless flags
- Residential IP preferred

Moli will almost always hit CAPTCHA or 403 on Shopee.

---

## Login Options

1. **Email/Password:** `input[name="loginKey"]` + `input[name="password"]` → click `button[type="submit"]`
2. **QR Code:** Click `a[href*="/buyer/login/qr"]` → scan with Shopee app
3. **Google Login:** Click `button[aria-label="Google"]` → OAuth flow
4. **Facebook Login:** Click `button[aria-label="Facebook"]` → OAuth flow

---

## Anti-patterns to Avoid
- **Don't use Moli for Shopee** — will hit CAPTCHA/Challenge within 1-2 requests
- **Don't use `networkidle`** — Shopee has constant background requests (analytics, ads, recommendations)
- **Don't scrape at high frequency** — aggressive rate limiting (IP + fingerprint)
- **Don't ignore CAPTCHA** — slide puzzle appears frequently; ego-browser needs human interaction or retry
- **Don't assume static selectors** — Shopee A/B tests heavily; selectors change by user cohort
- **Don't use headless Chrome flags** — `--headless` is detected; use `--disable-blink-features=AutomationControlled`
- **Don't scrape reviews without login** — verified purchase filter requires auth
- **Don't ignore variation data** — color/size/bundle changes price & availability
- **Don't scrape without login** — search results and product pages show "Login Required" modal

---

## Special Considerations

### Shopee Mall (Official Brand Stores)
- Verified authentic products
- Better return policy
- Selectors same but look for `.mall-badge` or `.official-store`

### Shopee Live / Video Commerce
- Live streaming sales
- Requires ego-browser for video + chat interaction

### Shopee Pay / SPayLater
- BNPL option at checkout
- Separate from cashback earning

### Voucher Stacking
- Platform vouchers + seller vouchers + bank offers
- Apply at checkout — test with ego-browser

### Price History
- Use ego-browser for public price tracking
- Member prices may differ — need ego-browser for comparison

### Shopee Pay / Wallet
- Digital wallet for payments
- Cashback credits stored here
- Separate from marketplace balance

---

## Environment Variables for Testing

```bash
# Use a real Chrome profile with Shopee login
export CHROME_USER_DATA_DIR="/path/to/chrome-profile-with-shopee-login"
export CHROME_PROFILE_DIR="Profile 1"

# Or launch ego-browser with existing profile
ego-browser nodejs --user-data-dir="$CHROME_USER_DATA_DIR" --profile-directory="$CHROME_PROFILE_DIR"
```

---

## Integration with SkillOpt

Add to webintel config:
```yaml
env:
  site_config: skillopt/envs/webintel/site_configs/shopee_sg.md
  skill_template: skillopt/envs/webintel/skills/initial.md
```