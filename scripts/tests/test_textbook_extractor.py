"""
Unit tests for Textbook PDF Discovery and Extraction Engine.
Verifies config-based discovery, directory-based scanning, syllabus filtering,
caching mechanisms, and structured curricular content extraction for PSYC 2110
and PSYC 3590.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from scripts.textbook_extractor import (
    discover_course_textbook,
    extract_textbook_data,
    get_cache_path,
    load_config,
    _normalize_course_code,
)


class TestTextbookDiscovery:
    """Tests for discovering textbook PDFs from config and directory scanning."""

    def test_discover_from_config_psyc_2110(self):
        """Verifies discovery of PSYC 2110 textbook configured in config.json."""
        path = discover_course_textbook("PSYC 2110")
        assert path is not None
        p = Path(path)
        assert p.exists()
        assert "Tamis-LeMonda" in p.name or "Child development" in p.name

    def test_discover_from_config_psyc_3590(self):
        """Verifies discovery of PSYC 3590 textbook configured in config.json."""
        path = discover_course_textbook("PSYC 3590")
        assert path is not None
        p = Path(path)
        assert p.exists()
        assert "Drugs, Behaviour, and Society" in p.name

    def test_discover_fuzzy_course_codes(self):
        """Verifies fuzzy matching with no spaces, lowercase, and numeric codes."""
        assert discover_course_textbook("psyc2110") is not None
        assert discover_course_textbook("2110") is not None
        assert discover_course_textbook("psyc3590") is not None
        assert discover_course_textbook("3590") is not None

    def test_discover_directory_scan_and_syllabus_filtering(self, tmp_path):
        """Verifies directory scanning filters out syllabi/outlines and picks the textbook."""
        mock_classes_dir = tmp_path / "Classes"
        mock_classes_dir.mkdir()
        course_folder = mock_classes_dir / "F PSYC 9999 Advanced Cognition"
        course_folder.mkdir()

        # Create files
        syllabus_pdf = course_folder / "PSYC 9999 Syllabus Fall 2026.pdf"
        syllabus_pdf.write_bytes(b"%PDF-1.4 dummy syllabus" * 100)

        outline_pdf = course_folder / "Course Outline.pdf"
        outline_pdf.write_bytes(b"%PDF-1.4 dummy outline" * 100)

        textbook_pdf = course_folder / "9780123456789_Advanced_Cognition_Textbook.pdf"
        textbook_pdf.write_bytes(b"%PDF-1.4 dummy real textbook" * 1000)

        mock_config = {
            "classes_base_directory": str(mock_classes_dir),
            "textbooks": {}
        }
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(mock_config), encoding="utf-8")

        discovered = discover_course_textbook("PSYC 9999", config_path=cfg_path)
        assert discovered is not None
        assert Path(discovered).name == "9780123456789_Advanced_Cognition_Textbook.pdf"

    def test_discover_nonexistent_course_returns_none(self):
        """Verifies None returned for nonexistent course code."""
        assert discover_course_textbook("NONEXISTENT_99999") is None
        assert discover_course_textbook("") is None
        assert discover_course_textbook(None) is None


class TestTextbookCachingAndDataStructures:
    """Tests for extraction data structure, caching, and refresh behavior."""

    def test_missing_textbook_raises_filenotfound(self, tmp_path):
        """Verifies FileNotFoundError when attempting extraction on nonexistent course."""
        with pytest.raises(FileNotFoundError):
            extract_textbook_data("NONEXISTENT_COURSE_9999", cache_dir=tmp_path)

    def test_caching_roundtrip(self, tmp_path):
        """Verifies that extracted data is cached and reloaded without re-extracting."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        fake_cache_content = {
            "course_code": "PSYC 9999",
            "textbook_path": "dummy.pdf",
            "extractor": "mock",
            "extracted_at": "2026-10-06T00:00:00Z",
            "chapters": {
                "1": {
                    "chapter_number": 1,
                    "chapter_title": "Foundations",
                    "summary": "Summary text",
                    "learning_objectives": [{"lo": "LO1", "text": "Objective 1"}],
                    "glossary_terms": {"term a": "definition a"},
                    "review_questions": ["1. Question 1?"]
                }
            },
            "glossary": {
                "term a": {"term": "term a", "definition": "definition a", "chapter": 1}
            }
        }
        cache_file = get_cache_path("PSYC 9999", cache_dir=cache_dir)
        cache_file.write_text(json.dumps(fake_cache_content), encoding="utf-8")

        # extract_textbook_data should load from cache directly without needing PDF
        data = extract_textbook_data("PSYC 9999", force_refresh=False, cache_dir=cache_dir)
        assert data["course_code"] == "PSYC 9999"
        assert "1" in data["chapters"]
        assert data["chapters"]["1"]["chapter_title"] == "Foundations"
        assert "term a" in data["glossary"]

    def test_psyc_2110_extracted_structure_and_developmental_niche(self):
        """
        Verifies real PSYC 2110 textbook extraction contains:
        1. 16 chapters
        2. Chapter summaries
        3. Comprehensive glossary containing 'developmental niche'
        """
        data = extract_textbook_data("PSYC 2110", force_refresh=False)
        assert data["course_code"] == "PSYC 2110"
        assert len(data["chapters"]) >= 16

        # Check Chapter 1
        ch1 = data["chapters"]["1"]
        assert ch1["chapter_number"] == 1
        assert len(ch1["summary"]) > 50
        assert len(ch1["glossary_terms"]) > 10

        # Check developmental niche in glossary
        glossary = data["glossary"]
        assert "developmental niche" in glossary
        dn = glossary["developmental niche"]
        assert dn["term"].lower() == "developmental niche"
        assert dn["chapter"] == 1
        defn = dn["definition"].lower()
        # Must encompass the 3 pillars: settings, customs, and caregiver beliefs
        assert "physical and social settings" in defn
        assert "customs" in defn
        assert "beliefs" in defn or "caregiver" in defn

    def test_psyc_3590_extracted_structure_and_learning_objectives(self):
        """
        Verifies real PSYC 3590 textbook extraction contains:
        1. 18 chapters
        2. Chapter titles
        3. Learning objectives (e.g. LO1..LO9 in Ch 4)
        4. Chapter summary bullet points
        5. Review questions
        """
        data = extract_textbook_data("PSYC 3590", force_refresh=False)
        assert data["course_code"] == "PSYC 3590"
        assert len(data["chapters"]) == 18

        # Check Chapter 4: The Nervous System
        ch4 = data["chapters"]["4"]
        assert ch4["chapter_number"] == 4
        assert "Nervous System" in ch4["chapter_title"]
        assert len(ch4["learning_objectives"]) >= 4
        lo_tags = [lo["lo"] for lo in ch4["learning_objectives"]]
        assert "LO1" in lo_tags
        assert "LO2" in lo_tags
        assert "LO3" in lo_tags

        # Verify summary points and review questions
        assert len(ch4["summary"]) > 100
        assert len(ch4["review_questions"]) > 0
        assert any("homeostasis" in q.lower() or "glia" in q.lower() for q in ch4["review_questions"])
