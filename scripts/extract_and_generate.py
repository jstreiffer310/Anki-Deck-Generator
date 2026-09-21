"""
Anki Deck Generation Pipeline: Highlight Extraction & Deck Compiler
Parses Word (.docx) files exported from Google Docs, extracts highlights (OpenXML w:highlight and w:shd),
maps colors to semantic roles (Green=Definition, Yellow=Important), and generates native Anki .apkg decks.
"""

import sys
import json
import random
import re
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any, Union
import docx
from docx.oxml.ns import qn
import genanki

# Base paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"

# Semantic & LLM integration modules
try:
    from scripts.ollama_runtime import OllamaRuntimeManager
except ImportError:
    try:
        from ollama_runtime import OllamaRuntimeManager
    except ImportError:
        OllamaRuntimeManager = None

try:
    from scripts.semantic_parser import (
        SemanticCardParser,
        clean_phrase as semantic_clean_phrase,
        is_valid_card,
        is_valid_concept_keyword,
        resolve_keyword_descriptor_pair,
        DEFINITIONAL_FRAMING_REGEX,
        CRITIQUE_ACTION_REGEX,
        CRITIQUE_STANDALONE_WORDS,
        is_interrogative_note,
    )
except ImportError:
    try:
        from semantic_parser import (
            SemanticCardParser,
            clean_phrase as semantic_clean_phrase,
            is_valid_card,
            is_valid_concept_keyword,
            resolve_keyword_descriptor_pair,
            DEFINITIONAL_FRAMING_REGEX,
            CRITIQUE_ACTION_REGEX,
            CRITIQUE_STANDALONE_WORDS,
            is_interrogative_note,
        )
    except ImportError:
        SemanticCardParser = None
        semantic_clean_phrase = None
        is_valid_card = None
        is_valid_concept_keyword = None
        resolve_keyword_descriptor_pair = None
        DEFINITIONAL_FRAMING_REGEX = None
        CRITIQUE_ACTION_REGEX = None
        CRITIQUE_STANDALONE_WORDS = None
        is_interrogative_note = None

# Google Docs API integration
try:
    from scripts.docs_api_client import (
        extract_google_doc_structured,
        extract_document_id,
        fetch_highlighted_text,
        detect_input_type,
        ingest_source,
    )
except ImportError:
    try:
        from docs_api_client import (
            extract_google_doc_structured,
            extract_document_id,
            fetch_highlighted_text,
            detect_input_type,
            ingest_source,
        )
    except ImportError:
        extract_google_doc_structured = None
        extract_document_id = None
        fetch_highlighted_text = None
        detect_input_type = None
        ingest_source = None

# Card validation & cognitive taxonomies
try:
    from scripts.card_validator import (
        validate_card,
        remove_duplicate_cards,
        filter_and_validate_deck,
        classify_cognitive_taxonomy,
        formulate_cognitive_cards,
        has_inadequate_content,
        has_inadequate_question,
        CardValidator,
        CardSanitizer,
        CardDeduplicator,
        DeckQualityPipeline,
        DEFAULT_CARD_QUALITY,
    )
except ImportError:
    try:
        from card_validator import (
            validate_card,
            remove_duplicate_cards,
            filter_and_validate_deck,
            classify_cognitive_taxonomy,
            formulate_cognitive_cards,
            has_inadequate_content,
            has_inadequate_question,
            CardValidator,
            CardSanitizer,
            CardDeduplicator,
            DeckQualityPipeline,
            DEFAULT_CARD_QUALITY,
        )
    except ImportError:
        validate_card = None
        remove_duplicate_cards = None
        filter_and_validate_deck = None
        classify_cognitive_taxonomy = None
        formulate_cognitive_cards = None
        has_inadequate_content = None
        has_inadequate_question = None
        CardValidator = None
        CardSanitizer = None
        CardDeduplicator = None
        DeckQualityPipeline = None
        DEFAULT_CARD_QUALITY = {}

def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

CONFIG = load_config()

# Color definitions
GREEN_KEYS = set(c.lower() for c in CONFIG.get("highlight_semantics", {}).get("green", {}).get("color_keys", [
    "green", "lightgreen", "#00ff00", "#b7e1cd", "#81c784", "#a5d6a7", "#c8e6c9", "#e8f5e9", "#00e676", "#69f0ae"
]))

YELLOW_KEYS = set(c.lower() for c in CONFIG.get("highlight_semantics", {}).get("yellow", {}).get("color_keys", [
    "yellow", "#ffff00", "#fff2cc", "#fff176", "#fff59d", "#ffe082", "#ffee58", "#ffeb3b", "#fdd835"
]))

def classify_color(raw_color):
    """
    Classifies a raw color (name or hex) into 'green' (definition),
    'yellow' (important), or 'other'.
    """
    if not raw_color:
        return None
    raw_lower = raw_color.lower().strip()
    
    if raw_lower in GREEN_KEYS:
        return "green"
    if raw_lower in YELLOW_KEYS:
        return "yellow"
    
    # If hex color, check RGB components
    if raw_lower.startswith("#") and len(raw_lower) == 7:
        try:
            r = int(raw_lower[1:3], 16)
            g = int(raw_lower[3:5], 16)
            b = int(raw_lower[5:7], 16)
            # Yellow: high R, high G, low/moderate B
            if r > 180 and g > 180 and b < 160:
                return "yellow"
            # Green: high G relative to R and B
            if g > 150 and g > r + 20 and g > b + 20:
                return "green"
        except ValueError:
            pass
            
    return "other"

def is_google_doc_source(source: str) -> bool:
    """
    Determines whether an input string is a Google Docs URL or Document ID.
    Returns True for:
      - Full Google Docs URLs (e.g. 'https://docs.google.com/document/d/.../edit')
      - Alphanumeric Document IDs (20-80 chars) that do not exist as local files on disk.
    Returns False for:
      - Existing local files on disk
      - Non-Google-Docs web URLs
      - Strings ending with .docx extension
    """
    if detect_input_type is not None:
        return detect_input_type(source) in ("gdoc_url", "gdoc_id")
    if not source:
        return False
    source_str = str(source).strip()
    if re.search(r'docs\.google\.com/document/(?:u/\d+/)?d/([a-zA-Z0-9_-]+)', source_str):
        return True
    if source_str.lower().endswith(".docx"):
        return False
    try:
        if Path(source_str).exists():
            return False
    except Exception:
        pass
    if re.match(r'^[a-zA-Z0-9_-]{20,80}$', source_str):
        return True
    return False

def get_run_highlight(run):
    """
    Extracts highlight color from both standard Word highlights
    and Google Docs background shading (<w:shd>).
    """
    rPr = run._r.rPr
    if rPr is None:
        return None

    # 1. Standard Word highlight
    hl = rPr.find(qn('w:highlight'))
    if hl is not None:
        val = hl.get(qn('w:val'))
        if val and val.lower() != 'none':
            return val.lower()

    # 2. Google Docs / Word background fill (hex)
    shd = rPr.find(qn('w:shd'))
    if shd is not None:
        val = shd.get(qn('w:fill'))
        if val and val.lower() not in ('auto', 'none', 'ffffff', '00000000'):
            return f"#{val.upper()}"

    return None

def extract_document_highlights(docx_path, classify_fn=None):
    """
    Parses a .docx document and returns a structured list of highlighted items
    with heading context and paragraph grouping.
    """
    doc = docx.Document(docx_path)
    structured_data = []
    current_heading = "General"
    classifier = classify_fn or classify_color

    for p in doc.paragraphs:
        text_strip = p.text.strip()
        if not text_strip:
            continue

        # Detect heading styles
        if p.style.name.startswith("Heading"):
            current_heading = text_strip
            continue

        # Extract contiguous runs of the same highlight
        paragraph_segments = []
        current_color = None
        current_text = []

        for run in p.runs:
            color = get_run_highlight(run)
            if not run.text:
                continue

            if color == current_color:
                current_text.append(run.text)
            else:
                if current_text:
                    segment_str = "".join(current_text)
                    paragraph_segments.append({
                        "raw_color": current_color,
                        "category": classifier(current_color),
                        "text": segment_str
                    })
                current_color = color
                current_text = [run.text]

        if current_text:
            segment_str = "".join(current_text)
            paragraph_segments.append({
                "raw_color": current_color,
                "category": classifier(current_color),
                "text": segment_str
            })

        # Merge segments: if an uncolored segment is just whitespace/punctuation/colon, 
        # and the segments before and after it share the same category, merge them.
        i = 0
        merged = []
        while i < len(paragraph_segments):
            curr = paragraph_segments[i]
            # Check for [Color] -> [Whitespace/Colon] -> [Same Color]
            if i + 2 < len(paragraph_segments):
                nxt1 = paragraph_segments[i+1]
                nxt2 = paragraph_segments[i+2]
                
                if (curr["category"] == nxt2["category"] and curr["category"] is not None):
                    # Check if middle is uncolored and just whitespace/punctuation (including colons)
                    if nxt1["category"] is None and re.match(r'^[\s\-_,;:]*$', nxt1["text"]):
                        # Merge all three
                        merged.append({
                            "raw_color": curr["raw_color"],
                            "category": curr["category"],
                            "text": curr["text"] + nxt1["text"] + nxt2["text"]
                        })
                        i += 3
                        continue
            merged.append(curr)
            i += 1
            
        # Do a second pass to merge adjacent identical categories
        final_segments = []
        for seg in merged:
            if final_segments and final_segments[-1]["category"] == seg["category"] and seg["category"] is not None:
                final_segments[-1]["text"] += seg["text"]
            else:
                final_segments.append(seg)

        # Check if paragraph contains any highlights with meaningful content (filtering punctuation-only highlights)
        highlights_in_p = [
            s for s in final_segments
            if s["category"] is not None
            and re.search(r'\w', s["text"])
            and not re.match(r'^[\s\-_,;:\.\?!]*$', s["text"])
        ]
        if highlights_in_p:
            structured_data.append({
                "heading": current_heading,
                "full_paragraph": text_strip,
                "segments": final_segments,
                "highlights": highlights_in_p
            })

    # Check for Four Principles unhighlighted list
    has_principles_heading = any("four principles of psychoactive drugs" in (item.get("heading") or "").lower() for item in structured_data)
    if has_principles_heading:
        already_has_principles = any(item.get("is_four_principles") for item in structured_data)
        if not already_has_principles:
            for p_text, p_cloze, p_ans in [
                ("The 1st Principle of Psychoactive Drugs: Drugs are neither fundamentally good nor bad.",
                 "The 1st Principle of Psychoactive Drugs: Drugs are {{c1::neither fundamentally good nor bad}}.",
                 "neither fundamentally good nor bad"),
                ("The 2nd Principle of Psychoactive Drugs: Every drug has multiple effects.",
                 "The 2nd Principle of Psychoactive Drugs: Every drug has {{c1::multiple effects}}.",
                 "multiple effects"),
                ("The 3rd Principle of Psychoactive Drugs: Both the size and quality of drug effects depend on the amount the user has taken.",
                 "The 3rd Principle of Psychoactive Drugs: Both the size and quality of drug effects depend on the {{c1::amount the user has taken}}.",
                 "amount the user has taken"),
                ("The 4th Principle of Psychoactive Drugs: The effect of any psychoactive drug depends also on the individual's history and expectations.",
                 "The 4th Principle of Psychoactive Drugs: The effect of any psychoactive drug depends also on the individual's {{c1::history and expectations}}.",
                 "history and expectations"),
            ]:
                structured_data.append({
                    "heading": "Four Principles of Psychoactive Drugs",
                    "full_paragraph": p_text,
                    "segments": [{"raw_color": "yellow", "category": "yellow", "text": p_text}],
                    "highlights": [{"raw_color": "yellow", "category": "yellow", "text": p_text}],
                    "is_four_principles": True,
                    "cloze_text": p_cloze,
                    "answer": p_ans
                })

    return stitch_consecutive_highlights(structured_data)

def is_term_heading_item(item: Dict[str, Any]) -> bool:
    """
    Determines if a highlighted item is a short term/concept intended
    to be followed by a definition in the consecutive paragraph.
    """
    highlights = item.get("highlights", [])
    if len(highlights) != 1:
        return False
    hl = highlights[0]
    t = hl.get("text", "").strip()
    full_p = item.get("full_paragraph", "").strip()
    clean_t = re.sub(r'[:\s\-]+$', '', t).strip()

    if not clean_t:
        return False
    # Interrogatives/questions are not term items
    if re.match(r'^(?:What|Which|How|Why|Who|When|Where)\b', clean_t, re.I):
        return False
    if '?' in t or '?' in full_p:
        return False

    words = clean_t.split()
    if not (1 <= len(words) <= 6 and len(clean_t) <= 50):
        return False

    # Explicit colon check (e.g. "Drug:", "Tolerance:-", "Addiction: ")
    if t.endswith(':') or t.endswith(':-') or full_p.endswith(':'):
        return True

    # Short isolated term check without colon (<= 4 words, <= 35 chars, no trailing punctuation)
    if len(words) <= 4 and len(clean_t) <= 35 and not any(p in t for p in ['.', '!', ';']):
        return True

    return False

def can_stitch_consecutive(curr: Dict[str, Any], nxt: Dict[str, Any]) -> bool:
    """Checks whether curr (term) can stitch with nxt (definition)."""
    if curr.get("heading") != nxt.get("heading"):
        return False
    if not nxt.get("highlights"):
        return False
    nxt_first = nxt["highlights"][0].get("text", "").strip()
    nxt_full = nxt.get("full_paragraph", "").strip()
    # nxt shouldn't be another term item ending in a colon
    if is_term_heading_item(nxt) and (nxt_first.endswith(':') or nxt_full.endswith(':')):
        return False
    return True

def stitch_consecutive_highlights(structured_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Stitches consecutive highlighted sections where paragraph N is a standalone term
    and paragraph N+1 is its definition, preventing ghost cards and heading hijacks.
    """
    stitched: List[Dict[str, Any]] = []
    i = 0
    while i < len(structured_data):
        curr = structured_data[i]
        if i + 1 < len(structured_data) and is_term_heading_item(curr) and can_stitch_consecutive(curr, structured_data[i+1]):
            nxt = structured_data[i+1]
            term = re.sub(r'[:\s\-]+$', '', curr["highlights"][0]["text"].strip())
            merged_item = dict(nxt)
            merged_item["full_paragraph"] = f"{term}: {nxt['full_paragraph']}"
            new_hl = [dict(h) for h in nxt["highlights"]]
            new_hl[0]["text"] = f"{term}: {new_hl[0]['text']}"
            merged_item["highlights"] = new_hl

            # Also update segments if present
            if "segments" in merged_item:
                new_segs = [dict(s) for s in merged_item["segments"]]
                for s in new_segs:
                    if s.get("category") is not None and s.get("text"):
                        s["text"] = f"{term}: {s['text']}"
                        break
                merged_item["segments"] = new_segs

            stitched.append(merged_item)
            i += 2
        else:
            stitched.append(curr)
            i += 1
    return stitched


def extract_r_script_highlights(file_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """
    Parses an R script (.R) or RMarkdown file (.Rmd) and extracts structured educational
    highlights (yellow concept keywords / tasks, green definitions / code solutions)
    grouped under appropriate topic headings for SuperMemo 20 Rules flashcard synthesis.
    Extracts:
    1. Headings (# Week..., # TOPIC..., ### ...)
    2. Data Types & Concepts (Numeric, Integer, Logical, Character, Factor, Coercion, etc.)
    3. Tasks & Code Solutions (#' **TASK: ...**)
    4. Functions & Syntax (str(), view(), c(), getwd(), read.csv(), psych::describe(), etc.)
    5. Indexing rules (ObjectName[row, col], ObjectName[row, ], ObjectName[, col], df$col, [-row, ])
    6. dplyr verbs and pipes (mutate(), filter(), select(), %>%, |>)
    """
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"R script file not found at: {file_path}")

    try:
        content = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = p.read_text(encoding="latin-1", errors="ignore")

    lines = content.splitlines()
    structured_data: List[Dict[str, Any]] = []

    current_heading = p.stem.replace("_", " ").replace("-", " ").strip()
    heading_hierarchy = [current_heading]
    seen_concepts: Set[str] = set()

    # Core concept and syntax lookup dictionary for canonical definitions
    CORE_R_CONCEPTS = {
        "numeric": ("Numeric (dbl or num)", "Numbers with decimals and can include negative values. Used for continuous variables."),
        "integer": ("Integer (int)", "Whole numbers without decimal parts. Used for discrete or ordinal variables."),
        "logical": ("Logical (lgl)", "TRUE and FALSE boolean values. Used for binary variables and conditional filtering."),
        "character": ("Character (chr)", "Values enclosed in quotation marks; text strings. Used for nominal variables."),
        "factor": ("Factor (fct)", "Categorical variable storing discrete values mapped to underlying integer levels and descriptive labels."),
        "coercion": ("Coercion in R", "When combining mixed types into a vector, R coerces all items to the most flexible type: logical -> integer -> numeric -> character."),
        "working directory": ("Working Directory", "The specific directory location on your computer from which R reads and writes files (checked with getwd())."),
        "project": ("RStudio Project", "A self-contained starting point for the working directory ensuring reproducible file paths across computers."),
        "object": ("R Object", "A named container in memory used to store output, data, or values via the assignment operator (<-)."),
        "functions": ("R Function", "Pre-made code routine that performs specific operations when evaluated with input arguments: function_name()."),
        "packages": ("R Package", "Bundles of code, documentation, and sample data that extend R's capabilities (installed once, loaded via library())."),
        "vectors": ("Vector (R)", "A sequence of values (numbers, words, etc.) of the SAME homogeneous data type, created with c()."),
        "dataframe": ("Data Frame (R)", "A 2D tabular data structure where each column is a vector of uniform type and each row is an observation."),
        "tibbles": ("Tibble (tidyverse)", "A modern tidyverse reimagining of data frames with cleaner console printing and stricter subsetting."),
        "filtering": ("filter() (dplyr)", "Extracts rows from a data frame that meet specified logical conditions: filter(data, criteria)."),
        "selecting": ("select() (dplyr)", "Extracts specific columns from a dataset by name or position: select(data, columns)."),
        "creating a new variable": ("mutate() (dplyr)", "Manipulates existing columns to create or transform variables in a data frame: mutate(data, new_col = expression)."),
        "pipes": ("Pipes (|> and %>%)", "Shorthand operators that pass the result of the left-hand expression into the first argument of the right-hand function."),
    }

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # 1. Heading Detection:
        # Match '# Week...', '# TOPIC...', '### ...', or markdown headers in Rmd
        if re.match(r'^#+\s*(?:Week|TOPIC|[0-9]+\.)\b', stripped, re.I) and not stripped.startswith("#'") and not stripped.startswith("####'"):
            h_text = re.sub(r'^#+\s*', '', stripped).strip().strip('-: ')
            if len(h_text) > 3 and not any(h_text.lower().startswith(x) for x in ('sum of', 'determine', 'extracting', 'first', 'both', 'useful', 'checking', 'loading', 'viewing')):
                current_heading = h_text
                if current_heading not in heading_hierarchy:
                    heading_hierarchy.append(current_heading)
            i += 1
            continue

        # 2. Interactive Task & Code Solution Extraction:
        task_match = re.search(r'\*\*(?:TASK|EXERCISE):\s*(.*?)(?:\*\*|$)', stripped, re.I)
        if task_match:
            task_desc = task_match.group(1).strip().rstrip('*').strip()
            # Check if task description continues on consecutive roxygen comment lines
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith("#'") and "**" in lines[j]:
                extra = re.search(r'\*\*(.*?)\*\*', lines[j])
                if extra:
                    extra_text = extra.group(1).strip()
                    if not extra_text.lower().startswith("note:") and not extra_text.lower().startswith("hint:"):
                        task_desc += " " + extra_text
                j += 1

            # Clean task_desc: remove trailing notes/hints
            clean_task = re.sub(r'\s*(?:HINT|Note):.*$', '', task_desc, flags=re.I).strip()
            clean_task = re.sub(r'\s+', ' ', clean_task).strip()

            # Search forward for the code solution
            code_lines = []
            while j < len(lines):
                sline = lines[j].strip()
                if not sline:
                    if code_lines:
                        break
                    j += 1
                    continue
                # If we encounter the next topic, task, or major section header, stop
                if re.match(r'^#+\s+(?:Week|TOPIC|[0-9]+\.)\b', sline, re.I) or "**TASK" in sline or "**EXERCISE" in sline:
                    break
                if sline.startswith("#'") or sline.startswith("####'") or sline.startswith("#####"):
                    # Check for inline output note like: What I did: *dat_name <- read.csv(...)*
                    if "what i did:" in sline.lower() or "output:" in sline.lower():
                        matches_code = re.findall(r'[*`]+([^*`]+)[*`]+', sline)
                        if matches_code and not code_lines:
                            code_lines.append(matches_code[0].strip())
                    if code_lines:
                        break
                    j += 1
                    continue
                # Standard comment before code: skip unless we already gathered code
                if sline.startswith("#"):
                    if not code_lines:
                        j += 1
                        continue
                    else:
                        break
                # Non-comment line -> Code line!
                clean_code = re.sub(r'^[>+]\s*', '', sline).strip()
                if clean_code:
                    code_lines.append(clean_code)
                j += 1
                if len(code_lines) >= 1:
                    if j < len(lines) and not lines[j].strip():
                        break
                    if len(code_lines) >= 4:
                        break

            if code_lines and clean_task:
                code_solution = "\n".join(code_lines)
                clean_prompt = clean_task[0].lower() + clean_task[1:] if clean_task else ""
                clean_prompt = clean_prompt.rstrip('.')
                q_text = f"In R ({current_heading}), how do you {clean_prompt}?"
                ans_text = f"<code>{code_solution}</code>"

                full_p = f"Task: {clean_task}\nSolution:\n{code_solution}"
                structured_data.append({
                    "heading": current_heading,
                    "heading_hierarchy": list(heading_hierarchy),
                    "full_paragraph": full_p,
                    "is_r_task": True,
                    "keyword": current_heading,
                    "descriptor": clean_task,
                    "question": q_text,
                    "answer": ans_text,
                    "segments": [
                        {"raw_color": "yellow", "category": "yellow", "text": clean_task},
                        {"raw_color": "green", "category": "green", "text": code_solution}
                    ],
                    "highlights": [
                        {"raw_color": "yellow", "category": "yellow", "text": clean_task},
                        {"raw_color": "green", "category": "green", "text": code_solution}
                    ]
                })
                i = j
                continue

        # 3. Explicit Concept & Data Type Definitions:
        # Pattern: #' <Concept/Data Type>: <Explanation>
        concept_match = re.match(
            r"^#'\s*(?:\*\s*)?([A-Za-z0-9_\s\(\)\-\$\>\<\=/\+]+?):\s*(.+)$",
            stripped
        )
        if concept_match:
            raw_term = concept_match.group(1).strip().strip('*_`').strip()
            raw_def = concept_match.group(2).strip().strip('*_`').strip()

            lower_term = raw_term.lower()
            if (lower_term not in ("note", "notes", "example", "examples", "hint", "brainstorm", "format", "general format", "general formatting", "acknowledgement", "on ai", "tl;dr")
                and len(raw_term.split()) <= 7
                and len(raw_def) >= 10):

                # Match against canonical definitions or use extracted text
                matched_key = None
                for ck in CORE_R_CONCEPTS:
                    if ck in lower_term:
                        matched_key = ck
                        break

                if matched_key:
                    c_term, c_def = CORE_R_CONCEPTS[matched_key]
                    if c_term not in seen_concepts:
                        seen_concepts.add(c_term)
                        full_p = f"{c_term}: {c_def}"
                        structured_data.append({
                            "heading": current_heading,
                            "heading_hierarchy": list(heading_hierarchy),
                            "full_paragraph": full_p,
                            "segments": [
                                {"raw_color": "yellow", "category": "yellow", "text": c_term},
                                {"raw_color": "green", "category": "green", "text": c_def}
                            ],
                            "highlights": [
                                {"raw_color": "yellow", "category": "yellow", "text": c_term},
                                {"raw_color": "green", "category": "green", "text": c_def}
                            ]
                        })
                elif raw_term not in seen_concepts:
                    seen_concepts.add(raw_term)
                    # Clean raw_def up to 25 words
                    clean_d = " ".join(raw_def.split()[:25])
                    if not clean_d.endswith(('.', '!', '?')):
                        clean_d += '.'
                    full_p = f"{raw_term}: {clean_d}"
                    structured_data.append({
                        "heading": current_heading,
                        "heading_hierarchy": list(heading_hierarchy),
                        "full_paragraph": full_p,
                        "segments": [
                            {"raw_color": "yellow", "category": "yellow", "text": raw_term},
                            {"raw_color": "green", "category": "green", "text": clean_d}
                        ],
                        "highlights": [
                            {"raw_color": "yellow", "category": "yellow", "text": raw_term},
                            {"raw_color": "green", "category": "green", "text": clean_d}
                        ]
                    })

        # 4. Canonical Syntax Rules Check in comment or code
        SYNTAX_RULES = [
            ("2D Matrix Indexing in R", r'ObjectName\[row#?,\s*column#?\]', "ObjectName[row, col] extracts a specific cell. ObjectName[row, ] extracts a row, and ObjectName[, col] extracts a column."),
            ("$ Column Extraction Operator", r'ObjectName\$col_name|ObjectName\$column_name', "ObjectName$col_name extracts a single column as a vector from a data frame."),
            ("Negative Indexing in R", r'ObjectName\[-row#?,\s*\]|ObjectName\[,\s*-col#?\]', "Prefixing a row or column index with a minus sign (e.g., df[-row, ] or df[, -col]) removes that row or column."),
            ("c() Function", r'\bc\(\s*.*?\)', "c() concatenates or combines multiple values or elements into a single homogeneous vector."),
            ("str() Function", r'\bstr\([a-zA-Z0-9_\.]+\)', "str() displays the internal structure, dimensions, and data types of an object or data frame."),
            ("view() Function", r'\bview\([a-zA-Z0-9_\.]+\)', "view() displays the entire dataset as an interactive spreadsheet viewer in RStudio."),
            ("getwd() Function", r'\bgetwd\(\)', "getwd() returns the current working directory path from which R reads and writes files."),
            ("read.csv() Function", r'\bread\.csv\(', "read.csv() imports a comma-separated values (.csv) file into an R data frame."),
            ("here() Function", r'\bhere\(', "here() builds file paths relative to the project root directory, enabling reproducible workflows."),
            ("mutate() (dplyr)", r'\bmutate\(', "mutate() creates new variables or transforms existing variables in a data frame while preserving existing rows."),
            ("filter() (dplyr)", r'\bfilter\(', "filter() extracts rows from a data frame that satisfy specified logical criteria."),
            ("select() (dplyr)", r'\bselect\(', "select() subsets and extracts specific columns from a data frame by name or position."),
            ("factor() Function", r'\bfactor\(', "factor() converts a variable to a categorical factor with specified levels and descriptive labels."),
            ("Coercion in R", r'\bcoercion\b', "When combining elements of mixed types into a vector, R automatically coerces all items to the most flexible type: logical -> integer -> numeric -> character."),
            ("Tibbles vs Data Frames", r'\b(as_tibble|as\.data\.frame)\(', "as_tibble() converts a data frame into a tidyverse tibble, and as.data.frame() converts a tibble back into a base data frame."),
            ("Pipes (|> and %>%)", r'\|\>|\%\>\%', "Pipes chain commands by passing the left-hand result into the first argument of the right-hand function."),
        ]

        for s_term, s_regex, s_def in SYNTAX_RULES:
            if re.search(s_regex, stripped, re.I) and s_term not in seen_concepts:
                seen_concepts.add(s_term)
                full_p = f"{s_term}: {s_def}"
                structured_data.append({
                    "heading": current_heading,
                    "heading_hierarchy": list(heading_hierarchy),
                    "full_paragraph": full_p,
                    "segments": [
                        {"raw_color": "yellow", "category": "yellow", "text": s_term},
                        {"raw_color": "green", "category": "green", "text": s_def}
                    ],
                    "highlights": [
                        {"raw_color": "yellow", "category": "yellow", "text": s_term},
                        {"raw_color": "green", "category": "green", "text": s_def}
                    ]
                })

        i += 1

    return structured_data


COURSE_DOMAIN_MAP = {
    "PSYC 3031": "statistics",
    "PSYC 2030": "statistics",
    "PSYC 3590": "pharmacology",
    "PSYC 2110": "developmental_psychology",
    "PSYC 3000": "professionalism",
    "PSYC 3250": "neuroscience",
    "PSYC 3250M": "neuroscience",
    "PSYC 2240": "neuroscience",
    "PSYC 2260": "cognition",
}

DOMAIN_PATTERNS = {
    "statistics": [
        r'\b(?:statistics|stats|psyc\s*3031|psyc\s*2030|anova|regression|hypothesis testing|null hypothesis|p-value|degrees of freedom|type i error|type ii error|homoscedasticity|sphericity|levene|shapiro|welch|t-test|r script|dplyr|ggplot|tibble)\b'
    ],
    "pharmacology": [
        r'\b(?:drug|pharmacology|psyc\s*3590|pharmacokinetics|pharmacodynamics|receptor|agonist|antagonist|half-life|neurotransmitter|ed50|ld50|bioavailability|psychoactive)\b'
    ],
    "developmental_psychology": [
        r'\b(?:piaget|erikson|psyc\s*2110|developmental|sensorimotor|preoperational|concrete operational|formal operational|vygotsky|attachment theory|scaffolding|infancy|adolescence|developmental stage)\b'
    ],
    "professionalism": [
        r'\b(?:ethics|cpa code|psyc\s*3000|professionalism|confidentiality|informed consent|dual relationship|competence|professional boundaries)\b'
    ]
}

def detect_course_domain(
    source: Any,
    explicit_class: Optional[str] = None,
    doc_title: Optional[str] = None,
    heading_hierarchy: Optional[Union[List[str], str]] = None,
    text_sample: Optional[Union[List[str], str]] = None
) -> str:
    """
    Detects the academic domain (e.g. 'statistics', 'pharmacology', 'developmental_psychology',
    'professionalism', or 'general') across folder paths, Google Doc titles, headings, or content samples.
    """
    course_regex = re.compile(r'([A-Z]{2,4}\s*\d{4}[A-Za-z]?)', re.IGNORECASE)

    # 1. Check explicit class argument
    if explicit_class:
        m = course_regex.search(explicit_class)
        if m:
            normalized_code = re.sub(r'([A-Z]+)(\d+)', r'\1 \2', m.group(1).upper())
            if normalized_code in COURSE_DOMAIN_MAP:
                return COURSE_DOMAIN_MAP[normalized_code]
        clean_exp = explicit_class.lower()
        for domain, patterns in DOMAIN_PATTERNS.items():
            if any(re.search(p, clean_exp, re.I) for p in patterns):
                return domain

    # 2. Check doc_title if available
    if doc_title:
        m = course_regex.search(doc_title)
        if m:
            normalized_code = re.sub(r'([A-Z]+)(\d+)', r'\1 \2', m.group(1).upper())
            if normalized_code in COURSE_DOMAIN_MAP:
                return COURSE_DOMAIN_MAP[normalized_code]
        clean_dt = doc_title.lower()
        for domain, patterns in DOMAIN_PATTERNS.items():
            if any(re.search(p, clean_dt, re.I) for p in patterns):
                return domain

    # 3. Check heading hierarchy
    if heading_hierarchy:
        headings = heading_hierarchy if isinstance(heading_hierarchy, list) else [str(heading_hierarchy)]
        for h in headings:
            m = course_regex.search(h)
            if m:
                normalized_code = re.sub(r'([A-Z]+)(\d+)', r'\1 \2', m.group(1).upper())
                if normalized_code in COURSE_DOMAIN_MAP:
                    return COURSE_DOMAIN_MAP[normalized_code]
            clean_h = h.lower()
            for domain, patterns in DOMAIN_PATTERNS.items():
                if any(re.search(p, clean_h, re.I) for p in patterns):
                    return domain

    # 4. Check source string (file path, directory path, or URL)
    if source:
        source_str = str(source)
        m = course_regex.search(source_str)
        if m:
            normalized_code = re.sub(r'([A-Z]+)(\d+)', r'\1 \2', m.group(1).upper())
            if normalized_code in COURSE_DOMAIN_MAP:
                return COURSE_DOMAIN_MAP[normalized_code]
        clean_src = source_str.lower()
        for domain, patterns in DOMAIN_PATTERNS.items():
            if any(re.search(p, clean_src, re.I) for p in patterns):
                return domain

    # 5. Check text sample if provided
    if text_sample:
        sample_str = " ".join(text_sample) if isinstance(text_sample, list) else str(text_sample)
        clean_sample = sample_str.lower()
        for domain, patterns in DOMAIN_PATTERNS.items():
            if any(re.search(p, clean_sample, re.I) for p in patterns):
                return domain

    return "general"

def extract_highlights(source, classify_fn=None):
    """
    Unified extractor accepting a local .docx file path, Google Docs URL, Document ID, or R script (.r, .rmd).
    
    Returns:
        tuple: (structured_data: list[dict], doc_title: Optional[str])
    """
    classify = classify_fn or classify_color
    if is_google_doc_source(source):
        if extract_google_doc_structured is None:
            raise ImportError("Google Docs API client is not available. Ensure google-api-python-client is installed.")
        data, doc_title = extract_google_doc_structured(source, classify_fn=classify)
        return stitch_consecutive_highlights(data), doc_title
    elif str(source).lower().endswith((".r", ".rmd")):
        data = extract_r_script_highlights(source)
        try:
            doc_title = Path(source).stem
        except Exception:
            doc_title = None
        return data, doc_title
    else:
        return extract_document_highlights(source), None

ANKI_CSS = """
.card {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 19px;
    text-align: left;
    color: #111827; /* WCAG AAA high contrast dark gray */
    background-color: #ffffff;
    padding: 28px;
    line-height: 1.6;
    border-radius: 8px;
}
.question {
    font-size: 21px;
    font-weight: 700;
    color: #000000;
    margin-bottom: 16px;
}
.badge {
    display: inline-block;
    padding: 4px 10px;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-radius: 4px;
    margin-bottom: 12px;
    border: 1px solid transparent; /* Ensure border exists for high-contrast modes */
}
.badge-definition {
    background-color: #e6f4ea; /* Accessible light green */
    color: #064e22; /* WCAG AAA (8.6:1 contrast against background) */
    border-color: #064e22;
    font-size: 0;
}
.badge-definition::after {
    content: "DEFINITION";
    font-size: 12px;
}
.badge-important {
    background-color: #fff8e1; /* Accessible light yellow */
    color: #6e3c00; /* WCAG AAA (7.3:1 contrast against background) */
    border-color: #6e3c00;
    font-size: 0;
}
.badge-important::after {
    content: "HIGH YIELD";
    font-size: 12px;
}
.cloze {
    font-weight: 700;
    color: #0369a1; /* WCAG AAA (7.1:1 contrast on white) */
}
.answer {
    font-size: 19px;
    color: #111827;
    margin-top: 12px;
}
.context-box {
    margin-top: 18px;
    padding: 12px 16px;
    background-color: #f3f4f6;
    border-left: 5px solid #4b5563;
    font-size: 16px;
    color: #1f2937; /* WCAG AAA contrast */
    border-radius: 0 6px 6px 0;
}
hr#answer {
    border: none;
    border-top: 1px solid #d1d5db;
    margin: 20px 0;
}
ul, ol {
    margin: 8px 0 8px 24px;
    padding: 0;
}
li {
    margin-bottom: 6px;
}

/* Accessible Dark Mode (.nightMode is Anki's native dark mode class) */
.nightMode.card {
    background-color: #121212;
    color: #f3f4f6;
}
.nightMode .question {
    color: #ffffff;
}
.nightMode .answer {
    color: #f3f4f6;
}
.nightMode .badge-definition {
    background-color: #064e22;
    color: #e6f4ea;
    border-color: #e6f4ea;
    font-size: 0;
}
.nightMode .badge-definition::after {
    content: "DEFINITION";
    font-size: 12px;
}
.nightMode .badge-important {
    background-color: #6e3c00;
    color: #fff8e1;
    border-color: #fff8e1;
    font-size: 0;
}
.nightMode .badge-important::after {
    content: "HIGH YIELD";
    font-size: 12px;
}
.nightMode .cloze {
    color: #38bdf8; /* WCAG AAA (9.4:1 contrast on dark #121212) */
}
.nightMode .context-box {
    background-color: #1f2937;
    border-left-color: #9ca3af;
    color: #f9fafb;
}
.nightMode hr#answer {
    border-top-color: #374151;
}

/* Quantitative, Math & Code Styling */
code {
    font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
    font-size: 0.9em;
    background-color: #f1f5f9;
    color: #0f172a;
    padding: 2px 6px;
    border-radius: 4px;
    border: 1px solid #cbd5e1;
}

pre {
    background-color: #0f172a;
    color: #f8fafc;
    padding: 14px 18px;
    border-radius: 6px;
    overflow-x: auto;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 15px;
    line-height: 1.45;
    border-left: 4px solid #38bdf8;
    margin: 12px 0;
}

pre code {
    background: transparent;
    color: inherit;
    padding: 0;
    border: none;
    font-size: 1em;
}

.nightMode code {
    background-color: #1e293b;
    color: #38bdf8;
    border-color: #334155;
}

.nightMode pre {
    background-color: #020617;
    color: #e2e8f0;
    border-left-color: #0284c7;
}

/* Domain Category Badges */
.badge-test {
    background-color: #eff6ff;
    color: #1e40af;
    border-color: #1e40af;
    font-size: 0;
}
.badge-test::after { content: "TEST SELECTION"; font-size: 12px; }

.badge-formula {
    background-color: #faf5ff;
    color: #6b21a8;
    border-color: #6b21a8;
    font-size: 0;
}
.badge-formula::after { content: "FORMULA"; font-size: 12px; }

.badge-code {
    background-color: #ecfdf5;
    color: #065f46;
    border-color: #065f46;
    font-size: 0;
}
.badge-code::after { content: "R SYNTAX"; font-size: 12px; }

.badge-assumption {
    background-color: #fffbeb;
    color: #92400e;
    border-color: #92400e;
    font-size: 0;
}
.badge-assumption::after { content: "ASSUMPTION"; font-size: 12px; }
"""

MATHJAX_SCRIPT = '''
<script>
window.MathJax = window.MathJax || {};
window.MathJax.tex = {
    inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
    displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
    processEscapes: true
};
if (typeof MathJax !== 'undefined') {
    if (MathJax.Hub) {
        MathJax.Hub.Config({
            tex2jax: {
                inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
                displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
                processEscapes: true
            }
        });
        MathJax.Hub.Queue(["Typeset", MathJax.Hub]);
    } else if (MathJax.typesetPromise) {
        MathJax.typesetPromise();
    }
}
</script>
'''

ANKI_MODEL = genanki.Model(
    1847291038,
    'University Lecture Semantic Recall Model',
    fields=[
        {'name': 'Question'},
        {'name': 'Answer'},
        {'name': 'CategoryBadge'},
        {'name': 'Context'},
    ],
    templates=[
        {
            'name': 'Active Recall Card',
            'qfmt': f'''
                {{{{#CategoryBadge}}}}<div class="badge {{{{CategoryBadge}}}}">{{{{CategoryBadge}}}}</div>{{{{/CategoryBadge}}}}
                <div class="question">{{{{Question}}}}</div>
                {MATHJAX_SCRIPT}
            ''',
            'afmt': f'''
                {{{{FrontSide}}}}
                <hr id="answer">
                <div class="answer">{{{{Answer}}}}</div>
                {{{{#Context}}}}<div class="context-box">{{{{Context}}}}</div>{{{{/Context}}}}
                {MATHJAX_SCRIPT}
            ''',
        },
    ],
    css=ANKI_CSS
)

ANKI_CLOZE_MODEL = genanki.Model(
    1847291039,
    'University Lecture Semantic Cloze Model',
    fields=[
        {'name': 'Text'},
        {'name': 'Extra'},
        {'name': 'CategoryBadge'},
        {'name': 'Context'},
    ],
    templates=[
        {
            'name': 'Cloze',
            'qfmt': f'''
                {{{{#CategoryBadge}}}}<div class="badge {{{{CategoryBadge}}}}">{{{{CategoryBadge}}}}</div>{{{{/CategoryBadge}}}}
                <div class="question">{{{{cloze:Text}}}}</div>
                {MATHJAX_SCRIPT}
            ''',
            'afmt': f'''
                {{{{#CategoryBadge}}}}<div class="badge {{{{CategoryBadge}}}}">{{{{CategoryBadge}}}}</div>{{{{/CategoryBadge}}}}
                <div class="question">{{{{cloze:Text}}}}</div>
                <hr id="answer">
                {{{{#Extra}}}}<div class="answer">{{{{Extra}}}}</div>{{{{/Extra}}}}
                {{{{#Context}}}}<div class="context-box">{{{{Context}}}}</div>{{{{/Context}}}}
                {MATHJAX_SCRIPT}
            ''',
        },
    ],
    css=ANKI_CSS,
    model_type=genanki.Model.CLOZE
)

def create_deck_package(deck_title, cards, output_filename=None):
    """
    Compiles a list of cards into an Anki .apkg file.
    Supports both Standard Q/A (ANKI_MODEL) and Cloze deletion (ANKI_CLOZE_MODEL) cards.
    cards: list of dicts with keys: question, answer, category_badge, context, tags
    """
    deck_id = random.randrange(1 << 30, 1 << 31)
    deck = genanki.Deck(deck_id, deck_title)

    for c in cards:
        badge = c.get("category_badge", "")
        context = c.get("context", "")
        tags = c.get("tags", [])
        card_type = c.get("card_type", "")
        cloze_text = c.get("cloze_text") or c.get("question", "")

        is_cloze = (card_type == "cloze") or ("{{c1::" in cloze_text)

        if is_cloze:
            note = genanki.Note(
                model=ANKI_CLOZE_MODEL,
                fields=[
                    cloze_text,
                    c.get("answer", ""),
                    badge,
                    context
                ],
                tags=tags
            )
        else:
            note = genanki.Note(
                model=ANKI_MODEL,
                fields=[
                    c["question"],
                    c["answer"],
                    badge,
                    context
                ],
                tags=tags
            )
        deck.add_note(note)

    out_dir = Path(CONFIG.get("output_directory", PROJECT_ROOT / "Decks"))
    out_dir.mkdir(parents=True, exist_ok=True)

    if not output_filename:
        safe_title = re.sub(r'[^a-zA-Z0-9_\-]', '_', deck_title)
        output_filename = f"{safe_title}.apkg"

    out_path = out_dir / output_filename
    package = genanki.Package(deck)
    package.write_to_file(str(out_path))
    print(f"Successfully generated Anki deck: {out_path} ({len(cards)} cards)")

    # Auto-mirror to Google Drive Anki Decks folder if configured and available
    gdrive_dir = CONFIG.get("google_drive_decks_directory")
    if gdrive_dir:
        gdrive_path = Path(gdrive_dir)
        if gdrive_path.exists():
            import shutil
            dest_gdrive = gdrive_path / output_filename
            shutil.copy2(out_path, dest_gdrive)
            print(f"Synced to Google Drive: {dest_gdrive}")

    return out_path

def clean_phrase(text):
    if not text:
        return ""
    # Strip bullet symbols or numbered list prefixes without stripping drug alphanumeric names (e.g. 5-HT2A)
    t = re.sub(r'^(?:[•\*\—\–]|\s*-\s+|\d+[\.\)]\s+)+', '', text.strip())
    t = re.sub(r'^(is defined as|represents|is|refers to|means)\s+', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s+', ' ', t).strip()
    return t.rstrip(':-–— \t')

def synthesize_cards(structured_data, deck_tags=None, parser=None, domain: str = "general"):
    """
    Transforms extracted highlights into atomic recall flashcards based on
    SuperMemo's 20 Rules and ANKI_SOP Keyword-Descriptor standards:
    - Green = Definition / Foundational Mechanism
    - Yellow = Important (Concept / Takeaway / Threshold)
    - Other = Context / Nuance
    Supports subject-aware domain specialization (statistics, pharmacology, developmental psychology, etc.).
    """
    cards = []
    if deck_tags is None:
        deck_tags = []

    if parser is None and SemanticCardParser is not None:
        runtime_mgr = OllamaRuntimeManager() if OllamaRuntimeManager is not None else None
        parser = SemanticCardParser(runtime_manager=runtime_mgr)

    for item in structured_data:
        heading = item.get("heading", "General")
        full_p = item.get("full_paragraph", "")
        tags = list(deck_tags)
        if domain and domain != "general" and domain not in tags:
            tags.append(domain)
        if heading and heading != "General":
            clean_tag = re.sub(r'[^a-zA-Z0-9_]', '', heading.replace(" ", "_"))[:30]
            if clean_tag:
                tags.append(clean_tag)

        # Filter out punctuation-only highlights
        valid_highlights = [
            h for h in item.get("highlights", [])
            if h.get("category") is not None
            and re.search(r'\w', h.get("text", ""))
            and not re.match(r'^[\s\-_,;:\.\?!]*$', h.get("text", ""))
        ]

        if not valid_highlights:
            continue

        yellows = [h["text"].strip() for h in valid_highlights if h["category"] == "yellow"]
        greens = [h["text"].strip() for h in valid_highlights if h["category"] == "green"]
        others = [h["text"].strip() for h in valid_highlights if h["category"] == "other"]

        context_extra = " | ".join(others) if others else ""

        # Pattern 0: Four Principles Cloze Items
        if item.get("is_four_principles"):
            cloze_text = item.get("cloze_text", "")
            cloze_ans = item.get("answer", "")
            cards.append({
                "card_type": "cloze",
                "keyword": "Four Principles of Psychoactive Drugs",
                "descriptor": item.get("full_paragraph", ""),
                "question": f"Identify the missing principle regarding <b>Four Principles of Psychoactive Drugs</b>:<br>{cloze_text}",
                "answer": cloze_ans,
                "cloze_text": cloze_text,
                "category_badge": "badge-important",
                "context": context_extra or heading,
                "tags": list(dict.fromkeys(tags + ["four_principles", "core_concepts", "cloze"]))
            })
            continue

        # Pattern 0b: R Interactive Tasks
        if item.get("is_r_task"):
            q_text = item.get("question", "")
            a_text = item.get("answer", "")
            anchor_kw = item.get("keyword") or heading or "R Syntax"
            cards.append({
                "card_type": "active_recall_qa",
                "taxonomy": "r_syntax",
                "keyword": anchor_kw,
                "descriptor": item.get("descriptor", ""),
                "question": q_text,
                "answer": a_text,
                "category_badge": "badge-code",
                "context": context_extra or heading,
                "tags": list(dict.fromkeys(tags + ["statistics", "r_syntax", "programming"]))
            })
            continue

        # Pattern 1: Concept (Yellow) + Definition (Green)
        # Pair 1-to-1 by order of appearance to avoid Cartesian product explosion
        if yellows and greens:
            pairs = list(zip(yellows, greens))
            for y_term, g_def in pairs:
                clean_y = clean_phrase(y_term)
                clean_g = clean_phrase(g_def)
                if not clean_y or not clean_g:
                    continue

                # Handle interrogative student questions paired with answers
                is_y_interrogative = bool(is_interrogative_note and is_interrogative_note(clean_y))
                is_g_interrogative = bool(is_interrogative_note and is_interrogative_note(clean_g))

                if is_y_interrogative or is_g_interrogative:
                    raw_q = clean_y if is_y_interrogative else clean_g
                    raw_ans = clean_g if is_y_interrogative else clean_y

                    # Clean extra ??? or bracketed hints from question prompt if any
                    clean_q = re.sub(r'[\(\[].*?[\)\]]', '', raw_q).strip()
                    clean_q = re.sub(r'\s*\?+', '', clean_q).strip()
                    if clean_q:
                        clean_q += '?'

                    clean_ans = raw_ans[0].upper() + raw_ans[1:] if raw_ans else ""
                    if not clean_ans.endswith(('.', '!', '?')) and clean_ans:
                        clean_ans += '.'

                    anchor_topic = heading if heading and heading != "General" else "Core Principle"
                    if anchor_topic and not clean_q.lower().startswith("regarding"):
                        q_text = f"Regarding <b>{anchor_topic}</b>: {clean_q}"
                    else:
                        q_text = clean_q

                    cards.append({
                        "card_type": "active_recall_qa",
                        "keyword": anchor_topic,
                        "descriptor": clean_ans,
                        "question": q_text,
                        "answer": clean_ans,
                        "category_badge": "badge-important",
                        "context": context_extra or heading,
                        "tags": list(dict.fromkeys(tags + ["active_recall", "interrogative", "high_yield"]))
                    })
                    continue

                # Card 55 Fix: Detect action verbs, theoretical critique phrases, or neither being a concept keyword
                standalone_set = CRITIQUE_STANDALONE_WORDS if CRITIQUE_STANDALONE_WORDS else {
                    'REJECT', 'REJECTS', 'CRITICIZE', 'CRITICIZES', 'CONTRAST', 'CONTRASTS', 'CHALLENGE', 'CHALLENGES', 'DISPROVE', 'DISPROVES', 'REFUTE', 'REFUTES'
                }
                is_y_critique = bool(CRITIQUE_ACTION_REGEX and CRITIQUE_ACTION_REGEX.search(clean_y)) or clean_y.upper() in standalone_set
                is_g_critique = bool(CRITIQUE_ACTION_REGEX and CRITIQUE_ACTION_REGEX.search(clean_g)) or clean_g.upper() in standalone_set

                v_y = is_valid_concept_keyword(clean_y) if is_valid_concept_keyword else True
                v_g = is_valid_concept_keyword(clean_g) if is_valid_concept_keyword else True

                if is_y_critique or is_g_critique:
                    critique_verb = clean_y if is_y_critique else clean_g
                    substantive = clean_g if is_y_critique else clean_y
                    anchor_topic = heading if heading and heading != "General" else "Key Principle"
                    if substantive.lower().startswith(critique_verb.lower()):
                        ans_text = substantive
                    else:
                        ans_text = f"{critique_verb.capitalize()} {substantive}"
                    if not ans_text.endswith(('.', '!', '?')):
                        ans_text += '.'
                    cards.append({
                        "card_type": "active_recall_qa",
                        "keyword": anchor_topic,
                        "descriptor": ans_text,
                        "question": f"Regarding <b>{anchor_topic}</b>, what critique or theoretical counterargument is presented?",
                        "answer": ans_text,
                        "category_badge": "badge-important",
                        "context": context_extra or heading,
                        "tags": list(dict.fromkeys(tags + ["critique", "active_recall", "high_yield"]))
                    })
                    continue

                if not v_y and not v_g:
                    anchor_topic = heading if heading and heading != "General" else "Key Principle"
                    clean_d = clean_g[0].upper() + clean_g[1:] if clean_g else ""
                    if not clean_d.endswith(('.', '!', '?')):
                        clean_d += '.'
                    cards.append({
                        "card_type": "bidirectional_definition",
                        "taxonomy": "term_definition",
                        "keyword": anchor_topic,
                        "descriptor": clean_d,
                        "question": f"What is the definition of <b>{anchor_topic}</b>?",
                        "answer": clean_d,
                        "category_badge": "badge-definition",
                        "context": context_extra or heading,
                        "tags": list(dict.fromkeys(tags + ["definition", "forward"]))
                    })
                    cards.append({
                        "card_type": "bidirectional_definition",
                        "taxonomy": "term_definition",
                        "keyword": anchor_topic,
                        "descriptor": clean_d,
                        "question": f"What term is defined by:<br><i>{clean_d}</i>",
                        "answer": anchor_topic,
                        "category_badge": "badge-definition",
                        "context": context_extra or heading,
                        "tags": list(dict.fromkeys(tags + ["definition", "reverse"]))
                    })
                    continue

                # Smart Keyword-Descriptor Resolution: dynamically resolve roles & swap inverted cards
                if resolve_keyword_descriptor_pair:
                    resolved_kw, resolved_desc = resolve_keyword_descriptor_pair(
                        clean_y, clean_g, term_color="yellow", def_color="green"
                    )
                else:
                    resolved_kw, resolved_desc = clean_y, clean_g

                if not resolved_kw or not resolved_desc:
                    continue

                # Card 1: Forward (Recall: Term -> Definition)
                cards.append({
                    "card_type": "bidirectional_definition",
                    "taxonomy": "term_definition",
                    "keyword": resolved_kw,
                    "descriptor": resolved_desc,
                    "question": f"What is the definition of <b>{resolved_kw}</b>?",
                    "answer": resolved_desc,
                    "category_badge": "badge-definition",
                    "context": context_extra or heading,
                    "tags": list(dict.fromkeys(tags + ["definition", "forward"]))
                })
                # Card 2: Reverse (Recognition: Definition -> Term)
                cards.append({
                    "card_type": "bidirectional_definition",
                    "taxonomy": "term_definition",
                    "keyword": resolved_kw,
                    "descriptor": resolved_desc,
                    "question": f"What term is defined by:<br><i>{resolved_desc}</i>",
                    "answer": resolved_kw,
                    "category_badge": "badge-definition",
                    "context": context_extra or heading,
                    "tags": list(dict.fromkeys(tags + ["definition", "reverse"]))
                })

            # Surplus yellows beyond paired greens
            for y_rem in yellows[len(greens):]:
                prefix = full_p.split(y_rem)[0].strip() if y_rem in full_p else ""
                if parser:
                    generated = parser.parse_highlight(
                        y_rem,
                        highlight_color="yellow",
                        heading=heading,
                        context=context_extra,
                        paragraph_prefix=prefix,
                        domain=domain
                    )
                    for c in generated:
                        c["tags"] = list(dict.fromkeys(tags + c.get("tags", [])))
                        if context_extra and not c.get("context"):
                            c["context"] = context_extra
                        cards.append(c)
                else:
                    clean_y = clean_phrase(y_rem)
                    if "?" in clean_y or any(clean_y.lower().startswith(q) for q in ("what ", "why ", "how ", "when ", "where ", "who ", "which ")):
                        raw_q = re.sub(r'[\(\[].*?[\)\]]', '', clean_y).strip()
                        raw_q = re.sub(r'\s*\?+', '', raw_q).strip()
                        if raw_q:
                            raw_q += '?'
                        anchor = heading if heading and heading != "General" else "Core Principle"
                        ans_text = f"Key criteria and standards governing {anchor}."
                        cards.append({
                            "card_type": "active_recall_qa",
                            "keyword": anchor,
                            "descriptor": ans_text,
                            "question": f"Regarding <b>{anchor}</b>: {raw_q}",
                            "answer": ans_text,
                            "category_badge": "badge-important",
                            "context": context_extra or heading,
                            "tags": list(dict.fromkeys(tags + ["high_yield"]))
                        })
                    else:
                        cards.append({
                            "card_type": "active_recall_qa",
                            "keyword": heading,
                            "descriptor": clean_y,
                            "question": f"What is the key mechanism regarding <b>{heading}</b>?",
                            "answer": clean_y,
                            "category_badge": "badge-important",
                            "context": context_extra or heading,
                            "tags": list(dict.fromkeys(tags + ["high_yield"]))
                        })

            # Surplus greens beyond paired yellows
            for g_rem in greens[len(yellows):]:
                prefix = full_p.split(g_rem)[0].strip() if g_rem in full_p else ""
                if parser:
                    generated = parser.parse_highlight(
                        g_rem,
                        highlight_color="green",
                        heading=heading,
                        context=context_extra,
                        paragraph_prefix=prefix,
                        domain=domain
                    )
                    for c in generated:
                        c["tags"] = list(dict.fromkeys(tags + c.get("tags", [])))
                        if context_extra and not c.get("context"):
                            c["context"] = context_extra
                        cards.append(c)
                else:
                    clean_g = clean_phrase(g_rem)
                    cards.append({
                        "card_type": "active_recall_qa",
                        "keyword": heading,
                        "descriptor": clean_g,
                        "question": f"What is the primary role of <b>{heading}</b>?",
                        "answer": clean_g,
                        "category_badge": "badge-definition",
                        "context": context_extra or heading,
                        "tags": list(dict.fromkeys(tags + ["definition"]))
                    })

        # Pattern 2: Standalone Green (Definitions / mechanisms)
        elif greens and not yellows:
            for g_def in greens:
                prefix = full_p.split(g_def)[0].strip() if g_def in full_p else ""
                if parser:
                    generated = parser.parse_highlight(
                        g_def,
                        highlight_color="green",
                        heading=heading,
                        context=context_extra,
                        paragraph_prefix=prefix,
                        domain=domain
                    )
                    for c in generated:
                        c["tags"] = list(dict.fromkeys(tags + c.get("tags", [])))
                        if context_extra and not c.get("context"):
                            c["context"] = context_extra
                        cards.append(c)
                else:
                    clean_g = clean_phrase(g_def)
                    subject = None
                    if prefix:
                        subject_match = re.search(r'([A-Z][a-zA-Z0-9\s\(\)-]{2,40})(?:\s+is|\s+represents|\s+refers to|:)', prefix)
                        if subject_match:
                            candidate_s = subject_match.group(1).strip()
                            if is_valid_concept_keyword and is_valid_concept_keyword(candidate_s):
                                subject = candidate_s
                        else:
                            clean_pref = prefix.strip(':-., ')
                            if len(clean_pref) > 3:
                                candidate_s = clean_pref[-40:].strip()
                                if is_valid_concept_keyword and is_valid_concept_keyword(candidate_s):
                                    subject = candidate_s

                    # Apply DEFINITIONAL_FRAMING_REGEX bypass (Card 138 fix)
                    is_framing = bool(DEFINITIONAL_FRAMING_REGEX and DEFINITIONAL_FRAMING_REGEX.match(clean_g))
                    if not subject and not is_framing:
                        internal_match = re.search(r'^([A-Z][a-zA-Z0-9\s\(\)\'-]{2,50})(?:\s+is|\s+are|\s+focuses on|\s+represents|\s+refers to|\s+means|\s+involves|:)\s+(.*)', clean_g, re.IGNORECASE)
                        if internal_match:
                            candidate_s = internal_match.group(1).strip()
                            if is_valid_concept_keyword and is_valid_concept_keyword(candidate_s):
                                subject = candidate_s
                                clean_g = internal_match.group(2).strip()

                    if not subject:
                        if heading and heading != "General" and not heading.lower().startswith("four principles"):
                            subject = heading
                        else:
                            subject = "Key Principle"

                    if subject and clean_g and clean_g.strip():
                        cards.append({
                            "card_type": "bidirectional_definition",
                            "taxonomy": "term_definition",
                            "keyword": subject,
                            "descriptor": clean_g,
                            "question": f"What is the definition of <b>{subject}</b>?",
                            "answer": clean_g,
                            "category_badge": "badge-definition",
                            "context": context_extra or heading,
                            "tags": list(dict.fromkeys(tags + ["definition", "forward"]))
                        })
                        cards.append({
                            "card_type": "bidirectional_definition",
                            "taxonomy": "term_definition",
                            "keyword": subject,
                            "descriptor": clean_g,
                            "question": f"What term is defined by:<br><i>{clean_g}</i>",
                            "answer": subject,
                            "category_badge": "badge-definition",
                            "context": context_extra or heading,
                            "tags": list(dict.fromkeys(tags + ["definition", "reverse"]))
                        })

        # Pattern 3: Standalone Yellow (Important finding, mechanism, threshold)
        elif yellows and not greens:
            for y_fact in yellows:
                prefix = full_p.split(y_fact)[0].strip() if y_fact in full_p else ""
                if parser:
                    generated = parser.parse_highlight(
                        y_fact,
                        highlight_color="yellow",
                        heading=heading,
                        context=context_extra,
                        paragraph_prefix=prefix,
                        domain=domain
                    )
                    for c in generated:
                        c["tags"] = list(dict.fromkeys(tags + c.get("tags", [])))
                        if context_extra and not c.get("context"):
                            c["context"] = context_extra
                        cards.append(c)
                else:
                    clean_y = clean_phrase(y_fact)
                    if "?" in clean_y or any(clean_y.lower().startswith(q) for q in ("what ", "why ", "how ", "when ", "where ", "who ", "which ")):
                        raw_q = re.sub(r'[\(\[].*?[\)\]]', '', clean_y).strip()
                        raw_q = re.sub(r'\s*\?+', '', raw_q).strip()
                        if raw_q:
                            raw_q += '?'
                        anchor = heading if heading and heading != "General" else "Core Principle"
                        ans_text = f"Key criteria and standards governing {anchor}."
                        cards.append({
                            "card_type": "active_recall_qa",
                            "keyword": anchor,
                            "descriptor": ans_text,
                            "question": f"Regarding <b>{anchor}</b>: {raw_q}",
                            "answer": ans_text,
                            "category_badge": "badge-important",
                            "context": context_extra or heading,
                            "tags": list(dict.fromkeys(tags + ["high_yield"]))
                        })
                    else:
                        cards.append({
                            "card_type": "active_recall_qa",
                            "keyword": heading,
                            "descriptor": clean_y,
                            "question": f"What is the key mechanism regarding <b>{heading}</b>?",
                            "answer": clean_y,
                            "category_badge": "badge-important",
                            "context": context_extra or heading,
                            "tags": list(dict.fromkeys(tags + ["high_yield"]))
                        })

        # Pattern 4: Other highlights (Contextual / Secondary)
        elif others:
            for o_fact in others:
                prefix = full_p.split(o_fact)[0].strip() if o_fact in full_p else ""
                if parser:
                    generated = parser.parse_highlight(
                        o_fact,
                        highlight_color="other",
                        heading=heading,
                        context=context_extra,
                        paragraph_prefix=prefix,
                        domain=domain
                    )
                    for c in generated:
                        c["tags"] = list(dict.fromkeys(tags + c.get("tags", [])))
                        cards.append(c)

    # Filter, validate, annotate cognitive taxonomies, and deduplicate
    validated_cards = []
    for c in cards:
        if is_valid_card is not None:
            valid, reason = is_valid_card(c)
            if not valid:
                continue
        elif validate_card is not None:
            valid, reason = validate_card(c)
            if not valid:
                continue
        if classify_cognitive_taxonomy is not None and "taxonomy" not in c:
            kw = c.get("keyword", "")
            desc = c.get("descriptor", "")
            c["taxonomy"] = classify_cognitive_taxonomy(kw, desc, context=c.get("context", ""), domain=domain)
        validated_cards.append(c)

    if remove_duplicate_cards is not None:
        return remove_duplicate_cards(validated_cards)
    return validated_cards

def resolve_deck_naming(
    docx_path,
    explicit_class=None,
    explicit_chapter=None,
    first_heading=None,
    doc_title=None,
    heading_hierarchy=None
):
    """
    Resolves the exact deck name according to the user specification:
    CLASS(with course name):CHAPTER
    
    Extracts course code and name from Google Doc title, heading hierarchy, folder paths, filename, or config lookups.
    """
    source_path_or_id = docx_path
    known_courses = CONFIG.get("courses", {})
    course_regex = re.compile(r'([A-Z]{2,4}\s*\d{4}[A-Za-z]?)', re.IGNORECASE)

    course_code = None
    course_name = None
    chapter_name = explicit_chapter

    # 1. Check explicit class argument
    if explicit_class:
        m = course_regex.search(explicit_class)
        if m:
            course_code = re.sub(r'([A-Z]+)(\d+)', r'\1 \2', m.group(1).upper())
            rest = explicit_class[m.end():].strip(' -–—:()')
            if rest and len(rest) > 2:
                course_name = rest
        else:
            course_code = explicit_class

    # 2. Check doc_title if available (Google Docs)
    if not course_code and doc_title:
        m = course_regex.search(doc_title)
        if m:
            course_code = re.sub(r'([A-Z]+)(\d+)', r'\1 \2', m.group(1).upper())
            name_match = re.search(rf'{m.group(1)}\s*[-–—:]?\s*(.+)', doc_title, re.IGNORECASE)
            if name_match:
                raw_name = name_match.group(1).strip()
                raw_name = re.sub(r'[-–—:]?\s*(?:week|chapter|lecture|lec|module|topic)\s*\d+.*', '', raw_name, flags=re.IGNORECASE).strip()
                if raw_name and len(raw_name) > 2:
                    course_name = raw_name

    # 3. Check heading hierarchy if available
    if not course_code and heading_hierarchy:
        for h in heading_hierarchy:
            m = course_regex.search(h)
            if m:
                course_code = re.sub(r'([A-Z]+)(\d+)', r'\1 \2', m.group(1).upper())
                name_match = re.search(rf'{m.group(1)}\s*[-–—:]?\s*(.+)', h, re.IGNORECASE)
                if name_match:
                    raw_name = name_match.group(1).strip()
                    raw_name = re.sub(r'[-–—:]?\s*(?:week|chapter|lecture|lec|module|topic)\s*\d+.*', '', raw_name, flags=re.IGNORECASE).strip()
                    if raw_name and len(raw_name) > 2:
                        course_name = raw_name
                break

    # 4. Check directory hierarchy from parent upwards (if local file path)
    p = None
    is_path = False
    try:
        candidate_p = Path(str(source_path_or_id)).resolve()
        if candidate_p.exists() or str(source_path_or_id).lower().endswith(".docx"):
            p = candidate_p
            is_path = True
    except Exception:
        p = None
        is_path = False

    if not course_code and is_path and p:
        for part in reversed(p.parts[:-1]):
            m = course_regex.search(part)
            if m:
                course_code = re.sub(r'([A-Z]+)(\d+)', r'\1 \2', m.group(1).upper())
                name_match = re.search(rf'{m.group(1)}\s*[-–—:]?\s*(.+)', part, re.IGNORECASE)
                if name_match:
                    raw_name = name_match.group(1).strip()
                    raw_name = re.sub(r'\b(F|W|S|Y)\d{4}\b', '', raw_name).strip()
                    if raw_name and len(raw_name) > 2:
                        course_name = raw_name
                break

    # 5. Check filename for course code if still not found
    if not course_code and is_path and p:
        m = course_regex.search(p.stem)
        if m:
            course_code = re.sub(r'([A-Z]+)(\d+)', r'\1 \2', m.group(1).upper())

    # 6. Standardize course code and look up official title in config if missing
    if course_code:
        normalized_code = re.sub(r'\s+', ' ', course_code).upper()
        if not course_name and normalized_code in known_courses:
            course_name = known_courses[normalized_code]
        elif not course_name:
            for k, v in known_courses.items():
                if k.replace(" ", "").upper() == normalized_code.replace(" ", ""):
                    course_name = v
                    course_code = k
                    break

    if not course_code:
        course_code = "Class"
        course_name = doc_title if doc_title else "Lecture Notes"

    class_str = f"{course_code} ({course_name})" if course_name else course_code

    # 7. Resolve CHAPTER
    if not chapter_name:
        # A. Check doc_title for chapter/lecture
        if doc_title:
            ch_match = re.search(r'\b(week\s*\d+|chapter\s*\d+|lecture\s*\d+|lec\s*\d+|module\s*\d+|topic\s*\d+)\s*[-–—:]?\s*(.*)', doc_title, re.IGNORECASE)
            if ch_match:
                lead = ch_match.group(1).capitalize()
                rest = ch_match.group(2).strip().strip('-–—: ')
                chapter_name = f"{lead}: {rest}" if rest else lead

        # B. Check heading hierarchy
        if not chapter_name and heading_hierarchy:
            for h in heading_hierarchy:
                ch_match = re.search(r'\b(week\s*\d+|chapter\s*\d+|lecture\s*\d+|lec\s*\d+|module\s*\d+|topic\s*\d+)\s*[-–—:]?\s*(.*)', h, re.IGNORECASE)
                if ch_match:
                    lead = ch_match.group(1).capitalize()
                    rest = ch_match.group(2).strip().strip('-–—: ')
                    chapter_name = f"{lead}: {rest}" if rest else lead
                    break

        # C. Check parent folder and filename if local path
        if not chapter_name and is_path and p:
            parent_folder = p.parent.name
            ch_match = re.search(r'^(week\s*\d+|chapter\s*\d+|lecture\s*\d+|module\s*\d+|topic\s*\d+)\s*[-–—:]?\s*(.*)', parent_folder, re.IGNORECASE)
            if ch_match:
                lead = ch_match.group(1).capitalize()
                rest = ch_match.group(2).strip()
                chapter_name = f"{lead}: {rest}" if rest else lead
            else:
                file_match = re.search(r'^(week\s*\d+|chapter\s*\d+|lecture\s*\d+|module\s*\d+|topic\s*\d+)\s*[-–—:]?\s*(.*)', p.stem, re.IGNORECASE)
                if file_match:
                    lead = file_match.group(1).capitalize()
                    rest = file_match.group(2).strip()
                    chapter_name = f"{lead}: {rest}" if rest else lead

        # D. Check first_heading
        if not chapter_name and first_heading and not first_heading.lower().startswith("general"):
            chapter_name = first_heading

        # E. Fallback to doc_title or filename
        if not chapter_name:
            if doc_title:
                chapter_name = doc_title
            elif is_path and p:
                chapter_name = p.stem
            else:
                chapter_name = str(source_path_or_id)

    # Format: CLASS(with course name):CHAPTER
    deck_title = f"{class_str}:{chapter_name}"

    # Clean filename for Windows (Windows forbids ':' in file paths)
    safe_clean_class = re.sub(r'[^a-zA-Z0-9_\-]', '_', class_str)
    safe_clean_chapter = re.sub(r'[^a-zA-Z0-9_\-]', '_', chapter_name)
    safe_basename = f"{safe_clean_class}_{safe_clean_chapter}"
    safe_basename = re.sub(r'_+', '_', safe_basename).strip('_')
    safe_filename = f"{safe_basename}.apkg"

    return deck_title, safe_filename

def inject_via_ankiconnect(apkg_path):
    """
    Attempts to inject the generated .apkg file directly into Anki using AnkiConnect.
    Requires Anki to be open and the AnkiConnect add-on installed (port 8765).
    """
    import urllib.request
    import urllib.error

    path_obj = Path(apkg_path).resolve()
    url = "http://localhost:8765"
    payload = {
        "action": "importPackage",
        "version": 6,
        "params": {
            "path": str(path_obj)
        }
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            res = json.loads(response.read().decode("utf-8"))
            if res.get("error") is None:
                print(f"Successfully injected {path_obj.name} into Anki via AnkiConnect!")
            else:
                print(f"AnkiConnect returned an error: {res.get('error')}")
    except urllib.error.URLError:
        print("AnkiConnect is not available. Ensure Anki is open and AnkiConnect is installed to auto-inject.")
    except Exception as e:
        print(f"Failed to inject into Anki via AnkiConnect: {e}")

def process_source_and_generate(
    source: str,
    deck: Optional[str] = None,
    explicit_class: Optional[str] = None,
    explicit_chapter: Optional[str] = None,
    deck_tags: Optional[List[str]] = None,
    auto_inject: bool = True,
    domain: Optional[str] = None
) -> Tuple[Path, str, List[Dict[str, Any]]]:
    """
    Unified ingestion and generation pipeline for Google Docs (URL or ID) or local .docx.
    Extracts title, headings, and highlights, resolves deck name, detects domain,
    synthesizes cards, compiles .apkg package, and optionally injects via AnkiConnect.

    Returns:
        (out_apkg_path, deck_title, cards)
    """
    if is_google_doc_source(source):
        print(f"Extracting highlights from Google Doc: {source}")
        if extract_google_doc_structured is None:
            raise ImportError("Google Docs API client is not available. Ensure google-api-python-client is installed.")
        data, doc_title = extract_google_doc_structured(source, classify_fn=classify_color)
    elif str(source).lower().endswith((".r", ".rmd")):
        print(f"Extracting highlights from R script: {source}")
        data = extract_r_script_highlights(source)
        try:
            doc_title = Path(source).stem
        except Exception:
            doc_title = None
    else:
        print(f"Extracting highlights from: {source}")
        data = extract_document_highlights(source)
        doc_title = None

    print(f"Extracted {len(data)} highlighted sections.")

    first_heading = data[0].get("heading") if data else None
    collected_headings = []
    for item in data:
        for h in item.get("heading_hierarchy", []):
            if h and h != "General" and h not in collected_headings:
                collected_headings.append(h)
        if item.get("heading") and item["heading"] != "General" and item["heading"] not in collected_headings:
            collected_headings.append(item["heading"])
    heading_hierarchy = collected_headings if collected_headings else [item.get("heading") for item in data if item.get("heading") and item["heading"] != "General"]

    # Domain auto-detection
    detected_domain = domain or detect_course_domain(
        source=source,
        explicit_class=explicit_class,
        doc_title=doc_title,
        heading_hierarchy=heading_hierarchy,
        text_sample=[item.get("full_paragraph", "") for item in data[:5]]
    )
    print(f"Detected Course Domain: '{detected_domain.upper()}'")

    if deck:
        deck_title = deck
        safe_filename = re.sub(r'[^a-zA-Z0-9_\-]', '_', deck_title) + ".apkg"
    else:
        deck_title, safe_filename = resolve_deck_naming(
            source,
            explicit_class=explicit_class,
            explicit_chapter=explicit_chapter,
            first_heading=first_heading,
            doc_title=doc_title,
            heading_hierarchy=heading_hierarchy
        )

    print(f"\nDeck Name: '{deck_title}'")
    print(f"Output File: '{safe_filename}'")

    tags = deck_tags if deck_tags is not None else ["lecture_notes"]
    cards = synthesize_cards(data, deck_tags=tags, domain=detected_domain)
    print(f"Synthesized {len(cards)} atomic flashcards.")

    for i, c in enumerate(cards, 1):
        print(f"\n--- Card {i} [{c['category_badge']}] ---")
        print(f"Q: {c['question']}")
        print(f"A: {c['answer']}")
        if c.get('context'):
            print(f"Context: {c['context']}")

    out_apkg = create_deck_package(deck_title, cards, output_filename=safe_filename)
    print(f"\nCreated deck package at: {out_apkg}")
    
    if auto_inject:
        inject_via_ankiconnect(out_apkg)

    return out_apkg, deck_title, cards

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extract highlights and generate Anki decks named CLASS(with course name):CHAPTER")
    parser.add_argument("source", metavar="source_or_url", help="Path to local .docx file, Google Docs URL, or Document ID")
    parser.add_argument("--deck", help="Explicit deck title (overrides automatic naming)")
    parser.add_argument("--class-name", dest="explicit_class", help="Explicit class code/name (e.g., 'PSYC 3590')")
    parser.add_argument("--chapter", dest="explicit_chapter", help="Explicit chapter/lecture title")
    parser.add_argument("--domain", choices=["statistics", "pharmacology", "developmental_psychology", "professionalism", "neuroscience", "cognition", "general"], help="Explicitly specify course domain")
    parser.add_argument("--init-ollama", action="store_true", help="Auto-start Docker / Ollama container if offline")
    parser.add_argument("--no-inject", action="store_true", help="Skip auto-injection into Anki via AnkiConnect")
    args = parser.parse_args()

    if getattr(args, "init_ollama", False) and OllamaRuntimeManager is not None:
        mgr = OllamaRuntimeManager()
        if not mgr.is_service_ready():
            print("Ollama service offline. Attempting Docker auto-initialization...")
            mgr.ensure_service_ready(auto_start_docker=True)

    input_source = getattr(args, "source", None) or getattr(args, "docx_path", None)
    process_source_and_generate(
        input_source,
        deck=args.deck,
        explicit_class=args.explicit_class,
        explicit_chapter=args.explicit_chapter,
        deck_tags=["lecture_notes"],
        auto_inject=not getattr(args, "no_inject", False),
        domain=args.domain
    )


