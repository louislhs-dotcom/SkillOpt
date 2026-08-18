#!/usr/bin/env python3
"""Universal agent log-pooling for the shared TDAI memory.

Lets ALL agents (Hermes, Prime, DSH, Claude Code) write and read logs,
assessments, and test results to the SAME shared namespace so the experience
is universal across agents. Any agent can import this module and pool its
logs into the shared store, then any other agent can search and assess them.

Why direct SQLite (not the gateway /v2/atomic/update):
- /v2/atomic/update 404s on NEW records (it only updates existing ones) —
  Prime's `remember()` has this latent bug.
- /v2/core/write writes to a separate core store that /v2/atomic/search does
  NOT index (returns 200 but invisible to search).
- Direct SQLite insert into l1_records + l1_fts is the VERIFIED path that
  /v2/atomic/search actually indexes (verified 2026-08-18).

Usage (any agent):
    from agent_log_pool import pool_log, search_logs, pool_assessment

    # Write a log entry tagged with your agent identity
    pool_log("hermes", "rollout", "hermes-prompt v8 step 8: soft=0.63 rejected")

    # Write a structured assessment any agent can read
    pool_assessment("hermes-prompt-test", {
        "verdict": "discriminates",
        "baseline_soft": 0.6892,
        "notes": "adversarial items correctly fail",
    })

    # Search pooled logs from any agent
    hits = search_logs("hermes-prompt test assessment", limit=10)
"""
from __future__ import annotations
import json
import os
import sqlite3
import time

DB_PATH = os.path.expanduser(
    "~/.memory-tencentdb/memory-tdai/instances/hermes-shared-memory/vectors.db"
)
RECORDS_DIR = os.path.expanduser("~/.memory-tencentdb/memory-tdai/records")

# Agent identity tags — keep in sync with the actual agents in the pipeline.
AGENTS = ("hermes", "prime", "dsh", "claude")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _record_id(agent: str, kind: str) -> str:
    return f"log_{int(time.time()*1000)}_{agent}_{kind}"


def pool_log(agent: str, kind: str, content: str, mem_type: str = "agent-log") -> bool:
    """Write a log entry tagged with agent identity to the shared store.

    Args:
        agent: one of AGENTS ("hermes", "prime", "dsh", "claude")
        kind: log category (e.g. "rollout", "assessment", "test", "error")
        content: the log text
        mem_type: TDAI record type (default "agent-log")
    """
    agent = agent.lower()
    if agent not in AGENTS:
        agent = "unknown"
    record_id = _record_id(agent, kind)
    now = _now_iso()
    ts = int(time.time() * 1000)
    # Prefix with agent + kind so search can filter by source.
    tagged = f"[{agent}:{kind}] {content}"
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO l1_records (record_id, content, type, priority, scene_name,
                                    session_key, session_id, timestamp_str,
                                    timestamp_start, timestamp_end, created_time, updated_time, metadata_json)
            VALUES (?, ?, ?, 50, ?, 'agent-log-pool', 'shared', ?, ?, ?, ?, ?, ?)
        """, (record_id, tagged, mem_type, agent, now, now, now, now, now, now))
        cur.execute("""
            INSERT INTO l1_fts (content, content_original, record_id, type, priority,
                               scene_name, session_key, session_id, timestamp_str,
                               timestamp_start, timestamp_end, metadata_json)
            VALUES (?, ?, ?, ?, '50', ?, 'agent-log-pool', 'shared', ?, ?, ?, '{}')
        """, (tagged, tagged, record_id, mem_type, agent, now, now, now))
        conn.commit()
        conn.close()
        # Append to records JSONL for backup consistency.
        record_path = os.path.join(RECORDS_DIR, time.strftime("%Y-%m-%d"))
        record = {
            "id": record_id, "content": tagged, "type": mem_type, "priority": 50,
            "scene_name": agent, "source_message_ids": [], "metadata": {},
            "timestamps": [], "createdAt": now, "updatedAt": now,
            "sessionKey": "agent-log-pool", "sessionId": "shared",
        }
        with open(record_path, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        print(f"[agent_log_pool] write failed: {e}", flush=True)
        return False


def pool_assessment(topic: str, data: dict, agent: str = "hermes") -> bool:
    """Write a structured assessment any agent can read and reason over.

    Args:
        topic: what is being assessed (e.g. "hermes-prompt-test")
        data: dict of assessment fields (verdict, scores, notes, ...)
        agent: which agent produced the assessment
    """
    content = json.dumps({"topic": topic, "agent": agent, **data}, ensure_ascii=False)
    return pool_log(agent, "assessment", content, mem_type="agent-assessment")


def search_logs(query: str, limit: int = 10, agent: str | None = None,
                kind: str | None = None) -> list[dict]:
    """Search pooled logs across all agents.

    Args:
        query: semantic search query
        limit: max results
        agent: filter by agent identity (None = all)
        kind: filter by log kind (None = all)
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        # FTS5 search on l1_fts, join back to l1_records for full content.
        q = query.replace('"', '""')
        cur.execute("""
            SELECT r.content, r.type, r.scene_name, r.created_time
            FROM l1_fts f JOIN l1_records r ON f.record_id = r.record_id
            WHERE l1_fts MATCH ? AND r.type IN ('agent-log', 'agent-assessment')
            ORDER BY r.created_time DESC LIMIT ?
        """, (f'"{q}"', limit))
        rows = cur.fetchall()
        conn.close()
        results = []
        for content, mtype, scene, created in rows:
            # Parse the [agent:kind] prefix.
            agent_tag = scene or "unknown"
            kind_tag = ""
            if content.startswith("["):
                inner = content[1:content.find("]")]
                if ":" in inner:
                    agent_tag, kind_tag = inner.split(":", 1)
            if agent and agent_tag != agent:
                continue
            if kind and kind_tag != kind:
                continue
            results.append({
                "agent": agent_tag, "kind": kind_tag, "type": mtype,
                "content": content, "created_at": created,
            })
        return results
    except Exception as e:
        print(f"[agent_log_pool] search failed: {e}", flush=True)
        return []


def list_agents() -> list[str]:
    """List which agents have written to the shared log pool."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT scene_name FROM l1_records
            WHERE type IN ('agent-log', 'agent-assessment')
        """)
        agents = [r[0] for r in cur.fetchall() if r[0]]
        conn.close()
        return agents
    except Exception:
        return []


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Self-test: write from each agent, search, verify.
        for a in AGENTS:
            ok = pool_log(a, "test", f"{a} agent log-pool self-test {time.time()}")
            print(f"  {a}: write={ok}")
        hits = search_logs("log-pool self-test", limit=10)
        print(f"search hits: {len(hits)}")
        for h in hits:
            print(f"  [{h['agent']}:{h['kind']}] {h['content'][:60]}")
        print("agents in pool:", list_agents())
