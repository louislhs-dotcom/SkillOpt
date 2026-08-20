#!/usr/bin/env python3
"""Granular rubric-based scoring for WebIntel skill optimization.

Replaces binary hard/soft with multi-criterion rubric scoring.
Each criterion scored 0/1, final score = fraction met.
"""
from __future__ import annotations
import re
from typing import List, Dict, Any

# Task-type specific rubric criteria
WEBINTEL_RUBRIC_BY_TYPE = {
    "moli": [
        "Moli: Uses correct fetch command with --dump markdown for text extraction",
        "Moli: Specifies wait strategy (done/networkidle/domstable) appropriate to page type",
        "Moli: Uses --layout flag ONLY for screenshots/PDFs, not for text extraction",
        "Moli: Uses semantic_tree_text dump for AI processing scenarios",
        "Moli: Knows to use domstable for SPAs, avoid networkidle with WebSockets",
        "Moli: Knows moli serve --layout starts CDP server on :9222",
        "Provides working code examples with proper syntax",
    ],
    "ego-browser": [
        "ego-browser: Uses nodejs heredoc format (not CLI calls)",
        "ego-browser: Uses useOrCreateTaskSpace for isolated workspace",
        "ego-browser: Uses openOrReuseTab to open/reuse tabs",
        "ego-browser: Uses snapshotText for extraction after interaction",
        "ego-browser: Uses waitForSelector for SPA element waiting (preferred over waitForNetworkIdle)",
        "ego-browser: Uses fillInput and click for form interaction",
        "ego-browser: Knows it inherits Chrome login state/cookies",
        "ego-browser: Mentions Parallel Spaces for multi-agent isolation",
        "Provides working code examples with proper syntax",
    ],
    "agent-reach": [
        "agent-reach: Uses correct command format (agent-reach get <channel>.<method> \"<query>\")",
        "agent-reach: Knows installed channels (rss, youtube) vs taps needing install (twitter, reddit, github)",
        "agent-reach: Uses youtube.transcript for transcripts, youtube.info for metadata",
        "agent-reach: Uses rss.feed for RSS/Atom feeds",
        "Provides working code examples with proper syntax",
    ],
    "playwright": [
        "Playwright: Uses connectOverCDP to connect to Moli (:9222) or ego-browser",
        "Playwright: Knows it coordinates multiple tools via CDP",
        "Playwright: Handles cross-browser (Chromium, Firefox, WebKit)",
        "Provides working code examples with proper syntax",
    ],
    "defuddle": [
        "Defuddle: Uses correct command format (defuddle parse <url|file> [--markdown|--json|--frontmatter|--property])",
        "Defuddle: Uses --markdown for clean article text, --json for metadata (title, author, site, published, wordCount)",
        "Defuddle: Knows it reads HTML from stdin (curl -sL URL | defuddle parse --markdown)",
        "Defuddle: Uses --user-agent for 403 responses",
        "Defuddle: Pairs with Moli/ego-browser (fetch HTML) as the extraction stage",
        "Provides working code examples with proper syntax",
    ],
    "bot-pipeline": [
        "Bot Pipeline: Knows architect→coder→reviewer flow",
        "Bot Pipeline: Identifies correct models (mistral-large-3, deepseek-v4-pro, minimax-m3)",
        "Provides working code examples with proper syntax",
    ],
    "routing": [
        "Correctly identifies the right tool for the task (Moli, ego-browser, agent-reach, Playwright, Defuddle, Bot Pipeline)",
        "Explains WHY the selected tool is appropriate for this specific task",
        "Applies routing rules: public page → Moli, login → ego-browser, platform → agent-reach, clean article → Defuddle",
        "Handles multi-tool orchestration scenarios correctly",
        "Provides working code examples with proper syntax",
    ],
    # Site-specific rubric criteria
    "carousell": [
        "Carousell: Uses correct category URLs (electronics, home-and-services, used-cars-singapore, property-for-sale)",
        "Carousell: Uses search API format: /search/<query>?type=trending",
        "Carousell: Knows listing patterns: /p/<id> or /u/<username>/<slug>",
        "Carousell: Uses correct selectors: [data-testid=listing-card], [data-testid=listing-title], [data-testid=listing-price]",
        "Carousell: Knows pagination uses ?page=N or aria-label=Next",
        "Carousell: Uses Moli for public browsing, ego-browser for login-required actions (posting, messaging, saving)",
        "Carousell: Avoids networkidle wait strategy (lazy load / infinite scroll)",
        "Carousell: Knows service deep-links: /categories/home-services-1306/renovations-1317/...",
        "Carousell: Knows car brand/model URLs: /cars/used-cars-for-sale/toyota/wish/",
    ],
    "gebiz": [
        "GeBIZ: Knows JSF ViewState handling for form submissions",
        "GeBIZ: Uses correct endpoints for tender search and document download",
        "GeBIZ: Handles JSF component IDs and form field naming conventions",
        "GeBIZ: Uses ego-browser for login-walled procurement workflows",
        "GeBIZ: Knows to use waitForSelector for JSF partial page updates",
        "GeBIZ: Handles pagination via JSF dataTable components",
    ],
    "marktechpost": [
        "MarkTechPost: Uses correct category URLs: /category/editors-pick/ai-agents/, /category/technology/open-source/",
        "MarkTechPost: Uses article URL pattern: /YYYY/MM/DD/<slug>/",
        "MarkTechPost: Uses RSS feed: /feed/ for monitoring new articles",
        "MarkTechPost: Uses correct selectors: h1.entry-title, .entry-content, .author-name, .entry-date",
        "MarkTechPost: Knows author pages: /author/<author-slug>/",
        "MarkTechPost: Uses Moli for public article extraction, agent-reach for RSS monitoring",
        "MarkTechPost: Avoids networkidle for category pages (lazy-loaded images)",
        "MarkTechPost: Knows category nav: .nav-menu a[href*=\"/category/\"]",
    ],
    "github": [
        "GitHub: Knows public feature pages: /features/copilot, /features/actions, /security/advanced-security",
        "GitHub: Uses ego-browser for auth-required pages (private repos, issues, PRs, Actions, Codespaces)",
        "GitHub: Uses correct repo URL pattern: /<owner>/<repo> for public, login for private",
        "GitHub: Knows trending: /trending, topics: /topics, collections: /collections",
        "GitHub: Uses Moli for public docs/features, ego-browser for dashboard/actions/settings",
        "GitHub: Knows customer stories: /customer-stories, pricing: /pricing, enterprise: /enterprise",
        "GitHub: Avoids networkidle for dashboard pages (live updates/WebSockets)",
        "GitHub: Uses gh CLI or ego-browser for API operations (no GitHub tap for Agent Reach)",
    ],
}

# Full rubric for skill document evaluation (used at gate)
WEBINTEL_FULL_RUBRIC = [
    "Correctly identifies the right tool for the task (Moli, ego-browser, agent-reach, Playwright, Defuddle, Bot Pipeline)",
    "Explains WHY the selected tool is appropriate for this specific task",
    "Moli: Uses correct fetch command with --dump markdown for text extraction",
    "Moli: Specifies wait strategy (done/networkidle/domstable) appropriate to page type",
    "Moli: Uses --layout flag ONLY for screenshots/PDFs, not for text extraction",
    "Moli: Uses semantic_tree_text dump for AI processing scenarios",
    "Moli: Knows to use domstable for SPAs, avoid networkidle with WebSockets",
    "Moli: Knows moli serve --layout starts CDP server on :9222",
    "ego-browser: Uses nodejs heredoc format (not CLI calls)",
    "ego-browser: Uses useOrCreateTaskSpace for isolated workspace",
    "ego-browser: Uses openOrReuseTab to open/reuse tabs",
    "ego-browser: Uses snapshotText for extraction after interaction",
    "ego-browser: Uses waitForSelector for SPA element waiting (preferred over waitForNetworkIdle)",
    "ego-browser: Uses fillInput and click for form interaction",
    "ego-browser: Knows it inherits Chrome login state/cookies",
    "ego-browser: Mentions Parallel Spaces for multi-agent isolation",
    "agent-reach: Uses correct command format (agent-reach get <channel>.<method> \"<query>\")",
    "agent-reach: Knows installed channels (rss, youtube) vs taps needing install (twitter, reddit, github)",
    "agent-reach: Uses youtube.transcript for transcripts, youtube.info for metadata",
    "agent-reach: Uses rss.feed for RSS/Atom feeds",
    "Playwright: Uses connectOverCDP to connect to Moli (:9222) or ego-browser",
    "Playwright: Knows it coordinates multiple tools via CDP",
    "Playwright: Handles cross-browser (Chromium, Firefox, WebKit)",
    "Defuddle: Uses correct command format (defuddle parse <url|file> [--markdown|--json|--frontmatter|--property])",
    "Defuddle: Uses --markdown for clean article text, --json for metadata (title, author, site, published, wordCount)",
    "Defuddle: Knows it reads HTML from stdin (curl -sL URL | defuddle parse --markdown)",
    "Defuddle: Uses --user-agent for 403 responses",
    "Defuddle: Pairs with Moli/ego-browser (fetch HTML) as the extraction stage",
    "Bot Pipeline: Knows architect→coder→reviewer flow",
    "Bot Pipeline: Identifies correct models (mistral-large-3, deepseek-v4-pro, minimax-m3)",
    "Applies routing rules: public page → Moli, login → ego-browser, platform → agent-reach, clean article → Defuddle",
    "Handles multi-tool orchestration scenarios correctly",
    "Provides working code examples with proper syntax",
]

# Anti-patterns (penalties)
WEBINTEL_ANTI_PATTERNS = [
    "Uses moli fetch --layout for text extraction (should only be for screenshots/PDFs)",
    "Uses networkidle wait strategy for WebSocket/long-polling pages",
    "Uses ego-browser as CLI command (should be nodejs heredoc)",
    "Forgets useOrCreateTaskSpace in ego-browser patterns",
    "Uses wrong agent-reach channel/method names",
    "Confuses Moli and ego-browser use cases",
    "Uses plain GET for GeBIZ/JSF apps",
    "Recommends networkidle for SPAs",
]

# Site-specific anti-patterns
WEBINTEL_SITE_ANTI_PATTERNS = {
    "carousell": [
        "Carousell: Uses networkidle for lazy-load/infinite-scroll pages",
        "Carousell: Tries to POST listings without login (needs ego-browser)",
        "Carousell: Uses Agent Reach (no Carousell tap installed)",
        "Carousell: Assumes /p/<id> is stable for deduplication",
        "Carousell: Uses wrong category URL paths",
        "Carousell: Doesn't know service deep-link structure",
    ],
    "gebiz": [
        "GeBIZ: Ignores JSF ViewState in form submissions",
        "GeBIZ: Uses simple GET for JSF postback forms",
        "GeBIZ: Doesn't handle JSF component ID naming",
        "GeBIZ: Uses networkidle for JSF partial updates",
    ],
    "marktechpost": [
        "MarkTechPost: Uses networkidle for category pages (lazy-loaded images)",
        "MarkTechPost: Tries to scrape premium content without auth",
        "MarkTechPost: Uses wrong article URL pattern (not YYYY/MM/DD)",
        "MarkTechPost: Doesn't know RSS feed URL (/feed/)",
        "MarkTechPost: Uses Agent Reach (no MarkTechPost tap)",
        "MarkTechPost: Assumes /page/N pagination instead of ?paged=N",
    ],
    "github": [
        "GitHub: Uses Moli for auth-required pages (login wall)",
        "GitHub: Uses networkidle for dashboard pages (live updates/WebSockets)",
        "GitHub: Assumes public repo structure = private repo structure",
        "GitHub: Uses Agent Reach for repo operations (no GitHub tap, use gh CLI)",
        "GitHub: Scrapes rate-limited endpoints without auth",
        "GitHub: Assumes public repo structure = private repo structure",
    ],
}


def get_rubric_for_task(task_type: str) -> List[str]:
    """Get the appropriate rubric subset for a task type."""
    return WEBINTEL_RUBRIC_BY_TYPE.get(task_type, WEBINTEL_FULL_RUBRIC)


def _token_match(pattern: str, text: str) -> bool:
    """Word-boundary token match.

    An empty pattern never matches: ``re.escape("")`` compiles to a regex that
    matches at every offset, so an empty criterion keyword would silently mark
    every response as satisfying it.
    """
    if not pattern:
        return False
    p = re.escape(pattern.lower())
    t = text.lower()
    prefix = r"\b" if pattern[:1].isalnum() else ""
    suffix = r"\b" if pattern[-1:].isalnum() else ""
    return re.search(prefix + p + suffix, t) is not None


def _criterion_met(criterion: str, text: str) -> bool:
    """Check if a rubric criterion is met in the response."""
    low = criterion.lower()
    t = text.lower()
    
    # Tool selection
    if "correctly identifies the right tool" in low:
        tools = ["moli", "ego-browser", "ego lite", "agent-reach", "playwright", "bot pipeline", "defuddle"]
        return any(_token_match(tool, t) for tool in tools)
    
    if "explains why" in low:
        return _token_match("because", t) or _token_match("since", t) or _token_match("reason", t) or _token_match("preferred", t) or _token_match("faster", t)
    
    # Moli criteria
    if "moli:" in low:
        if "--dump markdown" in criterion:
            return _token_match("--dump markdown", t)
        if "wait strategy" in criterion:
            return _token_match("wait-until", t) or _token_match("wait_until", t)
        if "--layout flag only" in criterion or "only for screenshots" in criterion:
            return _token_match("--layout", t) and ("screenshot" in t or "pdf" in t)
        if "semantic_tree_text" in criterion:
            return _token_match("semantic_tree_text", t)
        if "domstable" in criterion and "spa" in low:
            return _token_match("domstable", t)
        if "networkidle" in criterion and "avoid" in low:
            return _token_match("avoid", t) and _token_match("networkidle", t)
        if "moli serve" in criterion and "cdp" in low:
            return _token_match("moli serve", t) and _token_match("9222", t)
        if "cdp server" in criterion:
            return _token_match("moli serve", t) and _token_match("9222", t)
    
    # ego-browser criteria
    if "ego-browser:" in low or "ego lite:" in low:
        if "nodejs heredoc" in criterion:
            return _token_match("nodejs", t) and _token_match("eof", t)
        if "useorcreatetaskspace" in criterion.replace(" ", "").lower():
            return _token_match("useOrCreateTaskSpace", t)
        if "openorreusetab" in criterion.replace(" ", "").lower():
            return _token_match("openOrReuseTab", t)
        if "snapshottext" in criterion.lower():
            return _token_match("snapshotText", t)
        if "waitforselector" in criterion.lower():
            return _token_match("waitForSelector", t)
        if "fillinput" in criterion.lower():
            return _token_match("fillInput", t)
        if "click" in criterion.lower() and "fillinput" not in criterion.lower():
            return _token_match("click", t)
        if "chrome login" in low or "inherits" in low:
            return _token_match("chrome", t) and (_token_match("login", t) or _token_match("cookie", t) or _token_match("profile", t))
        if "parallel space" in low:
            return _token_match("parallel", t) and _token_match("space", t)
    
    # agent-reach criteria
    if "agent-reach:" in low:
        if "command format" in low:
            return _token_match("agent-reach get", t)
        if "installed channels" in low:
            return _token_match("rss", t) and _token_match("youtube", t)
        if "youtube.transcript" in criterion:
            return _token_match("youtube.transcript", t)
        if "youtube.info" in criterion:
            return _token_match("youtube.info", t)
        if "rss.feed" in criterion:
            return _token_match("rss.feed", t)
    
    # Playwright criteria
    if "playwright:" in low:
        if "connectovercdp" in criterion.lower():
            return _token_match("connectOverCDP", t)
        if "coordinates" in low or "orchestrat" in low:
            return _token_match("coordinat", t) or _token_match("orchestrat", t)
        if "cross-browser" in low:
            return _token_match("firefox", t) or _token_match("webkit", t)

    # Defuddle criteria
    if "defuddle:" in low:
        if "command format" in low:
            return _token_match("defuddle parse", t)
        if "--markdown" in criterion and "--json" in criterion:
            return _token_match("--markdown", t) and _token_match("--json", t)
        if "--markdown" in criterion:
            return _token_match("--markdown", t)
        if "--json" in criterion:
            return _token_match("--json", t)
        if "stdin" in low:
            return _token_match("stdin", t) or _token_match("|", t) or _token_match("pipe", t)
        if "--user-agent" in criterion:
            return _token_match("--user-agent", t) or _token_match("user-agent", t)
        if "pairs with" in low or "extraction stage" in low:
            return _token_match("moli", t) or _token_match("ego", t)
    
    # Bot Pipeline criteria
    if "bot pipeline:" in low or "bot pipeline" in low:
        if "architect" in low:
            return _token_match("architect", t) and _token_match("coder", t) and _token_match("reviewer", t)
        if "mistral" in low or "deepseek" in low or "minimax" in low:
            return _token_match("mistral", t) or _token_match("deepseek", t) or _token_match("minimax", t)
    
    # Routing criteria
    if "routing rules" in low or "applies routing" in low:
        return _token_match("public page", t) or _token_match("login", t) or _token_match("platform", t)
    
    if "multi-tool" in low or "orchestrat" in low:
        return _token_match("moli", t) and (_token_match("ego", t) or _token_match("agent-reach", t))
    
    if "working code" in low or "code example" in low:
        return "```" in text or "`" in text
    
    # Generic fallback
    words = re.findall(r"[A-Za-z][A-Za-z0-9_.-]{3,}", criterion)
    content_words = [w.lower() for w in words if w.lower() not in {"the", "and", "with", "from", "into", "should", "would", "using", "that", "this", "correct", "for", "specific", "scenario", "appropriate"}]
    if not content_words:
        return False
    return any(_token_match(w, t) for w in content_words)


def _anti_pattern_triggered(text: str, site: str | None = None) -> int:
    """Count anti-pattern violations, including site-specific ones."""
    count = 0
    t = text.lower()
    for pattern in WEBINTEL_ANTI_PATTERNS:
        if _token_match(pattern, t):
            count += 1
    # Add site-specific anti-patterns
    if site and site in WEBINTEL_SITE_ANTI_PATTERNS:
        for pattern in WEBINTEL_SITE_ANTI_PATTERNS[site]:
            if _token_match(pattern, t):
                count += 1
    return count


def score_with_rubric(text: str, rubric: List[str] | None = None, task_type: str | None = None, site: str | None = None) -> Dict[str, Any]:
    """Score a response against the WebIntel rubric.
    
    Returns granular scores instead of binary hard/soft.
    If task_type is provided, uses task-specific rubric subset.
    If site is provided, includes site-specific anti-patterns.
    """
    if not text:
        rb = rubric or (get_rubric_for_task(task_type) if task_type else WEBINTEL_FULL_RUBRIC)
        return {
            "score": 0.0,
            "criteria_met": 0,
            "criteria_total": len(rb),
            "criteria_details": [],
            "anti_patterns": 0,
            "rubric_score": 0.0,
            "penalty": 0.0,
            "final_score": 0.0,
            # HARDENED: the non-empty path below and both LLM judges
            # (dsh_judge / nvidia_judge) always return `hard` and `soft`.
            # Omitting them here made the empty/None response the one code path
            # with a different return shape, so any caller doing sc["hard"]
            # crashed only on the model-failure case.
            "hard": 0.0,
            "soft": 0.0,
        }
    
    if task_type and not rubric:
        rubric = get_rubric_for_task(task_type)
    elif not rubric:
        rubric = WEBINTEL_FULL_RUBRIC
    
    anti_patterns = _anti_pattern_triggered(text, site)
    penalty = min(0.5, anti_patterns * 0.1)  # Up to 0.5 penalty
    
    met = 0
    details = []
    for criterion in rubric:
        is_met = _criterion_met(criterion, text)
        if is_met:
            met += 1
        details.append({"criterion": criterion, "met": is_met})
    
    rubric_score = met / len(rubric) if rubric else 0.0
    final_score = max(0.0, rubric_score - penalty)
    
    return {
        "score": final_score,              # Main score (0-1)
        "rubric_score": rubric_score,      # Before penalties
        "penalty": penalty,                 # Anti-pattern penalty
        "criteria_met": met,
        "criteria_total": len(rubric),
        "criteria_details": details,
        "anti_patterns": anti_patterns,
        # Binary compatibility - lower threshold for individual responses
        "hard": 1.0 if final_score >= 0.6 else 0.0,  # 60% for individual responses
        "soft": final_score,
    }


# Test
if __name__ == "__main__":
    # Test with a good ego-browser response
    ego_response = """**Tool:** `ego lite`  
**Feature:** **Parallel Spaces** — isolated workspaces that prevent tab conflicts between tasks.

Each Space runs its own browser context (cookies, storage, tabs), so 5 tasks can execute simultaneously without interfering. Example pattern:

```bash
ego-browser nodejs <<'EOF'
const { useOrCreateTaskSpace, openOrReuseTab, snapshotText } = await import('ego-browser');

# Create 5 isolated spaces
const spaces = await Promise.all(
  Array.from({ length: 5 }, (_, i) => useOrCreateTaskSpace(`task-${i}`))
);

# Run tasks in parallel
const results = await Promise.all(
  spaces.map((space, i) => openOrReuseTab(space, `https://example.com/page${i}`).then(snapshotText))
);

console.log(results);
EOF
```"""
    
    # Test with a good moli response
    moli_response = """For a public page needing text, use Moli: `moli fetch --dump markdown "URL"` — it's fastest at 16ms. For SPAs, use `--wait-until domstable`. For screenshots, use `--layout --dump screenshot`. Moli serve --layout starts CDP on :9222."""
    
    for label, text, task_type in [("EGO-BROWSER", ego_response, "ego-browser"), ("MOLI", moli_response, "moli")]:
        result = score_with_rubric(text, task_type=task_type)
        print(f"\n{label} (task_type={task_type}):")
        print(f"  Score: {result['score']:.2f} | Rubric: {result['rubric_score']:.2f} | Penalty: {result['penalty']:.2f} | Hard: {result['hard']}")
        print(f"  Met: {result['criteria_met']}/{result['criteria_total']}")
        print(f"  Anti-patterns: {result['anti_patterns']}")
        print("  Criteria:")
        for d in result['criteria_details']:
            status = "✓" if d['met'] else "✗"
            print(f"    {status} {d['criterion']}")