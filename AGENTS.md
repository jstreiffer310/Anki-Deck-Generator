# Workspace Rules & Customizations: AnkiDeckCreator

This workspace contains the automated Python pipeline for creating Anki flashcards from lecture notes.

## Downstream Architectural Dependency
- **Shared Google Docs API Client**:
  - The script `scripts/docs_api_client.py` and the OAuth token `token.json` in this directory are an **active dependency** for the Cuing Sheet pipeline (`C:\Users\jstre\Projects\Cuing_Sheets\gdocs_reader.py`).
  - **Rule**: Do not relocate, delete, or break the public interface of `scripts/docs_api_client.py` (specifically `extract_google_doc_structured`, `extract_document_id`, `fetch_highlighted_text`, and `get_credentials`) without updating the downstream connector in `Cuing_Sheets`.
  - **Token Scope**: Ensure the OAuth scope in `token.json` maintains at least `https://www.googleapis.com/auth/documents.readonly`.

## Flashcard Formatting Rules
- **Keyword-Descriptor Format**: Always enforce the Keyword-Descriptor format (Term/Keyword -> Descriptor/Definition).
- **Chapter Tagging (Mandatory when available)**: Every card must be tagged by chapter (e.g., `Chapter_1`, `Chapter_2`, `Chapter_3`) whenever chapter information is identifiable from document titles, heading hierarchies, section headings, or metadata. Structural unit tags (e.g., `Lecture_1`, `Week_2`, `Topic_3`) should also be added when present to enable clean filtering in Anki.
- Follow standard operating procedures in [ANKI_SOP.md](file:///C:/Users/jstre/Projects/AnkiDeckCreator/ANKI_SOP.md).

