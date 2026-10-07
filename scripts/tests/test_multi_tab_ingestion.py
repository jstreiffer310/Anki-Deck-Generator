"""
Unit tests for Multi-Tab Google Docs Ingestion and Cuing Sheets Compatibility.
Verifies includeTabsContent=True, recursive tab traversal, tab title hierarchy
prepending, and 100% backward compatibility for downstream consumers.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.docs_api_client import (
    extract_document_id,
    extract_google_doc_structured,
    fetch_highlighted_text,
    default_classify_color,
)


def _build_mock_run(text: str, bg_rgb: dict = None) -> dict:
    """Helper to build textRun element."""
    run = {"content": text}
    if bg_rgb:
        run["textStyle"] = {
            "backgroundColor": {
                "color": {
                    "rgbColor": bg_rgb
                }
            }
        }
    return {"textRun": run}


def _build_mock_paragraph(runs: list, named_style: str = "NORMAL_TEXT") -> dict:
    """Helper to build paragraph structural element."""
    return {
        "paragraph": {
            "paragraphStyle": {"namedStyleType": named_style},
            "elements": runs
        }
    }


class TestMultiTabGoogleDocsIngestion:
    """Tests for multi-tab Google Docs traversal and hierarchy extraction."""

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_single_tab_legacy_fallback(self, mock_get_creds, mock_build):
        """Verifies backward compatibility with single-tab documents (no 'tabs' field)."""
        mock_service = MagicMock()
        mock_docs = MagicMock()
        mock_get = MagicMock()

        mock_build.return_value = mock_service
        mock_service.documents.return_value = mock_docs
        mock_docs.get.return_value = mock_get

        mock_get.execute.return_value = {
            "title": "Legacy Course Notes",
            "body": {
                "content": [
                    _build_mock_paragraph([_build_mock_run("Introduction\n")], named_style="HEADING_1"),
                    _build_mock_paragraph([
                        _build_mock_run("Concept A: ", bg_rgb={"red": 1.0, "green": 1.0, "blue": 0.0}),
                        _build_mock_run("the foundational mechanism of cognitive growth.", bg_rgb={"red": 0.0, "green": 1.0, "blue": 0.0}),
                    ]),
                ]
            }
        }

        data, title = extract_google_doc_structured("dummy_doc_id")
        assert title == "Legacy Course Notes"
        assert len(data) == 1
        item = data[0]
        assert item["heading"] == "Introduction"
        assert item["heading_hierarchy"] == ["Introduction"]
        assert "Concept A" in item["full_paragraph"]
        assert len(item["highlights"]) == 2

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_empty_tabs_fallback(self, mock_get_creds, mock_build):
        """Verifies fallback to body when 'tabs' is present but empty."""
        mock_service = MagicMock()
        mock_docs = MagicMock()
        mock_get = MagicMock()

        mock_build.return_value = mock_service
        mock_service.documents.return_value = mock_docs
        mock_docs.get.return_value = mock_get

        mock_get.execute.return_value = {
            "title": "Empty Tabs Doc",
            "tabs": [],
            "body": {
                "content": [
                    _build_mock_paragraph([_build_mock_run("Header\n")], named_style="HEADING_1"),
                    _build_mock_paragraph([
                        _build_mock_run("Term: ", bg_rgb={"red": 1.0, "green": 1.0, "blue": 0.0}),
                        _build_mock_run("Definition.", bg_rgb={"red": 0.0, "green": 1.0, "blue": 0.0}),
                    ]),
                ]
            }
        }

        data, title = extract_google_doc_structured("dummy_doc_id")
        assert len(data) == 1
        assert data[0]["heading_hierarchy"] == ["Header"]

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_multi_tab_full_ingestion_and_tab_title_prepend(self, mock_get_creds, mock_build):
        """Verifies that multi-tab documents ingest all tabs and prepend tab titles."""
        mock_service = MagicMock()
        mock_docs = MagicMock()
        mock_get = MagicMock()

        mock_build.return_value = mock_service
        mock_service.documents.return_value = mock_docs
        mock_docs.get.return_value = mock_get

        # Multi-tab response modeled after PSYC 2110 (Part 1 and Part 2)
        mock_get.execute.return_value = {
            "title": "2110 (Developmental): Lecture & Textbook Notes",
            "tabs": [
                {
                    "tabProperties": {"tabId": "t.0", "title": "Part 1: Foundations"},
                    "documentTab": {
                        "body": {
                            "content": [
                                _build_mock_paragraph([_build_mock_run("1: Goals, Theories, and Methods\n")], named_style="HEADING_1"),
                                _build_mock_paragraph([
                                    _build_mock_run("Developmental Niche: ", bg_rgb={"red": 1.0, "green": 1.0, "blue": 0.0}),
                                    _build_mock_run("framework consisting of physical settings, childcare customs, and caregiver beliefs.", bg_rgb={"red": 0.0, "green": 1.0, "blue": 0.0}),
                                ]),
                            ]
                        }
                    }
                },
                {
                    "tabProperties": {"tabId": "t.hxamzc6u5lt", "title": "Part 2: Infancy & Childhood"},
                    "documentTab": {
                        "body": {
                            "content": [
                                _build_mock_paragraph([_build_mock_run("4 Perceptual and Motor Development\n")], named_style="HEADING_1"),
                                _build_mock_paragraph([
                                    _build_mock_run("Ecological Theory of Perception: ", bg_rgb={"red": 1.0, "green": 1.0, "blue": 0.0}),
                                    _build_mock_run("Gibson's perspective emphasizing affordances and direct environment perception.", bg_rgb={"red": 0.0, "green": 1.0, "blue": 0.0}),
                                ]),
                            ]
                        }
                    }
                }
            ]
        }

        data, title = extract_google_doc_structured("dummy_doc_id")
        assert title == "2110 (Developmental): Lecture & Textbook Notes"
        # Must extract BOTH tabs (prevents tab truncation bug)
        assert len(data) == 2

        # Tab 1 item verification
        item_tab1 = data[0]
        assert item_tab1["heading"] == "1: Goals, Theories, and Methods"
        assert item_tab1["heading_hierarchy"] == ["Part 1: Foundations", "1: Goals, Theories, and Methods"]
        assert "Developmental Niche" in item_tab1["full_paragraph"]

        # Tab 2 item verification
        item_tab2 = data[1]
        assert item_tab2["heading"] == "4 Perceptual and Motor Development"
        assert item_tab2["heading_hierarchy"] == ["Part 2: Infancy & Childhood", "4 Perceptual and Motor Development"]
        assert "Ecological Theory of Perception" in item_tab2["full_paragraph"]

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_nested_child_tabs_traversal(self, mock_get_creds, mock_build):
        """Verifies recursive traversal of nested childTabs."""
        mock_service = MagicMock()
        mock_docs = MagicMock()
        mock_get = MagicMock()

        mock_build.return_value = mock_service
        mock_service.documents.return_value = mock_docs
        mock_docs.get.return_value = mock_get

        mock_get.execute.return_value = {
            "title": "Hierarchical Course Notes",
            "tabs": [
                {
                    "tabProperties": {"tabId": "t.1", "title": "Unit 1"},
                    "documentTab": {
                        "body": {
                            "content": [
                                _build_mock_paragraph([
                                    _build_mock_run("Unit 1 Overview: ", bg_rgb={"red": 1.0, "green": 1.0, "blue": 0.0}),
                                    _build_mock_run("General principles.", bg_rgb={"red": 0.0, "green": 1.0, "blue": 0.0}),
                                ]),
                            ]
                        }
                    },
                    "childTabs": [
                        {
                            "tabProperties": {"tabId": "t.1.1", "title": "Chapter 1"},
                            "documentTab": {
                                "body": {
                                    "content": [
                                        _build_mock_paragraph([_build_mock_run("Section A\n")], named_style="HEADING_1"),
                                        _build_mock_paragraph([
                                            _build_mock_run("Sub-item: ", bg_rgb={"red": 1.0, "green": 1.0, "blue": 0.0}),
                                            _build_mock_run("Sub-description.", bg_rgb={"red": 0.0, "green": 1.0, "blue": 0.0}),
                                        ]),
                                    ]
                                }
                            }
                        }
                    ]
                }
            ]
        }

        data, title = extract_google_doc_structured("dummy_doc_id")
        assert len(data) == 2
        # Root tab item
        assert data[0]["heading_hierarchy"] == ["Unit 1"]
        # Child tab item has nested tab hierarchy
        assert data[1]["heading_hierarchy"] == ["Unit 1", "Chapter 1", "Section A"]

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_heading_stack_resets_across_tabs(self, mock_get_creds, mock_build):
        """Verifies that heading hierarchy in earlier tabs does not bleed into subsequent tabs."""
        mock_service = MagicMock()
        mock_docs = MagicMock()
        mock_get = MagicMock()

        mock_build.return_value = mock_service
        mock_service.documents.return_value = mock_docs
        mock_docs.get.return_value = mock_get

        mock_get.execute.return_value = {
            "title": "Multi-Tab Reset Test",
            "tabs": [
                {
                    "tabProperties": {"title": "Tab One"},
                    "documentTab": {
                        "body": {
                            "content": [
                                _build_mock_paragraph([_build_mock_run("Deep Heading 1\n")], named_style="HEADING_1"),
                                _build_mock_paragraph([_build_mock_run("Deep Heading 2\n")], named_style="HEADING_2"),
                                _build_mock_paragraph([
                                    _build_mock_run("Item 1: ", bg_rgb={"red": 1.0, "green": 1.0, "blue": 0.0}),
                                    _build_mock_run("Def 1.", bg_rgb={"red": 0.0, "green": 1.0, "blue": 0.0}),
                                ])
                            ]
                        }
                    }
                },
                {
                    "tabProperties": {"title": "Tab Two"},
                    "documentTab": {
                        "body": {
                            "content": [
                                # No headings in Tab Two before highlighted text
                                _build_mock_paragraph([
                                    _build_mock_run("Item 2: ", bg_rgb={"red": 1.0, "green": 1.0, "blue": 0.0}),
                                    _build_mock_run("Def 2.", bg_rgb={"red": 0.0, "green": 1.0, "blue": 0.0}),
                                ])
                            ]
                        }
                    }
                }
            ]
        }

        data, _ = extract_google_doc_structured("dummy_doc_id")
        assert len(data) == 2
        assert data[0]["heading_hierarchy"] == ["Tab One", "Deep Heading 1", "Deep Heading 2"]
        # Tab Two must NOT contain "Deep Heading 1" or "Deep Heading 2"
        assert data[1]["heading_hierarchy"] == ["Tab Two"]
        assert data[1]["heading"] == "Tab Two"


class TestFetchHighlightedTextMultiTab:
    """Tests for fetch_highlighted_text multi-tab extraction."""

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_fetch_highlighted_text_multi_tab(self, mock_get_creds, mock_build):
        """Verifies highlight extraction across multiple tabs."""
        mock_service = MagicMock()
        mock_docs = MagicMock()
        mock_get = MagicMock()

        mock_build.return_value = mock_service
        mock_service.documents.return_value = mock_docs
        mock_docs.get.return_value = mock_get

        mock_get.execute.return_value = {
            "title": "Highlight Multi-Tab",
            "tabs": [
                {
                    "tabProperties": {"title": "Tab A"},
                    "documentTab": {
                        "body": {
                            "content": [
                                _build_mock_paragraph([
                                    _build_mock_run("Highlight One", bg_rgb={"red": 1.0, "green": 1.0, "blue": 0.0})
                                ])
                            ]
                        }
                    }
                },
                {
                    "tabProperties": {"title": "Tab B"},
                    "documentTab": {
                        "body": {
                            "content": [
                                _build_mock_paragraph([
                                    _build_mock_run("Highlight Two", bg_rgb={"red": 0.0, "green": 1.0, "blue": 0.0})
                                ])
                            ]
                        }
                    }
                }
            ]
        }

        highlights = fetch_highlighted_text("dummy_doc_id")
        assert len(highlights) == 2
        assert highlights[0]["text"] == "Highlight One"
        assert highlights[0]["color"] == "#ffff00"
        assert highlights[1]["text"] == "Highlight Two"
        assert highlights[1]["color"] == "#00ff00"


class TestCuingSheetsCompatibility:
    """Verifies 100% backward compatibility for C:\\Users\\jstre\\Projects\\Cuing_Sheets\\gdocs_reader.py."""

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_cuing_sheets_schema_invariants(self, mock_get_creds, mock_build):
        """Verifies that structured data contains all schema keys required by Cuing Sheets."""
        mock_service = MagicMock()
        mock_docs = MagicMock()
        mock_get = MagicMock()

        mock_build.return_value = mock_service
        mock_service.documents.return_value = mock_docs
        mock_docs.get.return_value = mock_get

        mock_get.execute.return_value = {
            "title": "PSYC 2110 Accommodation Study Notes",
            "tabs": [
                {
                    "tabProperties": {"title": "Part 1: Foundations"},
                    "documentTab": {
                        "body": {
                            "content": [
                                _build_mock_paragraph([_build_mock_run("Section 1\n")], named_style="HEADING_1"),
                                _build_mock_paragraph([
                                    _build_mock_run("Accommodation Cue: ", bg_rgb={"red": 1.0, "green": 1.0, "blue": 0.0}),
                                    _build_mock_run("Target retrieval memory anchor.", bg_rgb={"red": 0.0, "green": 1.0, "blue": 0.0}),
                                ])
                            ]
                        }
                    }
                }
            ]
        }

        # 1. extract_google_doc_structured return signature
        structured_data, doc_title = extract_google_doc_structured("dummy_doc_id")
        assert isinstance(structured_data, list)
        assert isinstance(doc_title, str)
        assert len(structured_data) == 1

        item = structured_data[0]
        # Cuing Sheets required keys
        required_keys = {"heading", "heading_hierarchy", "full_paragraph", "segments", "highlights"}
        assert required_keys.issubset(item.keys())

        assert isinstance(item["heading"], str)
        assert isinstance(item["heading_hierarchy"], list)
        assert isinstance(item["full_paragraph"], str)
        assert isinstance(item["segments"], list)
        assert isinstance(item["highlights"], list)

        # 2. fetch_highlighted_text return signature
        highlights = fetch_highlighted_text("dummy_doc_id")
        assert isinstance(highlights, list)
        assert len(highlights) == 2
        for h in highlights:
            assert "text" in h
            assert "color" in h
            assert "rgb" in h

    def test_cuing_sheets_gdocs_reader_importable(self):
        """Verifies that Cuing_Sheets/gdocs_reader.py can import from docs_api_client cleanly."""
        cuing_sheets_dir = Path(r"C:\Users\jstre\Projects\Cuing_Sheets")
        if cuing_sheets_dir.exists():
            import subprocess
            cmd = [
                sys.executable,
                "-c",
                "import sys; sys.path.insert(0, r'C:\\Users\\jstre\\Projects\\Cuing_Sheets'); "
                "import gdocs_reader; "
                "assert hasattr(gdocs_reader, 'fetch_course_notes'); "
                "assert hasattr(gdocs_reader, 'fetch_exam_highlights')"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            assert result.returncode == 0, f"Cuing Sheets gdocs_reader failed to import: {result.stderr}"
