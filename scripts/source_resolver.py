"""
scripts/source_resolver.py — Source Document & Google Doc Link Auto-Resolution Engine

Provides zero-friction auto-fill and auto-resolution for:
1. Course codes (e.g., 'PSYC 3590', 'PSYC 3000', 'PSYC 2110', 'PSYC 3031', '3590') -> Primary lecture notes (.docx, .r) or Google Doc URL
2. Virtual Google Drive files (.gdoc) -> Resolves to real Google Docs URL / ID via DriveFS SQLite or config.json
3. Local document paths (.docx, .r, .rmd) -> Validates existence, scores primary vs syllabus
4. Web UI dynamic endpoints -> Auto-populates active documents, links, and preferred ingestion mode
"""

import sys
import os
import re
import json
import glob
import sqlite3
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Union

logger = logging.getLogger("SourceResolver")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"

COURSE_CODE_REGEX = re.compile(r'([A-Z]{2,4})\s*(\d{4}[A-Za-z]?)', re.IGNORECASE)
GDOC_URL_REGEX = re.compile(r'docs\.google\.com/document/(?:u/\d+/)?d/([a-zA-Z0-9_-]{25,60})')
BARE_GDOC_ID_REGEX = re.compile(r'^[a-zA-Z0-9_-]{25,60}$')

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
    return {}

def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving config: {e}")

def normalize_course_code(input_str: str) -> Optional[str]:
    """
    Normalizes strings like 'psyc3590', 'PSYC 3590A', 'psyc 3590' into 'PSYC 3590'.
    Also resolves 4-digit numbers like '3590' if they match known courses.
    """
    if not input_str:
        return None
    s = input_str.strip()

    # Don't treat a file path or URL as a simple course code if it has path separators
    if "/" in s or "\\" in s or "http" in s:
        # Check if the folder or filename has a course code
        m = COURSE_CODE_REGEX.search(Path(s).name) or COURSE_CODE_REGEX.search(Path(s).parent.name)
        if m:
            dept = m.group(1).upper()
            num = m.group(2).upper()
            return f"{dept} {num}"
        return None

    config = load_config()
    known_courses = config.get("courses", {})

    m = COURSE_CODE_REGEX.search(s)
    if m:
        dept = m.group(1).upper()
        num = m.group(2).upper()
        code = f"{dept} {num}"
        if code in known_courses:
            return code
        # If trailing single letter (e.g. 3000A) and base code is in known_courses, strip section suffix
        if len(num) == 5 and re.match(r'^\d{4}[A-Z]$', num):
            base_code = f"{dept} {num[:-1]}"
            if base_code in known_courses:
                return base_code
        return code

    # Check 4-digit code e.g. '3590'
    m_num = re.match(r'^\d{4}[A-Za-z]?$', s)
    if m_num:
        target_num = m_num.group(0).upper()
        for code in known_courses:
            if target_num in code:
                return code

    return None

def lookup_drivefs_doc_id(stem_or_title: str, parent_folder_hint: Optional[str] = None) -> Optional[str]:
    """
    Queries local Google Drive for Desktop (DriveFS) SQLite databases (read-only)
    to resolve Google Doc IDs by file stem/title and parent folder name.
    """
    clean_stem = Path(stem_or_title).stem.strip() if stem_or_title.endswith(".gdoc") else stem_or_title.strip()
    db_patterns = glob.glob(r"C:\Users\*\AppData\Local\Google\DriveFS\*\mirror_metadata_sqlite.db")
    
    for db_path in db_patterns:
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
            cur = conn.cursor()

            # If parent folder hint is provided, join with stable_parents
            if parent_folder_hint:
                clean_parent = parent_folder_hint.strip()
                cur.execute("""
                    SELECT c.id, c.local_title, p.local_title
                    FROM items c
                    JOIN stable_parents sp ON c.stable_id = sp.item_stable_id
                    JOIN items p ON sp.parent_stable_id = p.stable_id
                    WHERE c.mime_type = 'application/vnd.google-apps.document'
                    AND (TRIM(c.local_title) = ? OR c.local_title = ? OR c.local_title LIKE ?)
                    AND (TRIM(p.local_title) = ? OR p.local_title LIKE ?)
                    LIMIT 1
                """, (clean_stem, clean_stem, f"%{clean_stem}%", clean_parent, f"%{clean_parent}%"))
                row = cur.fetchone()
                if row:
                    conn.close()
                    return row[0]

            # Fallback: direct match on local_title
            cur.execute("""
                SELECT id, local_title FROM items
                WHERE mime_type = 'application/vnd.google-apps.document'
                AND (TRIM(local_title) = ? OR local_title = ?)
                LIMIT 1
            """, (clean_stem, clean_stem))
            row = cur.fetchone()
            conn.close()
            if row:
                return row[0]

        except Exception as e:
            logger.debug(f"DriveFS query exception on {db_path}: {e}")

    return None

def score_document(file_path: Union[str, Path], ext: str, size_bytes: int = 0) -> int:
    """
    Scores document importance: higher score = better candidate for primary lecture notes.
    Syllabi, rubrics, assignments, and supplemental subfolders are penalized.
    """
    p = Path(file_path)
    nl = p.name.lower()
    score = 0

    # Penalize subfolders like assignments, rubrics, supplemental
    parts_lower = [part.lower() for part in p.parts]
    if any(k in parts_lower for k in ["assignments", "assignment", "rubric", "rubrics", "exercises", "supplimental resources", "resources"]):
        return -100

    # Strong disqualifiers / syllabus / admin forms penalty
    if any(k in nl for k in [
        "syllabus", "course outline", "schedule", "rubric", "assignment",
        "activity", "outline", "information sheet", "checklist", "expectation",
        "expectations", "handbook", "template", "agreement", "contract",
        "guidelines", "guide", "form", "evaluation"
    ]):
        return -100

    # Notes identifiers
    if "notes" in nl:
        score += 50
    if "lecture" in nl:
        score += 30
    if "textbook" in nl:
        score += 20
    if "week" in nl:
        score += 15

    # File type preferences
    if ext == ".docx":
        score += 25
    elif ext in (".r", ".rmd"):
        score += 20
    elif ext == ".gdoc":
        score += 10

    # Size bonus for content-rich files (up to +15)
    if size_bytes > 0:
        score += min(15, int(size_bytes / 50000))

    return score

def find_primary_document(folder_path: Path) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Finds (primary_local_file, primary_gdoc_file) in a course folder.
    primary_local_file: .docx, .r, .rmd with highest score.
    primary_gdoc_file: .gdoc with highest score.
    """
    best_local = None
    best_local_score = -999
    best_gdoc = None
    best_gdoc_score = -999

    try:
        for p in folder_path.rglob("*"):
            if not p.is_file() or p.name.startswith("~$") or p.name.startswith("."):
                continue
            ext = p.suffix.lower()
            if ext in (".docx", ".r", ".rmd"):
                size = p.stat().st_size
                s = score_document(p, ext, size)
                if s > best_local_score:
                    best_local_score = s
                    best_local = p
            elif ext == ".gdoc":
                s = score_document(p, ext, 0)
                if s > best_gdoc_score:
                    best_gdoc_score = s
                    best_gdoc = p
    except Exception as e:
        logger.error(f"Error scanning folder {folder_path}: {e}")

    # If the best local file scored <= 0 (e.g. only assignment / syllabus found), don't treat it as primary notes
    if best_local_score <= 0:
        best_local = None

    return best_local, best_gdoc

def get_course_registry(classes_base_dir: Optional[str] = None, config: Optional[dict] = None) -> Dict[str, Dict[str, Any]]:
    """
    Builds a rich course registry containing all classes discovered in 'Classes'
    with auto-detected primary documents, Google Doc links, and preferred modes.
    """
    cfg = config or load_config()
    classes_dir_str = classes_base_dir or cfg.get("classes_base_directory", r"H:\My Drive\Classes")
    classes_path = Path(classes_dir_str)
    
    known_courses = cfg.get("courses", {})
    recent_doc_links = cfg.get("recent_doc_links", {})

    registry = {}
    if not classes_path.exists():
        return registry

    for p in sorted(classes_path.iterdir()):
        if not p.is_dir() or p.name.startswith("."):
            continue

        folder_name = p.name
        code_match = COURSE_CODE_REGEX.search(folder_name)
        if code_match:
            course_code = f"{code_match.group(1).upper()} {code_match.group(2).upper()}"
            raw_title = folder_name[code_match.end():].strip(' -–—:()')
            raw_title = re.sub(r'^(?:F|W|S|Y)\s+', '', raw_title).strip()
            course_title = raw_title if len(raw_title) > 2 else known_courses.get(course_code, folder_name)
        else:
            course_code = folder_name.split()[0].upper()
            course_title = folder_name

        # Find primary documents
        primary_local, primary_gdoc = find_primary_document(p)

        # Resolve Google Doc URL
        gdoc_url = recent_doc_links.get(course_code)
        if not gdoc_url and primary_gdoc:
            doc_id = lookup_drivefs_doc_id(primary_gdoc.name, folder_name)
            if doc_id:
                gdoc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
                # Cache newly discovered link in config
                recent_doc_links[course_code] = gdoc_url
                cfg["recent_doc_links"] = recent_doc_links
                save_config(cfg)

        # Collect all documents
        documents = []
        try:
            for item in p.rglob("*"):
                if not item.is_file() or item.name.startswith("~$") or item.name.startswith("."):
                    continue
                ext = item.suffix.lower()
                if ext in (".docx", ".gdoc", ".r", ".rmd"):
                    name_lower = item.name.lower()
                    is_syllabus = any(w in name_lower for w in ["syllabus", "course outline", "schedule", "rubric", "activity", "assignment"])
                    documents.append({
                        "name": item.name,
                        "path": str(item),
                        "rel_path": str(item.relative_to(p)),
                        "ext": ext,
                        "is_syllabus": is_syllabus,
                        "size_bytes": item.stat().st_size if ext in (".docx", ".r", ".rmd") else 0
                    })
        except Exception:
            pass

        # Preferred ingestion mode:
        # If there's a valid primary local .docx or .r, prefer "file".
        # If only a .gdoc or Google Doc link exists (e.g. PSYC 3000), prefer "gdoc".
        if primary_local and score_document(primary_local, primary_local.suffix.lower()) > 0:
            preferred_mode = "file"
        elif gdoc_url:
            preferred_mode = "gdoc"
        else:
            preferred_mode = "file" if primary_local else "gdoc"

        registry[course_code] = {
            "course_code": course_code,
            "course_title": course_title,
            "folder_name": folder_name,
            "folder_path": str(p),
            "primary_doc_path": str(primary_local) if primary_local else None,
            "primary_doc_name": primary_local.name if primary_local else None,
            "primary_gdoc_path": str(primary_gdoc) if primary_gdoc else None,
            "saved_gdoc_url": gdoc_url or "",
            "preferred_mode": preferred_mode,
            "documents": sorted(documents, key=lambda x: (x["is_syllabus"], not "notes" in x["name"].lower(), x["name"]))
        }

    return registry

def resolve_source_document(
    source: Optional[str] = None,
    course_hint: Optional[str] = None,
    config: Optional[dict] = None
) -> Dict[str, Any]:
    r"""
    Comprehensive multi-format source resolver and auto-fill engine.

    Resolves:
    - None / Empty -> Uses course_hint to auto-fill primary document or Google Doc URL.
    - Course code (e.g., 'PSYC 3590', 'PSYC 3000', '3590') -> Auto-fills primary document or Google Doc URL.
    - .gdoc path on H:\ -> Resolves to real Google Docs URL / ID via DriveFS or config.
    - Existing .docx / .r / .rmd path -> Validates and uses.
    - Google Docs URL or Doc ID -> Normalizes and returns.

    Returns dict:
    {
        "resolved_source": str,
        "source_type": "local_docx" | "r_script" | "gdoc_url" | "gdoc_id",
        "course_code": Optional[str],
        "course_title": Optional[str],
        "primary_local_path": Optional[str],
        "gdoc_url": Optional[str],
        "preferred_mode": "file" | "gdoc",
        "auto_filled": bool,
        "resolution_reason": str
    }
    """
    cfg = config or load_config()
    registry = get_course_registry(config=cfg)

    source_str = (source or "").strip()
    norm_hint = normalize_course_code(course_hint) if course_hint else None

    # 1. Check if source is already a Google Docs URL
    m_url = GDOC_URL_REGEX.search(source_str)
    if m_url:
        doc_id = m_url.group(1)
        # Determine course from hint or doc ID
        course_code = norm_hint
        if not course_code:
            for c_code, c_data in registry.items():
                if doc_id in c_data.get("saved_gdoc_url", ""):
                    course_code = c_code
                    break
        course_info = registry.get(course_code, {}) if course_code else {}
        return {
            "resolved_source": f"https://docs.google.com/document/d/{doc_id}/edit",
            "source_type": "gdoc_url",
            "course_code": course_code or course_info.get("course_code"),
            "course_title": course_info.get("course_title"),
            "primary_local_path": course_info.get("primary_doc_path"),
            "gdoc_url": f"https://docs.google.com/document/d/{doc_id}/edit",
            "preferred_mode": "gdoc",
            "auto_filled": False,
            "resolution_reason": "Direct Google Docs URL"
        }

    # 2. Check if source is a bare Google Doc ID (25-60 chars) and NOT an existing file
    if BARE_GDOC_ID_REGEX.match(source_str):
        try:
            if not Path(source_str).exists():
                course_code = norm_hint
                if not course_code:
                    for c_code, c_data in registry.items():
                        if source_str in c_data.get("saved_gdoc_url", ""):
                            course_code = c_code
                            break
                course_info = registry.get(course_code, {}) if course_code else {}
                return {
                    "resolved_source": f"https://docs.google.com/document/d/{source_str}/edit",
                    "source_type": "gdoc_url",
                    "course_code": course_code or course_info.get("course_code"),
                    "course_title": course_info.get("course_title"),
                    "primary_local_path": course_info.get("primary_doc_path"),
                    "gdoc_url": f"https://docs.google.com/document/d/{source_str}/edit",
                    "preferred_mode": "gdoc",
                    "auto_filled": False,
                    "resolution_reason": "Bare Google Docs Document ID"
                }
        except Exception:
            pass

    # 3. Check if source is an explicit .gdoc file path (MUST precede course code regex)
    if source_str.lower().endswith(".gdoc"):
        p = Path(source_str)
        parent_folder = p.parent.name
        
        # Check course from path
        course_code = normalize_course_code(parent_folder) or norm_hint
        c_info = registry.get(course_code, {}) if course_code else {}

        # Look up Doc ID
        doc_id = None
        if c_info.get("saved_gdoc_url"):
            m = GDOC_URL_REGEX.search(c_info["saved_gdoc_url"])
            if m:
                doc_id = m.group(1)
        
        if not doc_id:
            doc_id = lookup_drivefs_doc_id(p.name, parent_folder)

        if doc_id:
            g_url = f"https://docs.google.com/document/d/{doc_id}/edit"
            return {
                "resolved_source": g_url,
                "source_type": "gdoc_url",
                "course_code": course_code or c_info.get("course_code"),
                "course_title": c_info.get("course_title"),
                "primary_local_path": c_info.get("primary_doc_path"),
                "gdoc_url": g_url,
                "preferred_mode": "gdoc",
                "auto_filled": True,
                "resolution_reason": f"Resolved .gdoc file to live Google Docs URL via DriveFS ({p.name})"
            }
        else:
            raise ValueError(f"Could not resolve Google Doc ID for virtual drive file: {source_str}")

    # 4. Check if source is an existing local file (.docx, .r, .rmd)
    try:
        p = Path(source_str)
        if p.exists() and p.is_file() and p.suffix.lower() in (".docx", ".r", ".rmd"):
            ext = p.suffix.lower()
            course_code = normalize_course_code(p.parent.name) or norm_hint
            c_info = registry.get(course_code, {}) if course_code else {}
            stype = "r_script" if ext in (".r", ".rmd") else "local_docx"

            return {
                "resolved_source": str(p.resolve()),
                "source_type": stype,
                "course_code": course_code or c_info.get("course_code"),
                "course_title": c_info.get("course_title"),
                "primary_local_path": str(p.resolve()),
                "gdoc_url": c_info.get("saved_gdoc_url", ""),
                "preferred_mode": "file",
                "auto_filled": False,
                "resolution_reason": "Existing local document file"
            }
    except Exception:
        pass

    # 5. Check if source is a course code, folder name, or empty (with course_hint)
    target_code = normalize_course_code(source_str) or norm_hint
    if target_code and (target_code in registry or any(target_code in c for c in registry)):
        # Match course in registry
        matched_key = target_code if target_code in registry else next((c for c in registry if target_code in c), None)
        c_info = registry[matched_key]
        
        # Decide between local file and Google Doc URL
        if c_info["preferred_mode"] == "file" and c_info["primary_doc_path"]:
            resolved = c_info["primary_doc_path"]
            ext = Path(resolved).suffix.lower()
            stype = "r_script" if ext in (".r", ".rmd") else "local_docx"
            reason = f"Auto-filled primary lecture notes file for {matched_key}"
        elif c_info["saved_gdoc_url"]:
            resolved = c_info["saved_gdoc_url"]
            stype = "gdoc_url"
            reason = f"Auto-filled Google Docs URL for {matched_key}"
        elif c_info["primary_doc_path"]:
            resolved = c_info["primary_doc_path"]
            ext = Path(resolved).suffix.lower()
            stype = "r_script" if ext in (".r", ".rmd") else "local_docx"
            reason = f"Auto-filled local document fallback for {matched_key}"
        else:
            raise FileNotFoundError(f"No lecture notes document or Google Doc URL found for course '{matched_key}'")

        return {
            "resolved_source": resolved,
            "source_type": stype,
            "course_code": c_info["course_code"],
            "course_title": c_info["course_title"],
            "primary_local_path": c_info["primary_doc_path"],
            "gdoc_url": c_info["saved_gdoc_url"],
            "preferred_mode": c_info["preferred_mode"],
            "auto_filled": True,
            "resolution_reason": reason
        }

    # If all resolutions fail
    raise ValueError(f"Unable to auto-resolve source document from input: '{source}'")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Auto-resolve course notes document and links")
    parser.add_argument("query", nargs="?", default="", help="Course code, folder name, or file path")
    args = parser.parse_args()

    if args.query:
        res = resolve_source_document(args.query)
        print(json.dumps(res, indent=2))
    else:
        reg = get_course_registry()
        print(f"Discovered {len(reg)} courses:")
        for k, v in reg.items():
            print(f"- {k}: {v['course_title']}")
            print(f"  Primary Doc: {v['primary_doc_name']}")
            print(f"  Google Doc:  {v['saved_gdoc_url']}")
            print(f"  Preferred:   {v['preferred_mode']}")
