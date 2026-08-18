#!/usr/bin/env python3
"""Generate GeBIZ SkillOpt training data (train/val/test splits)."""
import json, os

BASE = os.path.join(os.path.dirname(__file__), "..", "data", "gebiz_split")

# Each item: question + check patterns the target model's answer must contain.
# The core lesson: GeBIZ is JSF -> POST with ViewState, not GET.
train = [
    {"id": "train_000", "task_type": "gebiz",
     "question": "How do I search GeBIZ (https://www.gebiz.gov.sg) for government tenders? A plain curl GET returns 'No opportunity found'. What's the correct approach?",
     "check": ["BOAdvancedSearch", "ViewState", "POST"],
     "order": ["ViewState", "POST"],
     "must_not": ["advancedSearch.xhtml"]},
    {"id": "train_001", "task_type": "gebiz",
     "question": "What is the correct endpoint for GeBIZ advanced search?",
     "check": ["BOAdvancedSearch.xhtml", "gebiz.gov.sg"],
     "must_not": ["advancedSearch.xhtml"]},
    {"id": "train_002", "task_type": "gebiz",
     "question": "Why does a simple curl GET to the GeBIZ opportunity listing show 'No opportunity found'?",
     "check": ["JSF", "ViewState", "POST"]},
    {"id": "train_003", "task_type": "gebiz",
     "question": "What form field holds the search keyword in GeBIZ advanced search?",
     "check": ["j_idt148", "inputText"]},
    {"id": "train_004", "task_type": "gebiz",
     "question": "How do I download a specific GeBIZ tender document by its document code?",
     "check": ["directlink.xhtml", "docCode"]},
    {"id": "train_005", "task_type": "gebiz",
     "question": "What is the first step in a GeBIZ JSF search flow?",
     "check": ["GET", "ViewState", "cookie"],
     "order": ["GET", "ViewState"]},
    {"id": "train_006", "task_type": "gebiz",
     "question": "I want to find construction tenders on GeBIZ. What keyword field should I use and what button submits the search?",
     "check": ["j_idt148", "buttonSearch"]},
    {"id": "train_007", "task_type": "gebiz",
     "question": "What is the difference between GeBIZ and URA CID?",
     "check": ["procurement", "planning", "URA"]},
    {"id": "train_008", "task_type": "gebiz",
     "question": "How are GeBIZ search results structured in the returned HTML?",
     "check": ["formSectionHeader6", "docCode"]},
    {"id": "train_009", "task_type": "gebiz",
     "question": "What HTTP method must I use to actually get GeBIZ search results?",
     "check": ["POST", "ViewState"]},
    {"id": "train_010", "task_type": "gebiz",
     "question": "What is the opportunity listing URL on GeBIZ?",
     "check": ["BOListing.xhtml", "origin=opportunities"]},
    {"id": "train_011", "task_type": "gebiz",
     "question": "When searching GeBIZ, must I preserve the session cookie between the initial page load and the search request?",
     "check": ["cookie", "session"]},
    {"id": "train_012", "task_type": "gebiz",
     "question": "What header should I send when querying GeBIZ to avoid being blocked?",
     "check": ["User-Agent"]},
    {"id": "train_013", "task_type": "gebiz",
     "question": "What does the 'All these words' field map to in the GeBIZ advanced search form?",
     "check": ["j_idt148", "All these words"]},
    {"id": "train_014", "task_type": "gebiz",
     "question": "Give me a complete working approach to search GeBIZ for 'construction' tenders.",
     "check": ["BOAdvancedSearch", "ViewState", "POST", "j_idt148"],
     "order": ["ViewState", "POST"],
     "must_not": ["advancedSearch.xhtml"]},
]

val = [
    {"id": "val_000", "task_type": "gebiz",
     "question": "What is the single most important thing to know about searching GeBIZ programmatically?",
     "check": ["ViewState", "POST", "JSF"]},
    {"id": "val_001", "task_type": "gebiz",
     "question": "Which portal should I use to find government tender opportunities?",
     "check": ["GeBIZ", "procurement"]},
    {"id": "val_002", "task_type": "gebiz",
     "question": "How do I extract the document code from a GeBIZ search result?",
     "check": ["directlink", "docCode"]},
    {"id": "val_003", "task_type": "gebiz",
     "question": "What is the correct order of operations for a GeBIZ search?",
     "check": ["GET", "ViewState", "POST"]},
    {"id": "val_004", "task_type": "gebiz",
     "question": "Why would a GeBIZ search return no results even with a correct keyword?",
     "check": ["ViewState", "POST", "GET"]},
]

test = [
    {"id": "test_000", "task_type": "gebiz",
     "question": "Write the exact steps to search GeBIZ for 'construction' and get real results.",
     "check": ["BOAdvancedSearch", "ViewState", "POST", "j_idt148"]},
    {"id": "test_001", "task_type": "gebiz",
     "question": "What endpoint and form field do I use to search GeBIZ by keyword?",
     "check": ["BOAdvancedSearch.xhtml", "j_idt148"]},
    {"id": "test_002", "task_type": "gebiz",
     "question": "Explain why GeBIZ cannot be searched with a simple GET request.",
     "check": ["JSF", "ViewState", "POST"]},
    {"id": "test_003", "task_type": "gebiz",
     "question": "How do I retrieve a specific tender's details after finding it in search results?",
     "check": ["directlink.xhtml", "docCode"]},
    {"id": "test_004", "task_type": "gebiz",
     "question": "What is the complete GeBIZ search workflow from start to finish?",
     "check": ["GET", "ViewState", "POST", "parse"]},
]

for split, items in [("train", train), ("val", val), ("test", test)]:
    d = os.path.join(BASE, split)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "items.json"), "w") as f:
        json.dump(items, f, indent=2)
    print(f"{split}: {len(items)} items -> {os.path.join(d, 'items.json')}")
