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
    from scripts.semantic_parser import SemanticCardParser, clean_phrase as semantic_clean_phrase, is_valid_card
except ImportError:
    try:
        from semantic_parser import SemanticCardParser, clean_phrase as semantic_clean_phrase, is_valid_card
    except ImportError:
        SemanticCardParser = None
        semantic_clean_phrase = None
        is_valid_card = None

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

    return structured_data

def extract_highlights(source, classify_fn=None):
    """
    Unified extractor accepting a local .docx file path, Google Docs URL, or Document ID.
    
    Returns:
        tuple: (structured_data: list[dict], doc_title: Optional[str])
    """
    classify = classify_fn or classify_color
    if is_google_doc_source(source):
        if extract_google_doc_structured is None:
            raise ImportError("Google Docs API client is not available. Ensure google-api-python-client is installed.")
        return extract_google_doc_structured(source, classify_fn=classify)
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
    color: #0d652d; /* WCAG AAA contrast against background */
    border-color: #0d652d;
}
.badge-important {
    background-color: #fff8e1; /* Accessible light yellow */
    color: #8f4f00; /* WCAG AAA contrast against background */
    border-color: #8f4f00;
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
    background-color: #0d652d;
    color: #e6f4ea;
    border-color: #e6f4ea;
}
.nightMode .badge-important {
    background-color: #8f4f00;
    color: #fff8e1;
    border-color: #fff8e1;
}
.nightMode .context-box {
    background-color: #1f2937;
    border-left-color: #9ca3af;
    color: #f9fafb;
}
.nightMode hr#answer {
    border-top-color: #374151;
}
"""

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
            'qfmt': '''
                {{#CategoryBadge}}<div class="badge {{CategoryBadge}}">{{CategoryBadge}}</div>{{/CategoryBadge}}
                <div class="question">{{Question}}</div>
            ''',
            'afmt': '''
                {{FrontSide}}
                <hr id="answer">
                <div class="answer">{{Answer}}</div>
                {{#Context}}<div class="context-box">{{Context}}</div>{{/Context}}
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
            'qfmt': '''
                {{#CategoryBadge}}<div class="badge {{CategoryBadge}}">{{CategoryBadge}}</div>{{/CategoryBadge}}
                <div class="question">{{cloze:Text}}</div>
            ''',
            'afmt': '''
                {{#CategoryBadge}}<div class="badge {{CategoryBadge}}">{{CategoryBadge}}</div>{{/CategoryBadge}}
                <div class="question">{{cloze:Text}}</div>
                <hr id="answer">
                {{#Extra}}<div class="answer">{{Extra}}</div>{{/Extra}}
                {{#Context}}<div class="context-box">{{Context}}</div>{{/Context}}
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

def synthesize_cards(structured_data, deck_tags=None, parser=None):
    """
    Transforms extracted highlights into atomic recall flashcards based on
    SuperMemo's 20 Rules and ANKI_SOP Keyword-Descriptor standards:
    - Green = Definition / Foundational Mechanism
    - Yellow = Important (Concept / Takeaway / Threshold)
    - Other = Context / Nuance
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

        # Pattern 1: Concept (Yellow) + Definition (Green)
        # Pair 1-to-1 by order of appearance to avoid Cartesian product explosion
        if yellows and greens:
            pairs = list(zip(yellows, greens))
            for y_term, g_def in pairs:
                clean_y = clean_phrase(y_term)
                clean_g = clean_phrase(g_def)
                # Card 1: Forward (Recall: Term -> Definition)
                cards.append({
                    "card_type": "bidirectional_definition",
                    "keyword": clean_y,
                    "descriptor": clean_g,
                    "question": f"What is the definition of <b>{clean_y}</b>?",
                    "answer": clean_g,
                    "category_badge": "badge-definition",
                    "context": context_extra or heading,
                    "tags": list(dict.fromkeys(tags + ["definition", "forward"]))
                })
                # Card 2: Reverse (Recognition: Definition -> Term)
                cards.append({
                    "card_type": "bidirectional_definition",
                    "keyword": clean_y,
                    "descriptor": clean_g,
                    "question": f"What term is defined by:<br><i>{clean_g}</i>",
                    "answer": clean_y,
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
                        paragraph_prefix=prefix
                    )
                    for c in generated:
                        c["tags"] = list(dict.fromkeys(tags + c.get("tags", [])))
                        if context_extra and not c.get("context"):
                            c["context"] = context_extra
                        cards.append(c)
                else:
                    term = clean_phrase(y_rem)
                    cards.append({
                        "card_type": "active_recall_qa",
                        "keyword": term,
                        "descriptor": term,
                        "question": f"What is the key mechanism regarding <b>{term}</b>?",
                        "answer": term,
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
                        paragraph_prefix=prefix
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
                        paragraph_prefix=prefix
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
                            subject = subject_match.group(1).strip()
                        else:
                            clean_pref = prefix.strip(':-., ')
                            if len(clean_pref) > 3:
                                subject = clean_pref[-40:].strip()
                    if not subject:
                        internal_match = re.search(r'^([A-Z][a-zA-Z0-9\s\(\)\'-]{2,50})(?:\s+is|\s+are|\s+focuses on|\s+represents|\s+refers to|\s+means|\s+involves|:)\s+(.*)', clean_g, re.IGNORECASE)
                        if internal_match:
                            subject = internal_match.group(1).strip()
                            clean_g = internal_match.group(2).strip()
                    if not subject:
                        subject = heading if heading and heading != "General" else "Key Principle"

                    cards.append({
                        "card_type": "bidirectional_definition",
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
                        paragraph_prefix=prefix
                    )
                    for c in generated:
                        c["tags"] = list(dict.fromkeys(tags + c.get("tags", [])))
                        if context_extra and not c.get("context"):
                            c["context"] = context_extra
                        cards.append(c)
                else:
                    clean_y = clean_phrase(y_fact)
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
                        paragraph_prefix=prefix
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
            c["taxonomy"] = classify_cognitive_taxonomy(kw, desc, context=c.get("context", ""))
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
    auto_inject: bool = True
) -> Tuple[Path, str, List[Dict[str, Any]]]:
    """
    Unified ingestion and generation pipeline for Google Docs (URL or ID) or local .docx.
    Extracts title, headings, and highlights, resolves deck name, synthesizes cards,
    compiles .apkg package, and optionally injects via AnkiConnect.

    Returns:
        (out_apkg_path, deck_title, cards)
    """
    if is_google_doc_source(source):
        print(f"Extracting highlights from Google Doc: {source}")
        if extract_google_doc_structured is None:
            raise ImportError("Google Docs API client is not available. Ensure google-api-python-client is installed.")
        data, doc_title = extract_google_doc_structured(source, classify_fn=classify_color)
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
    cards = synthesize_cards(data, deck_tags=tags)
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
        auto_inject=not getattr(args, "no_inject", False)
    )


