# Carousell Singapore — Site Configuration

**Site:** Carousell Singapore (carousell.sg)  
**Type:** Classifieds marketplace (C2C + B2C) — goods, cars, property, services  
**Auth:** Public browse OK; login required for posting, messaging, saved searches

---

## Base URLs
- **Root:** `https://www.carousell.sg/`
- **Search:** `https://www.carousell.sg/search/<query>?type=trending`
- **Categories:** `https://www.carousell.sg/<category-path>`

---

## Category Structure

### Electronics
- `/electronics` — general electronics
- `/smart_render/?name=ap-mobiles-gadgets&t-source=homepage&type=market-landing-page` — mobiles & gadgets landing

### Fashion
- `/womens-fashion/h-2/` — women's fashion
- `/men-s-fashion/h-6/` — men's fashion
- `/luxury/h-9/` — luxury (certified luxury watches at `/categories/luxury-20/certified-luxury-watches-256/`)

### Home & Services (major vertical)
- `/home-and-services/` — home services root
- `/categories/home-services-1306/renovations-1317/full-home-renovation-6315/hdb-renovation-6371/` — HDB renovation
- `/categories/home-services-1306/renovations-1317/full-home-renovation-6315/bto-renovation-6372/` — BTO renovation
- `/categories/home-services-1306/renovations-1317/full-home-renovation-6315/condo-renovation-6373/` — condo renovation
- `/categories/home-services-1306/renovations-1317/toilet-renovation-6316/` — toilet renovation
- `/categories/home-services-1306/renovations-1317/carpentry-6317/` — carpentry
- `/categories/home-services-1306/renovations-1317/painting-wallpaper-6318/` — painting & wallpaper
- `/categories/home-services-1306/aircon-services-1313/` — aircon services
- `/categories/home-services-1306/renovations-1317/interior-design-services-6319/` — interior design
- `/categories/home-services-1306/renovations-1317/aluminium-work-6320/` — aluminium work
- `/categories/home-services-1306/renovations-1317/flooring-6324/` — flooring (laminate/epoxy/parquet/vinyl)
- `/categories/home-services-1306/home-repairs-1315/plumbing-services-6331/` — plumbing
- `/categories/home-services-1306/home-repairs-1315/electrician-services-6332/` — electrician
- `/categories/home-services-1306/home-repairs-1315/handyman-and-drilling-services-6334/` — handyman
- `/categories/home-services-1306/home-cleaning-1312/deep-cleaning-services-6349/` — deep cleaning
- `/categories/home-services-1306/movers-delivery-1316/furniture-movers-6361/` — furniture movers
- `/categories/home-services-1306/movers-delivery-1316/house-moving-6362/` — house moving

### Cars
- `/used-cars-singapore/h-1233/` — used cars root
- `/cars/used-cars-for-sale/toyota/` — Toyota
- `/cars/used-cars-for-sale/mercedes-benz/` — Mercedes-Benz
- `/cars/used-cars-for-sale/honda/` — Honda
- `/cars/used-cars-for-sale/audi/` — Audi
- `/cars/used-cars-for-sale/bmw/` — BMW
- `/cars/used-cars-for-sale/hyundai/` — Hyundai
- `/cars/used-cars-for-sale/kia/` — Kia
- `/cars/used-cars-for-sale/mitsubishi/` — Mitsubishi
- `/cars/used-cars-for-sale/nissan/` — Nissan
- `/cars/used-cars-for-sale/volkswagen/` — Volkswagen
- `/cars/used-cars-for-sale/lexus/` — Lexus
- `/cars/used-cars-for-sale/mazda/` — Mazda
- `/cars/used-cars-for-sale/suzuki/` — Suzuki

**Popular models:**
- `/cars/used-cars-for-sale/toyota/wish/` — Toyota Wish
- `/cars/used-cars-for-sale/toyota/noah-hybrid/` — Toyota Noah Hybrid
- `/cars/used-cars-for-sale/toyota/alphard/` — Toyota Alphard
- `/cars/used-cars-for-sale/toyota/sienta/` — Toyota Sienta
- `/cars/used-cars-for-sale/honda/civic/` — Honda Civic
- `/cars/used-cars-for-sale/honda/fit/` — Honda Fit
- `/cars/used-cars-for-sale/honda/vezel/` — Honda Vezel
- `/cars/used-cars-for-sale/mercedes-benz/a-class-hatchback/` — Mercedes A-Class
- `/cars/used-cars-for-sale/hyundai/avante/` — Hyundai Avante
- `/cars/used-cars-for-sale/suzuki/swift/` — Suzuki Swift

### Property
- `/property-for-sale/h-377/` — property for sale

---

## Listing Patterns
- **Listing page:** `/p/<listing-id>` or `/u/<username>/<slug>`
- **User profile:** `/u/<username>/`
- **Category listing:** paginated, `?page=N`

---

## Selectors (for ego-browser / Moli extraction)

### Listing cards (search/category pages)
- **Listing container:** `[data-testid="listing-card"]` or `.listing-card`
- **Title:** `[data-testid="listing-title"]` or `.listing-title`
- **Price:** `[data-testid="listing-price"]` or `.price`
- **Location:** `[data-testid="listing-location"]` or `.location`
- **Image:** `[data-testid="listing-image"] img` or `.listing-image img`
- **Link:** `a[data-testid="listing-link"]` or `.listing-card a`

### Pagination
- **Next page:** `a[aria-label="Next"]` or `.pagination-next`
- **Page numbers:** `.pagination button`, `.pagination a`

### Listing detail page
- **Title:** `h1[data-testid="listing-title"]` or `h1`
- **Price:** `[data-testid="price"]` or `.price-display`
- **Description:** `[data-testid="description"]` or `.description`
- **Seller info:** `[data-testid="seller-profile"]` or `.seller-info`
- **Location:** `[data-testid="location"]` or `.location`
- **Category breadcrumb:** `[data-testid="breadcrumb"]` or `.breadcrumb`
- **Images:** `[data-testid="image-gallery"] img` or `.gallery img`

### Auth-required elements
- **Login button:** `[data-testid="login-btn"]`, `a[href*="/login"]`
- **Post listing:** `[data-testid="sell-btn"]`, `a[href*="/sell"]`
- **Chat/message:** `[data-testid="chat-btn"]`, `button:has-text("Chat")`
- **Save listing:** `[data-testid="save-btn"]`, `button:has-text("Save")`

---

## Tool Routing for Carousell

**IMPORTANT: Carousell blocks non-browser fetchers (Moli, curl) with HTTP 403.**
Use **ego-browser** (real Chrome, passes bot detection) for ALL Carousell
interaction. Moli cannot fetch Carousell — verified live (403 + domstable timeout).

| Task | Tool | Rationale |
|------|------|-----------|
| Browse categories, extract listings | **ego-browser** | Carousell 403-blocks Moli; real browser passes bot detection |
| Search listings | **ego-browser** | `/search/<query>` — 403 to Moli, works in real browser |
| Extract listing details | **ego-browser** | Public listing pages — 403 to Moli |
| Post new listing | **ego-browser** | Requires login, form filling |
| Message seller | **ego-browser** | Requires login, chat interaction |
| Save/unsave listings | **ego-browser** | Requires login |
| Monitor price drops | **ego-browser** (scheduled) | 403 to Moli |
| Scrape 50+ listings | **ego-browser** | Real browser, handles lazy-load |
| Competitor analysis (logged-in dashboard) | **ego-browser** | Login-walled |

**General rule:** If a site returns 403 to Moli/curl (bot-protected: Carousell,
many marketplaces, Cloudflare-fronted sites), route to **ego-browser** — it
inherits real Chrome login state and passes bot detection. Moli is only for
sites that allow non-browser fetches.

---

## Anti-patterns to Avoid
- Don't use `networkidle` wait for listing pages (infinite scroll / lazy load)
- Don't try to POST to listing creation without login (ego-browser required)
- Don't use Agent Reach (no Carousell tap installed)
- Don't assume `/p/<id>` is stable — use listing title + price for dedup
- **Don't use Moli for Carousell** — it returns HTTP 403 (bot-protected). Use ego-browser.

---

## Trust & Safety Notes
- Fraud education banner present on homepage
- Phishing awareness content
- "Transact with trusted local community" messaging
- User testimonials with handles