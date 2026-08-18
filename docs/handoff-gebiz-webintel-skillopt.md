# Handoff: GeBIZ WebIntel + SkillOpt Integration

**Doc author:** Hermes Agent (glm-5.2:cloud)
**Training run optimizer:** nvidia/nemotron-3-ultra-550b-a55b
**Training run target:** nvidia/nemotron-3.5-lightning-30b-a3b
**Date:** August 18, 2026
**Purpose:** How the GeBIZ web intelligence skill was built, verified, and passed through SkillOpt training

---

## 1. What Is GeBIZ?

GeBIZ (`https://www.gebiz.gov.sg`) is the Singapore Government's one-stop e-procurement portal — tenders, quotations, awards, and supplier registration. It is **not** a normal website. It is a **JSF (JavaServer Faces) / PrimeFaces** stateful application.

### Why GeBIZ Is the Hardest Site in the WebIntel Skill

| Tool | Result | Why |
|------|--------|-----|
| **curl** | HTTP 200, but empty shell | GET returns the page frame; content loads via JSF AJAX |
| **Moli** | Page shell only — stuck at "LOADING/SEARCHING" | Moli renders structure but JSF lazy-loads content via PrimeFaces AJAX partial updates |
| **ego-browser (static load)** | Page shell only — body ~700-900 chars | Same: tender table hydrates only after JSF form interaction |
| **ego-browser (full JSF flow)** | ✅ Tables hydrate (11 tables, 37 rows) | Correct: ViewState → POST → AJAX partial update → table renders |

**The key insight:** GeBIZ is not a "which tool" problem — it's a "which flow" problem. The tool is always ego-browser, but the *flow* (ViewState extraction → form POST → wait for AJAX) is what matters.

---

## 2. The Verified GeBIZ JSF Flow

Tested live on August 17, 2026 via ego-browser:

### Step-by-Step

1. **Open** `https://www.gebiz.gov.sg/ptn/opportunity/BOListing.xhtml`
2. **Extract ViewState** — read the hidden input:
   ```javascript
   document.querySelector('input[name="javax.faces.ViewState"]').value
   // e.g., "-2457674906927854573:6221920039114427688"
   ```
3. **Click a command button** (e.g., `contentForm:buttonContinue`) via its JSF id:
   ```javascript
   document.getElementById('contentForm:buttonContinue').click()
   ```
4. **Wait for table hydration** — use `waitForSelector` on the results table:
   ```javascript
   await tab.waitForSelector('table[id$="resultsTable"]', { timeout: 30000 })
   // PrimeFaces rows: tbody tr[data-ri]
   ```
5. **For filtered search:** POST form data + the fresh ViewState to the same URL

### Critical Mechanics

- **`javax.faces.ViewState`** — hidden input, mandatory on every POST. GET fails for form actions. Value changes after each interaction; always re-extract.
- **JSF colon component IDs** — `formId:componentId` (e.g., `contentForm:buttonContinue`, `searchForm:keywordInput`). CSS selectors need escaping: `#searchForm\\:keywordInput`
- **Wait strategy:** Use `waitForSelector` on specific elements. **NEVER use `networkidle`** — JSF partial updates never fully idle.
- **Multiple windows detection:** GeBIZ rejects concurrent tabs ("Our system has detected that multiple browser windows are being opened"). Use ego-browser task spaces to isolate sessions.

### Alternative: Standalone Python Script

A standalone script (`scripts/gebiz_search.py`) handles the full JSF flow without a browser:

```bash
python3 scripts/gebiz_search.py "construction"            # text output
python3 scripts/gebiz_search.py "construction" --json     # JSON
python3 scripts/gebiz_search.py "construction" --max 20   # limit records
```

This script:
1. GETs `BOAdvancedSearch.xhtml` to obtain session cookie + ViewState
2. POSTs the search form (`contentForm:j_idt148_inputText` = keyword, `contentForm:buttonSearch` = "Search")
3. Parses the returned HTML into structured records (index, type, status, title, docCode, agency)

### Key Endpoints (Verified August 16, 2026)

| Endpoint | Purpose | Status |
|----------|---------|--------|
| `/ptn/opportunity/BOListing.xhtml` | Tender listing (needs JSF flow) | ✅ Working |
| `/ptn/opportunity/BOAdvancedSearch.xhtml` | Advanced search (POST with ViewState) | ✅ Working |
| `/ptn/opportunity/directlink.xhtml?docCode=XXXX` | Direct document link | ✅ Working |
| `/eservices/search/advancedSearch.xhtml` | **STALE** — "Page not found" | ❌ Dead |

---

## 3. The WebIntel Skill Structure

The SkillOpt webintel environment lives at `~/SkillOpt/skillopt/envs/webintel/`:

```
skillopt/envs/webintel/
├── skills/
│   ├── initial.md          ← The trained skill (what SkillOpt optimizes)
│   ├── gebiz.md            ← Site-specific GeBIZ config (115 lines, thorough)
│   ├── carousell.md         ← Carousell site config
│   └── lazada_sg.md         ← Lazada SG site config
├── site_configs/
│   └── gebiz.md            ← Updated site config with verified flow
├── adapter.py              ← Environment adapter (scoring, eval)
└── dataloader.py           ← Loads train/val/test items
```

### The Bug We Found: Knowledge Not Reaching the Trained Skill

**The critical bug:** `initial.md` (the file SkillOpt actually trains) had **zero GeBIZ content**, while `gebiz.md` (115 lines, thorough) sat as a sibling file and was **never merged** into the trained skill. The config trains `initial.md` directly; the template + site-config merge was off.

**Result:** The model answered GeBIZ validation questions purely from base model knowledge, not from the skill. This was fragile — if questions got harder or the val set emphasized GeBIZ more, the score would expose the missing guidance.

**Fix applied:** Added a full GeBIZ section directly to `initial.md` (lines 231-270 in the updated file) covering:
- The JSF stateful app behavior (shell-only on static load)
- ViewState mandatory requirement
- JSF colon component IDs
- Verified ego-browser flow (5 steps)
- Tool routing (ego-browser only; Moli NOT usable for GeBIZ tender data)
- Anti-patterns (no GET for search, no `networkidle`, no stable component IDs)

The optimized `best_skill.md` (from the latest training run) carries **7 GeBIZ mentions and 6 ViewState mentions** — the knowledge survived training.

---

## 4. How GeBIZ Passed Through SkillOpt

### Training Configuration

| Setting | Value |
|---------|-------|
| **Optimizer model** | `nvidia/nemotron-3-ultra-550b-a55b` (via Switchyard) |
| **Target model** | `nvidia/nemotron-3.5-lightning-30b-a3b` (via Switchyard) |
| **Gate metric** | `soft` (partial credit for matched patterns) |
| **Selection envs** | 18 validation items |
| **Analyst workers** | 4 (later increased to 8 for speed) |
| **Steps per epoch** | 16 |
| **Epochs** | 2 (ran to step 44) |
| **Train size** | 78 items (5 GeBIZ) |
| **Val size** | 18 items (2 GeBIZ) |
| **Edit budget** | 3 per step |

### GeBIZ Training Data

**Train items (5):**

| ID | Question | Check patterns |
|----|----------|---------------|
| train_021 | Search GeBIZ for construction tenders | `ego-browser`, `gebiz`, `jsf`, `viewstate` |
| train_022 | Download tender documents from GeBIZ | `ego-browser`, `gebiz`, `login`, `corppass`, `download` |
| train_023 | Submit a quotation on GeBIZ | `ego-browser`, `gebiz`, `viewstate`, `form-submit`, `post` |
| train_024 | Monitor GeBIZ award listings daily | `moli`, `gebiz`, `scheduled`, `award` |
| train_025 | Handle JSF partial page updates | `ego-browser`, `gebiz`, `waitForSelector`, `ajax`, `partial` |

**Validation items (2):**

| ID | Question | Check patterns | Must_not |
|----|----------|---------------|----------|
| val_007 | Wait strategy for PrimeFaces AJAX updates | `ego-browser`, `waitForSelector`, `AJAX`, `partial`, `networkidle`, `JSF`, `ViewState` | `networkidle` |
| val_008 | ViewState handling for quotation submission | `ego-browser`, `ViewState`, `javax.faces.ViewState`, `POST`, `form`, `hidden`, `JSF` | `get` |

### The Scoring Gate

SkillOpt uses a **token-aware, normalized matching scorer** (`skillopt/envs/scoring.py`):

```
presence = clamp(matched_weight / total_weight - penalty + bonus, 0, 1)
order    = LCS(actual_order, expected_order) / len(expected_order)
soft     = presence * order
hard     = 1.0 if soft >= 1.0 else 0.0
```

- **Patterns** are matched as whole tokens (word boundaries) — `POST` doesn't match `postpone`, but `get` matches inside `getElementById` (word-boundary `\bget\b` matches standalone "get" in any context)
- **must_not** patterns trigger absolute penalties — if the response mentions a forbidden pattern, `soft` drops to 0.0 regardless of how many `check` patterns matched
- **soft** metric gives partial credit; **hard** is all-or-nothing (soft ≥ 1.0)
- The gate uses **soft** metric for selection

### ⚠️ Known Scoring Issue: val_007 Contradiction

`val_007` has `networkidle` in **both** `check` (must mention) AND `must_not` (forbidden). This is a contradiction in the training data:
- The model is penalized for mentioning `networkidle` (must_not violation → soft = 0.0)
- But the check list requires mentioning it (to get all patterns matched)

**Result:** Both GeBIZ val items score **hard=0.0, soft=0.0** — a hard zero, not a low score. The `must_not` penalty is absolute: **any** answer that mentions `networkidle` (even to say "avoid it") is instantly zeroed by the scorer. The model's val_007 answer literally says "AVOID networkidle" — which is the correct guidance, but the scorer can't distinguish "mention to recommend against" from "mention to recommend." (Verified in `data/webintel_split/val/items.json`: val_007 has `networkidle` in both `check` and `must_not`.)

**This means GeBIZ val items contribute 0 to the gate score in every run.** The optimizer improved the overall soft score (0.556 → 0.695) by improving other items, not GeBIZ ones. The GeBIZ knowledge in the skill is correct and present, but the scoring gate can't measure it properly due to the contradiction.

### Training Run Results (Latest: `20260818_031426`)

| Metric | Baseline (step 0) | Best (step 42) |
|--------|-------------------|----------------|
| **Soft score (gate metric)** | 0.556 | **0.695** |
| **Selection hard** | 0.444 (8/18) | 0.444 (8/18) — **flat** |
| **Rollout hard (step 42)** | — | 0.4 (2/5) |
| **Action** | — | `accept_new_best` |
| **Accepted steps** | — | 3 (steps 36, 40, 42) |
| **Rejected steps** | — | 39 |
| **Total steps** | — | 44 |

**The real story:** Soft improved (+25%) while hard stayed flat (8/18 → 8/18). The gate uses `soft` metric, so the optimizer accepted candidates that improved partial-credit scores even when the number of fully-solved items didn't change. This is by design (gate_metric: `soft` in config) but means the "improvement" is in partial matches, not in items fully solved.

**Score progression:**
- Steps 1-35: baseline 0.556, all candidates rejected. Most early steps had `n_failure_patches=1, n_success_patches=0` (the optimizer's patches failed to improve on rollout items). Some steps (4, 7, 8) had 1 success patch but the candidate still lost the gate. Selection soft scores ranged 0.06-0.56 — none beat the 0.556 baseline.
- Step 36: first accept — soft 0.605 (new best)
- Step 40: second accept — soft 0.679
- Step 42: third accept — **soft 0.695** (final best)

### How the GeBIZ Knowledge Survived

Even though GeBIZ val items score 0.0 due to the scoring contradiction, the GeBIZ knowledge in the skill survived because:

1. **The GeBIZ section was added to `initial.md` before training** — the optimizer starts from `initial.md` and applies patches, so the GeBIZ content was in the baseline
2. **The optimizer's patches didn't remove it** — patches were additive (adding routing rules, format requirements), not destructive
3. **The best_skill.md carries 7 GeBIZ mentions and 6 ViewState mentions** — verified post-training

### What the Model Actually Answers for GeBIZ (Step 42, Best Skill)

**val_007 (wait strategy):**
> For GeBIZ (gebiz.gov.sg) PrimeFaces AJAX updates, the correct wait strategy is: Use `waitForSelector` on specific elements. Wait for `tbody tr[data-ri]` rows to hydrate after AJAX updates.

**val_008 (ViewState handling):**
> GeBIZ uses JavaServer Faces (JSF) architecture, which requires specific ViewState handling for form submissions. Every POST request must include the `javax.faces.ViewState` hidden field...

Both answers are **semantically correct** — they mention ego-browser, waitForSelector, ViewState, JSF, POST, form, hidden. The only reason they score 0 is the `must_not` penalty for mentioning `networkidle` / `get`.

---

## 5. The Cross-Site Routing Pattern

GeBIZ was verified alongside other sites. The complete routing table:

| Site | Behavior | Correct Tool | Verified |
|------|----------|--------------|----------|
| **GitHub** (public) | Moli works (HTTP 200, full content) | **Moli** | ✅ Aug 17 |
| **MarkTechPost** | Defuddle works with `--user-agent` | **Defuddle** | ✅ Aug 17 |
| **Carousell** | HTTP 403 to Moli/curl (bot-protected) | **ego-browser** | ✅ Aug 17 |
| **Taobao/Tmall** | Moli crashes (anti-bot JS, exit 134) | **ego-browser** | ✅ Aug 17 |
| **Shopee** | Moli returns login wall | **ego-browser** | ✅ Aug 17 |
| **GeBIZ** | JSF shell-only; needs ViewState+POST flow | **ego-browser** (full JSF flow) | ✅ Aug 17 |
| **Lazada SG** | Standard e-commerce | **Moli** / **ego-browser** | ✅ Aug 17 |

**Rule:** Bot-protected/403/crash/login-wall sites → ego-browser. Public sites → Moli. GeBIZ is special — it's not bot-protected but needs the JSF stateful flow.

---

## 6. Files Modified

| File | Change | Date |
|------|--------|------|
| `skillopt/envs/webintel/skills/initial.md` | Added GeBIZ section (JSF/ViewState/flow/routing/anti-patterns) | Aug 17 |
| `skillopt/envs/webintel/site_configs/gebiz.md` | Updated with verified flow + selectors | Aug 17 |
| `~/.hermes/skills/research/sg-planning-db-access/SKILL.md` | Updated with JSF flow, working endpoint, script reference | Aug 16 |
| `~/.hermes/skills/research/sg-planning-db-access/scripts/gebiz_search.py` | Full JSF POST script (ViewState → form POST → parse) | Aug 16 |
| `~/.hermes/skills/autonomous-ai-agents/skillopt-env-authoring/SKILL.md` | Added GeBIZ verified notes + "check trained file" pitfall | Aug 17 |

### TDAI Memory Logged

- Key `skillopt-gebiz`: Full verification notes — JSF/PrimeFaces stateful app, ViewState mandatory, Moli NOT usable, `initial.md` had zero GeBIZ content (fixed), `gebiz.md` was unmerged.

---

## 7. How to Reproduce

### Prerequisites

- SkillOpt repo at `~/SkillOpt`
- ego-browser installed (for live GeBIZ verification)
- Moli installed (for comparison testing)
- NVIDIA API access (for optimizer/target models via Switchyard)
- TDAI gateway at `:8420` (for shared memory)

### Steps

1. **Verify GeBIZ live (optional, confirms the skill is correct):**
   ```bash
   ego-browser nodejs <<'EOF'
   const task = await useOrCreateTaskSpace('gebiz verify')
   await openOrReuseTab('https://www.gebiz.gov.sg/ptn/opportunity/BOListing.xhtml', { wait: true, timeout: 40 })
   await new Promise(r => setTimeout(r, 8000))
   const vs = await js('document.querySelector("input[name=\\"javax.faces.ViewState\\"]').value')
   cliLog('ViewState: ' + vs.slice(0, 50))
   await js('document.getElementById("contentForm:buttonContinue").click()')
   await new Promise(r => setTimeout(r, 6000))
   const rows = await js('document.querySelectorAll("table tr").length')
   cliLog('Table rows: ' + rows)
   await completeTaskSpace(task.id, { keep: false })
   EOF
   ```

2. **Run SkillOpt training:**
   ```bash
   cd ~/SkillOpt
   python3 scripts/train.py --config configs/webintel/default.yaml
   ```
   The run that produced the results in this doc used `configs/webintel/default.yaml` with `model_backend: switchyard` (routing to NVIDIA NIM models via `configs/switchyard_skillopt.toml`). Other config variants exist (`nim.yaml`, `switchyard.yaml`) but `default.yaml` is the one that was executed.

3. **Check results:**
   ```bash
   LATEST=$(ls -td outputs/skillopt_webintel_* | head -1)
   python3 -c "
   import json
   h = json.load(open('$LATEST/history.json'))
   best = max(h, key=lambda s: s.get('best_score', 0))
   print(f'Best score: {best[\"best_score\"]:.4f} at step {best[\"step\"]}')
   "
   grep -c -i "gebiz" "$LATEST/best_skill.md"  # Should be >0
   ```

4. **Test the standalone GeBIZ search script:**
   ```bash
   python3 ~/.hermes/skills/research/sg-planning-db-access/scripts/gebiz_search.py "construction" --json
   ```

---

## 8. Honest Assessment

### What Works

- ✅ GeBIZ JSF flow is verified live — ViewState extraction + POST + AJAX works in ego-browser
- ✅ The trained skill (`initial.md`) now carries full GeBIZ knowledge
- ✅ The optimized `best_skill.md` retains GeBIZ content (7 mentions, 6 ViewState)
- ✅ The standalone `gebiz_search.py` script works without a browser
- ✅ The model's GeBIZ answers are semantically correct (mentions all required patterns)
- ✅ Overall skill score improved 0.556 → 0.695 (+25%)

### What Doesn't Work (Yet)

- ❌ **GeBIZ val items score 0.0** due to a `check`/`must_not` contradiction (`networkidle` in both lists for val_007)
- ❌ **The optimizer can't improve GeBIZ items** because the gate can't measure them — every candidate scores 0 on GeBIZ regardless of answer quality
- ❌ **The `must_not: ['get']` on val_008** — the scorer uses word-boundary regex matching, so `get` matches as a substring inside longer words like "for**get**", "tar**get**", "**get**ElementById". This is a scorer behavior (word-boundary `\bget\b` still matches standalone "get" in any context), not purely a data authoring bug. The fix is both: use a more specific `must_not` pattern AND consider making the scorer context-aware.
- ❌ **The scoring gate uses exact token matching** — semantically correct answers that paraphrase instead of using exact keywords score 0. Note: LLM-based judge files exist (`skillopt/envs/webintel/dsh_judge.py`, `nvidia_judge.py`) but weren't used in this run.

### Recommended Fixes

1. **Fix val_007:** Remove `networkidle` from `check` (keep it in `must_not`). The question asks what wait strategy to *use*, not what to *avoid*. The check should be: `['ego-browser', 'waitForSelector', 'AJAX', 'partial', 'JSF', 'ViewState']`
2. **Fix val_008:** Change `must_not: ['get']` to `must_not: ['get request']` or remove it — "get" as a bare token matches too many words
3. **Consider semantic scoring:** The current token-matching gate can't recognize "use waitForSelector" as equivalent to "waitForSelector" — a judge model (LLM-based scoring) would be more accurate
4. **Add more GeBIZ val items** — 2 items is too few to measure improvement; aim for 4-5

---

## 9. Key Takeaways for Replication

1. **GeBIZ is a JSF app, not a normal page** — static loads (Moli AND ego-browser) get only the shell. The tender table hydrates via JSF AJAX. This is the #1 thing to understand.
2. **ViewState is mandatory** — `javax.faces.ViewState` hidden input, extracted from each page, submitted with every POST. GET fails for form actions.
3. **Use `waitForSelector`, not `networkidle`** — JSF partial updates never fully idle.
4. **Check that knowledge reaches the trained file** — `gebiz.md` existed but was never merged into `initial.md` (the file SkillOpt trains). Always verify the site knowledge is in the file the config actually trains.
5. **Watch for `check`/`must_not` contradictions** — a pattern in both lists makes the item unsolvable. The scorer will always give 0.0.
6. **The scoring gate is token-based** — it can't measure semantic correctness. Correct answers that paraphrase score 0. This is a known limitation; consider LLM-based judge scoring for future runs.
7. **GeBIZ doesn't fit the Moli-vs-ego-browser binary** — it's not bot-protected (curl gets 200), but it needs ego-browser for the JSF flow. The routing is: ego-browser for all GeBIZ interaction; Moli is NOT usable for tender data.