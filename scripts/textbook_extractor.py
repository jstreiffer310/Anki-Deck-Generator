"""
Textbook PDF Discovery and Extraction Engine
---------------------------------------------
Discovers and extracts structured curricular data (chapter summaries,
glossary terms, learning objectives, and review questions) from course
textbook PDFs.

Supports both PyMuPDF (fitz) and pypdf with automated caching in
data/textbook_cache/<course_code>.json.
"""

import os
import sys
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Optional PDF parsing engines with graceful fallback
try:
    import pymupdf  # type: ignore
    HAS_PYMUPDF = True
except (ImportError, Exception):
    try:
        import fitz as pymupdf  # type: ignore
        HAS_PYMUPDF = True
    except (ImportError, Exception):
        HAS_PYMUPDF = False

try:
    import pypdf  # type: ignore
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


def get_project_root() -> Path:
    """Returns the root directory of the AnkiDeckCreator project."""
    return Path(__file__).resolve().parent.parent


def load_config(config_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Loads configuration from config.json."""
    if config_path is None:
        config_path = get_project_root() / "config.json"
    p = Path(config_path)
    if p.exists() and p.is_file():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[textbook_extractor] Warning: Failed to load config from {p}: {e}")
    return {}


def _normalize_course_code(code: str) -> str:
    """Normalizes course code for fuzzy matching (e.g. 'PSYC 2110' -> 'psyc2110')."""
    return re.sub(r'[^a-zA-Z0-9]', '', str(code)).lower()


def discover_course_textbook(
    course_code: str,
    config_path: Optional[Union[str, Path]] = None
) -> Optional[str]:
    """
    Discovers the textbook PDF for a course.
    
    1. Checks config.json under 'textbooks' mapping first.
    2. Scans classes_base_directory (e.g. 'H:\\My Drive\\Classes\\') for matching
       course folders and searches for candidate .pdf files, filtering out
       syllabi and outlines.
    
    Returns:
        Absolute path to the discovered textbook PDF, or None if not found.
    """
    if not course_code or not str(course_code).strip():
        return None
    
    clean_code = str(course_code).strip()
    norm_target = _normalize_course_code(clean_code)
    if not norm_target:
        return None
    
    config = load_config(config_path)
    textbooks_cfg = config.get("textbooks", {})
    
    # 1. Direct or normalized match in config.json
    for key, path_val in textbooks_cfg.items():
        if key.strip().lower() == clean_code.lower() or _normalize_course_code(key) == norm_target:
            p = Path(path_val)
            if p.exists() and p.is_file():
                return str(p.resolve())
            
    # Also check if any numeric code matches (e.g. "2110" in "PSYC 2110")
    num_match = re.search(r'\b(\d{3,4})\b', clean_code)
    target_num = num_match.group(1) if num_match else ""
    if target_num:
        for key, path_val in textbooks_cfg.items():
            if target_num in key:
                p = Path(path_val)
                if p.exists() and p.is_file():
                    return str(p.resolve())

    # 2. Filesystem search in classes_base_directory
    classes_dir_str = config.get("classes_base_directory", r"H:\My Drive\Classes")
    classes_dir = Path(classes_dir_str)
    if not classes_dir.exists() or not classes_dir.is_dir():
        return None

    # Search for matching course directory
    matched_dirs = []
    try:
        for entry in classes_dir.iterdir():
            if entry.is_dir():
                entry_norm = _normalize_course_code(entry.name)
                if norm_target in entry_norm:
                    matched_dirs.append(entry)
                elif target_num and target_num in entry.name:
                    matched_dirs.append(entry)
    except Exception as e:
        print(f"[textbook_extractor] Error listing classes directory: {e}")
        return None

    if not matched_dirs:
        return None

    # Exclude patterns that indicate syllabi, course outlines, assignments, rubrics
    exclude_patterns = [
        "syllabus", "outline", "schedule", "assignment", "rubric",
        "grading", "exam", "test", "slide", "handout"
    ]

    candidate_pdfs = []
    for c_dir in matched_dirs:
        try:
            for item in c_dir.iterdir():
                if item.is_file() and item.suffix.lower() == ".pdf":
                    name_lower = item.name.lower()
                    if any(pat in name_lower for pat in exclude_patterns):
                        continue
                    candidate_pdfs.append(item)
        except Exception:
            continue

    if not candidate_pdfs:
        return None

    # Prefer PDFs with explicit textbook keywords, ISBNs, or larger file size
    def _rank_pdf(p: Path) -> int:
        score = 0
        name = p.name.lower()
        if "textbook" in name:
            score += 50
        if "978" in name:  # ISBN
            score += 40
        if "anna" in name or "archive" in name:
            score += 30
        try:
            sz = p.stat().st_size
            # Textbooks are typically > 15MB
            if sz > 15 * 1024 * 1024:
                score += 25
            score += min(int(sz / (1024 * 1024)), 20)  # Up to 20 pts for size
        except Exception:
            pass
        return score

    candidate_pdfs.sort(key=_rank_pdf, reverse=True)
    return str(candidate_pdfs[0].resolve())


def _extract_psyc_2110_pymupdf(doc: Any) -> Dict[str, Any]:
    """Extracts chapter summaries and glossary terms from Tamis-LeMonda using PyMuPDF."""
    toc = doc.get_toc()
    
    # 1. Map chapter summaries
    # Format in TOC: [level, title, page_number_1_based]
    chapter_summaries: Dict[int, str] = {}
    summary_entries = [item for item in toc if 'summary' in item[1].lower()]
    for idx, item in enumerate(summary_entries, 1):
        pno = item[2] - 1  # 0-based
        if 0 <= pno < len(doc):
            text = doc[pno].get_text()
            # Clean summary text
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            summary_text = "\n".join(lines)
            chapter_summaries[idx] = summary_text

    # 2. Extract glossary from pages 2015 to 2127
    glossary: Dict[str, Dict[str, Any]] = {}
    current_ch = 1
    
    # Find glossary start page in TOC if present
    start_pno = 2014  # default index for p. 2015
    for item in toc:
        if 'glossary' in item[1].lower():
            start_pno = item[2] - 1
            break
            
    end_pno = min(start_pno + 115, len(doc))
    
    for pno in range(start_pno, end_pno):
        page = doc[pno]
        blocks = page.get_text('dict').get('blocks', [])
        for b in blocks:
            for l in b.get('lines', []):
                bold_spans = []
                regular_spans = []
                for s in l.get('spans', []):
                    t = s.get('text', '').strip()
                    if not t:
                        continue
                    font_name = s.get('font', '').lower()
                    flags = s.get('flags', 0)
                    if 'bold' in font_name or (flags & 16) or (flags & 4 and 'georgia-bold' in font_name):
                        bold_spans.append(t)
                    else:
                        regular_spans.append(t)
                        
                if bold_spans:
                    joined_bold = ' '.join(bold_spans).strip()
                    if re.match(r'^Chapter\s+(\d+)$', joined_bold, re.IGNORECASE):
                        try:
                            current_ch = int(re.search(r'\d+', joined_bold).group())
                        except Exception:
                            pass
                    else:
                        term = joined_bold
                        defn = ' '.join(regular_spans).strip()
                        term_key = term.lower()
                        if term_key not in glossary:
                            glossary[term_key] = {
                                'term': term,
                                'definition': defn,
                                'chapter': current_ch
                            }
                elif regular_spans and glossary:
                    # Continuation of previous definition
                    last_key = list(glossary.keys())[-1]
                    glossary[last_key]['definition'] += ' ' + ' '.join(regular_spans)

    # Clean definitions
    for k, item in glossary.items():
        item['definition'] = ' '.join(item['definition'].split()).strip()

    # Organize chapters
    chapters: Dict[str, Dict[str, Any]] = {}
    for ch_num in range(1, 17):
        ch_key = str(ch_num)
        ch_terms = {
            item['term']: item['definition']
            for item in glossary.values()
            if item.get('chapter') == ch_num
        }
        chapters[ch_key] = {
            "chapter_number": ch_num,
            "chapter_title": f"Chapter {ch_num}",
            "summary": chapter_summaries.get(ch_num, ""),
            "learning_objectives": [],
            "glossary_terms": ch_terms,
            "review_questions": []
        }

    return {
        "chapters": chapters,
        "glossary": glossary
    }


def _extract_psyc_2110_pypdf(reader: Any) -> Dict[str, Any]:
    """Fallback extraction for Tamis-LeMonda using pypdf."""
    glossary: Dict[str, Dict[str, Any]] = {}
    current_ch = 1
    
    start_pno = min(2014, len(reader.pages) - 1)
    end_pno = min(start_pno + 115, len(reader.pages))
    
    for pno in range(start_pno, end_pno):
        text = reader.pages[pno].extract_text()
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for line in lines:
            if re.match(r'^Chapter\s+(\d+)$', line, re.IGNORECASE):
                try:
                    current_ch = int(re.search(r'\d+', line).group())
                except Exception:
                    pass
                continue
            
            # Match Term followed by definition
            # Format: 'term Defn begins...'
            m = re.match(r'^([a-z][a-zA-Z\s\-–\(\)\'\’]{2,40})\s+([A-Z][a-zA-Z0-9\s\-–\(\)\'\’\.,;:“”"]+)', line)
            if m:
                term = m.group(1).strip()
                defn = m.group(2).strip()
                term_key = term.lower()
                if term_key not in glossary:
                    glossary[term_key] = {
                        'term': term,
                        'definition': defn,
                        'chapter': current_ch
                    }
            elif glossary:
                last_key = list(glossary.keys())[-1]
                glossary[last_key]['definition'] += ' ' + line

    for k, item in glossary.items():
        item['definition'] = ' '.join(item['definition'].split()).strip()

    chapters: Dict[str, Dict[str, Any]] = {}
    for ch_num in range(1, 17):
        ch_key = str(ch_num)
        ch_terms = {
            item['term']: item['definition']
            for item in glossary.values()
            if item.get('chapter') == ch_num
        }
        chapters[ch_key] = {
            "chapter_number": ch_num,
            "chapter_title": f"Chapter {ch_num}",
            "summary": "",
            "learning_objectives": [],
            "glossary_terms": ch_terms,
            "review_questions": []
        }

    return {
        "chapters": chapters,
        "glossary": glossary
    }


def _extract_psyc_3590_pymupdf(doc: Any) -> Dict[str, Any]:
    """Extracts chapter summaries, LOs, and review questions from Drugs, Behaviour & Society."""
    # Brief contents on page 4 (index 3)
    toc_text = doc[3].get_text() if len(doc) > 3 else ""
    matches = re.findall(r'Chapter\s+(\d+)\s*\n([^\n]+)\s*\n(\d+)', toc_text)
    
    chapter_meta = {}
    for ch_str, title, p_str in matches:
        ch_num = int(ch_str)
        printed_page = int(p_str)
        start_pno = printed_page + 17  # Offset +17 for 0-based PDF page index
        chapter_meta[ch_num] = {
            'number': ch_num,
            'title': title.strip(),
            'start_pno': start_pno
        }
        
    chapters: Dict[str, Dict[str, Any]] = {}
    glossary: Dict[str, Dict[str, Any]] = {}

    sorted_ch_nums = sorted(chapter_meta.keys())
    for idx, ch_num in enumerate(sorted_ch_nums):
        info = chapter_meta[ch_num]
        start_pno = info['start_pno']
        next_pno = chapter_meta[sorted_ch_nums[idx + 1]]['start_pno'] if idx + 1 < len(sorted_ch_nums) else min(start_pno + 35, len(doc))
        
        # 1. Learning Objectives from opener
        lo_items = []
        if 0 <= start_pno < len(doc):
            text = doc[start_pno].get_text()
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            current_lo = None
            current_lo_text = []
            for line in lines:
                m = re.match(r'^LO(\d+)$', line)
                if m:
                    if current_lo:
                        lo_items.append({'lo': current_lo, 'text': ' '.join(current_lo_text).strip()})
                    current_lo = f"LO{m.group(1)}"
                    current_lo_text = []
                elif current_lo:
                    if re.match(r'^(Section|\d+|Chapter|Review)', line):
                        lo_items.append({'lo': current_lo, 'text': ' '.join(current_lo_text).strip()})
                        current_lo = None
                        current_lo_text = []
                    else:
                        current_lo_text.append(line)
            if current_lo and current_lo_text:
                lo_items.append({'lo': current_lo, 'text': ' '.join(current_lo_text).strip()})

        # 2. Summary bullets and Review Questions from ending pages
        summary_bullets = []
        review_questions = []
        
        for p in range(start_pno, next_pno):
            if p >= len(doc):
                break
            page_text = doc[p].get_text()
            if 'summary' in page_text.lower() and ('••••' in page_text or '•' in page_text):
                lines = [l.strip() for l in page_text.splitlines() if l.strip()]
                for line in lines:
                    if line.startswith('•') and not line.startswith('••••'):
                        clean_bullet = line.lstrip('•').strip()
                        if clean_bullet:
                            summary_bullets.append(clean_bullet)
                            
            if 'review questions' in page_text.lower():
                rq_idx = page_text.lower().find('review questions')
                rq_text = page_text[rq_idx:]
                q_matches = re.findall(r'(\d+)\.\s*\n([^\n]+(?:\n[^\n\d]+)*)', rq_text)
                for q_num, q_body in q_matches:
                    clean_q = ' '.join(q_body.split()).strip()
                    if clean_q:
                        review_questions.append(f"{q_num}. {clean_q}")

        summary_text = "\n".join(summary_bullets)
        chapters[str(ch_num)] = {
            "chapter_number": ch_num,
            "chapter_title": info['title'],
            "summary": summary_text,
            "learning_objectives": lo_items,
            "glossary_terms": {},
            "review_questions": review_questions
        }

    return {
        "chapters": chapters,
        "glossary": glossary
    }


def _extract_psyc_3590_pypdf(reader: Any) -> Dict[str, Any]:
    """Fallback extraction for PSYC 3590 using pypdf."""
    toc_text = reader.pages[3].extract_text() if len(reader.pages) > 3 else ""
    matches = re.findall(r'Chapter\s+(\d+)\s+([^\n\d]+)\s+(\d+)', toc_text)
    
    chapter_meta = {}
    for ch_str, title, p_str in matches:
        ch_num = int(ch_str)
        printed_page = int(p_str)
        start_pno = printed_page + 17
        chapter_meta[ch_num] = {
            'number': ch_num,
            'title': title.strip(),
            'start_pno': start_pno
        }

    chapters: Dict[str, Dict[str, Any]] = {}
    for ch_num, info in chapter_meta.items():
        start_pno = info['start_pno']
        lo_items = []
        if 0 <= start_pno < len(reader.pages):
            text = reader.pages[start_pno].extract_text()
            matches_lo = re.findall(r'(LO\d+)\s+([^\n]+)', text)
            for lo_tag, lo_text in matches_lo:
                lo_items.append({'lo': lo_tag, 'text': lo_text.strip()})

        chapters[str(ch_num)] = {
            "chapter_number": ch_num,
            "chapter_title": info['title'],
            "summary": "",
            "learning_objectives": lo_items,
            "glossary_terms": {},
            "review_questions": []
        }

    return {
        "chapters": chapters,
        "glossary": {}
    }


def _extract_generic_textbook(pdf_path: str, course_code: str, engine: str = "pymupdf") -> Dict[str, Any]:
    """Generic fallback textbook extractor for other courses."""
    chapters: Dict[str, Dict[str, Any]] = {}
    glossary: Dict[str, Dict[str, Any]] = {}

    if engine == "pymupdf" and HAS_PYMUPDF:
        doc = pymupdf.open(pdf_path)
        toc = doc.get_toc()
        ch_idx = 1
        for item in toc:
            lvl, title, pno = item[0], item[1], item[2]
            if re.search(r'\b(?:chapter|ch\.|unit|module)\s*(\d+)', title, re.IGNORECASE):
                chapters[str(ch_idx)] = {
                    "chapter_number": ch_idx,
                    "chapter_title": title.strip(),
                    "summary": "",
                    "learning_objectives": [],
                    "glossary_terms": {},
                    "review_questions": []
                }
                ch_idx += 1
    elif HAS_PYPDF:
        reader = pypdf.PdfReader(pdf_path)
        # Create minimal chapter stub
        for i in range(1, 10):
            chapters[str(i)] = {
                "chapter_number": i,
                "chapter_title": f"Chapter {i}",
                "summary": "",
                "learning_objectives": [],
                "glossary_terms": {},
                "review_questions": []
            }

    return {
        "chapters": chapters,
        "glossary": glossary
    }


def get_cache_path(course_code: str, cache_dir: Optional[Union[str, Path]] = None) -> Path:
    """Returns the standardized cache file path for a course textbook."""
    if cache_dir is None:
        cache_dir = get_project_root() / "data" / "textbook_cache"
    p = Path(cache_dir)
    slug = re.sub(r'[^a-zA-Z0-9_]', '_', course_code).strip('_')
    return p / f"{slug}.json"


def extract_textbook_data(
    course_code: str,
    force_refresh: bool = False,
    pdf_path: Optional[str] = None,
    cache_dir: Optional[Union[str, Path]] = None,
    engine: Optional[str] = None
) -> Dict[str, Any]:
    """
    Extracts structured textbook data for a course, caching the result as JSON.
    
    Args:
        course_code: Course code string (e.g. 'PSYC 2110', 'PSYC 3590')
        force_refresh: If True, ignores existing cache and re-extracts from PDF
        pdf_path: Optional explicit path to textbook PDF
        cache_dir: Optional override for cache directory (default data/textbook_cache)
        engine: 'pymupdf' or 'pypdf' (defaults to best available)
        
    Returns:
        Structured dictionary:
        {
            "course_code": str,
            "textbook_path": str,
            "extractor": str,
            "extracted_at": str,
            "chapters": Dict[str, Dict],
            "glossary": Dict[str, Dict]
        }
    """
    cache_file = get_cache_path(course_code, cache_dir=cache_dir)
    
    # 1. Return cached data if available and refresh not forced
    if not force_refresh and cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[textbook_extractor] Warning: Failed to load cache from {cache_file}: {e}")

    # 2. Discover textbook PDF if path not provided
    target_pdf = pdf_path or discover_course_textbook(course_code)
    if not target_pdf or not Path(target_pdf).exists():
        raise FileNotFoundError(f"No textbook PDF found for course: {course_code}")

    target_pdf_path = str(Path(target_pdf).resolve())

    # 3. Choose extraction engine
    chosen_engine = engine or ("pymupdf" if HAS_PYMUPDF else ("pypdf" if HAS_PYPDF else None))
    if not chosen_engine:
        raise RuntimeError("No PDF extraction library available. Please install pymupdf or pypdf.")

    extracted_data = {}
    norm_code = _normalize_course_code(course_code)

    # 4. Route extraction based on course code
    if "2110" in norm_code:
        if chosen_engine == "pymupdf" and HAS_PYMUPDF:
            doc = pymupdf.open(target_pdf_path)
            extracted_data = _extract_psyc_2110_pymupdf(doc)
        elif HAS_PYPDF:
            reader = pypdf.PdfReader(target_pdf_path)
            extracted_data = _extract_psyc_2110_pypdf(reader)
    elif "3590" in norm_code:
        if chosen_engine == "pymupdf" and HAS_PYMUPDF:
            doc = pymupdf.open(target_pdf_path)
            extracted_data = _extract_psyc_3590_pymupdf(doc)
        elif HAS_PYPDF:
            reader = pypdf.PdfReader(target_pdf_path)
            extracted_data = _extract_psyc_3590_pypdf(reader)
    else:
        extracted_data = _extract_generic_textbook(target_pdf_path, course_code, engine=chosen_engine)

    result = {
        "course_code": course_code,
        "textbook_path": target_pdf_path,
        "extractor": chosen_engine,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "chapters": extracted_data.get("chapters", {}),
        "glossary": extracted_data.get("glossary", {})
    }

    # 5. Save to cache
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"[textbook_extractor] Cached textbook data to {cache_file}")
    except Exception as e:
        print(f"[textbook_extractor] Warning: Failed to write cache to {cache_file}: {e}")

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Discover and extract course textbook content.")
    parser.add_argument("--course", help="Course code (e.g. 'PSYC 2110', 'PSYC 3590')")
    parser.add_argument("--discover", action="store_true", help="Only discover and print textbook path")
    parser.add_argument("--refresh", action="store_true", help="Force refresh cache")
    args = parser.parse_args()

    course = args.course or "PSYC 2110"
    if args.discover:
        path = discover_course_textbook(course)
        print(f"Discovered textbook for {course}: {path}")
    else:
        print(f"Extracting textbook data for {course}...")
        t0 = time.time()
        res = extract_textbook_data(course, force_refresh=args.refresh)
        elapsed = time.time() - t0
        print(f"Extraction complete in {elapsed:.2f}s")
        print(f"Chapters found: {len(res.get('chapters', {}))}")
        print(f"Glossary terms found: {len(res.get('glossary', {}))}")
        if "developmental niche" in res.get("glossary", {}):
            print("Found 'developmental niche':", res["glossary"]["developmental niche"])
