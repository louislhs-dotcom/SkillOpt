# Site: ShopBack Singapore (shopback.sg)
**Type:** Cashback & coupon platform — earn cashback on purchases from partner merchants (e-commerce, travel, food delivery, groceries)
**Auth:** Public browse OK; login required for cashback tracking, withdrawal, claiming coupons, referral
**Bot protection:** Moderate — some endpoints have rate limiting; Moli works for public merchant listings but login-walled pages (account, withdrawal) need ego-browser

---

## Base URLs
- **Root:** `https://www.shopback.sg/`
- **All Stores:** `https://www.shopback.sg/stores`
- **Categories:** `https://www.shopback.sg/categories`
- **Coupons/Vouchers:** `https://www.shopback.sg/coupons`
- **Cashback Rates:** `https://www.shopback.sg/rates`
- **Account Dashboard:** `https://www.shopback.sg/account` (login required)
- **Withdrawal:** `https://www.shopback.sg/withdraw` (login required)
- **Referral:** `https://www.shopback.sg/referral` (login required)
- **Help Center:** `https://help.shopback.sg/`

---

## Category Structure

### E-commerce Marketplaces
- **Lazada:** `https://www.shopback.sg/lazada`
- **Shopee:** `https://www.shopback.sg/shopee`
- **Amazon:** `https://www.shopback.sg/amazon`
- **Qoo10:** `https://www.shopback.sg/qoo10`
- **Zalora:** `https://www.shopback.sg/zalora`

### Travel & Transport
- **Agoda:** `https://www.shopback.sg/agoda`
- **Booking.com:** `https://www.shopback.sg/booking-com`
- **Klook:** `https://www.shopback.sg/klook`
- **Grab:** `https://www.shopback.sg/grab`
- **Gojek:** `https://www.shopback.sg/gojek`
- **Trip.com:** `https://www.shopback.sg/trip-com`

### Food Delivery
- **Foodpanda:** `https://www.shopback.sg/foodpanda`
- **Deliveroo:** `https://www.shopback.sg/deliveroo`
- **GrabFood:** `https://www.shopback.sg/grabfood`

### Groceries
- **RedMart (Lazada):** `https://www.shopback.sg/redmart`
- **FairPrice:** `https://www.shopback.sg/fairprice`
- **Cold Storage:** `https://www.shopback.sg/cold-storage`

### Fashion & Beauty
- **Sephora:** `https://www.shopback.sg/sephora`
- **Zalora:** `https://www.shopback.sg/zalora`
- **ASOS:** `https://www.shopback.sg/asos`
- **Uniqlo:** `https://www.shopback.sg/uniqlo`

### Electronics
- **Apple:** `https://www.shopback.sg/apple`
- **Samsung:** `https://www.shopback.sg/samsung`
- **Dyson:** `https://www.shopback.sg/dyson`

---

## Selectors (ego-browser / Moli extraction)

### Store Cards (All Stores Page)
- **Container:** `[data-testid="store-card"]` or `.store-card`
- **Store Name:** `[data-testid="store-name"]` or `.store-name`
- **Cashback Rate:** `[data-testid="cashback-rate"]` or `.cashback-rate` (e.g., "5%")
- **Store Logo:** `[data-testid="store-logo"] img` or `.store-logo img`
- **Category Tags:** `[data-testid="store-category"]` or `.category-tag`
- **Link:** `a[data-testid="store-link"]` or `.store-card a`
- **Special Badge:** `.special-rate` / `.limited-time` / `.exclusive`

### Store Detail Page
- **Store Name:** `h1[data-testid="store-title"]` or `.store-header h1`
- **Cashback Rate:** `[data-testid="main-cashback-rate"]` or `.main-rate`
- **Rate Breakdown:** `[data-testid="rate-breakdown"]` or `.rate-details` (e.g., "Up to 10% on Fashion, 5% on Electronics")
- **Terms & Conditions:** `[data-testid="terms"]` or `.terms-content`
- **Shop Now Button:** `[data-testid="shop-now-btn"]` or `.btn-shop-now`
- **Coupons Section:** `[data-testid="coupons-section"]` or `.coupons-list`

### Coupons/Vouchers
- **Container:** `[data-testid="coupon-card"]` or `.coupon-card`
- **Code:** `[data-testid="coupon-code"]` or `.coupon-code` (copyable)
- **Description:** `[data-testid="coupon-desc"]` or `.coupon-description`
- **Expiry:** `[data-testid="coupon-expiry"]` or `.coupon-expiry`
- **Terms:** `[data-testid="coupon-terms"]` or `.coupon-terms`
- **Copy Button:** `[data-testid="copy-btn"]` or `.btn-copy`
- **Store Filter:** `[data-testid="store-filter"]` or `.store-filter-select`

### Cashback Rates Page
- **Category Card:** `[data-testid="category-rate"]` or `.category-rate-card`
- **Category Name:** `.category-name`
- **Rate:** `.category-rate` (e.g., "Up to 8%")
- **Merchant Examples:** `.merchant-examples`

### Account Dashboard (Login Required)
- **Available Balance:** `[data-testid="available-balance"]` or `.balance-amount`
- **Pending Cashback:** `[data-testid="pending-cashback"]` or `.pending-amount`
- **Transaction History:** `[data-testid="transactions"]` or `.transaction-list`
- **Transaction Item:** `.transaction-item` (date, store, amount, status)
- **Withdraw Button:** `[data-testid="withdraw-btn"]` or `.btn-withdraw`
- **Referral Code:** `[data-testid="referral-code"]` or `.referral-code`

### Withdrawal Page (Login Required)
- **Withdrawal Methods:** Bank transfer, PayNow, PayPal
- **Bank Form:** Account holder name, bank, account number
- **PayNow:** UEN / NRIC / Mobile
- **Min Amount:** Typically $10 SGD
- **Processing Time:** 1-3 business days

---

## Tool Routing for ShopBack Singapore

| Task | Tool | Rationale |
|------|------|-----------|
| Browse stores, compare cashback rates | **Moli** (primary) | Public pages work well; fast batch extraction |
| Search for specific merchant | **Moli** | `/stores?search=<query>` works |
| Extract store cashback rates & terms | **Moli** | Public store pages accessible |
| Browse coupons/vouchers | **Moli** | Public coupon pages work |
| Check cashback rates by category | **Moli** | `/rates` page accessible |
| Account dashboard (balance, history) | **ego-browser** | Login required |
| Withdraw cashback | **ego-browser** | Login + bank form |
| Claim coupons (copy codes) | **Moli** (primary) | Public coupon codes copyable |
| Referral program | **ego-browser** | Login required for referral link |
| Track cashback status for specific purchase | **ego-browser** | Login required, transaction details |

**Key Rule:** ShopBack public pages (stores, coupons, rates) work well with **Moli**. Use **ego-browser** for:
- Account dashboard (balance, pending, history)
- Withdrawal (bank forms, PayNow)
- Referral link generation
- Any login-walled feature

---

## Anti-patterns to Avoid
- Don't try to access account dashboard without login (ego-browser required)
- Don't assume cashback rates are static — they change per campaign
- Don't ignore terms & conditions — exclusions apply (e.g., gift cards, certain categories)
- Don't try to withdraw below minimum amount ($10 SGD typically)
- Don't use Agent Reach (no ShopBack tap installed)
- **Moli works well for public pages** — no heavy bot protection on store/coupon listings

---

## Special Notes

### Cashback Tracking
- Cashback tracks via affiliate links — must click "Shop Now" from ShopBack
- Pending cashback appears within 24-48 hours
- Confirmed cashback after merchant confirms no return/cancellation (30-90 days)

### Stacking
- ShopBack cashback + merchant vouchers + credit card cashback often stack
- Check terms: some merchants exclude cashback on voucher-discounted items

### Referral Program
- Referral gives bonus to both referrer and referee
- Bonus credited after referee's first confirmed purchase

### Mobile App
- App has same cashback rates
- App-exclusive deals sometimes available
- Push notifications for flash cashback increases

### ShopBack Pay / PayLater
- BNPL option at checkout on partner sites
- Separate from cashback earning