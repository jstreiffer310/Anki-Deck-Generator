import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/documents.readonly"]

def get_credentials():
    """Gets valid user credentials from storage or initiates OAuth2 flow."""
    creds = None
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    token_path = os.path.join(project_root, "token.json")
    creds_path = os.path.join(project_root, "credentials.json")

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_path):
                raise FileNotFoundError(f"Credentials not found at {creds_path}")
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())
    return creds

def extract_document_id(url_or_id):
    """Extracts the document ID from a full Google Docs URL or returns the ID if provided."""
    if not url_or_id:
        return ""
    url_str = str(url_or_id).strip()
    match = re.search(r'(?:/document/(?:u/\d+/)?d/|/d/)([a-zA-Z0-9_-]+)', url_str)
    if match:
        return match.group(1)
    id_match = re.match(r'^([a-zA-Z0-9_-]{20,80})$', url_str)
    if id_match:
        return id_match.group(1)
    return url_str

def rgb_to_hex(rgb_color):
    """Converts a Google Docs API RGB color to a hex string."""
    r = int(rgb_color.get('red', 0) * 255)
    g = int(rgb_color.get('green', 0) * 255)
    b = int(rgb_color.get('blue', 0) * 255)
    return f"#{r:02x}{g:02x}{b:02x}"

def extract_text_runs(elements):
    """Recursively extract text runs from structural elements."""
    runs = []
    for element in elements:
        if 'paragraph' in element:
            for el in element['paragraph'].get('elements', []):
                if 'textRun' in el:
                    runs.append(el['textRun'])
        elif 'table' in element:
            for row in element['table'].get('tableRows', []):
                for cell in row.get('tableCells', []):
                    runs.extend(extract_text_runs(cell.get('content', [])))
        elif 'tableOfContents' in element:
            runs.extend(extract_text_runs(element['tableOfContents'].get('content', [])))
    return runs

def fetch_highlighted_text(url_or_id):
    """Fetches the document and extracts highlighted text segments.
    
    Returns:
        List of dictionaries containing 'text', 'color' (hex), and 'rgb' values.
    """
    document_id = extract_document_id(url_or_id)
    creds = get_credentials()

    try:
        service = build("docs", "v1", credentials=creds)
        document = service.documents().get(documentId=document_id).execute()
        
        highlighted_segments = []
        
        contents_to_process = []
        if 'body' in document:
            contents_to_process.append(document['body'].get('content', []))
            
        for section in ['headers', 'footers', 'footnotes']:
            if section in document:
                for item_id, item in document[section].items():
                    contents_to_process.append(item.get('content', []))
                    
        text_runs = []
        for content in contents_to_process:
            text_runs.extend(extract_text_runs(content))
        
        for text_run in text_runs:
            text = text_run.get('content', '')
            if not text.strip(): # Skip empty or whitespace-only
                continue
                
            text_style = text_run.get('textStyle', {})
            bg_color = text_style.get('backgroundColor', {})
            color = bg_color.get('color', {})
            rgb_color = color.get('rgbColor', None)

            if rgb_color is not None:
                hex_color = rgb_to_hex(rgb_color)
                highlighted_segments.append({
                    'text': text.strip(),
                    'color': hex_color,
                    'rgb': rgb_color
                })

        return highlighted_segments

    except HttpError as err:
        print(f"An API error occurred: {err}")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

DEFAULT_GREEN_KEYS = {
    "green", "lightgreen", "#00ff00", "#b7e1cd", "#81c784", "#a5d6a7", "#c8e6c9", "#e8f5e9", "#00e676", "#69f0ae"
}
DEFAULT_YELLOW_KEYS = {
    "yellow", "#ffff00", "#fff2cc", "#fff176", "#fff59d", "#ffe082", "#ffee58", "#ffeb3b", "#fdd835"
}

def default_classify_color(hex_color):
    """Classifies a hex color into 'green', 'yellow', or 'other'."""
    if not hex_color:
        return None
    h = hex_color.lower().strip()
    if h in DEFAULT_GREEN_KEYS or h.lstrip('#') in DEFAULT_GREEN_KEYS or f"#{h.lstrip('#')}" in DEFAULT_GREEN_KEYS:
        return "green"
    if h in DEFAULT_YELLOW_KEYS or h.lstrip('#') in DEFAULT_YELLOW_KEYS or f"#{h.lstrip('#')}" in DEFAULT_YELLOW_KEYS:
        return "yellow"
    return "other"

def extract_paragraphs_from_elements(elements):
    """Recursively extracts paragraph dictionaries from structural elements."""
    paragraphs = []
    for element in elements:
        if 'paragraph' in element:
            paragraphs.append(element['paragraph'])
        elif 'table' in element:
            for row in element['table'].get('tableRows', []):
                for cell in row.get('tableCells', []):
                    paragraphs.extend(extract_paragraphs_from_elements(cell.get('content', [])))
        elif 'tableOfContents' in element:
            paragraphs.extend(extract_paragraphs_from_elements(element['tableOfContents'].get('content', [])))
    return paragraphs

def extract_google_doc_structured(url_or_id, classify_fn=None):
    """
    Fetches the document and extracts structured paragraphs with headings,
    segments, and highlights formatted identically to extract_document_highlights.
    
    Returns:
        tuple: (structured_data: list[dict], document_title: str)
    """
    document_id = extract_document_id(url_or_id)
    creds = get_credentials()
    classify = classify_fn or default_classify_color

    try:
        service = build("docs", "v1", credentials=creds)
        document = service.documents().get(documentId=document_id).execute()
        
        doc_title = document.get("title", "")
        contents_to_process = []
        if 'body' in document:
            contents_to_process.append(document['body'].get('content', []))

        paragraphs = []
        for content in contents_to_process:
            paragraphs.extend(extract_paragraphs_from_elements(content))

        structured_data = []
        current_heading = "General"
        heading_stack = []

        for p in paragraphs:
            style = p.get('paragraphStyle', {}).get('namedStyleType', '')
            elements = p.get('elements', [])
            
            # Combine all text runs in this paragraph
            text_runs = [el['textRun'] for el in elements if 'textRun' in el]
            full_text = "".join(tr.get('content', '') for tr in text_runs).strip()
            if not full_text:
                continue

            # Check if this paragraph is a heading or title
            if style.startswith("HEADING") or style in ("TITLE", "SUBTITLE"):
                current_heading = full_text
                if not doc_title and style == "TITLE":
                    doc_title = full_text
                heading_stack.append(full_text)
                continue

            paragraph_segments = []
            current_color = None
            current_text = []

            for tr in text_runs:
                content = tr.get('content', '')
                if not content:
                    continue
                bg = tr.get('textStyle', {}).get('backgroundColor', {}).get('color', {})
                rgb = bg.get('rgbColor', None)
                color = rgb_to_hex(rgb) if rgb is not None else None

                if color == current_color:
                    current_text.append(content)
                else:
                    if current_text:
                        segment_str = "".join(current_text)
                        paragraph_segments.append({
                            "raw_color": current_color,
                            "category": classify(current_color),
                            "text": segment_str
                        })
                    current_color = color
                    current_text = [content]

            if current_text:
                segment_str = "".join(current_text)
                paragraph_segments.append({
                    "raw_color": current_color,
                    "category": classify(current_color),
                    "text": segment_str
                })

            # Merge whitespace/colon gaps between identical highlight categories
            i = 0
            merged = []
            while i < len(paragraph_segments):
                curr = paragraph_segments[i]
                if i + 2 < len(paragraph_segments):
                    nxt1 = paragraph_segments[i + 1]
                    nxt2 = paragraph_segments[i + 2]
                    if curr["category"] == nxt2["category"] and curr["category"] is not None:
                        if nxt1["category"] is None and re.match(r'^[\s\-_,;:]*$', nxt1["text"]):
                            merged.append({
                                "raw_color": curr["raw_color"],
                                "category": curr["category"],
                                "text": curr["text"] + nxt1["text"] + nxt2["text"]
                            })
                            i += 3
                            continue
                merged.append(curr)
                i += 1

            # Second pass: merge adjacent identical categories
            final_segments = []
            for seg in merged:
                if final_segments and final_segments[-1]["category"] == seg["category"] and seg["category"] is not None:
                    final_segments[-1]["text"] += seg["text"]
                else:
                    final_segments.append(seg)

            highlights_in_p = [
                s for s in final_segments
                if s["category"] is not None
                and re.search(r'\w', s["text"])
                and not re.match(r'^[\s\-_,;:\.\?!]*$', s["text"])
            ]

            if highlights_in_p:
                structured_data.append({
                    "heading": current_heading,
                    "heading_hierarchy": list(heading_stack),
                    "full_paragraph": full_text,
                    "segments": final_segments,
                    "highlights": highlights_in_p
                })

        try:
            from scripts.extract_and_generate import stitch_consecutive_highlights
            structured_data = stitch_consecutive_highlights(structured_data)
        except ImportError:
            try:
                from extract_and_generate import stitch_consecutive_highlights
                structured_data = stitch_consecutive_highlights(structured_data)
            except ImportError:
                pass

        return structured_data, doc_title

    except HttpError as err:
        print(f"An API error occurred: {err}")
        return [], ""
    except Exception as e:
        print(f"An error occurred: {e}")
        return [], ""

def detect_input_type(source: str, raise_on_error: bool = False) -> str:
    """
    Classifies an input source into:
    - 'gdoc_url': A valid Google Docs URL containing /document/d/ or /document/u/{N}/d/
    - 'gdoc_id': A bare alphanumeric Google Docs document ID (25-60 chars)
    - 'docx_file': An existing local Word .docx file
    - 'docx_missing': A path ending with .docx that does not exist on disk
    - 'invalid': Empty, non-existent, wrong extension (.pdf, .txt), or unsupported URL

    If raise_on_error is True:
    - Empty or non-string input raises ValueError("Input source cannot be empty")
    - Unrecognized/invalid format raises ValueError(f"Unrecognized or unsupported input source format: {source}")
    """
    if not source or not isinstance(source, str):
        if raise_on_error:
            raise ValueError("Input source cannot be empty")
        return "invalid"
    source_str = source.strip()
    if not source_str:
        if raise_on_error:
            raise ValueError("Input source cannot be empty")
        return "invalid"

    # 1. URL checks
    if source_str.startswith("http://") or source_str.startswith("https://"):
        if re.search(r'docs\.google\.com/document/(?:u/\d+/)?d/([a-zA-Z0-9-_]+)', source_str):
            return "gdoc_url"
        if raise_on_error:
            raise ValueError(f"Unrecognized or unsupported input source format: {source}")
        return "invalid"

    # 2. Local file checks
    p = Path(source_str)
    if source_str.lower().endswith(".docx"):
        try:
            if p.exists() and p.is_file():
                return "docx_file"
            else:
                return "docx_missing"
        except Exception:
            return "docx_missing"

    if source_str.lower().endswith((".r", ".rmd")):
        try:
            if p.exists() and p.is_file():
                return "r_script"
            else:
                return "r_missing"
        except Exception:
            return "r_missing"

    try:
        if p.exists() and p.is_file():
            # Existing file with unsupported extension (e.g. .pdf, .txt)
            if raise_on_error:
                raise ValueError(f"Unrecognized or unsupported input source format: {source}")
            return "invalid"
    except Exception:
        pass

    # 3. Bare Document ID check (alphanumeric + _ - typically 25-60 chars)
    if re.match(r'^[a-zA-Z0-9-_]{25,60}$', source_str) and not p.exists():
        return "gdoc_id"

    if raise_on_error:
        raise ValueError(f"Unrecognized or unsupported input source format: {source}")
    return "invalid"

def ingest_source(source: str, classify_fn: Optional[Callable] = None) -> Tuple[List[Dict[str, Any]], str]:
    """
    Polymorphically extracts structured paragraph highlights and document title
    from a Google Docs URL, Document ID, local .docx file, or local .R/.Rmd script.

    Returns:
        tuple: (structured_data: list[dict], document_title: str)
    """
    if not source or not isinstance(source, str) or not source.strip():
        raise ValueError("Input source cannot be empty")

    input_type = detect_input_type(source, raise_on_error=False)
    if input_type in ("gdoc_url", "gdoc_id"):
        return extract_google_doc_structured(source, classify_fn=classify_fn)
    elif input_type in ("docx_file", "docx_path"):
        try:
            from scripts.extract_and_generate import extract_document_highlights
        except ImportError:
            from extract_and_generate import extract_document_highlights
        data = extract_document_highlights(source, classify_fn=classify_fn)
        try:
            title = Path(source).stem if Path(source).exists() else ""
        except Exception:
            title = ""
        return data, title
    elif input_type == "docx_missing":
        raise FileNotFoundError(f"Specified .docx file not found at: {source}")
    elif input_type in ("r_script",):
        try:
            from scripts.extract_and_generate import extract_r_script_highlights
        except ImportError:
            from extract_and_generate import extract_r_script_highlights
        data = extract_r_script_highlights(source)
        try:
            title = Path(source).stem if Path(source).exists() else ""
        except Exception:
            title = ""
        return data, title
    elif input_type == "r_missing":
        raise FileNotFoundError(f"Specified R script file not found at: {source}")
    else:
        raise ValueError(f"Unrecognized or unsupported input source format: {source}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fetch highlighted text from a Google Doc")
    parser.add_argument("document", help="Google Docs URL or Document ID")
    parser.add_argument("--structured", action="store_true", help="Output structured paragraph highlights")
    args = parser.parse_args()

    if args.structured:
        data, title = extract_google_doc_structured(args.document)
        print(f"Document Title: {title}")
        print(f"Found {len(data)} paragraphs with highlights.")
        for idx, p in enumerate(data, 1):
            print(f"\n[{idx}] Heading: {p['heading']}")
            print(f"Paragraph: {p['full_paragraph']}")
            for h in p['highlights']:
                print(f"  - [{h['category']}|{h['raw_color']}] {h['text']}")
    else:
        highlights = fetch_highlighted_text(args.document)
        if highlights is not None:
            print(f"Found {len(highlights)} highlighted segments.")
            for i, segment in enumerate(highlights, 1):
                print(f"{i}. [{segment['color']}] {segment['text']}")
