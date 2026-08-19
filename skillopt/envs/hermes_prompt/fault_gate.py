"""Automated harness-fault detection gate for the hermes-prompt env.

Harness faults are failures of the *measurement apparatus*, not of the model
under test. They were previously found only by manual inspection of a finished
run; this module turns them into a deterministic, self-running check.

Four detectors, all read-only over a completed run directory plus the dataset
that produced it:

``empty_response_spike``
    More than 20% of the responses in a single eval batch came back empty or
    as an ``ERROR:`` marker. The target model / gateway broke; the resulting
    zeros say nothing about the skill.

``false_veto_pattern``
    A ``must_not`` pattern hard-vetoed a response in which every occurrence of
    that pattern is *negated* (e.g. the response says "don't click it" and the
    forbidden pattern is "click it"). The item punishes a correct answer.

``optimizer_did_nothing``
    Five or more consecutive steps with ``action == "skip_no_patches"``. The
    optimizer produced no candidate at all, so those steps bought nothing.

``discrimination_drift``
    A dataset item that no longer separates right from wrong: a naive good
    answer (every ``check`` pattern, in ``order``) fails to score ``hard=1.0``,
    or a naive bad answer (the good answer plus one forbidden pattern) fails to
    score ``hard=0.0``.

Scoring is delegated to :mod:`skillopt.envs.scoring` — the same hardened scorer
the rollout uses — so the gate can never disagree with the trainer about what
a pattern means. Nothing here mutates the run or the dataset.

Usage::

    python3 -m skillopt.envs.hermes_prompt.fault_gate runs/hermes-prompt-v8 \
        data/hermes-prompt-lean

Exit code 0 = no faults, 1 = at least one fault. Deterministic, stdlib-only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from skillopt.envs.scoring import (
    NEGATION_WINDOW,
    NEGATORS,
    _forbidden_match,
    _is_negated,
    _normalize,
    _strict_variants,
    _word_regex,
    score_response,
)

# ── Thresholds ──────────────────────────────────────────────────────────────
EMPTY_RESPONSE_FRACTION = 0.20   # >20% empty/ERROR in one batch => harness fault
OPTIMIZER_NOOP_STREAK = 5        # >=5 consecutive skip_no_patches steps

# NEGATION_WINDOW / NEGATORS / _word_regex / _strict_variants / _is_negated are
# imported from skillopt.envs.scoring so the gate and the scorer can never
# disagree about what counts as a negated forbidden phrase.

#: Severity per fault type. Informational — the CLI fails on any fault.
SEVERITY = {
    "empty_response_spike": "critical",
    "discrimination_drift": "critical",
    "false_veto_pattern": "high",
    "optimizer_did_nothing": "medium",
}


def _fault(fault_type: str, detail: str) -> dict:
    """Build one fault record."""
    return {
        "fault_type": fault_type,
        "severity": SEVERITY.get(fault_type, "medium"),
        "detail": detail,
    }


# ── Pattern helpers ─────────────────────────────────────────────────────────
def _pattern_texts(specs: Any) -> list[str]:
    """Flatten a check / must_not / order spec list to its pattern strings."""
    out: list[str] = []
    for s in specs or []:
        if isinstance(s, dict):
            out.append(str(s.get("pattern", "")))
        else:
            out.append(str(s))
    return [p for p in out if p]


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


# ── Loaders ─────────────────────────────────────────────────────────────────
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
    data = _read_json(Path(out_dir) / "history.json")
    return [s for s in data if isinstance(s, dict)] if isinstance(data, list) else []


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


# ── Detector 1: empty-response spikes ───────────────────────────────────────
def _is_empty_row(row: dict) -> bool:
    """True if a telemetry row records an empty / ERROR target response."""
    reason = str(row.get("fail_reason") or "")
    return reason.startswith("empty_response") or reason.startswith("harness_error")


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


# ── Detector 2: false vetoes ────────────────────────────────────────────────
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


# ── Detector 3: optimizer no-op streaks ─────────────────────────────────────
def detect_optimizer_did_nothing(history: Iterable[dict]) -> list[dict]:
    """Flag >=5 consecutive steps whose action is ``skip_no_patches``."""
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
            if streak >= OPTIMIZER_NOOP_STREAK:
                runs.append((start_step, last_step, streak))
            streak = 0
    if streak >= OPTIMIZER_NOOP_STREAK:
        runs.append((start_step, last_step, streak))
    return [
        _fault(
            "optimizer_did_nothing",
            f"{n} consecutive steps with action=skip_no_patches "
            f"(steps {first}..{last}, threshold {OPTIMIZER_NOOP_STREAK}) — the "
            f"optimizer produced no candidate; those steps bought nothing",
        )
        for first, last, n in runs
    ]


# ── Detector 4: dataset discrimination drift ────────────────────────────────
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


# ── Entry point ─────────────────────────────────────────────────────────────
def run_fault_gate(out_dir: str, dataset_dir: str) -> list[dict]:
    """Check a completed run for harness faults.

    ``out_dir`` is a run directory (``runs/<name>``) holding
    ``selection_eval_baseline/telemetry.jsonl``, per-step telemetry, and
    ``history.json``. ``dataset_dir`` is the split dir that produced it.
    Missing inputs are skipped rather than raising, so the gate can run on a
    partial or in-progress run.

    Returns a list of ``{fault_type, severity, detail}`` dicts, ordered by
    detector; empty means the harness looks healthy.
    """
    batches = load_telemetry_batches(out_dir)
    predictions = load_predictions(out_dir)
    history = load_history(out_dir)
    items = load_dataset_items(dataset_dir)

    faults: list[dict] = []
    faults.extend(detect_empty_response_spike(batches))
    faults.extend(detect_false_veto_pattern(predictions, items))
    faults.extend(detect_optimizer_did_nothing(history))
    faults.extend(detect_discrimination_drift(items))
    return faults


def main(argv: list[str] | None = None) -> int:
    """CLI: print detected faults; exit 0 if clean, 1 if any fault is found."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print(
            "usage: python3 -m skillopt.envs.hermes_prompt.fault_gate "
            "<out_dir> <dataset_dir>",
            file=sys.stderr,
        )
        return 2
    out_dir, dataset_dir = args
    faults = run_fault_gate(out_dir, dataset_dir)

    print(f"=== FAULT GATE run={out_dir} dataset={dataset_dir} ===")
    if not faults:
        print("no harness faults detected")
        print("FAULT GATE: PASS")
        return 0
    for f in faults:
        print(f"  [{f['severity'].upper()}] {f['fault_type']}: {f['detail']}")
    print(f"FAULT GATE: FAIL ({len(faults)} fault(s))")
    return 1


if __name__ == "__main__":
    sys.exit(main())
