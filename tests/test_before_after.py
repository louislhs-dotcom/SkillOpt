#!/usr/bin/env python3
"""Before/after demonstration of the scoring + dataloader hardening.

Shows concretely what the naive scorer + check-dropping dataloader get wrong,
then (after porting) what the hardened scorer gets right.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

print("=" * 70)
print("BEFORE: naive substring scorer + check-dropping dataloader")
print("=" * 70)

# 1. Demonstrate the dataloader drops `check`
from skillopt.envs.moli.dataloader import MoliDataLoader
dl = MoliDataLoader(split_dir="data/moli_split", split_mode="split_dir")
dl.setup({})
item = dl.train_items[0]
print(f"\n[1] moli dataloader item keys: {sorted(item.keys())}")
print(f"    'check' present? {'check' in item}")
print(f"    -> raw data has 'check', but _normalize_item DROPS it")

# 2. Demonstrate naive substring matching false positives
def naive_score(text, check_list):
    if check_list:
        found = sum(1 for p in check_list if p.lower() in text.lower())
        return found / len(check_list)
    return 0.5

print(f"\n[2] naive scorer false positives:")
print(f"    'POST' in 'we will postpone the meeting' -> {naive_score('we will postpone the meeting', ['POST'])} (should be 0)")
print(f"    'GET' in 'the target is here' -> {naive_score('the target is here', ['GET'])} (should be 0)")
print(f"    'advancedSearch.xhtml' in 'BOAdvancedSearch.xhtml' -> {naive_score('BOAdvancedSearch.xhtml', ['advancedSearch.xhtml'])} (should be 0)")

# 3. Demonstrate the 0.5 neutral fallback
print(f"\n[3] naive scorer neutral fallback:")
print(f"    empty check list -> {naive_score('anything', [])} (should be 0, not 0.5)")
print(f"    empty answer -> {naive_score('', ['POST'])} (should be 0, not 0.0/0.5)")

print("\n" + "=" * 70)
print("AFTER: hardened token-aware scorer + check-preserving dataloader")
print("=" * 70)

from skillopt.envs.scoring import score_response, _token_match

print(f"\n[1] token-aware matching:")
print(f"    'POST' in 'we will postpone the meeting' -> {_token_match('POST', 'we will postpone the meeting')} (correct: False)")
print(f"    'GET' in 'the target is here' -> {_token_match('GET', 'the target is here')} (correct: False)")
print(f"    'advancedSearch.xhtml' in 'BOAdvancedSearch.xhtml' -> {_token_match('advancedSearch.xhtml', 'BOAdvancedSearch.xhtml')} (correct: False)")

print(f"\n[2] no neutral fallback:")
r = score_response("anything", check=[])
print(f"    empty check -> hard={r['hard']} reason={r['reason']} (correct: 0.0, not 0.5)")
r = score_response("", check=["POST"])
print(f"    empty answer -> hard={r['hard']} reason={r['reason']} (correct: 0.0)")

print(f"\n[3] anti-pattern detection:")
r = score_response("use advancedSearch.xhtml and POST", check=["POST", "ViewState"], must_not=["advancedSearch.xhtml"])
print(f"    violations={r['violations']} soft={r['soft']:.2f} (correct: penalized)")

print("\nDone.")
