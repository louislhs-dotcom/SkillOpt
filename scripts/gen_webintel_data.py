#!/usr/bin/env python3
"""
Generate SkillOpt webintel training data by mining real usage from the TDAI memory gateway.
"""

import json
import os
import uuid
import re
from pathlib import Path
from typing import List, Dict, Set

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Constants
TDAI_GATEWAY_URL = "http://127.0.0.1:8420/v2/conversation/search"
API_KEY_PATH = os.path.expanduser("~/.memory-tencentdb/.gateway-key")
SERVICE_ID = "hermes-shared-memory"
SKILLOPT_DIR = os.path.expanduser("~/SkillOpt")
SEARCH_TERMS = [
    "web", "fetch", "scrape", "extract", "search", "article", 
    "RSS", "YouTube", "Carousell", "GeBIZ", "MarkTechPost", "GitHub"
]
TASK_TYPE_MAPPING = {
    "extract": "moli",
    "article": "moli",
    "RSS": "moli",
    "MarkTechPost": "moli",
    "scrape": "ego-browser",
    "YouTube": "agent-reach",
    "Carousell": "agent-reach",
    "GeBIZ": "agent-reach",
    "GitHub": "agent-reach",
    "web": "routing",
    "search": "routing",
    "fetch": "playwright"
}
SITE_MAPPING = {
    "Carousell": "carousell",
    "GeBIZ": "gebiz", 
    "MarkTechPost": "marktechpost",
    "GitHub": "github"
}


# Mock data for testing
def generate_mock_items() -> List[Dict]:
    return [
        {
            "id": str(uuid.uuid4()),
            "question": "Extract the main content from this article: https://example.com/article",
            "check": ["article", "content"],
            "task_type": "moli",
            "site": "empty"
        },
        {
            "id": str(uuid.uuid4()),
            "question": "Scrape Carousell listings for iPhone 15",
            "check": ["carousell", "iphone"],
            "task_type": "agent-reach",
            "site": "carousell"
        },
        {
            "id": str(uuid.uuid4()),
            "question": "Fetch the latest RSS feed from MarkTechPost",
            "check": ["rss", "marktechpost"],
            "task_type": "moli",
            "site": "marktechpost"
        }
    ]


# Deterministic ego-lite cleanup items: the agent must close its browser tabs
# (completeTaskSpace / closeTab) when the task finishes, or RAM creeps across
# many webintel tasks. These are ALWAYS added regardless of TDAI query results.
# The must_not "leave the tab open" / "keep it open" catches the RAM-leak habit.
EGO_LITE_CLEANUP_ITEMS = [
    {
        "id": "egolite_cleanup_001",
        "question": (
            "You finished scraping Carousell with ego-browser. The task is done "
            "and the user has the data. What is the last step?"
        ),
        "check": [
            {"pattern": "close", "accept": ["closed", "closing", "completeTaskSpace"]},
            {"pattern": "tab", "accept": ["task space", "taskspace"]},
        ],
        "must_not": [
            "leave it open", "keep the tab open", "keep it open",
            "stay open", "no need to close the tab", "handles it automatically",
        ],
        "task_type": "webintel",
        "site": "carousell",
    },
    {
        "id": "egolite_cleanup_003",
        "question": (
            "After completing a webintel task with ego-browser, what should you "
            "call to prevent RAM creep from open task spaces?"
        ),
        "check": [
            {"pattern": "completeTaskSpace", "accept": ["complete task space", "completetaskspace"]},
            {"pattern": "task space", "accept": ["taskspace", "tab", "completeTaskSpace"]},
        ],
        "must_not": [
            "keep the space", "leave it open", "keep it open",
            "stay open", "no need to call", "automatically",
        ],
        "task_type": "webintel",
        "site": "empty",
    },
]


# Load API key
def load_api_key() -> str:
    with open(API_KEY_PATH, "r") as f:
        return f.read().strip()


# Extract queries from assistant messages
def extract_queries_from_messages(messages: List[Dict]) -> List[str]:
    queries = []
    # Patterns to identify user queries in assistant responses
    patterns = [
        r"Extract the (.*?) from",
        r"Scrape (.*?)",
        r"Fetch the (.*?) from",
        r"I need to (.*?)",
        r"How do I (.*?)",
        r"What selectors for (.*?)"
    ]

    for msg in messages:
        content = msg.get("content", "")
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                if match.strip():
                    queries.append(match.strip())

    return list(set(queries))  # Deduplicate


# Query TDAI gateway
def query_tdai_gateway(query: str, api_key: str, limit: int = 100) -> List[str]:
    headers = {
        "x-tdai-service-id": SERVICE_ID,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    body = {"query": query, "limit": limit}

    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount("http://", HTTPAdapter(max_retries=retries))

    try:
        response = session.post(TDAI_GATEWAY_URL, headers=headers, json=body)
        response.raise_for_status()
        result = response.json()
        print(f"Gateway response for '{query}': {result}")  # Debug
        messages = result.get("data", {}).get("messages", [])
        return extract_queries_from_messages(messages)
    except requests.RequestException as e:
        print(f"Error querying TDAI gateway for '{query}': {e}")
        return []


# Convert query to training item
def query_to_item(query: str) -> Dict:
    """Convert a real query into a training item."""
    task_type = "routing"
    site = "empty"
    check = []

    # Determine task_type and site
    for term, tt in TASK_TYPE_MAPPING.items():
        if term.lower() in query.lower():
            task_type = tt
            break

    for term, s in SITE_MAPPING.items():
        if term.lower() in query.lower():
            site = s
            check.append(term.lower())
            break

    # Generate check keywords
    if not check:
        check = [word.lower() for word in query.split() if len(word) > 3][:3]

    return {
        "id": str(uuid.uuid4()),
        "question": query,
        "check": check,
        "task_type": task_type,
        "site": site
    }


# Deduplicate items by question
def deduplicate_items(existing_items: List[Dict], new_items: List[Dict]) -> List[Dict]:
    existing_questions = {item["question"] for item in existing_items}
    deduplicated = [item for item in new_items if item["question"] not in existing_questions]
    return existing_items + deduplicated


# Write items to file
def write_items(split: str, items: List[Dict]) -> None:
    split_dir = Path(SKILLOPT_DIR) / "data" / "webintel_split" / split
    split_dir.mkdir(parents=True, exist_ok=True)
    file_path = split_dir / "items.json"

    with open(file_path, "w") as f:
        json.dump(items, f, indent=2)


# Main function
def main():
    api_key = load_api_key()
    all_queries = []

    # Query TDAI gateway for each search term
    for term in SEARCH_TERMS:
        print(f"Querying TDAI gateway for: '{term}'")
        queries = query_tdai_gateway(term, api_key)
        all_queries.extend(queries)

    # Convert queries to training items
    all_items = [query_to_item(query) for query in all_queries]

    # Fallback: Use mock data if no items found
    if not all_items:
        print("No items found in TDAI gateway. Using mock data.")
        all_items = generate_mock_items()

    # ALWAYS include the ego-lite cleanup items (RAM-creep prevention). These
    # are deterministic and independent of TDAI query results, so the test
    # suite always exercises tab-closing behavior.
    all_items = EGO_LITE_CLEANUP_ITEMS + all_items

    # Split items into train/val/test (80/10/10)
    train_split = int(0.8 * len(all_items))
    val_split = int(0.1 * len(all_items))
    splits = {
        "train": all_items[:train_split],
        "val": all_items[train_split:train_split + val_split],
        "test": all_items[train_split + val_split:]
    }

    # Process each split
    added_counts = {}
    for split, new_items in splits.items():
        split_dir = Path(SKILLOPT_DIR) / "data" / "webintel_split" / split
        items_file = split_dir / "items.json"

        if items_file.exists():
            with open(items_file, "r") as f:
                existing_items = json.load(f)
        else:
            existing_items = []

        updated_items = deduplicate_items(existing_items, new_items)
        added = len(updated_items) - len(existing_items)
        added_counts[split] = added

        write_items(split, updated_items)

    # Report
    print("\n--- Results ---")
    for split, count in added_counts.items():
        print(f"Added {count} items to {split}/items.json")


if __name__ == "__main__":
    main()
