# Web Intelligence Routing Skill — Template

**General principles for web interaction tool selection and usage.**

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
10. **Site blocks or guts non-browser fetches — 403 (Carousell), crash (Taobao/Tmall), or login-wall (Shopee)? → ego lite** (real Chrome passes bot detection and loads full logged-in state; Moli cannot fetch these)