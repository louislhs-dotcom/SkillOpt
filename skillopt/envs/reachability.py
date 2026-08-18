#!/usr/bin/env python3
"""Reachability check for the SkillOpt webintel scorer.

Detects a specific failure mode: a response recommends `moli fetch` (or curl)
for a site that returns HTTP 403 to non-browser fetches (bot-protected sites
like Carousell, many marketplaces, Cloudflare-fronted pages). Moli cannot fetch
these — the correct tool is ego-browser (real Chrome, passes bot detection).

The scorer should penalize responses that recommend Moli for a 403-blocked
site, because those commands fail in practice even though the text looks right.

Usage:
    from skillopt.envs.reachability import check_reachability
    result = check_reachability(text)
    # {"ok": bool, "penalty": float, "blocked": [urls], "reason": str}
"""
from __future__ import annotations

import re
import urllib.request
import urllib.error

# Sites verified to return 403 / crash non-browser fetches (Moli/curl).
# These MUST be fetched with ego-browser, not Moli.
# - carousell.sg: HTTP 403 to Moli/curl
# - taobao.com: Moli crashes (exit 134, anti-bot JS fireyejs/flexible.js errors);
#   curl gets 200 but content is JS-rendered; ego-browser loads full logged-in state
# - shopee.sg: Moli returns a stripped "Login Required" wall (no useful content);
#   ego-browser loads the full logged-in marketplace
BOT_PROTECTED_DOMAINS = {
    "carousell.sg",
    "www.carousell.sg",
    "carousell.com",
    "www.carousell.com",
    "taobao.com",
    "www.taobao.com",
    "taobao.cn",
    "www.taobao.cn",
    "tmall.com",
    "www.tmall.com",
    "shopee.sg",
    "www.shopee.sg",
    "shopee.com",
    "www.shopee.com",
}

# Penalty applied when a response recommends Moli for a bot-protected site.
PENALTY_PER_BLOCKED = 0.2
MAX_PENALTY = 0.4

# A response "recommends Moli" if it mentions moli fetch / moli serve near a URL.
_MOLI_RE = re.compile(
    r"moli\s+(?:fetch|serve|--dump)", re.IGNORECASE
)
_URL_RE = re.compile(
    r"https?://([a-z0-9.-]+)(?:/[^\s\"'`<>]*)?", re.IGNORECASE
)


def _extract_domains(text: str) -> set[str]:
    """Extract unique domains from URLs in the text."""
    return {m.group(1).lower() for m in _URL_RE.finditer(text)}


def _recommends_moli(text: str) -> bool:
    """True if the response recommends using Moli to fetch pages."""
    return bool(_MOLI_RE.search(text))


def _is_bot_protected(domain: str) -> bool:
    """Check if a domain is in the known bot-protected set."""
    return domain in BOT_PROTECTED_DOMAINS


def check_reachability(text: str) -> dict:
    """Check whether a response recommends Moli for a bot-protected site.

    Returns:
        {
          "ok": bool,          # True if no Moli-for-blocked-site defect
          "penalty": float,    # 0.0 if ok, else up to MAX_PENALTY
          "blocked": [str],    # domains that are bot-protected but Moli-recommended
          "reason": str,
        }
    """
    if not text or not text.strip():
        return {"ok": True, "penalty": 0.0, "blocked": [], "reason": "empty"}

    domains = _extract_domains(text)
    if not domains:
        return {"ok": True, "penalty": 0.0, "blocked": [], "reason": "no_urls"}

    recommends_moli = _recommends_moli(text)
    blocked = sorted(d for d in domains if _is_bot_protected(d))

    if blocked and recommends_moli:
        penalty = min(MAX_PENALTY, PENALTY_PER_BLOCKED * len(blocked))
        return {
            "ok": False,
            "penalty": penalty,
            "blocked": blocked,
            "reason": (
                f"recommends Moli for bot-protected site(s) {blocked} "
                f"which return HTTP 403 to non-browser fetches; use ego-browser"
            ),
        }

    return {"ok": True, "penalty": 0.0, "blocked": blocked, "reason": "ok"}


if __name__ == "__main__":
    import sys
    text = sys.stdin.read()
    print(check_reachability(text))
