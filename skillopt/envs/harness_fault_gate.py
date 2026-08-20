#!/usr/bin/env python3
"""The single automated harness-fault gate for every SkillOpt env.

Harness faults are failures of the *measurement apparatus*, not of the model
under test. They used to be found only by reading a finished run by hand; this
module turns them into deterministic, self-running checks.

This is the ONLY fault gate. It is env-agnostic: nothing here knows about
hermes-prompt, webintel, coding or moli specifically, so every env gets every
detector for free. (A per-env copy of this file was deleted in favour of this
one — a second gate meant two thresholds, two sets of detectors, and only one
of them wired into the trainer.)

Three phases:

  CONFIG IDENTITY (run FIRST, before any model call)
    - env coherence: the declared ``env`` must agree with the paths the run
      actually uses (skill_init / split_dir / data_path / out_root). Catches
      the "ran the wrong env" class: a hermes-prompt config writing into
      ``runs/webintel-*``, or a webintel skill_init under a hermes-prompt env.
    - run-dir identity: if ``out_root`` already holds a ``config.json`` from a
      previous run, its identity fields must match the config about to run.
      Catches pointing a new config at an old run's directory.

  PREFLIGHT (run BEFORE the baseline eval)
    - Dataset discrimination: every item must separate a "good" answer
      (all check patterns present, no must_not) from a "bad" answer (missing
      patterns / violating must_not). Catches the val_007 class of bug where a
      pattern sits in BOTH check and must_not, making the item unsolvable.
    - Config/dataset match: split sizes, gate metric, veto flag present.

  POSTFLIGHT (run AFTER a run, or on a live run dir)
    - Empty-response spikes: fraction of ERROR:/empty responses in rollout
      telemetry above a threshold => harness/infra fault, not a wrong answer.
    - Optimizer-did-nothing streaks: consecutive steps with no patches or all
      rejects => the optimizer is stalling (brevity veto, rate-limit, etc.).
    - False vetoes: a ``must_not`` pattern that vetoes a response using that
      pattern only in negated form ("don't click it" vs must_not "click it").
    - Env coherence of the persisted config, and (when an independent expected
      config is supplied) identity-field mismatches against it.

Usage:
    python skillopt/envs/harness_fault_gate.py preflight \
        --data data/hermes-prompt-lean --config configs/hermes-prompt/default.yaml
    python skillopt/envs/harness_fault_gate.py postflight --run runs/hermes-prompt-v8
    python skillopt/envs/harness_fault_gate.py audit \
        --run runs/hermes-prompt-v8 --data data/hermes-prompt-lean

Exit code 0 = PASS, 1 = FAIL (findings printed). Deterministic, stdlib-only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable

# Allow running as a script from the repo root or from anywhere.
# __file__ = <root>/skillopt/envs/harness_fault_gate.py -> root is 3 levels up.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO_ROOT)

from skillopt.envs.scoring import (  # noqa: E402
    NEGATION_WINDOW,
    NEGATORS,
    _forbidden_match,
    _is_negated,
    _normalize,
    _strict_variants,
    _word_regex,
    score_response,
)


# ── Thresholds (tunable) ────────────────────────────────────────────────────
EMPTY_RESPONSE_FRACTION = 0.20   # >20% of responses empty/ERROR => harness fault
OPTIMIZER_NOOP_STREAK = 3        # >=3 consecutive no-patch/all-reject steps
OPTIMIZER_NO_CANDIDATE_STREAK = 5  # >=5 consecutive skip_no_patches (no candidate at all)
OPTIMIZER_NOOP_ABORT = 5         # >=5 consecutive => abort the run mid-flight
FALSE_VETO_MIN_LEN = 3           # must_not patterns shorter than this are suspect

# Step actions that mean "the optimizer changed nothing this step".
NOOP_ACTIONS = ("skip_no_patches", "reject")

#: Severity per fault type. Informational — the CLI fails on any fault.
SEVERITY = {
    "empty_response_spike": "critical",
    "discrimination_drift": "critical",
    "env_incoherent": "critical",
    "false_veto_pattern": "high",
    "config_mismatch": "high",
    "optimizer_did_nothing": "medium",
}


def _fault(fault_type: str, detail: str) -> dict:
    """Build one fault record."""
    return {
        "fault_type": fault_type,
        "severity": SEVERITY.get(fault_type, "medium"),
        "detail": detail,
    }


# ── Shared helpers ──────────────────────────────────────────────────────────
def _pattern_texts(specs: Any) -> list[str]:
    """Flatten check/must_not/order specs (dict or plain str) to pattern text."""
    out: list[str] = []
    for s in specs or []:
        if isinstance(s, dict):
            out.append(str(s.get("pattern", "")))
        else:
            out.append(str(s))
    return [p for p in out if p]


def _slug(text: str) -> str:
    """Lowercase *text* with every run of non-alphanumerics collapsed to '-'.

    Makes ``hermes-prompt``, ``hermes_prompt`` and ``data/hermes-prompt-lean``
    directly comparable: all three slug to a string containing the token
    ``hermes-prompt`` at a '-' boundary.
    """
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def _has_token(slug: str, token: str) -> bool:
    """True if *token* appears in *slug* delimited by '-' or string bounds.

    Boundary-aware so ``coding`` does not match ``data-encoding-x``.
    """
    if not token:
        return False
    return re.search(rf"(?:^|-){re.escape(token)}(?:-|$)", slug) is not None


# ── Config identity: env coherence + run-dir identity ───────────────────────
#: Identity fields that must match the intended config. A divergence means the
#: run optimized the wrong env / skill / dataset / model.
CONFIG_IDENTITY_FIELDS = (
    "env", "skill_init", "split_dir", "target_model", "optimizer_model",
    "gate_metric", "data_path",
)

#: Config fields whose *paths* encode which env a run belongs to.
ENV_PATH_FIELDS = ("skill_init", "split_dir", "data_path", "out_root")


def discover_env_names(repo_root: str | None = None) -> set[str]:
    """Slugged names of every env known to the repo.

    Sourced from ``skillopt/envs/<name>/`` packages and ``configs/<name>/``
    directories so a new env needs no registration here. Private/underscore
    names (``_template``, ``_base_``, ``__pycache__``) are excluded.
    """
    root = Path(repo_root or _REPO_ROOT)
    names: set[str] = set()
    for parent in (root / "skillopt" / "envs", root / "configs"):
        if not parent.is_dir():
            continue
        for child in parent.iterdir():
            if not child.is_dir() or child.name.startswith("_"):
                continue
            names.add(_slug(child.name))
    # 'features' is a configs/ helper dir, not an env.
    names.discard("features")
    return {n for n in names if n}


def check_env_coherence(cfg: dict, known_envs: Iterable[str] | None = None) -> dict:
    """Verify the declared ``env`` agrees with the paths the run actually uses.

    High-precision rule: a field is flagged only when it names a *different*
    known env and does NOT name the declared one. A path that mentions neither
    (``data/lean``, ``outputs/exp3``) is fine — skills and datasets are allowed
    to live anywhere. This is what catches the webintel/hermes-prompt
    conflation without flagging every unconventional path.
    """
    problems: list[str] = []
    env = str(cfg.get("env") or "")
    if not env:
        return {"ok": False, "env": "", "problems": ["env is empty — nothing to check against"]}

    token = _slug(env)
    known = {e for e in (known_envs if known_envs is not None else discover_env_names()) if e}
    others = {e for e in known if e != token}

    # The declared env itself must be a known env. A typo'd / nonexistent env
    # (e.g. "webintel-typo") would otherwise pass silently because no path
    # names a *different* known env — the exact "silly error" class this guard
    # exists to catch.
    if token not in known:
        problems.append(
            f"env={env!r} is not a known env (known: {sorted(known)}) — "
            f"the run is about to optimize a nonexistent env"
        )

    for field in ENV_PATH_FIELDS:
        value = cfg.get(field)
        if not value:
            continue
        slug = _slug(str(value))
        if _has_token(slug, token):
            continue
        foreign = sorted(e for e in others if _has_token(slug, e))
        if foreign:
            problems.append(
                f"{field}={value!r} names env {foreign[0]!r} but the run declares "
                f"env={env!r} — the run is about to optimize the wrong env"
            )
    return {"ok": not problems, "env": env, "problems": problems}


def check_run_dir_identity(prior_config: dict, cfg: dict) -> dict:
    """Compare a run dir's PRE-EXISTING ``config.json`` against the new config.

    ``prior_config`` is whatever ``out_root/config.json`` held before this run
    overwrote it. Empty (fresh dir) => nothing to check. A divergence means the
    operator pointed a new config at a previous run's directory, which mixes
    two runs' skills/history/telemetry in one folder.
    """
    if not prior_config:
        return {"ok": True, "problems": []}
    problems = []
    for field in CONFIG_IDENTITY_FIELDS:
        got = prior_config.get(field)
        want = cfg.get(field)
        if want is None or got is None:
            continue
        if got != want:
            problems.append(
                f"{field}: out_root already holds a run with {got!r}, this config "
                f"says {want!r} — reusing another run's directory"
            )
    return {"ok": not problems, "problems": problems}


def preflight_config_identity(
    cfg: dict,
    prior_config: dict | None = None,
    known_envs: Iterable[str] | None = None,
) -> dict:
    """Both config-identity guards, run before any model call.

    Returns ``{"ok", "checks": {"env_coherence", "run_dir_identity"}}``.
    """
    checks = {
        "env_coherence": check_env_coherence(cfg, known_envs),
        "run_dir_identity": check_run_dir_identity(prior_config or {}, cfg),
    }
    return {"ok": all(c["ok"] for c in checks.values()), "checks": checks}


# ── Preflight: dataset discrimination ───────────────────────────────────────
def _build_good_answer(item: dict) -> str:
    """A canonical 'good' answer: mentions every check pattern, no must_not."""
    parts = []
    for p in _pattern_texts(item.get("check")):
        parts.append(p)
    # A good answer must NOT trip any must_not. We simply omit them.
    return ". ".join(parts) + "."


def _build_bad_answer(item: dict) -> str:
    """A canonical 'bad' answer: violates a must_not (or omits a check)."""
    must_not = _pattern_texts(item.get("must_not"))
    if must_not:
        # Deliberately mention a forbidden pattern => must be hard=0.
        return ". ".join(must_not) + "."
    # No must_not: omit the first check pattern => must be hard=0.
    check = _pattern_texts(item.get("check"))
    if check:
        return ". ".join(check[1:]) + "."
    return ""


def check_item_discriminates(item: dict) -> dict:
    """Verify one item separates good from bad. Returns a finding dict or None."""
    iid = item.get("id", "?")
    good = _build_good_answer(item)
    bad = _build_bad_answer(item)

    sg = score_response(good, check=item.get("check"), must_not=item.get("must_not"),
                        optional=item.get("optional"), order=item.get("order"))
    sb = score_response(bad, check=item.get("check"), must_not=item.get("must_not"),
                        optional=item.get("optional"), order=item.get("order"))

    problems = []
    if sg["hard"] != 1.0:
        problems.append(f"good answer scored hard={sg['hard']} (missed={sg['missed']}, "
                        f"violations={sg['violations']})")
    if sb["hard"] != 0.0:
        problems.append(f"bad answer scored hard={sb['hard']} (should be 0)")

    # Contradiction: a pattern in BOTH check and must_not makes the item
    # unsolvable — the good answer can't mention it without tripping must_not.
    check_set = set(_pattern_texts(item.get("check")))
    must_set = set(_pattern_texts(item.get("must_not")))
    overlap = check_set & must_set
    if overlap:
        problems.append(f"check/must_not contradiction: {sorted(overlap)} in both lists")

    if problems:
        return {"id": iid, "ok": False, "problems": problems}
    return {"id": iid, "ok": True, "problems": []}


def preflight_discrimination(items: list[dict]) -> dict:
    """Run discrimination check over all items. Returns summary + findings."""
    findings = []
    for item in items:
        r = check_item_discriminates(item)
        if not r["ok"]:
            findings.append(r)
    return {
        "ok": not findings,
        "total": len(items),
        "failed": len(findings),
        "findings": findings,
    }


# ── Preflight: config/dataset match ─────────────────────────────────────────
def preflight_config(items: dict[str, list], cfg: dict) -> dict:
    """Verify config split sizes and gate settings match the dataset."""
    problems = []
    train = items.get("train", [])
    val = items.get("val", [])
    test = items.get("test", [])

    env = cfg.get("env", {})
    train_size = cfg.get("train", {}).get("train_size")
    sel_env_num = cfg.get("evaluation", {}).get("sel_env_num")
    test_env_num = cfg.get("evaluation", {}).get("test_env_num")

    if train_size is not None and len(train) < train_size:
        problems.append(f"config train_size={train_size} but dataset has only {len(train)} train items")
    if sel_env_num is not None and len(val) < sel_env_num:
        problems.append(f"config sel_env_num={sel_env_num} but dataset has only {len(val)} val items")
    if test_env_num is not None and len(test) < test_env_num:
        problems.append(f"config test_env_num={test_env_num} but dataset has only {len(test)} test items")

    # Veto flag: the hard no-growth veto is a critical harness guard. If it's
    # off, flag it so the run doesn't silently regress into growth-acceptance.
    # Check BOTH nested (raw structured cfg) and flattened (scripts/train.py
    # flattens a structured cfg before handing it to the trainer) forms.
    veto = (
        cfg.get("optimizer", {}).get("veto_growing_candidates")
        or cfg.get("veto_growing_candidates")
    )
    if not veto:
        problems.append("veto_growing_candidates is OFF — growth candidates will not be auto-rejected")

    return {"ok": not problems, "problems": problems}


# ── Loaders ──────────────────────────────────────────────────────────────────
def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return rows
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_history(run_dir: str) -> list[dict]:
    data = _read_json(Path(run_dir) / "history.json")
    return [s for s in data if isinstance(s, dict)] if isinstance(data, list) else []


def _load_telemetry(run_dir: str) -> list[dict]:
    """Collect telemetry.jsonl rows from the run dir (recursively), flat."""
    lines: list[dict] = []
    for p in sorted(Path(run_dir).rglob("telemetry.jsonl")):
        lines.extend(_read_jsonl(p))
    return lines


def load_telemetry_batches(out_dir: str) -> list[tuple[str, list[dict]]]:
    """Collect every telemetry.jsonl under ``out_dir``, grouped into batches.

    A batch is one rollout: the adapter appends all of a rollout's rows in a
    single pass with one shared ``ts``, so ``(file, ts)`` is the batch key.
    Returns ``[(label, rows), ...]`` sorted by label for determinism.
    """
    root = Path(out_dir)
    if not root.is_dir():
        return []
    batches: dict[str, list[dict]] = {}
    for path in sorted(root.rglob("telemetry.jsonl")):
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.as_posix()
        for row in _read_jsonl(path):
            batches.setdefault(f"{rel}@{row.get('ts', '?')}", []).append(row)
    return sorted(batches.items())


def load_predictions(out_dir: str) -> list[tuple[str, str, str]]:
    """Collect persisted rollout responses as ``(label, item_id, response)``."""
    root = Path(out_dir)
    if not root.is_dir():
        return []
    preds: list[tuple[str, str, str]] = []
    for path in sorted(root.rglob("predictions/*/conversation.json")):
        convo = _read_json(path)
        if not isinstance(convo, list):
            continue
        text = ""
        for msg in convo:
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                text = str(msg.get("content") or "")
        if not text:
            continue
        try:
            rel = path.parent.parent.parent.relative_to(root).as_posix()
        except ValueError:
            rel = path.parent.parent.parent.as_posix()
        preds.append((rel or ".", path.parent.name, text))
    return preds


def load_history(out_dir: str) -> list[dict]:
    """Load ``history.json`` (per-step trainer records) from a run dir."""
    return _load_history(out_dir)


def load_config(out_dir: str) -> dict:
    """Load the run's persisted ``config.json`` (the resolved config that
    produced the run). Returns {} when absent."""
    data = _read_json(Path(out_dir) / "config.json")
    return data if isinstance(data, dict) else {}


#: Back-compat alias used by the trainer and by postflight.
_load_run_config = load_config


def load_dataset_items(dataset_dir: str) -> list[dict]:
    """Load dataset items from a split dir (train/val/test) or a flat dir.

    Items are deduplicated by ``id`` so an item present in several splits is
    only reported once.
    """
    root = Path(dataset_dir)
    if not root.is_dir():
        return []
    files: list[Path] = []
    for split in ("train", "val", "test"):
        files.extend(sorted((root / split).glob("*.json")))
    if not files:
        files = sorted(root.glob("*.json"))
    items: list[dict] = []
    seen: set[str] = set()
    for path in files:
        payload = _read_json(path)
        if not isinstance(payload, list):
            continue
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            iid = str(raw.get("id") or "")
            if iid and iid in seen:
                continue
            if iid:
                seen.add(iid)
            items.append(raw)
    return items


def _load_split_items(split_dir: str, split: str) -> list[dict]:
    data = _read_json(Path(split_dir) / split / "items.json")
    return data if isinstance(data, list) else []


# ── Detector: empty-response spikes ─────────────────────────────────────────
def _is_empty_row(row: dict) -> bool:
    """True if a telemetry row records an empty / ERROR target response."""
    reason = str(row.get("fail_reason") or "")
    return reason.startswith("empty_response") or reason.startswith("harness_error")


def postflight_empty_responses(telemetry: list[dict]) -> dict:
    """Flag empty/ERROR response spikes across the whole run's telemetry."""
    if not telemetry:
        return {"ok": True, "checked": 0, "empty": 0, "fraction": 0.0, "findings": []}
    empty = [t for t in telemetry if _is_empty_row(t)]
    frac = len(empty) / len(telemetry)
    findings = []
    if frac > EMPTY_RESPONSE_FRACTION:
        findings.append(
            f"{len(empty)}/{len(telemetry)} responses empty/ERROR ({frac:.0%}) "
            f"> threshold {EMPTY_RESPONSE_FRACTION:.0%} — harness/infra fault, not wrong answers"
        )
    return {"ok": not findings, "checked": len(telemetry), "empty": len(empty),
            "fraction": frac, "findings": findings}


def detect_empty_response_spike(batches: Iterable[tuple[str, list[dict]]]) -> list[dict]:
    """Flag any eval batch where >20% of responses were empty or ERROR."""
    faults = []
    for label, rows in batches:
        if not rows:
            continue
        empty = [r for r in rows if _is_empty_row(r)]
        frac = len(empty) / len(rows)
        if frac > EMPTY_RESPONSE_FRACTION:
            ids = ", ".join(str(r.get("id", "?")) for r in empty[:5])
            faults.append(_fault(
                "empty_response_spike",
                f"{label}: {len(empty)}/{len(rows)} responses empty/ERROR "
                f"({frac:.0%} > {EMPTY_RESPONSE_FRACTION:.0%}) — target model or "
                f"gateway fault, not wrong answers. ids: {ids}",
            ))
    return faults


# ── Detector: false vetoes ──────────────────────────────────────────────────
def find_false_veto(pattern: str, text: str) -> str | None:
    """Detect a must_not ``pattern`` that vetoes ``text`` only in negated form.

    Returns a human-readable detail string when the scorer really vetoed AND
    every locatable occurrence of the forbidden phrase is preceded by a negator
    ("don't click" vs must_not "click it"). Returns None when the veto did not
    fire, when any occurrence is un-negated (a legitimate veto), or when the
    veto came from a lemma match whose position cannot be recovered.

    The gate is ``scoring._forbidden_match`` — the same predicate
    ``score_response`` uses — so this reports only vetoes the scorer actually
    applied. Since that predicate is itself negation-aware, this now acts as a
    regression guard: it fires if the scorer's negation handling ever regresses.
    """
    if not _forbidden_match(pattern, text):
        return None
    norm = _normalize(text)
    hits: list[tuple[int, str]] = []
    for variant in _strict_variants(pattern):
        for m in re.finditer(_word_regex(variant), norm):
            hits.append((m.start(), variant))
    if not hits:
        # Veto came from a lemma match; no offset to reason about. Stay silent
        # rather than guess — a false positive here would be its own fault.
        return None
    cues: list[str] = []
    for start, variant in sorted(hits):
        cue = _is_negated(norm, start)
        if not cue:
            return None  # at least one bare occurrence => the veto is real
        snippet = norm[max(0, start - 30):start + len(variant)].strip()
        cues.append(f"'{snippet}' (negated by '{cue}')")
    return "; ".join(cues)


def detect_false_veto_pattern(
    predictions: Iterable[tuple[str, str, str]],
    items: Iterable[dict],
) -> list[dict]:
    """Flag must_not patterns that veto a response using them in negated form."""
    by_id = {str(i.get("id") or ""): i for i in items}
    faults = []
    seen: set[tuple[str, str]] = set()
    for label, iid, text in predictions:
        item = by_id.get(iid)
        if not item:
            continue
        for pattern in _pattern_texts(item.get("must_not")):
            key = (iid, pattern)
            if key in seen:
                continue
            detail = find_false_veto(pattern, text)
            if detail:
                seen.add(key)
                faults.append(_fault(
                    "false_veto_pattern",
                    f"{label}/{iid}: must_not '{pattern}' vetoed a response that "
                    f"only uses it in negated form — {detail}",
                ))
    return faults


# ── Detector: optimizer no-op streaks ───────────────────────────────────────
def optimizer_noop_streak(actions) -> int:
    """Length of the TRAILING consecutive no-op/reject run in a step-action stream.

    Pure helper shared by the mid-run early-stop (trainer) and postflight.
    Any non-noop action (accept / accept_new_best / force_accept / skip_no_rewrite)
    resets the streak to 0.
    """
    streak = 0
    for action in actions:
        streak = streak + 1 if action in NOOP_ACTIONS else 0
    return streak


def optimizer_no_candidate_streak(actions) -> int:
    """Length of the TRAILING consecutive ``skip_no_patches`` run.

    A ``reject`` means the optimizer DID produce a candidate that lost — that
    is a working optimizer, not a stall. Only ``skip_no_patches`` (the analyst
    produced no candidate at all) is a true stall. This is the streak the
    mid-run early-stop must use so a run that is legitimately losing is NOT
    force-aborted after a few rejects.
    """
    streak = 0
    for action in actions:
        streak = streak + 1 if action == "skip_no_patches" else 0
    return streak


def optimizer_noop_abort_step(actions, threshold: int = OPTIMIZER_NOOP_ABORT):
    """1-indexed position in *actions* where the noop streak first hits *threshold*.

    Returns None if the stream never stalls that long — i.e. the step number at
    which an early-stop would fire, so the gate is testable without a trainer.
    """
    if threshold <= 0:
        return None
    streak = 0
    for i, action in enumerate(actions, start=1):
        streak = streak + 1 if action in NOOP_ACTIONS else 0
        if streak >= threshold:
            return i
    return None


def postflight_optimizer_noop(history: list[dict]) -> dict:
    """Flag consecutive no-patch / all-reject steps (optimizer stalling)."""
    if not history:
        return {"ok": True, "streak": 0, "findings": []}
    streak = 0
    max_streak = 0
    for s in history:
        action = s.get("action")
        if action in NOOP_ACTIONS:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    findings = []
    if max_streak >= OPTIMIZER_NOOP_STREAK:
        findings.append(
            f"{max_streak} consecutive no-patch/reject steps >= threshold "
            f"{OPTIMIZER_NOOP_STREAK} — optimizer stalling (brevity veto, rate-limit, "
            f"or analyst producing no useful edits)"
        )
    return {"ok": not findings, "streak": max_streak, "findings": findings}


def detect_optimizer_did_nothing(history: Iterable[dict]) -> list[dict]:
    """Flag >=5 consecutive steps whose action is ``skip_no_patches``.

    Stricter sibling of :func:`postflight_optimizer_noop`: a ``reject`` means
    the optimizer DID produce a candidate, so only ``skip_no_patches`` counts
    here. Reports every streak with its step range.
    """
    streak = 0
    start_step: Any = None
    runs: list[tuple[Any, Any, int]] = []
    last_step: Any = None
    for record in history:
        step = record.get("step")
        if record.get("action") == "skip_no_patches":
            if streak == 0:
                start_step = step
            streak += 1
            last_step = step
        else:
            if streak >= OPTIMIZER_NO_CANDIDATE_STREAK:
                runs.append((start_step, last_step, streak))
            streak = 0
    if streak >= OPTIMIZER_NO_CANDIDATE_STREAK:
        runs.append((start_step, last_step, streak))
    return [
        _fault(
            "optimizer_did_nothing",
            f"{n} consecutive steps with action=skip_no_patches "
            f"(steps {first}..{last}, threshold {OPTIMIZER_NO_CANDIDATE_STREAK}) — the "
            f"optimizer produced no candidate; those steps bought nothing",
        )
        for first, last, n in runs
    ]


# ── Detector: dataset discrimination drift ──────────────────────────────────
def _naive_good_answer(item: dict) -> str:
    """A canonical correct answer: every check pattern, honouring ``order``."""
    order = _pattern_texts(item.get("order"))
    check = _pattern_texts(item.get("check"))
    parts = list(order) + [p for p in check if p not in order]
    return ". ".join(parts) + "." if parts else ""


def detect_discrimination_drift(items: Iterable[dict]) -> list[dict]:
    """Flag items that no longer separate a naive good answer from a bad one."""
    faults = []
    for item in items:
        iid = str(item.get("id") or "?")
        check = _pattern_texts(item.get("check"))
        if not check:
            faults.append(_fault(
                "discrimination_drift",
                f"{iid}: no check patterns — every response scores hard=0.0",
            ))
            continue

        good = _naive_good_answer(item)
        sg = score_response(
            good,
            check=item.get("check"), must_not=item.get("must_not"),
            optional=item.get("optional"), order=item.get("order"),
            max_chars=item.get("max_chars"),
        )
        if sg["hard"] != 1.0:
            faults.append(_fault(
                "discrimination_drift",
                f"{iid}: naive good answer scored hard={sg['hard']} soft={sg['soft']:.2f} "
                f"(missed={sg['missed']}, violations={sg['violations']}, "
                f"order_score={sg['order_score']:.2f}) — the item is unsolvable",
            ))

        for forbidden in _pattern_texts(item.get("must_not")):
            bad = f"{good} {forbidden}."
            sb = score_response(
                bad,
                check=item.get("check"), must_not=item.get("must_not"),
                optional=item.get("optional"), order=item.get("order"),
                max_chars=item.get("max_chars"),
            )
            if sb["hard"] != 0.0:
                faults.append(_fault(
                    "discrimination_drift",
                    f"{iid}: naive bad answer containing must_not '{forbidden}' still "
                    f"scored hard={sb['hard']} — the forbidden pattern does not veto",
                ))
    return faults


# ── Detector: config / env mismatch ─────────────────────────────────────────
def detect_config_mismatch(run_config: dict, expected: dict) -> list[dict]:
    """Flag identity-field divergences between a run's config and the intended one.

    ``run_config`` is the run's persisted ``config.json``; ``expected`` is an
    INDEPENDENT statement of intent — the config file the operator meant to
    run, or a prior run's config. Passing the same dict the run was launched
    from is tautological and detects nothing. Only ``CONFIG_IDENTITY_FIELDS``
    are compared; missing expected config is skipped.
    """
    if not expected:
        return []
    faults: list[dict] = []
    for field in CONFIG_IDENTITY_FIELDS:
        got = run_config.get(field)
        want = expected.get(field)
        if want is None:
            continue
        if got != want:
            faults.append(_fault(
                "config_mismatch",
                f"{field}: run has {got!r}, expected {want!r} — the run may "
                f"have optimized the wrong env/skill/dataset/model",
            ))
    return faults


def detect_env_incoherent(run_config: dict,
                          known_envs: Iterable[str] | None = None) -> list[dict]:
    """Flag a persisted run config whose paths disagree with its declared env."""
    if not run_config:
        return []
    res = check_env_coherence(run_config, known_envs)
    return [_fault("env_incoherent", p) for p in res["problems"]]


def postflight_config_mismatch(run_config: dict, expected: dict) -> dict:
    """Dict-shaped wrapper over :func:`detect_config_mismatch` for postflight."""
    faults = detect_config_mismatch(run_config, expected)
    return {"ok": not faults, "checked": len(CONFIG_IDENTITY_FIELDS),
            "findings": [f["detail"] for f in faults]}


def postflight_env_coherence(run_config: dict,
                             known_envs: Iterable[str] | None = None) -> dict:
    """Dict-shaped wrapper over :func:`detect_env_incoherent` for postflight."""
    faults = detect_env_incoherent(run_config, known_envs)
    return {"ok": not faults, "findings": [f["detail"] for f in faults]}


# ── Postflight ──────────────────────────────────────────────────────────────
def postflight(run_dir: str, expected_config: dict | None = None,
               known_envs: Iterable[str] | None = None) -> dict:
    """Run all postflight checks on a run directory.

    ``expected_config`` (optional) must be an INDEPENDENT statement of intent
    (see :func:`detect_config_mismatch`). ``env_coherence`` needs no external
    input: it cross-checks the persisted config's own fields.
    """
    history = _load_history(run_dir)
    telemetry = _load_telemetry(run_dir)
    run_config = load_config(run_dir)
    checks = {
        "empty_responses": postflight_empty_responses(telemetry),
        "optimizer_noop": postflight_optimizer_noop(history),
        "env_coherence": postflight_env_coherence(run_config, known_envs),
        "config_mismatch": postflight_config_mismatch(run_config, expected_config or {}),
    }
    ok = all(c["ok"] for c in checks.values())
    return {"ok": ok, "run_dir": run_dir, "checks": checks}


# ── Full audit (run dir + dataset) ──────────────────────────────────────────
def run_fault_gate(out_dir: str, dataset_dir: str,
                   expected_config: dict | None = None,
                   known_envs: Iterable[str] | None = None) -> list[dict]:
    """Check a completed run for harness faults.

    ``out_dir`` is a run directory (``runs/<name>``) holding
    ``selection_eval_baseline/telemetry.jsonl``, per-step telemetry, and
    ``history.json``. ``dataset_dir`` is the split dir that produced it.
    ``expected_config`` (optional) is an INDEPENDENT intended config; when
    given, the run's persisted ``config.json`` is checked against it for
    identity mismatches (wrong env / skill / dataset / model).
    Missing inputs are skipped rather than raising, so the gate can run on a
    partial or in-progress run.

    Returns a list of ``{fault_type, severity, detail}`` dicts, ordered by
    detector; empty means the harness looks healthy.
    """
    batches = load_telemetry_batches(out_dir)
    predictions = load_predictions(out_dir)
    history = load_history(out_dir)
    items = load_dataset_items(dataset_dir)
    run_config = load_config(out_dir)

    faults: list[dict] = []
    faults.extend(detect_empty_response_spike(batches))
    faults.extend(detect_false_veto_pattern(predictions, items))
    faults.extend(detect_optimizer_did_nothing(history))
    faults.extend(detect_discrimination_drift(items))
    faults.extend(detect_env_incoherent(run_config, known_envs))
    faults.extend(detect_config_mismatch(run_config, expected_config or {}))
    return faults


# ── Config loading for the CLI ──────────────────────────────────────────────
def _load_config(path: str) -> dict:
    # Minimal YAML-ish loader for the flat keys the gate needs. Full YAML is
    # overkill here; we only read top-level sections.
    cfg: dict = {}
    current = None
    for line in Path(path).read_text().splitlines():
        line = line.split("#")[0].rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r"^(\w+):\s*$", stripped)
        if m:
            current = m.group(1)
            cfg.setdefault(current, {})
            continue
        m = re.match(r"^(\w+):\s*(.+)$", stripped)
        if m and current:
            k, v = m.group(1), m.group(2).strip()
            if v.lower() in ("true", "false"):
                v = v.lower() == "true"
            elif v.isdigit():
                v = int(v)
            cfg[current][k] = v
    return cfg


# ── CLI ──────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="SkillOpt harness-fault gate")
    sub = p.add_subparsers(dest="cmd", required=True)

    pre = sub.add_parser("preflight", help="dataset discrimination + config match")
    pre.add_argument("--data", required=True, help="split dir (train/val/test)")
    pre.add_argument("--config", required=True, help="config yaml")

    post = sub.add_parser("postflight", help="run-level anomaly detection")
    post.add_argument("--run", required=True, help="run directory")

    aud = sub.add_parser("audit", help="full audit: run dir + dataset")
    aud.add_argument("--run", required=True, help="run directory")
    aud.add_argument("--data", required=True, help="dataset / split dir")

    args = p.parse_args(argv)

    if args.cmd == "preflight":
        items = {
            "train": _load_split_items(args.data, "train"),
            "val": _load_split_items(args.data, "val"),
            "test": _load_split_items(args.data, "test"),
        }
        all_items = items["train"] + items["val"] + items["test"]
        disc = preflight_discrimination(all_items)
        cfg = load_config(args.config)
        cfgchk = preflight_config(items, cfg)

        print(f"=== PREFLIGHT {args.data} ===")
        print(f"items: train={len(items['train'])} val={len(items['val'])} test={len(items['test'])}")
        print(f"discrimination: {disc['total']} items, {disc['failed']} failed")
        for f in disc["findings"]:
            print(f"  [FAIL] {f['id']}: {'; '.join(f['problems'])}")
        print(f"config match: {'PASS' if cfgchk['ok'] else 'FAIL'}")
        for prob in cfgchk["problems"]:
            print(f"  [FAIL] {prob}")

        ok = disc["ok"] and cfgchk["ok"]
        print("PREFLIGHT:", "PASS" if ok else "FAIL")
        return 0 if ok else 1

    if args.cmd == "postflight":
        res = postflight(args.run)
        print(f"=== POSTFLIGHT {args.run} ===")
        for name, c in res["checks"].items():
            status = "PASS" if c["ok"] else "FAIL"
            print(f"  {name}: {status}")
            for f in c["findings"]:
                print(f"    [FAIL] {f}")
        print("POSTFLIGHT:", "PASS" if res["ok"] else "FAIL")
        return 0 if res["ok"] else 1

    if args.cmd == "audit":
        faults = run_fault_gate(args.run, args.data)
        print(f"=== FAULT GATE run={args.run} dataset={args.data} ===")
        if not faults:
            print("no harness faults detected")
            print("FAULT GATE: PASS")
            return 0
        for f in faults:
            print(f"  [{f['severity'].upper()}] {f['fault_type']}: {f['detail']}")
        print(f"FAULT GATE: FAIL ({len(faults)} fault(s))")
        return 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
