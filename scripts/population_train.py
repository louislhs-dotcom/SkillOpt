#!/usr/bin/env python3
"""Population-based SkillOpt training with chunked parallel execution and crossover.

This script runs N independent training populations in parallel, each with different
seeds/configs. Periodically performs crossover: extracts successful edits from
top performers and injects them into weaker populations.

Usage:
    python scripts/population_train.py \\
        --config configs/webintel/switchyard.yaml \\
        --skill-init outputs/.../best_skill.md \\
        --population 4 \\
        --seeds 42 123 456 789 \\
        --steps-per-chunk 5 \\
        --chunks 4 \\
        --workers 4
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import difflib
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# Add project root to path
_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


def run_single_population(args: tuple) -> dict:
    """Run one population member for a chunk of steps. Returns summary dict."""
    idx, config_path, seed, skill_init, out_root_base, steps, extra_cfg, env_vars = args
    
    out_root = os.path.join(out_root_base, f"pop_{idx:02d}_seed{seed}")
    os.makedirs(out_root, exist_ok=True)
    
    # Build command
    cmd = [
        sys.executable, "scripts/train.py",
        "--config", config_path,
        "--skill_init", skill_init,
        "--cfg-options",
        f"train.seed={seed}",
        f"train.steps={steps}",
        f"env.out_root={out_root}",
    ]
    if extra_cfg:
        for k, v in extra_cfg.items():
            cmd.extend(["--cfg-options", f"{k}={v}"])
    
    # Prepare environment
    env = os.environ.copy()
    env.update(env_vars)
    
    print(f"[pop {idx}] Starting: seed={seed}, steps={steps}, out={out_root}")
    start = time.time()
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200, cwd=_PROJECT_ROOT, env=env)
        elapsed = time.time() - start
        
        # Parse final skill and score from output dir
        best_skill_path = os.path.join(out_root, "best_skill.md")
        runtime_state_path = os.path.join(out_root, "runtime_state.json")
        
        best_skill = ""
        best_score = 0.0
        last_step = 0
        
        if os.path.exists(runtime_state_path):
            with open(runtime_state_path) as f:
                rs = json.load(f)
                best_score = rs.get("best_score", 0.0)
                last_step = rs.get("last_completed_step", 0)
        
        if os.path.exists(best_skill_path):
            with open(best_skill_path) as f:
                best_skill = f.read()
        
        return {
            "idx": idx,
            "seed": seed,
            "out_root": out_root,
            "best_score": best_score,
            "best_skill": best_skill,
            "last_step": last_step,
            "elapsed": elapsed,
            "success": result.returncode == 0,
            "stdout": result.stdout[-5000:] if result.stdout else "",
            "stderr": result.stderr[-2000:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {
            "idx": idx,
            "seed": seed,
            "out_root": out_root,
            "best_score": 0.0,
            "best_skill": "",
            "last_step": 0,
            "elapsed": 7200,
            "success": False,
            "error": "timeout",
        }
    except Exception as e:
        return {
            "idx": idx,
            "seed": seed,
            "out_root": out_root,
            "best_score": 0.0,
            "best_skill": "",
            "last_step": 0,
            "elapsed": time.time() - start,
            "success": False,
            "error": str(e),
        }


def extract_edits(base_skill: str, candidate_skill: str, max_edits: int = 5) -> list[str]:
    """Extract meaningful edit sections from candidate that differ from base.
    
    Returns list of edit blocks (strings) that can be applied to another skill.
    """
    base_lines = base_skill.splitlines()
    cand_lines = candidate_skill.splitlines()
    matcher = difflib.SequenceMatcher(None, base_lines, cand_lines)
    
    edits = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "insert") and (j2 - j1) > 3:
            # Candidate has new/changed content here
            section = "\n".join(cand_lines[j1:j2])
            if len(section.strip()) > 50:  # Meaningful size
                edits.append({
                    "content": section,
                    "base_start": i1,
                    "base_end": i2,
                    "cand_start": j1,
                    "cand_end": j2,
                    "size": len(section),
                })
    
    # Sort by size (largest edits first) and take top N
    edits.sort(key=lambda e: e["size"], reverse=True)
    return [e["content"] for e in edits[:max_edits]]


def apply_edits_to_skill(target_skill: str, edits: list[str], max_applied: int = 3) -> str:
    """Apply edit sections to target skill by finding best match locations.
    
    Simple strategy: for each edit, find the most similar section in target
    and replace it, or append if no good match.
    """
    target_lines = target_skill.splitlines()
    applied = 0
    
    for edit_content in edits:
        if applied >= max_applied:
            break
            
        edit_lines = edit_content.splitlines()
        if len(edit_lines) < 3:
            continue
        
        # Try to find best match in target using difflib
        matcher = difflib.SequenceMatcher(None, target_lines, edit_lines)
        best_ratio = 0
        best_pos = -1
        
        # Look for similar sections in target
        for block in matcher.get_matching_blocks():
            if block.size >= 3 and block.a < len(target_lines):
                ratio = block.size / max(len(edit_lines), 1)
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_pos = block.a
        
        if best_ratio > 0.3 and best_pos >= 0:
            # Replace the matched section
            # Find extent of match
            match_len = min(len(edit_lines), len(target_lines) - best_pos)
            target_lines[best_pos:best_pos + match_len] = edit_lines
            applied += 1
        elif applied < max_applied:
            # Append as new section (before final newline)
            target_lines.extend(["", "=== CROSSED EDIT ===", edit_content, ""])
            applied += 1
    
    return "\n".join(target_lines)


def crossover_skills(donor_skills: list[str], target_skill: str, max_edits_per_donor: int = 2, max_total: int = 4) -> str:
    """Extract top edits from donor skills and apply to target."""
    merged = target_skill
    total_applied = 0
    
    for donor in donor_skills:
        if total_applied >= max_total:
            break
        edits = extract_edits(target_skill, donor, max_edits=max_edits_per_donor)
        if edits:
            merged = apply_edits_to_skill(merged, edits, max_applied=max_total - total_applied)
            total_applied += min(len(edits), max_edits_per_donor)
    
    return merged


def main():
    parser = argparse.ArgumentParser(description="Population SkillOpt training with crossover")
    parser.add_argument("--config", required=True, help="Base config YAML")
    parser.add_argument("--skill-init", required=True, help="Initial skill file")
    parser.add_argument("--population", type=int, default=4, help="Population size")
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 123, 456, 789], help="Seeds for each population")
    parser.add_argument("--steps-per-chunk", type=int, default=5, help="Steps per training chunk")
    parser.add_argument("--chunks", type=int, default=4, help="Number of chunks (generations)")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers")
    parser.add_argument("--out-root", default="outputs/population", help="Base output directory")
    parser.add_argument("--cfg-options", nargs="*", default=[], help="Extra config overrides")
    parser.add_argument("--elite-keep", type=int, default=1, help="Number of elites to keep unchanged")
    parser.add_argument("--crossover-top-k", type=int, default=2, help="Top K donors for crossover")
    parser.add_argument("--max-cross-edits", type=int, default=3, help="Max edits per crossover")
    args = parser.parse_args()
    
    # Parse extra cfg options
    extra_cfg = {}
    for opt in args.cfg_options:
        if "=" in opt:
            k, v = opt.split("=", 1)
            extra_cfg[k] = v
    
    # Get NVIDIA API key from env
    env_vars = {}
    if "NVIDIA_API_KEY" in os.environ:
        env_vars["NVIDIA_API_KEY"] = os.environ["NVIDIA_API_KEY"]
    
    os.makedirs(args.out_root, exist_ok=True)
    
    # Initial skill
    with open(args.skill_init) as f:
        initial_skill = f.read()
    
    print(f"=== Population Training ===")
    print(f"Population size: {args.population}")
    print(f"Seeds: {args.seeds[:args.population]}")
    print(f"Steps per chunk: {args.steps_per_chunk}")
    print(f"Chunks (generations): {args.chunks}")
    print(f"Workers: {args.workers}")
    print(f"Output: {args.out_root}")
    print()
    
    # Track skills per population
    current_skills = [initial_skill] * args.population
    all_results_history = []
    
    for chunk in range(args.chunks):
        print(f"\n{'='*60}")
        print(f"  CHUNK {chunk + 1}/{args.chunks}  (steps {chunk * args.steps_per_chunk + 1} - {(chunk + 1) * args.steps_per_chunk})")
        print(f"{'='*60}\n")
        
        # Run populations in parallel
        pop_args = [
            (i, args.config, args.seeds[i], current_skills[i], args.out_root, args.steps_per_chunk, extra_cfg, env_vars)
            for i in range(args.population)
        ]
        
        results = []
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(run_single_population, pa) for pa in pop_args]
            for fut in as_completed(futures):
                res = fut.result()
                results.append(res)
                status = "✓" if res["success"] else "✗"
                print(f"  {status} pop {res['idx']} (seed={res['seed']}): score={res['best_score']:.4f}, steps={res['last_step']}, time={res['elapsed']:.0f}s")
                if not res["success"] and "error" in res:
                    print(f"    Error: {res['error']}")
        
        # Store history
        all_results_history.append({
            "chunk": chunk + 1,
            "results": results,
        })
        
        # Sort by score (descending)
        results.sort(key=lambda r: r["best_score"], reverse=True)
        
        print(f"\n  Chunk {chunk+1} ranking:")
        for rank, r in enumerate(results):
            marker = " ★" if rank < args.elite_keep else ""
            print(f"    {rank+1}. pop {r['idx']} (seed={r['seed']}): {r['best_score']:.4f}{marker}")
        
        # Crossover: top K donate to others
        if chunk < args.chunks - 1:
            top_k = results[:args.crossover_top_k]
            donor_skills = [r["best_skill"] for r in top_k if r["best_skill"]]
            
            print(f"\n  Crossover: top {len(donor_skills)} → others")
            
            new_skills = []
            for i, r in enumerate(results):
                if i < args.elite_keep:
                    # Elite: keep their best skill
                    new_skills.append(r["best_skill"])
                    print(f"    pop {r['idx']} (elite) keeps own skill (score={r['best_score']:.4f})")
                else:
                    # Weak: receive crossover from elites
                    crossed = crossover_skills(
                        donor_skills, 
                        r["best_skill"] or current_skills[r["idx"]],
                        max_edits_per_donor=args.max_cross_edits // len(donor_skills) if donor_skills else 0,
                        max_total=args.max_cross_edits
                    )
                    new_skills.append(crossed)
                    print(f"    pop {r['idx']} receives crossover from {len(donor_skills)} donors")
            
            current_skills = new_skills
        else:
            # Last chunk - keep best skills
            current_skills = [r["best_skill"] or current_skills[i] for i, r in enumerate(results)]
    
    # Final summary
    print(f"\n{'='*60}")
    print(f"  FINAL RESULTS")
    print(f"{'='*60}")
    
    # Get final results from last chunk
    final_results = all_results_history[-1]["results"]
    final_results.sort(key=lambda r: r["best_score"], reverse=True)
    
    for rank, r in enumerate(final_results):
        print(f"  {rank+1}. pop {r['idx']} (seed={r['seed']}): {r['best_score']:.4f} @ {r['out_root']}")
    
    # Save best overall
    best = final_results[0]
    final_best_path = os.path.join(args.out_root, "population_best_skill.md")
    with open(final_best_path, "w") as f:
        f.write(best["best_skill"])
    print(f"\n  Best overall saved to: {final_best_path}")
    print(f"  Score: {best['best_score']:.4f} (pop {best['idx']}, seed {best['seed']})")
    
    # Save full history
    history_path = os.path.join(args.out_root, "population_history.json")
    with open(history_path, "w") as f:
        json.dump(all_results_history, f, indent=2)
    print(f"  History saved to: {history_path}")


if __name__ == "__main__":
    main()