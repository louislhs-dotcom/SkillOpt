# Moli WebFetch Skill

You are an agent using Moli, a Rust-based headless browser for AI agents, to fetch and extract web pages.

## Core Commands
- `moli fetch --dump markdown --wait-until done "URL"` — extract page as Markdown (default, structure-first)
- `moli fetch --dump semantic_tree_text --wait-selector body "URL"` — compact semantic tree for AI processing
- `moli fetch --dump html "URL"` — raw HTML output
- `moli fetch --dump json "URL"` — JSON serialization
- `moli fetch --layout --dump screenshot "URL" > page.png` — viewport screenshot (requires --layout)
- `moli fetch --layout --dump pdf "URL" > page.pdf` — paginated PDF (requires --layout)
- `moli serve` — start CDP server on http://127.0.0.1:9222
- `moli serve --layout` — enable real geometry, coordinate input, screenshots
- `moli serve --layout --resource` — also fetch images, fonts, audio, video, media
- `moli version` — check installed version

## Key Rules
- Structure-first: DOM extraction (markdown, semantic_tree_text, html, json) does NOT need --layout
- --layout only needed for: screenshots, PDFs, element geometry, coordinate input
- --wait-until options: done (default), networkidle (quiet network), domstable (DOM mutations settle)
- AVOID networkidle on long-polling/WebSocket sites — use domstable instead
- --wait-selector blocks until a specific CSS selector appears
- CDP server serves CDP + WebDriver Classic + WebDriver BiDi on same endpoint
- Playwright: `chromium.connectOverCDP("http://127.0.0.1:9222")`
- Moli executes JavaScript and maintains live DOM by default
- No visual rendering cost unless --layout is used

## Workflow Patterns
1. Content extraction: `moli fetch --dump markdown --wait-until done "URL"`
2. AI processing: `moli fetch --dump semantic_tree_text --wait-selector body "URL"`  
3. Screenshot: `moli fetch --layout --dump screenshot "URL" > output.png`
4. CDP automation: `moli serve --layout` → connect Playwright over CDP
5. JS-heavy SPA: `moli fetch --wait-until domstable --dump markdown "URL"`
