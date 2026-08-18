# Site: Lazada Singapore (lazada.sg)
**Type:** E-commerce marketplace (B2C + C2C) — electronics, fashion, home, beauty, groceries
**Auth:** Public browse OK; login required for cart, orders, seller center, flash deals
**Bot protection:** Moderate — Cloudflare challenge on some endpoints; Moli works for public listings but login-walled pages need ego-browser

---

## Base URLs
- **Root:** `https://www.lazada.sg/`
- **Search:** `https://www.lazada.sg/catalog/?q=<query>`
- **Categories:** `https://www.lazada.sg/<category-path>/`
- **Flash Deals:** `https://www.lazada.sg/flash_deals/`
- **Mall (Official Brands):** `https://www.lazada.sg/mall/`
- **Supermarket (Groceries):** `https://www.lazada.sg/groceries/`
- **Seller Center:** `https://sellercenter.lazada.sg/`

---

## Category Structure

### Electronics
- `/shop-computers-laptops/` — laptops, desktops, accessories
- `/shop-phones-tablets/` — smartphones, tablets, wearables
- `/shop-cameras/` — cameras, drones, audio
- `/shop-gaming/` — consoles, games, accessories
- `/shop-tv-home-theater/` — TVs, soundbars, projectors

### Fashion
- `/women-fashion/` — women's clothing, shoes, bags
- `/men-fashion/` — men's clothing, shoes, watches
- `/kids-fashion/` — kids' clothing, toys
- `/sports-outdoor/` — sports gear, outdoor equipment

### Home & Living
- `/home-living/` — furniture, decor, kitchen, bedding
- `/home-appliances/` — large & small appliances
- `/home-improvement/` — tools, hardware, lighting

### Beauty & Health
- `/beauty/` — skincare, makeup, haircare, fragrance
- `/health-wellness/` — vitamins, supplements, personal care

### Groceries (RedMart)
- `/groceries/` — fresh food, pantry, beverages, household

### Toys & Baby
- `/toys-games/` — toys, games, collectibles
- `/baby/` — diapers, formula, gear, nursery

---

## Selectors (ego-browser / Moli extraction)

### Product Cards (Search/Category Pages)
- **Container:** `[data-testid="product-item"]` or `.Bm3ON`
- **Title:** `[data-testid="product-title"]` or `.RfADt`
- **Price:** `[data-testid="product-price"]` or `.aBrP0`
- **Original Price:** `.price-original` or `._8cR5_`
- **Discount:** `.discount` or `._9c44d`
- **Rating:** `[data-testid="product-rating"]` or `._9c44d`
- **Sold Count:** `._9c44d` (e.g., "1.2k sold")
- **Image:** `[data-testid="product-image"] img` or `.picture-wrapper img`
- **Link:** `a[data-testid="product-link"]` or `.BMm2E a`
- **Location/Shipped From:** `._29R_un` or `.location`

### Pagination
- **Next Page:** `[data-testid="pagination-next"]` or `li.ant-pagination-next a`
- **Page Numbers:** `.ant-pagination-item a`
- **Total Pages:** `.ant-pagination-total-text`

### Product Detail Page
- **URL Pattern:** `https://www.lazada.sg/products/<product-name>-i<item_id>-s<sku_id>.html`
- **Alternative:** `https://www.lazada.sg/p/<product-id>.html`
- **Title:** `h1[data-testid="product-title"]` or `.pdp-mod-product-badge-title`
- **Price:** `[data-testid="product-price"]` or `.pdp-price`
- **Original Price:** `.pdp-price__original` or `.price-original`
- **Discount Badge:** `.pdp-price__discount` or `.discount-percent`
- **Description:** `[data-testid="product-description"]` or `.pdp-product-desc`
- **Seller Name:** `[data-testid="seller-name"]` or `.seller-name`
- **Seller Rating:** `[data-testid="seller-rating"]` or `.seller-rating-score`
- **Location:** `[data-testid="seller-location"]` or `.seller-location`
- **Images:** `[data-testid="product-image-gallery"] img` or `.image-gallery img`
- **SKU Options:** `.sku-prop` or `.pdp-mod-spec`
- **Add to Cart:** `[data-testid="add-to-cart"]` or `.pdp-button`
- **Buy Now:** `[data-testid="buy-now"]` or `.buy-now-button`

### Reviews
- **Review Container:** `[data-testid="review-item"]` or `.review-item`
- **Rating Stars:** `.review-rating` or `.star-rating`
- **Review Text:** `.review-content` or `.review-text`
- **Verified Purchase:** `.verified-purchase`

### Flash Deals
- **Timer:** `[data-testid="flash-deal-timer"]` or `.countdown-timer`
- **Progress Bar:** `.deal-progress` or `.progress-bar`
- **Claim Button:** `[data-testid="claim-deal"]` or `.claim-button`

### Auth-Required Elements
- **Login Button:** `[data-testid="login-btn"]`, `a[href*="/login"]`
- **Cart:** `[data-testid="cart-btn"]`, `.cart-icon`
- **Checkout:** `[data-testid="checkout-btn"]`, `.checkout-button`
- **Seller Center:** `https://seller.lazada.sg/`

---

## Tool Routing for Lazada Singapore

| Task | Tool | Rationale |
|------|------|-----------|
| Browse categories, extract listings | **Moli** (primary) | Public listings work; fast batch extraction |
| Search products | **Moli** | `/catalog/?q=<query>` works |
| Extract product details | **Moli** (primary) | Public product pages accessible |
| Flash deals monitoring | **ego-browser** | Dynamic timers, may need login for claims |
| Cart/checkout flow | **ego-browser** | Requires login, form interaction |
| Seller center operations | **ego-browser** | Login required, complex forms |
| Price monitoring (logged-in prices) | **ego-browser** | Member-only pricing |
| Groceries (RedMart) | **ego-browser** | Requires login, perishable inventory |
| Voucher/coupon application | **ego-browser** | Login-walled, dynamic |

**Key Rule:** Lazada public listings work with Moli. Use **ego-browser** for:
- Flash deals with dynamic timers
- Login-required pages (cart, checkout, seller center)
- Member-exclusive pricing/vouchers
- RedMart groceries (login-walled)

---

## Anti-patterns to Avoid
- Don't use `networkidle` for listing pages (infinite scroll / lazy load images)
- Don't assume product IDs are stable — use title + price + SKU for dedup
- Don't try to access Seller Center without login (ego-browser + SingPass/CorpPass)
- Don't assume flash deal timers are static — they update via AJAX
- Don't use Agent Reach (no Lazada tap installed)
- **Moli limitation:** Some product detail AJAX content may not render — use ego-browser for full detail

---

## Special Notes

### LazMall (Official Brand Stores)
- Verified authentic products
- Better return policy
- Selectors same but look for `.mall-badge` or `.official-store`

### Lazada Live / Video Commerce
- Live streaming sales
- Requires ego-browser for video + chat interaction

### RedMart (Groceries)
- Separate subdomain feel but same domain
- Delivery slot selection requires login
- Perishable inventory = real-time stock checks needed

### Voucher Stacking
- Platform vouchers + seller vouchers + bank offers
- Apply at checkout — test with ego-browser

### Price History
- Use Moli for public price tracking
- Member prices may differ — need ego-browser for comparison