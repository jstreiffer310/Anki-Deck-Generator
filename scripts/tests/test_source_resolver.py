"""
scripts/tests/test_source_resolver.py — Automated Unit Tests for Source Document Auto-Resolution
Verifies automatic detection, auto-fill, and linking across all university courses.
"""

import pytest
from pathlib import Path
from scripts.source_resolver import (
    normalize_course_code,
    score_document,
    get_course_registry,
    resolve_source_document,
    lookup_drivefs_doc_id,
)
from scripts.ui_server import discover_classes_and_notes

class TestSourceResolver:
    def test_normalize_course_code(self):
        assert normalize_course_code("PSYC 3590") == "PSYC 3590"
        assert normalize_course_code("psyc3590") == "PSYC 3590"
        assert normalize_course_code("PSYC 3000A") == "PSYC 3000"
        assert normalize_course_code("3590") == "PSYC 3590"
        assert normalize_course_code("3000") == "PSYC 3000"
        assert normalize_course_code("2110") == "PSYC 2110"
        assert normalize_course_code("3031") == "PSYC 3031"
        assert normalize_course_code("invalid_code_xyz") is None

    def test_score_document_heuristics(self):
        # Syllabus and outline should receive heavy penalties
        assert score_document("PSYC 3590 Syllabus.pdf", ".pdf") < 0
        assert score_document("Course Outline.docx", ".docx") < 0
        assert score_document("Assignments/Rubric.docx", ".docx") < 0

        # Lecture notes should score highly
        notes_score = score_document("Lecture & Textbook Notes.docx", ".docx", size_bytes=100000)
        assert notes_score > 50

        # R scripts with week identifier should score positively
        r_score = score_document("Week 1_2026.R", ".r", size_bytes=5000)
        assert r_score > 20

    def test_get_course_registry(self):
        reg = get_course_registry()
        assert len(reg) >= 4
        assert "PSYC 3590" in reg
        assert "PSYC 2110" in reg
        assert "PSYC 3031" in reg
        assert "PSYC 3000" in reg

        # PSYC 3590 should prefer file and have primary_doc_path
        p3590 = reg["PSYC 3590"]
        assert p3590["preferred_mode"] == "file"
        assert p3590["primary_doc_path"] is not None
        assert p3590["primary_doc_path"].endswith(".docx")
        assert "1TA17mmRt0KEqZbjzB1j9b9mTuBbR_5S1tOxlby2Nz4I" in p3590["saved_gdoc_url"]

        # PSYC 2110 should prefer file
        p2110 = reg["PSYC 2110"]
        assert p2110["preferred_mode"] == "file"
        assert p2110["primary_doc_path"] is not None
        assert "1zUJDj_GuMtPVINzUvL8C_LKkYMeId9CJuUEKGo0Dx8Q" in p2110["saved_gdoc_url"]

        # PSYC 3031 should prefer file and point to R script
        p3031 = reg["PSYC 3031"]
        assert p3031["preferred_mode"] == "file"
        assert p3031["primary_doc_path"] is not None
        assert p3031["primary_doc_path"].endswith(".r") or p3031["primary_doc_path"].endswith(".R")

        # PSYC 3000 should prefer gdoc since only .gdoc lecture notes exist
        p3000 = reg["PSYC 3000"]
        assert p3000["preferred_mode"] == "gdoc"
        assert "1YPIcPSSARjJBQtRnIvD30XZia-g_O8m2_6kr-_h2h-A" in p3000["saved_gdoc_url"]

    def test_resolve_course_code_psyc3590(self):
        res = resolve_source_document("PSYC 3590")
        assert res["auto_filled"] is True
        assert res["course_code"] == "PSYC 3590"
        assert res["source_type"] == "local_docx"
        assert res["resolved_source"].endswith(".docx")

    def test_resolve_course_code_psyc3000(self):
        res = resolve_source_document("PSYC 3000")
        assert res["auto_filled"] is True
        assert res["course_code"] == "PSYC 3000"
        assert res["source_type"] == "gdoc_url"
        assert "docs.google.com" in res["resolved_source"]
        assert "1YPIcPSSARjJBQtRnIvD30XZia-g_O8m2_6kr-_h2h-A" in res["resolved_source"]

    def test_resolve_course_code_psyc3031(self):
        res = resolve_source_document("PSYC 3031")
        assert res["auto_filled"] is True
        assert res["course_code"] == "PSYC 3031"
        assert res["source_type"] == "r_script"
        assert res["resolved_source"].lower().endswith((".r", ".rmd"))

    def test_resolve_gdoc_file_path(self):
        gdoc_path = r"H:\My Drive\Classes\Y PSYC 3000  Professionalism & Communication\PSYC 3000 - Lecture Notes.gdoc"
        res = resolve_source_document(gdoc_path)
        assert res["auto_filled"] is True
        assert res["source_type"] == "gdoc_url"
        assert "1YPIcPSSARjJBQtRnIvD30XZia-g_O8m2_6kr-_h2h-A" in res["resolved_source"]

    def test_resolve_direct_gdoc_url(self):
        url = "https://docs.google.com/document/d/1TA17mmRt0KEqZbjzB1j9b9mTuBbR_5S1tOxlby2Nz4I/edit"
        res = resolve_source_document(url)
        assert res["source_type"] == "gdoc_url"
        assert res["resolved_source"] == url
        assert res["course_code"] == "PSYC 3590"

    def test_ui_server_discovery_enrichment(self):
        courses = discover_classes_and_notes()
        assert len(courses) >= 4
        for c in courses:
            assert "primary_doc_path" in c
            assert "preferred_mode" in c
            assert c["preferred_mode"] in ("file", "gdoc")
            assert "saved_gdoc_url" in c
            assert c["saved_gdoc_url"].startswith("https://docs.google.com/document/d/")
