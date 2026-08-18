# MarkTechPost — Site Configuration

**Site:** MarkTechPost (marktechpost.com)  
**Type:** AI/ML news blog & tutorial site  
**Auth:** Public read; newsletter signup; partner forms  

---

## Base URLs
- **Root:** `https://www.marktechpost.com/`
- **Category:** `https://www.marktechpost.com/category/<category-slug>/`
- **Article:** `https://www.marktechpost.com/2026/08/15/<slug>/`
- **Author:** `https://www.marktechpost.com/author/<author-slug>/`
- **RSS:** `https://www.marktechpost.com/feed/`
- **Search:** `https://www.marktechpost.com/?s=<query>`
- **Newsletter:** `https://www.aidevsignals.com/`

---

## Category Structure

### Technology
- `/category/technology/open-source/` — Open Source/Weights
- `/category/technology/artificial-intelligence/voice-ai/` — Voice AI
- `/category/technology/artificial-intelligence/applications/` — Applications
- `/category/technology/artificial-intelligence/ai-ethics/` — AI Ethics
- `/category/technology/artificial-intelligence/ai-shorts/` — AI Shorts
- `/category/tech-news/data-visualization/` — Data Visualization

### Editors' Pick
- `/category/editors-pick/ai-agents/` — AI Agents
- `/category/editors-pick/agentic-ai/` — Agentic AI
- `/category/editors-pick/generative-ai/` — Generative AI
- `/category/editors-pick/enterprise-ai/` — Enterprise AI

### Other
- `/category/robotics/` — Robotics
- `/category/tutorials/` — Tutorials

---

## Article Pattern
- **URL:** `/YYYY/MM/DD/<slug>/` (e.g., `/2026/08/15/fine-tuning-tool-calling-llms/`)
- **Date in URL:** Year/month/day from publish date
- **Category breadcrumb:** Visible on article page

---

## Selectors (for Moli / ego-browser extraction)

### Homepage / Category pages
- **Article links:** `h2 a`, `h3 a`, `.post-title a`, `article a`
- **Article container:** `article`, `.post-item`, `.post-card`
- **Category nav:** `.nav-menu a[href*="/category/"]`, `.categories a`
- **Featured/Trending:** `.featured-post`, `.trending-post`, `.trending article`

### Article page
- **Title:** `h1.entry-title`, `h1.post-title`, `h1`
- **Author:** `.author-name a`, `.author a[href*="/author/"]`, `.byline`
- **Date:** `.entry-date`, `.post-date`, `time[datetime]`
- **Categories:** `.entry-categories a`, `.post-categories a`, `.cat-links a`
- **Tags:** `.entry-tags a`, `.tags a`
- **Content:** `.entry-content`, `.post-content`, `article .content`
- **Images:** `.entry-content img`, `.post-content img`, `figure img`
- **Author bio:** `.author-bio`, `.author-box`, `.author-info`

### Pagination
- **Next/Prev:** `.pagination .next`, `.pagination .prev`, `.nav-links a`
- **Page numbers:** `.page-numbers`, `.pagination a`

### Newsletter / Forms
- **Email input:** `input[type="email"][name*="email"]`
- **Submit:** `button[type="submit"]`, `input[type="submit"]`
- **Newsletter link:** `a[href*="aidevsignals.com"]`

### Social / Partner
- **Social links:** `a[href*="linkedin.com"]`, `a[href*="twitter.com"]`, `a[href*="x.com"]`, `a[href*="discord.gg"]`, `a[href*="reddit.com"]`
- **Partner logos:** `.partner-logo`, `.sponsor-logo`
- **Newsletter CTA:** `a[href*="aidevsignals.com"]`

---

## Tool Routing for MarkTechPost

| Task | Tool | Rationale |
|------|------|-----------|
| Browse categories, list articles | **Moli** | Public pages, fast batch extraction |
| Extract article content | **Defuddle** | Clean article + metadata (title, author, date) from Moli/ego-browser HTML |
| Monitor new articles (RSS) | **agent-reach** | `/feed/` RSS/Atom feed |
| Scrape 50+ articles | **Moli** | 16ms each, no rendering |
| Author page + articles | **Moli** | Public author pages |
| Search articles | **Moli** | `?s=<query>` public search |
| Newsletter signup | **ego-browser** | Form filling, login if needed |

---

## Anti-patterns to Avoid
- Don't use `networkidle` for category pages (lazy-loaded images)
- Don't assume `/page/N` pagination — check for `?paged=N`
- Don't try to scrape "Premium Content" without auth (ego-browser if needed)
- Don't use Agent Reach (no MarkTechPost tap)

---

## Trust & Safety Notes
- Cookie consent banner (CookieYes) — dismiss or configure
- Partner/sponsored content marked
- Newsletter: aidevsignals.com
- Social: Discord, LinkedIn, Reddit, X
- Copyright: Marktechpost AI Media Inc