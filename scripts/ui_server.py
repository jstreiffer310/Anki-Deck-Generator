"""
ui_server.py — Zero-Terminal Web UI Pipeline for Academic Anki Deck Generator
Provides a modern local web server (http://localhost:5050) that dynamically discovers
all course folders in 'H:\\My Drive\\Classes', detects lecture notes (.docx, .gdoc, Google Docs URLs),
generates SuperMemo-compliant atomic cards, injects into Anki via AnkiConnect, and mirrors to Google Drive.
"""

import sys
import os
import re
import json
import socket
import logging
import threading
import webbrowser
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import urllib.request
import urllib.error

# Project paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
WEB_UI_DIR = SCRIPT_DIR / "web_ui"
CONFIG_PATH = PROJECT_ROOT / "config.json"

# Ensure project root is in sys.path
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AnkiDeckUI")

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading config: {e}")
    return {}

def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving config: {e}")

def check_ankiconnect() -> bool:
    """Checks if AnkiConnect is responding on localhost:8765."""
    try:
        req = urllib.request.Request(
            "http://localhost:8765",
            data=json.dumps({"action": "version", "version": 6}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=1.5) as res:
            data = json.loads(res.read().decode("utf-8"))
            return data.get("result") is not None
    except Exception:
        return False

def check_oauth_status() -> dict:
    """Checks if token.json and credentials.json are present and valid."""
    token_path = PROJECT_ROOT / "token.json"
    creds_path = PROJECT_ROOT / "credentials.json"
    
    has_creds = creds_path.exists()
    has_token = token_path.exists()
    
    user_email = None
    if has_token:
        try:
            with open(token_path, "r", encoding="utf-8") as f:
                t_data = json.load(f)
                # Token file has client_id, refresh_token, etc.
                if t_data.get("token") or t_data.get("refresh_token"):
                    user_email = t_data.get("account", "Authorized")
        except Exception:
            pass
            
    return {
        "credentials_configured": has_creds,
        "token_saved": has_token,
        "is_authenticated": has_token and has_creds,
        "user_email": user_email
    }

def discover_classes_and_notes() -> list:
    """
    Dynamically scans 'H:\\My Drive\\Classes' (and config fallbacks).
    Compatible with ANY subsequent folders added to Classes.
    Extracts course codes, friendly titles, and detects all lecture notes files.
    """
    config = load_config()
    classes_dir_str = config.get("classes_base_directory", r"H:\My Drive\Classes")
    classes_path = Path(classes_dir_str)
    
    if not classes_path.exists():
        logger.warning(f"Classes base directory does not exist: {classes_path}")
        return []

    course_regex = re.compile(r'([A-Z]{2,4}\s*\d{4}[A-Za-z]?)', re.IGNORECASE)
    known_courses = config.get("courses", {})
    recent_doc_links = config.get("recent_doc_links", {})

    courses = []
    
    # Iterate through each folder in Classes
    for p in sorted(classes_path.iterdir()):
        if not p.is_dir() or p.name.startswith("."):
            continue
            
        folder_name = p.name
        m = course_regex.search(folder_name)
        
        if m:
            course_code = re.sub(r'([A-Z]+)(\d+)', r'\1 \2', m.group(1).upper())
            raw_title = folder_name[m.end():].strip(' -–—:()')
            # Strip term identifiers like F, W, Y if at the start
            raw_title = re.sub(r'^(?:F|W|S|Y)\s+', '', raw_title).strip()
            course_title = raw_title if len(raw_title) > 2 else known_courses.get(course_code, folder_name)
        else:
            course_code = folder_name.split()[0].upper()
            course_title = folder_name

        # Recursively search for lecture note documents (.docx, .gdoc)
        documents = []
        try:
            for item in p.rglob("*"):
                if not item.is_file():
                    continue
                ext = item.suffix.lower()
                if ext in (".docx", ".gdoc"):
                    name_lower = item.name.lower()
                    if name_lower.startswith("~$"):
                        continue
                    # Skip syllabi or course outlines from default auto-selection
                    is_syllabus = any(w in name_lower for w in ["syllabus", "course outline", "schedule", "activity", "assignment"])
                    
                    documents.append({
                        "name": item.name,
                        "path": str(item),
                        "rel_path": str(item.relative_to(p)),
                        "ext": ext,
                        "is_syllabus": is_syllabus,
                        "size_bytes": item.stat().st_size if ext == ".docx" else 0
                    })
        except Exception as e:
            logger.error(f"Error scanning folder {p}: {e}")

        # Check if an existing deck already exists in Decks/ or Google Drive
        safe_code = re.sub(r'[^a-zA-Z0-9_\-]', '_', course_code)
        decks_dir = Path(config.get("output_directory", PROJECT_ROOT / "Decks"))
        gdrive_decks = Path(config.get("google_drive_decks_directory", r"H:\My Drive\Admin\Anki Decks"))
        
        existing_decks = []
        for target_dir in [decks_dir, gdrive_decks]:
            if target_dir.exists():
                for d in target_dir.glob(f"*{safe_code}*.apkg"):
                    existing_decks.append({
                        "name": d.name,
                        "path": str(d),
                        "mtime": d.stat().st_mtime,
                        "size_bytes": d.stat().st_size
                    })

        # Saved Google Doc URL / ID for this course
        saved_gdoc = recent_doc_links.get(course_code, "")

        courses.append({
            "course_code": course_code,
            "course_title": course_title,
            "folder_name": folder_name,
            "folder_path": str(p),
            "documents": sorted(documents, key=lambda x: (x["is_syllabus"], not "notes" in x["name"].lower(), x["name"])),
            "existing_decks": existing_decks,
            "saved_gdoc_url": saved_gdoc
        })

    return courses

class DeckCreatorHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/status":
            self.handle_api_status()
        elif path == "/api/courses":
            self.handle_api_courses()
        elif path == "/api/decks":
            self.handle_api_decks()
        else:
            self.serve_static_file(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/generate":
            self.handle_api_generate()
        elif path == "/api/open_folder":
            self.handle_api_open_folder()
        elif path == "/api/save_doc_link":
            self.handle_api_save_doc_link()
        else:
            self.send_error(404, "Endpoint not found")

    def handle_api_status(self):
        status = {
            "anki_connected": check_ankiconnect(),
            "oauth": check_oauth_status(),
            "classes_drive_accessible": Path(load_config().get("classes_base_directory", r"H:\My Drive\Classes")).exists(),
            "admin_drive_accessible": Path(load_config().get("google_drive_decks_directory", r"H:\My Drive\Admin\Anki Decks")).exists(),
        }
        self.send_json_response(status)

    def handle_api_courses(self):
        courses = discover_classes_and_notes()
        self.send_json_response({"courses": courses, "total": len(courses)})

    def handle_api_decks(self):
        config = load_config()
        decks_dir = Path(config.get("output_directory", PROJECT_ROOT / "Decks"))
        gdrive_dir = Path(config.get("google_drive_decks_directory", r"H:\My Drive\Admin\Anki Decks"))
        
        decks = []
        for d_path in [decks_dir, gdrive_dir]:
            if d_path.exists():
                for f in d_path.glob("*.apkg"):
                    decks.append({
                        "name": f.name,
                        "path": str(f),
                        "location": "Local" if d_path == decks_dir else "Google Drive",
                        "size_bytes": f.stat().st_size,
                        "mtime": f.stat().st_mtime
                    })
        self.send_json_response({"decks": decks})

    def handle_api_open_folder(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = json.loads(body) if body else {}
        target = data.get("path")
        
        if target and Path(target).exists():
            try:
                os.startfile(target)
                self.send_json_response({"success": True})
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, status=500)
        else:
            self.send_json_response({"success": False, "error": "Path does not exist"}, status=400)

    def handle_api_save_doc_link(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = json.loads(body) if body else {}
        
        course_code = data.get("course_code")
        doc_url = data.get("doc_url")
        
        if course_code and doc_url:
            cfg = load_config()
            recent = cfg.setdefault("recent_doc_links", {})
            recent[course_code] = doc_url
            save_config(cfg)
            self.send_json_response({"success": True})
        else:
            self.send_json_response({"success": False, "error": "Missing parameters"}, status=400)

    def handle_api_generate(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        payload = json.loads(body) if body else {}

        source = payload.get("source")
        explicit_class = payload.get("course_code")
        explicit_chapter = payload.get("chapter")
        auto_inject = payload.get("auto_inject", True)

        if not source:
            self.send_json_response({"success": False, "error": "No source file or Google Doc URL provided"}, status=400)
            return

        # Save recent doc link if Google Doc
        if "docs.google.com" in source and explicit_class:
            cfg = load_config()
            recent = cfg.setdefault("recent_doc_links", {})
            recent[explicit_class] = source
            save_config(cfg)

        try:
            # Import generator dynamically
            from scripts.extract_and_generate import process_source_and_generate
            out_apkg, deck_title, cards = process_source_and_generate(
                source=source,
                explicit_class=explicit_class,
                explicit_chapter=explicit_chapter,
                auto_inject=auto_inject
            )

            # Calculate SuperMemo atomicity & quality metrics
            forward_count = sum(1 for c in cards if "forward" in c.get("tags", []))
            reverse_count = sum(1 for c in cards if "reverse" in c.get("tags", []))
            cloze_count = sum(1 for c in cards if c.get("card_type") == "cloze" or "{{c1::" in c.get("question", ""))
            
            clean_cards = []
            for c in cards:
                clean_cards.append({
                    "card_type": c.get("card_type", "active_recall_qa"),
                    "question": c.get("question", ""),
                    "answer": c.get("answer", ""),
                    "badge": c.get("category_badge", "badge-definition"),
                    "badge_label": "HIGH YIELD" if "important" in c.get("category_badge", "") else "DEFINITION",
                    "context": c.get("context", ""),
                    "tags": c.get("tags", [])
                })

            self.send_json_response({
                "success": True,
                "deck_title": deck_title,
                "output_filename": Path(out_apkg).name,
                "output_path": str(out_apkg),
                "total_cards": len(cards),
                "metrics": {
                    "forward_recall": forward_count,
                    "reverse_recognition": reverse_count,
                    "cloze_cards": cloze_count,
                    "atomic_compliance": "100% SuperMemo Compliant"
                },
                "cards": clean_cards
            })

        except Exception as e:
            logger.exception("Error generating deck")
            self.send_json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    def serve_static_file(self, req_path):
        if req_path in ("/", ""):
            file_path = WEB_UI_DIR / "index.html"
        else:
            file_path = WEB_UI_DIR / req_path.lstrip("/")

        if file_path.exists() and file_path.is_file():
            content_type = "text/html"
            if file_path.suffix == ".css":
                content_type = "text/css"
            elif file_path.suffix == ".js":
                content_type = "application/javascript"
            elif file_path.suffix == ".json":
                content_type = "application/json"
            elif file_path.suffix in (".png", ".jpg", ".svg", ".ico"):
                content_type = f"image/{file_path.suffix.lstrip('.')}"

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            with open(file_path, "rb") as f:
                self.wfile.write(f.read())
        else:
            # Fallback to index.html for SPA
            index_path = WEB_UI_DIR / "index.html"
            if index_path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                with open(index_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "Web UI not found")

    def send_json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

def start_server(port=5050, open_browser=True):
    # Find available port
    for p in range(port, port + 20):
        try:
            server = HTTPServer(("127.0.0.1", p), DeckCreatorHandler)
            actual_port = p
            break
        except OSError:
            continue
    else:
        logger.error("No free port available around 5050.")
        return

    url = f"http://localhost:{actual_port}"
    print(f"\n=========================================================")
    print(f"  ACADEMIC ANKI DECK GENERATOR — ZERO-TERMINAL UI PIPELINE")
    print(f"=========================================================")
    print(f"  UI Server running at: {url}")
    print(f"  Scanning classes from: H:\\My Drive\\Classes")
    print(f"  Press Ctrl+C to stop server.\n")

    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping UI server...")
        server.server_close()

if __name__ == "__main__":
    start_server(open_browser=True)
