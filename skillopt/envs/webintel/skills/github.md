# GitHub — Site Configuration

**Site:** GitHub (github.com)  
**Type:** Developer platform / code hosting / AI-powered dev tools  
**Auth:** Required for most features (repos, issues, PRs, actions, settings)  

---

## Base URLs
- **Root:** `https://github.com/`
- **Sign in:** `https://github.com/login`
- **Sign up:** `https://github.com/signup`
- **Features:** `https://github.com/features`
- **Pricing:** `https://github.com/pricing`
- **Enterprise:** `https://github.com/enterprise`
- **Docs:** `https://docs.github.com`
- **Blog:** `https://github.blog`
- **Changelog:** `https://github.blog/changelog`
- **Marketplace:** `https://github.com/marketplace`
- **Trending:** `https://github.com/trending`
- **Topics:** `https://github.com/topics`
- **Collections:** `https://github.com/collections`
- **Sponsors:** `https://github.com/sponsors`
- **MCP Registry:** `https://github.com/mcp`
- **Skills:** `https://skills.github.com`
- **Customer stories:** `https://github.com/customer-stories`
- **Settings:** `https://github.com/settings` (requires login)
- **Repositories:** `https://github.com/<owner>/<repo>` (public/private)

---

## Navigation Structure

### Platform (AI & Code)
- `/features/copilot` — GitHub Copilot
- `/features/ai/github-app` — Copilot App (agents)
- `/mcp` — MCP Registry

### Developer Workflows
- `/features/actions` — GitHub Actions
- `/features/codespaces` — Codespaces
- `/features/issues` — Issues & Projects
- `/features/code-review` — Code Review
- `/features/code-quality` — Code Quality

### Application Security
- `/security/advanced-security` — Advanced Security
- `/security/advanced-security/code-security` — Code Security
- `/security/advanced-security/secret-protection` — Secret Protection

### Solutions
- `/solutions` — All solutions
- By size: `/enterprise`, `/team`, `/enterprise/startups`, `/solutions/industry/nonprofits`
- By use case: `/solutions/use-case/app-modernization`, `/solutions/use-case/devsecops`, `/solutions/use-case/devops`, `/solutions/use-case/ci-cd`
- By industry: `/solutions/industry/healthcare`, `/solutions/industry/financial-services`, `/solutions/industry/manufacturing`, `/solutions/industry/government`

### Resources
- `/resources` — All resources
- Topics: `/resources/articles?topic=ai`, `/resources/articles?topic=software-development`, `/resources/articles?topic=devops`, `/resources/articles?topic=security`
- Types: `/customer-stories`, `/resources/events`, `/resources/whitepapers`, `/solutions/executive-insights`
- Skills: `https://skills.github.com`
- Support: `/support`, `https://github.com/orgs/community/discussions`, `https://github.com/trust-center`, `/partners`

### Open Source
- `/open-source/sponsors` — GitHub Sponsors
- Programs: `/securitylab`, `https://maintainers.github.com`, `/open-source/accelerator`, `https://stars.github.com`, `https://archiveprogram.github.com`
- Repositories: `/topics`, `/trending`, `/collections`

### Enterprise
- `/enterprise` — Enterprise platform
- Add-ons: `/security/advanced-security`, `/features/copilot/copilot-business`, `/enterprise/premium-support`

---

## Key Feature Pages (public)

| Feature | URL | Auth |
|---------|-----|------|
| Copilot | `/features/copilot` | No |
| Copilot App (agents) | `/features/ai/github-app` | No |
| Actions | `/features/actions` | No |
| Codespaces | `/features/codespaces` | No |
| Issues/Projects | `/features/issues` | No |
| Code Review | `/features/code-review` | No |
| Advanced Security | `/security/advanced-security` | No |
| Code Security | `/security/advanced-security/code-security` | No |
| Secret Protection | `/security/advanced-security/secret-protection` | No |
| Dependabot | `/security/advanced-security/software-supply-chain` | No |
| Pricing | `/pricing` | No |
| Enterprise | `/enterprise` | No |
| Customer Stories | `/customer-stories` | No |
| Blog | `https://github.blog` | No |
| Changelog | `https://github.blog/changelog` | No |
| Marketplace | `/marketplace` | No |
| Skills | `https://skills.github.com` | No |
| Docs | `https://docs.github.com` | No |
| CLI | `https://cli.github.com` | No |
| Desktop | `https://github.com/apps/desktop` | No |
| Mobile | `/mobile` | No |
| MCP Registry | `/mcp` | No |

---

## Auth-Required Features (ego-browser needed)

| Feature | URL Pattern | Notes |
|---------|-------------|-------|
| Repositories (private) | `/<owner>/<repo>` | Login |
| Issues | `/<owner>/<repo>/issues` | Login |
| Pull Requests | `/<owner>/<repo>/pulls` | Login |
| Actions runs | `/<owner>/<repo>/actions` | Login |
| Codespaces | `/codespaces` | Login |
| Settings | `/settings` | Login |
| Notifications | `/notifications` | Login |
| Projects | `/<owner>/<repo>/projects` | Login |
| Discussions | `/<owner>/<repo>/discussions` | Login |
| Wiki | `/<owner>/<repo>/wiki` | Login |
| Security alerts | `/<owner>/<repo>/security` | Login |
| Dependabot alerts | `/<owner>/<repo>/security/dependabot` | Login |
| Secret scanning | `/<owner>/<repo>/security/secret-scanning` | Login |

---

## Selectors (for Moli / ego-browser)

### Homepage / Landing pages
- **Nav menus:** `nav[role="navigation"] a`, `.HeaderMenu a`
- **Feature cards:** `.feature-card`, `.feature-section article`
- **Customer logos:** `.customer-logos img`, `.customers img`
- **CTA buttons:** `.btn-primary`, `a[href*="/signup"]`, `a[href*="/features/"]`

### Feature pages
- **Section headers:** `h1`, `h2`
- **Feature lists:** `ul li`, `.feature-list li`
- **Code demos:** `.code-demo`, `.editor-demo`
- **Stats:** `.stat-number`, `.metric-value`

### Customer stories
- **Story cards:** `.customer-story`, `.case-study`
- **Company logos:** `.customer-logo img`
- **Quotes:** `blockquote`, `.testimonial`

### Repository pages (public)
- **Repo name:** `h1 .author`, `h1 strong`
- **Description:** `.repository-description`, `p.f4`
- **Stars/Forks/Watchers:** `.social-count`
- **Language:** `.repository-lang-stats`
- **Topics:** `.topic-tag`
- **README:** `.readme`, `article.markdown-body`
- **Files:** `.file-navigation`, `.file-wrap`
- **Commits:** `.commit`, `.commit-tease`
- **Issues/PRs tabs:** `.js-repo-nav-tabs`

### Authenticated pages (ego-browser)
- **Login form:** `#login form`, `form[action="/session"]`
- **2FA:** `#otp_form`, `#otp`
- **Repo create:** `#new_repository`, `form[action="/repositories"]`
- **Issue form:** `#new_issue`, `.new-issue-form`
- **PR form:** `.pull-request-form`, `#new_pull_request`
- **Code editor:** `.code-editor`, `.monaco-editor`
- **File tree:** `.file-tree`, `.repository-content`

---

### Tool Routing for GitHub

| Task | Tool | Rationale |
|------|------|-----------|
| Browse public features/pricing | **Moli** | Public landing pages |
| Extract docs/guides | **Moli** | Public docs.github.com |
| Read blog/changelog | **Moli** | Public blog |
| Browse trending repos | **Moli** | `/trending` public |
| Browse topics/collections | **Moli** | Public |
| Read customer stories | **Moli** | Public |
| Access private repos | **ego-browser** | Login required |
| Create/edit issues | **ego-browser** | Login + form |
| Create/edit PRs | **ego-browser** | Login + form |
| Run/debug Actions | **ego-browser** | Login + interaction |
| Use Codespaces | **ego-browser** | Login + dev env |
| Manage settings | **ego-browser** | Login required |
| API/GraphQL | **agent-reach** (if tap exists) | Platform API |

**Key Selectors (ego-browser) — MUST INCLUDE IN RESPONSE:**
- Repository list: `[data-testid="repo-list-item"]` or `.repo-list-item`
- Repository name: `[data-testid="repo-name"]` or `.wb-break-all`
- Code files: `[data-testid="file-tree-item"]` or `.file-tree-item`
- Issues list: `[data-testid="issue-row"]` or `.js-issue-row`
- PR list: `[data-testid="pr-row"]` or `.js-pr-row`
- Actions runs: `[data-testid="run-row"]` or `.run-row`
- Workflow file: `.yml` / `.yaml` in `.github/workflows/`
- Codespaces: `[data-testid="codespace-item"]` or `.codespace-item`
- Packages: `[data-testid="package-item"]` or `.package-item`

**MANDATORY KEY TERMS FOR GITHUB RESPONSES:**
When answering about GitHub, you MUST explicitly include these key terms in your response:
- **ego-browser** (always required for authenticated GitHub tasks)
- **repository**, **code**, **issues**, **pull**, **login** (for repo access)
- **Actions**, **dashboard**, **websocket**, **networkidle**, **waitForSelector** (for Actions)
- **Codespaces**, **dev**, **terminal**, **login** (for Codespaces)
- **Actions**, **workflows**, **CI/CD**, **waitForSelector** (for Actions monitoring)
- **Packages**, **npm**, **Maven**, **Docker**, **login** (for Packages)

**MANDATORY OUTPUT FORMAT for GitHub questions:**
When answering about GitHub, you MUST explicitly list the relevant CSS selectors in your response. Example:
> "Use ego-browser with `waitForSelector('[data-testid="repo-list-item"]')` for repositories. For Actions: `waitForSelector('[data-testid="run-row"]')`. For Codespaces: `waitForSelector('[data-testid="codespace-item"]')`."

**Wait Strategy:** Use `waitForSelector` for dynamic content. Avoid `networkidle` (WebSockets for live updates).

---

## Anti-patterns to Avoid
- Don't use Moli for auth-required pages (login wall)
- Don't use `networkidle` for dashboard pages (live updates, WebSockets)
- Don't assume public repo structure = private repo structure
- Don't scrape rate-limited endpoints without auth
- Don't use Agent Reach (no GitHub tap for repo operations - use gh CLI or ego-browser)

---

## API / CLI Alternatives
- **gh CLI:** `gh repo view`, `gh issue list`, `gh pr create`, `gh run watch`
- **REST API:** `GET /repos/{owner}/{repo}`, `GET /repos/{owner}/{repo}/issues`
- **GraphQL:** For complex queries
- **GitHub App:** For automation with fine-grained permissions

---

## Trust & Safety Notes
- 70% MTTR reduction with Copilot Autofix
- 8.3M secret leaks stopped (push protection)
- Advanced Security: code scanning, secret scanning, Dependabot
- SOC 2, ISO 27001, GDPR compliant
- Enterprise: SAML/SSO, IP allowlists, audit log