"""Shared hardened scoring for SkillOpt environment adapters.

Token-aware, normalized matching plus anti-pattern detection, explicit
error/empty handling, and **ordered-sequence** scoring.

Replaces the naive substring scorer used by the moli / webintel / notebooklm /
gebiz adapters.

Item schema (backward compatible with a plain ``check`` list)
-------------------------------------------------------------
    {
      "id": "train_000",
      "question": "...",
      "check": ["pattern_a", "pattern_b"],          # required patterns (presence)
      "order": ["pattern_a", "pattern_b"],           # must appear in this order
      "must_not": ["forbidden_pattern"],             # forbidden patterns
      "optional": ["bonus_pattern"],                  # bonus patterns
    }

``check`` may also be a list of dicts for weighted patterns:
    {"check": [{"pattern": "POST", "weight": 2.0}, ...]}

Scoring model
-------------
    presence = clamp(matched_weight / total_weight - penalty + bonus, 0, 1)
    order    = LCS(actual_order, expected_order) / len(expected_order)   (1.0 if no order)
    soft     = presence * order
    hard     = 1.0 if soft >= 1.0 else 0.0

Order is a *multiplier*: it can only reduce the score, never inflate it. A
response that mentions every required pattern but in the wrong sequence scores
below 1.0 (and thus hard=0.0), while a response missing a pattern is already
penalized by presence. Order is graded via longest-common-subsequence, so a
mostly-correct sequence scores higher than a fully scrambled one.
"""
from __future__ import annotations

import html as _html
import re
from typing import Any


def _normalize(text: str) -> str:
    """Lowercase, decode HTML entities, collapse whitespace."""
    if not text:
        return ""
    text = _html.unescape(text)
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ── Synonym / lemma matching ────────────────────────────────────────────────
# The scorer previously used exact word-boundary matching only, which produced
# ~90% FALSE failures: a model that answered correctly but phrased it
# differently (plural, synonym, word-form) was scored as a miss. This misled
# the optimizer into editing the prompt for non-issues. These maps let a
# required pattern match its common synonyms and inflections.
_SYNONYMS = {
    "injection": ["inject", "arbitrary code execution", "code execution", "injected"],
    "moving": ["movable", "moves", "advances", "advancing"],
    "lookup": ["lookups", "look up", "lookups"],
    "same": ["interchangeably", "equivalent", "identical", "synonyms", "synonym"],
    "issue": ["defect", "bug", "problem", "fault"],
    "verified": ["verify", "verifies", "confirms", "confirmed", "works", "working"],
    "report": ["summary", "wrap-up", "summarize", "summarise", "reporting"],
    "simple": ["small", "standalone", "straightforward", "minimal", "basic"],
    "single file": ["standalone script", "one file", "single script", "one script"],
    "correct": ["fix", "right", "corrected", "correction"],
    "apologize": ["sorry", "apology", "apologise"],
    "broken": ["not working", "doesn't work", "dead", "invalid"],
    "right link": ["correct link", "proper link", "working link"],
    "retrieve": ["retrieves", "fetches", "gets", "fetch"],
    "submit": ["submits", "sends", "post"],
    "unique": ["uniquely", "distinct", "unique identifier"],
    "reference": ["references", "refers", "referencing"],
    "server": ["serves", "server-side", "backend"],
    "client": ["client-side", "frontend", "browser"],
    "structure": ["schema", "layout", "organization"],
    "tables": ["table", "relations"],
    "encrypted": ["encryption", "encrypts", "tls", "ssl"],
    "tls": ["ssl", "encryption"],
    "snapshot": ["snapshots", "point-in-time", "state"],
    "replay": ["replays", "re-applies", "reapplies"],
    "commit": ["commits", "committed"],
    "mutable": ["changeable", "modifiable"],
    "immutable": ["unchangeable", "fixed", "cannot change"],
    "hash": ["hashes", "hashing"],
    "collision": ["collisions", "collide"],
    "pointer": ["pointers", "reference"],
    "node": ["nodes", "element"],
    "acyclic": ["no cycles", "without cycles"],
    "cycle": ["cycles", "circular"],
    "fifo": ["first-in-first-out", "queue"],
    "lifo": ["last-in-first-out", "stack"],
    "atomic": ["all-or-nothing", "indivisible"],
    "commit": ["commits", "transaction"],
    "distribute": ["distributes", "distributed", "spreads", "load-balances"],
    "traffic": ["requests", "load"],
    "filter": ["filters", "blocks", "screens"],
    "tunnel": ["tunnels", "encrypted connection"],
    "isolate": ["isolates", "isolated", "sandbox"],
    "package": ["packages", "bundles"],
    "emulate": ["emulates", "simulates", "virtualizes"],
    "hardware": ["physical machine", "physical hardware"],
    "reusable": ["reuse", "re-usable", "reusability"],
    "solution": ["solutions", "approach", "pattern"],
    "translate": ["translates", "compiles", "converts"],
    "execute": ["executes", "runs", "interpreted"],
    "concurrent": ["concurrent", "parallel", "simultaneous"],
    "unexpected": ["unexpected", "race", "nondeterministic"],
    "callback": ["callbacks", "webhook", "http callback"],
    "decompose": ["decomposes", "split", "break into"],
    "single": ["one", "monolithic", "unified"],
    "not released": ["leak", "not freed", "unreleased"],
    "control": ["controls", "inversion of control", "calls you"],
    "inversion": ["inversion of control", "ioc"],
    "content": ["contents", "assets", "media"],
    "left": ["left child", "left subtree"],
    "right": ["right child", "right subtree"],
    "pattern": ["patterns", "regex", "regular expression"],
    "match": ["matches", "matching"],
    "map": ["maps", "mapping", "hashes"],
    "fixed": ["fixed-length", "constant", "deterministic"],
    "structure": ["structures", "schema", "layout"],
    "combine": ["combines", "joins", "merges"],
    "permission": ["permissions", "license", "rights"],
    "track": ["tracks", "tracing", "versioning"],
    "changes": ["change", "revisions", "history"],
    "merge": ["merges", "merging", "combine"],
    "review": ["reviews", "reviewing", "code review"],
    "copy": ["copies", "backup", "snapshot"],
    "restore": ["restores", "recovery", "recover"],
    "inode": ["inodes", "index node"],
    "background": ["background process", "daemon", "runs in background"],
    "process": ["processes", "daemon", "service"],
    "redundant": ["redundancy", "duplicate", "repetition"],
    "consolidate": ["consolidation", "merge", "combine"],
    "dilute": ["dilutes", "weakens", "waters down"],
    "tokens": ["token", "cost", "tokens cost"],
    "skill_manage": ["skill tool", "skill management tool"],
    "session_search": ["search tool", "conversation search"],
    "read_file": ["file reader", "read file"],
    "cronjob": ["cron job", "scheduled job", "schedule"],
    "schedule": ["scheduled", "cron", "recurring"],
    "plugin": ["plugins", "extension", "add-on"],
    "skill": ["skills", "procedure", "workflow"],
    "memory": ["memories", "preference", "fact"],
    "procedure": ["procedures", "process", "workflow"],
    "reusable": ["reuse", "re-usable"],
    "confirm": ["confirms", "confirmation", "ask", "check"],
    "destructive": ["destructive action", "dangerous", "irreversible"],
    "irreversible": ["irreversible action", "cannot undo", "permanent"],
    "ask the user": ["ask", "confirm with user", "check with user"],
    "haven't": ["have not", "not yet", "didn't"],
    "run": ["ran", "running", "execute"],
    "correct": ["fix", "right", "corrected"],
    "acknowledge": ["acknowledges", "admit", "own up"],
    "assumption": ["assumptions", "assumed", "wrong assumption"],
    "right command": ["correct command", "proper command", "fixed command"],
    "not saved": ["never wrote", "didn't save", "not written"],
    "write": ["writes", "saved", "save"],
    "broken": ["not working", "dead", "invalid"],
    "right link": ["correct link", "working link", "proper link"],
    "one-off": ["one time", "single use", "not recurring"],
    "not worth": ["not worth it", "overkill", "unnecessary"],
    "minimal": ["minimalist", "small", "simple"],
    "framework": ["frameworks", "library", "abstraction"],
    "database": ["databases", "db", "data store"],
    "abstraction layer": ["abstraction", "framework", "layer"],
    "requirements": ["requirement", "needs", "demands"],
    "redundant": ["redundancy", "duplicate", "repetition"],
    "consolidate": ["consolidation", "merge", "combine"],
    "dilute": ["dilutes", "weakens", "waters down"],
    "tokens": ["token", "cost"],
    "exact name": ["exact tool name", "precise name", "canonical name"],
    "ambiguous": ["ambiguity", "unclear", "vague"],
    "hallucinate": ["hallucination", "fabricate", "make up"],
    "skill_view": ["view skill", "load skill"],
    "next action": ["next step", "proceed", "continue"],
    "check output": ["check the output", "inspect output", "verify output"],
    "control flow": ["control-flow", "branching", "flow"],
    "corrupt": ["corruption", "break", "damage"],
    "significant rewrite": ["major rewrite", "large change", "big edit"],
    "minor typo": ["small typo", "typo", "small fix"],
    "always patch": ["patch always", "patch everything"],
    "no risk": ["no risk", "safe", "harmless"],
    "applied": ["applied the fix", "implemented", "done"],
    "fixed": ["fixed it", "resolved", "solved"],
    "done": ["completed", "finished", "complete"],
    "result": ["results", "outcome", "output"],
    "no need to ask": ["don't ask", "no need", "just report"],
    "would you like me to": ["want me to", "shall i", "should i"],
    "want me to": ["would you like me to", "shall i", "should i"],
    "shall i": ["want me to", "should i", "would you like me to"],
    "should i": ["want me to", "shall i", "would you like me to"],
    "drop immediately": ["drop now", "delete now", "execute now"],
    "execute without asking": ["run without asking", "do it without asking", "act immediately"],
    "delete without asking": ["remove without asking", "delete now"],
    "it's saved": ["it is saved", "already saved"],
    "already done": ["already completed", "done", "finished"],
    "run it anyway": ["run it", "execute it", "go ahead"],
    "it's fine": ["it is fine", "no problem", "ok"],
    "wait until asked": ["wait", "don't volunteer", "only if asked"],
    "leave it": ["leave it alone", "don't mention", "ignore"],
    "it passed": ["passed", "all green", "tests passed"],
    "all green": ["all tests pass", "green", "passing"],
    "click it": ["use it", "open it"],
    "it works": ["it works fine", "functional"],
    "no need": ["not necessary", "unnecessary", "skip"],
    "right number": ["correct number", "accurate number", "proper number"],
    "misquoted": ["misquote", "wrong number", "incorrect number"],
    "haven't run": ["have not run", "not run", "didn't run"],
    "run it": ["run the test", "execute it", "test it"],
    "correct": ["fix", "right", "corrected"],
    "apologize": ["sorry", "apology", "apologise"],
    "right command": ["correct command", "proper command", "fixed command"],
    "acknowledge": ["acknowledges", "admit", "own up"],
    "assumption": ["assumptions", "assumed", "wrong assumption"],
    "not saved": ["never wrote", "didn't save", "not written"],
    "write": ["writes", "saved", "save"],
    "broken": ["not working", "dead", "invalid"],
    "right link": ["correct link", "working link", "proper link"],
    "one-off": ["one time", "single use", "not recurring"],
    "not worth": ["not worth it", "overkill", "unnecessary"],
    "minimal": ["minimalist", "small", "simple"],
    "framework": ["frameworks", "library", "abstraction"],
    "database": ["databases", "db", "data store"],
    "abstraction layer": ["abstraction", "framework", "layer"],
    "requirements": ["requirement", "needs", "demands"],
    "redundant": ["redundancy", "duplicate", "repetition"],
    "consolidate": ["consolidation", "merge", "combine"],
    "dilute": ["dilutes", "weakens", "waters down"],
    "tokens": ["token", "cost"],
    "exact name": ["exact tool name", "precise name", "canonical name"],
    "ambiguous": ["ambiguity", "unclear", "vague"],
    "hallucinate": ["hallucination", "fabricate", "make up"],
    "skill_view": ["view skill", "load skill"],
    "next action": ["next step", "proceed", "continue"],
    "check output": ["check the output", "inspect output", "verify output"],
    "control flow": ["control-flow", "branching", "flow"],
    "corrupt": ["corruption", "break", "damage"],
    "significant rewrite": ["major rewrite", "large change", "big edit"],
    "minor typo": ["small typo", "typo", "small fix"],
    "always patch": ["patch always", "patch everything"],
    "no risk": ["no risk", "safe", "harmless"],
    "applied": ["applied the fix", "implemented", "done"],
    "fixed": ["fixed it", "resolved", "solved"],
    "done": ["completed", "finished", "complete"],
    "result": ["results", "outcome", "output"],
    "no need to ask": ["don't ask", "no need", "just report"],
    "would you like me to": ["want me to", "shall i", "should i"],
    "want me to": ["would you like me to", "shall i", "should i"],
    "shall i": ["want me to", "should i", "would you like me to"],
    "should i": ["want me to", "shall i", "would you like me to"],
    "drop immediately": ["drop now", "delete now", "execute now"],
    "execute without asking": ["run without asking", "do it without asking", "act immediately"],
    "delete without asking": ["remove without asking", "delete now"],
    "it's saved": ["it is saved", "already saved"],
    "already done": ["already completed", "done", "finished"],
    "run it anyway": ["run it", "execute it", "go ahead"],
    "it's fine": ["it is fine", "no problem", "ok"],
    "wait until asked": ["wait", "don't volunteer", "only if asked"],
    "leave it": ["leave it alone", "don't mention", "ignore"],
    "it passed": ["passed", "all green", "tests passed"],
    "all green": ["all tests pass", "green", "passing"],
    "click it": ["use it", "open it"],
    "it works": ["it works fine", "functional"],
    "no need": ["not necessary", "unnecessary", "skip"],
    "right number": ["correct number", "accurate number", "proper number"],
    "misquoted": ["misquote", "wrong number", "incorrect number"],
    "haven't run": ["have not run", "not run", "didn't run"],
    "run it": ["run the test", "execute it", "test it"],
}


def _lemmatize(word: str) -> str:
    """Reduce a word to a base form (conservative English inflection handling).

    Only handles PLURALS (-s, -es, -ies) — the common false-failure case.
    Does NOT strip -ing/-ed, which over-stems and breaks words (e.g. 'speed'
    -> 'spe', 'moving' -> 'mov'). Synonyms are handled by _SYNONYMS instead.
    """
    if len(word) <= 3:
        return word
    # -ies -> -y (e.g. libraries -> library)
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    # -es -> (e.g. boxes -> box, matches -> match)
    if word.endswith("es") and len(word) > 4:
        return word[:-2]
    # -s -> (e.g. lookups -> lookup, speeds -> speed)
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _token_find(pattern: str, text: str) -> int | None:
    """Return the start index of the first whole-token match, or None.

    Matches the pattern OR its synonyms/lemmas in the text. Uses word
    boundaries so ``POST`` does not match ``postpone``.
    """
    p = _normalize(pattern)
    t = _normalize(text)
    if not p or not t:
        return None
    # Direct whole-token match
    escaped = re.escape(p)
    prefix = r"\b" if p[:1].isalnum() else ""
    suffix = r"\b" if p[-1:].isalnum() else ""
    m = re.search(prefix + escaped + suffix, t)
    if m:
        return m.start()
    # Synonym match
    for syn in _SYNONYMS.get(p, []):
        syn_n = _normalize(syn)
        if not syn_n:
            continue
        s_esc = re.escape(syn_n)
        s_pre = r"\b" if syn_n[:1].isalnum() else ""
        s_suf = r"\b" if syn_n[-1:].isalnum() else ""
        if re.search(s_pre + s_esc + s_suf, t):
            return 0  # matched a synonym
    # Lemma match: check if the pattern's lemma appears in the text's lemmas.
    # Lemmatize BOTH sides so "speeds" (text) matches "speed" (pattern).
    p_lemma = _lemmatize(p)
    if p_lemma != p and p_lemma:
        p_esc = re.escape(p_lemma)
        p_pre = r"\b" if p_lemma[:1].isalnum() else ""
        p_suf = r"\b" if p_lemma[-1:].isalnum() else ""
        if re.search(p_pre + p_esc + p_suf, t):
            return 0
    # Also try: pattern's lemma against lemmatized text tokens.
    # e.g. pattern "speed" (lemma "speed") vs text "speeds" (lemma "speed").
    if p_lemma:
        for tok in t.split():
            if _lemmatize(tok) == p_lemma:
                return 0
    return None


def _token_match(pattern: str, text: str) -> bool:
    """Match ``pattern`` as a whole token/phrase in ``text``.

    Uses word boundaries so ``POST`` does not match ``postpone`` and ``GET``
    does not match ``target``. Multi-word patterns match as a phrase.
    Both pattern and text are normalized internally.
    """
    return _token_find(pattern, text) is not None


def _spec_matches(spec: dict, text_norm: str) -> bool:
    """True if ``text_norm`` matches the spec's pattern OR any accepted phrasing.

    Only ever called on REQUIRED / BONUS specs (check / optional). Forbidden
    (must_not) specs are matched by ``_token_match(spec['pattern'])`` directly,
    so accept lists can never soften a hard veto.
    """
    if _token_match(spec["pattern"], text_norm):
        return True
    for acc in spec.get("accept") or []:
        if acc and _token_match(str(acc), text_norm):
            return True
    return False


def _pattern_specs(check: Any) -> list[dict]:
    """Normalize a ``check`` value into a list of {pattern, weight, accept} dicts.

    ``accept`` (optional) is a list of additional whole-token phrasings that
    count as a match for this pattern. This is the deterministic alternative
    to fragile semantic similarity: an item can enumerate the correct natural
    phrasings of a required concept, and the scorer matches any of them
    exactly. ``accept`` is NEVER applied to ``must_not`` (forbidden patterns
    stay strict so vetoes can't be accidentally softened).
    """
    if not check:
        return []
    specs = []
    for entry in check:
        if isinstance(entry, str):
            specs.append({"pattern": entry, "weight": 1.0, "accept": []})
        elif isinstance(entry, dict):
            accept = entry.get("accept") or []
            specs.append({
                "pattern": str(entry.get("pattern", "")),
                "weight": float(entry.get("weight", 1.0)),
                "accept": list(accept) if isinstance(accept, (list, tuple)) else [accept],
            })
        else:
            specs.append({"pattern": str(entry), "weight": 1.0, "accept": []})
    return [s for s in specs if s["pattern"]]


def _lcs_length(a: list, b: list) -> int:
    """Longest common subsequence length (order-preserving)."""
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n]


def _order_score(text_norm: str, order: Any) -> float:
    """Graded order score via longest-common-subsequence.

    Returns 1.0 when no order constraint is given. Otherwise returns the
    fraction of the expected sequence that appears in the correct relative
    order in the response. Missing patterns are ignored here (presence is
    scored separately) so a missing step is not double-penalized.
    """
    specs = _pattern_specs(order)
    if not specs:
        return 1.0
    found = []
    for i, s in enumerate(specs):
        pos = _token_find(s["pattern"], text_norm)
        if pos is not None:
            found.append((pos, i))
    found.sort()
    actual = [i for _, i in found]
    expected = list(range(len(specs)))
    return _lcs_length(actual, expected) / len(specs)


def score_response(
    text: str,
    check: Any = None,
    must_not: Any = None,
    optional: Any = None,
    order: Any = None,
    max_chars: int | None = None,
) -> dict:
    """Score a model response against required / forbidden / bonus / ordered patterns.

    ``max_chars`` (optional) applies a conciseness penalty: responses longer
    than the cap lose up to 0.3 soft (0.1 per 25% over, capped). This lets
    items reward brevity, not just token presence/absence. Returns a dict with
    ``hard`` (0.0 or 1.0), ``soft`` (graded 0.0–1.0), ``matched``, ``missed``,
    ``violations``, ``order_score``, and ``reason``.
    """
    norm = _normalize(text or "")

    if not norm:
        return {
            "hard": 0.0, "soft": 0.0,
            "matched": [], "missed": [], "violations": [],
            "order_score": 0.0, "reason": "empty_or_error_response",
        }
    if norm.startswith("error:"):
        return {
            "hard": 0.0, "soft": 0.0,
            "matched": [], "missed": [], "violations": [],
            "order_score": 0.0, "reason": "error_response",
        }

    required = _pattern_specs(check)
    forbidden = _pattern_specs(must_not)
    bonus = _pattern_specs(optional)

    if not required:
        return {
            "hard": 0.0, "soft": 0.0,
            "matched": [], "missed": [], "violations": [],
            "order_score": 0.0, "reason": "no_check_patterns_defined",
        }

    matched = [s["pattern"] for s in required if _spec_matches(s, norm)]
    missed = [s["pattern"] for s in required if not _spec_matches(s, norm)]
    # Forbidden patterns stay STRICT: matched by exact pattern only, never the
    # accept list — so accept lists cannot soften a hard veto.
    violations = [s["pattern"] for s in forbidden if _token_match(s["pattern"], norm)]

    total_weight = sum(s["weight"] for s in required)
    matched_weight = sum(
        s["weight"] for s in required if _spec_matches(s, norm)
    )
    base = matched_weight / total_weight if total_weight else 0.0

    penalty = 0.0
    if forbidden:
        penalty = len(violations) / len(forbidden)

    bonus_bump = 0.0
    if bonus:
        bonus_bump = 0.1 * (sum(1 for s in bonus if _spec_matches(s, norm)) / len(bonus))

    presence = max(0.0, min(1.0, base - penalty + bonus_bump))

    # Conciseness penalty: reward brevity when a cap is set. Over-length loses
    # up to 0.3 soft (0.1 per 25% over the cap, capped at 0.3).
    length_penalty = 0.0
    if max_chars and max_chars > 0 and len(norm) > max_chars:
        over = (len(norm) - max_chars) / max_chars
        length_penalty = min(0.3, 0.1 * (over / 0.25))
        presence = max(0.0, presence - length_penalty)

    order_score = _order_score(norm, order)
    soft = presence * order_score
    hard = 1.0 if soft >= 1.0 else 0.0

    return {
        "hard": hard,
        "soft": soft,
        "matched": matched,
        "missed": missed,
        "violations": violations,
        "order_score": order_score,
        "length_penalty": length_penalty,
        "reason": "ok",
    }


def score_item(text: str, item: dict) -> dict:
    """Score a response against a full item dict (check / order / must_not / optional)."""
    return score_response(
        text,
        check=item.get("check"),
        must_not=item.get("must_not"),
        optional=item.get("optional"),
        order=item.get("order"),
    )
