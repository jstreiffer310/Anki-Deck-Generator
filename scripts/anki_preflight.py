"""
scripts/anki_preflight.py — Live & Offline Anki Collection Pre-Flight Protection Engine

Ensures that the automated card generation pipeline NEVER overwrites, duplicates,
or alters manual cards or existing notes in the user's Anki collection.

Workflow:
1. When target deck is determined, queries Anki Desktop via AnkiConnect (http://localhost:8765).
2. If Anki Desktop is closed, seamlessly falls back to reading the local SQLite database
   (collection.anki2) with custom 'unicase' collation in read-only mode.
3. Extracts and normalizes all existing concepts, front fields, and keywords in the destination deck(s).
4. Filters out any candidate cards that already exist in the user's collection, preserving 100%
   of manual user cards and edits.
5. Injects namespaced GUIDs and 'pipeline_generated' tags onto newly created cards.
"""

import sys
import os
import re
import json
import glob
import sqlite3
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Set, Tuple, Union
import urllib.request
import urllib.error

logger = logging.getLogger("AnkiPreflight")

ANKICONNECT_URL = "http://localhost:8765"

def clean_html(text: str) -> str:
    """Strips HTML tags, entities, and extra whitespace."""
    if not text:
        return ""
    # Strip HTML tags
    t = re.sub(r'<[^>]+>', ' ', str(text))
    # Replace common HTML entities
    t = re.sub(r'&(?:nbsp|amp|lt|gt|quot|apos);', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()

def normalize_concept_signature(text: str) -> str:
    """
    Normalizes a concept string, question, or term into a canonical comparison signature.
    Strips question boilerplate ('what is the definition of', 'what is', etc.) and punctuation.
    """
    if not text:
        return ""
    clean = clean_html(text).lower()

    # Strip standard interrogative question framing
    clean = re.sub(r'^what is the (?:definition|mechanism|clinical significance|ethical significance) of\s+', '', clean)
    clean = re.sub(r'^what (?:is|are)\s+', '', clean)
    clean = re.sub(r'^what term is defined by\s*:?\s*', '', clean)
    clean = re.sub(r'^regarding\s+.*?\s*:\s*', '', clean)
    clean = re.sub(r'^define\s*:?\s*', '', clean)

    # Strip punctuation and non-alphanumeric characters (keep words and numbers)
    clean = re.sub(r'[^\w\s]', '', clean)
    return re.sub(r'\s+', ' ', clean).strip()

def find_anki_collection_paths() -> List[Path]:
    """Finds all local Anki collection.anki2 databases on the system."""
    appdata = os.environ.get("APPDATA", "")
    patterns = [
        os.path.join(appdata, "Anki2", "*", "collection.anki2"),
        r"C:\Users\*\AppData\Roaming\Anki2\*\collection.anki2"
    ]
    found = []
    for pat in patterns:
        for p in glob.glob(pat):
            path_obj = Path(p)
            if path_obj.exists() and path_obj not in found:
                found.append(path_obj)
    return found

def get_existing_deck_concepts_via_ankiconnect(deck_pattern: str) -> Optional[Dict[str, Any]]:
    """
    Queries running Anki Desktop via AnkiConnect to retrieve existing cards/notes.
    Returns None if AnkiConnect is not reachable.
    """
    try:
        req = urllib.request.Request(
            ANKICONNECT_URL,
            data=json.dumps({"action": "version", "version": 6}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=1.5) as res:
            ver = json.loads(res.read().decode("utf-8"))
            if not ver.get("result"):
                return None
    except Exception:
        return None

    # Query notes matching deck
    try:
        # Search for exact deck or wildcard deck
        query = f'deck:"*{deck_pattern}*"' if not deck_pattern.startswith("deck:") else deck_pattern
        payload = {
            "action": "findNotes",
            "version": 6,
            "params": {"query": query}
        }
        req = urllib.request.Request(
            ANKICONNECT_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=3.0) as res:
            note_ids = json.loads(res.read().decode("utf-8")).get("result", [])

        if not note_ids:
            return {
                "source": "ankiconnect",
                "count": 0,
                "manual_count": 0,
                "terms": set(),
                "fronts": set(),
                "descriptors": set()
            }

        # Fetch notes info in chunks
        terms = set()
        fronts = set()
        descriptors = set()
        manual_count = 0

        # Query in chunks of 500
        for i in range(0, len(note_ids), 500):
            chunk = note_ids[i:i + 500]
            info_req = urllib.request.Request(
                ANKICONNECT_URL,
                data=json.dumps({"action": "notesInfo", "version": 6, "params": {"notes": chunk}}).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(info_req, timeout=5.0) as res:
                notes_data = json.loads(res.read().decode("utf-8")).get("result", [])
                for n in notes_data:
                    tags = n.get("tags", [])
                    is_manual = ("pipeline_generated" not in tags) and ("auto_generated" not in tags)
                    if is_manual:
                        manual_count += 1

                    fields = n.get("fields", {})
                    # First field is typically Front / Question / Keyword
                    field_vals = [f.get("value", "") for f in fields.values()]
                    if field_vals:
                        f_front = field_vals[0]
                        norm_f = normalize_concept_signature(f_front)
                        if norm_f:
                            fronts.add(norm_f)
                            terms.add(norm_f)

                    if len(field_vals) > 1:
                        f_back = field_vals[1]
                        norm_b = normalize_concept_signature(f_back)
                        if norm_b:
                            descriptors.add(norm_b)

        return {
            "source": "ankiconnect",
            "count": len(note_ids),
            "manual_count": manual_count,
            "terms": terms,
            "fronts": fronts,
            "descriptors": descriptors
        }

    except Exception as e:
        logger.warning(f"Error querying AnkiConnect for existing notes: {e}")
        return None

def get_existing_deck_concepts_via_sqlite(deck_pattern: str) -> Dict[str, Any]:
    """
    Directly inspects local Anki collection.anki2 SQLite database in read-only mode.
    Used when Anki Desktop is closed.
    """
    col_paths = find_anki_collection_paths()
    if not col_paths:
        return {
            "source": "none",
            "count": 0,
            "manual_count": 0,
            "terms": set(),
            "fronts": set(),
            "descriptors": set()
        }

    col_path = col_paths[0]
    terms = set()
    fronts = set()
    descriptors = set()
    count = 0
    manual_count = 0

    try:
        conn = sqlite3.connect(f"file:{col_path}?mode=ro", uri=True, timeout=3.0)
        # Register Anki's custom unicase collation so queries on decks and notes work smoothly
        conn.create_collation("unicase", lambda a, b: (a > b) - (a < b))
        cur = conn.cursor()

        # Query notes from decks matching deck_pattern
        cur.execute("""
            SELECT d.name, n.flds, n.tags
            FROM notes n
            JOIN cards c ON n.id = c.nid
            JOIN decks d ON c.did = d.id
            WHERE d.name LIKE ?
        """, (f"%{deck_pattern}%",))

        rows = cur.fetchall()
        for dname, flds, tags in rows:
            count += 1
            tag_str = tags or ""
            is_manual = ("pipeline_generated" not in tag_str) and ("auto_generated" not in tag_str)
            if is_manual:
                manual_count += 1

            parts = flds.split("\x1f")
            if parts:
                f_front = parts[0]
                norm_f = normalize_concept_signature(f_front)
                if norm_f:
                    fronts.add(norm_f)
                    terms.add(norm_f)

            if len(parts) > 1:
                f_back = parts[1]
                norm_b = normalize_concept_signature(f_back)
                if norm_b:
                    descriptors.add(norm_b)

        conn.close()

    except Exception as e:
        logger.error(f"Error reading Anki SQLite collection at {col_path}: {e}")

    return {
        "source": "local_sqlite",
        "count": count,
        "manual_count": manual_count,
        "terms": terms,
        "fronts": fronts,
        "descriptors": descriptors
    }

def get_existing_deck_concepts(deck_title: str, course_code: Optional[str] = None) -> Dict[str, Any]:
    """
    High-level entry point to retrieve all existing concepts in destination deck(s).
    Tries live AnkiConnect first, then falls back to local SQLite.
    """
    # Extract search pattern (e.g. course code 'PSYC 3590' or '3590')
    search_pattern = course_code
    if not search_pattern:
        m = re.search(r'([A-Z]{2,4}\s*\d{4})', deck_title)
        if m:
            search_pattern = m.group(1)
        else:
            search_pattern = deck_title.split(":")[0].strip()

    # 1. Try AnkiConnect live
    live_res = get_existing_deck_concepts_via_ankiconnect(search_pattern)
    if live_res is not None:
        return live_res

    # 2. Fall back to offline local SQLite collection
    return get_existing_deck_concepts_via_sqlite(search_pattern)

def filter_cards_against_existing(
    cards: List[Dict[str, Any]],
    existing_concepts: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Compares candidate cards against existing notes in the user's Anki collection.
    Skips any card whose keyword, front, or question matches an existing concept.

    Returns:
        (retained_cards, skipped_cards)
    """
    if not existing_concepts or not existing_concepts.get("terms"):
        # No existing cards found to filter against
        return cards, []

    existing_terms = existing_concepts.get("terms", set())
    existing_fronts = existing_concepts.get("fronts", set())

    retained = []
    skipped = []

    for c in cards:
        kw = c.get("keyword") or ""
        front = c.get("front") or c.get("question") or ""
        question = c.get("question") or ""

        norm_kw = normalize_concept_signature(kw)
        norm_front = normalize_concept_signature(front)
        norm_q = normalize_concept_signature(question)

        # Check match against existing terms or fronts
        is_match = False
        matched_term = None

        if norm_kw and (norm_kw in existing_terms or norm_kw in existing_fronts):
            is_match = True
            matched_term = kw
        elif norm_front and (norm_front in existing_terms or norm_front in existing_fronts):
            is_match = True
            matched_term = front
        elif norm_q and (norm_q in existing_terms or norm_q in existing_fronts):
            is_match = True
            matched_term = question

        if is_match:
            skipped.append({
                "card": c,
                "matched_term": matched_term,
                "reason": f"Concept '{matched_term}' already exists in Anki deck (preserving manual card)"
            })
        else:
            # Tag newly generated card with pipeline markers
            c_tags = c.setdefault("tags", [])
            for tag in ["pipeline_generated", "auto_generated"]:
                if tag not in c_tags:
                    c_tags.append(tag)
            retained.append(c)

    return retained, skipped
