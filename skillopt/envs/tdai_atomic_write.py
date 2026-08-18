#!/usr/bin/env python3
"""
TDAI atomic memory writer for SkillOpt training results.

Writes directly to the SQLite vector store (l1_records + l1_fts)
because the /v2/core/write endpoint writes to a separate core memory store
that /v2/atomic/search doesn't index.

Usage:
    from tdai_atomic_write import write_skillopt_memory
    write_skillopt_memory("content here", "skillopt-notebooklm")
"""

import sqlite3
import os
import time
import json

DB_PATH = os.path.expanduser(
    "~/.memory-tencentdb/memory-tdai/instances/hermes-shared-memory/vectors.db"
)
RECORDS_DIR = os.path.expanduser("~/.memory-tencentdb/memory-tdai/records")


def write_skillopt_memory(content: str, mem_type: str = "skillopt") -> bool:
    """Write a memory directly to the TDAI SQLite vector store.

    Inserts into both l1_records and l1_fts so /v2/atomic/search can find it.
    Also appends to the records JSONL for backup consistency.
    """
    try:
        now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        ts = int(time.time() * 1000)
        record_id = f"m_{ts}_{mem_type.replace('-', '_')}"

        # 1. Insert into SQLite (l1_records + l1_fts)
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO l1_records (record_id, content, type, priority, scene_name,
                                    session_key, session_id, timestamp_str,
                                    timestamp_start, timestamp_end, created_time, updated_time, metadata_json)
            VALUES (?, ?, ?, 50, '', 'skillopt-training', 'skillopt', ?, ?, ?, ?, ?, '{}')
        """, (record_id, content, mem_type, now, now, now, now, now))

        cur.execute("""
            INSERT INTO l1_fts (content, content_original, record_id, type, priority,
                               scene_name, session_key, session_id, timestamp_str,
                               timestamp_start, timestamp_end, metadata_json)
            VALUES (?, ?, ?, ?, '50', '', 'skillopt-training', 'skillopt', ?, ?, ?, '{}')
        """, (content, content, record_id, mem_type, now, now, now))

        conn.commit()
        conn.close()

        # 2. Append to records JSONL for backup
        today = time.strftime("%Y-%m-%d")
        record_path = os.path.join(RECORDS_DIR, f"{today}.jsonl")
        record = {
            "id": record_id,
            "content": content,
            "type": mem_type,
            "priority": 50,
            "scene_name": "",
            "source_message_ids": [],
            "metadata": {},
            "timestamps": [],
            "createdAt": now,
            "updatedAt": now,
            "sessionKey": "skillopt-training",
            "sessionId": "skillopt",
        }
        with open(record_path, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return True
    except Exception as e:
        print(f"[TDAI atomic write failed: {e}]", flush=True)
        return False
