"""
Adversarial Stress Test Suite for Milestone M14: Textbook Discovery & Extraction.
Authored by Challenger 2 (challenger_m14_2).

Covers:
1. Malformed / corrupted JSON cache handling & recovery (truncated, empty, binary garbage, non-dict).
2. Missing / unreadable / directory / corrupt PDF error handling.
3. Ground-truth verification of PSYC 2110 cache (16 chapters, 3 pillars of developmental niche, 769 terms).
4. Ground-truth verification of PSYC 3590 cache (18 chapters, LOs, RQs, and summary bullet extraction gaps).
5. Discovery priority hierarchy (config override vs. missing-config fallback vs. filesystem scan vs. syllabus filtering).
6. Config loading resilience (nonexistent file, invalid JSON, directory as config path).
7. Course code normalization edge cases.
"""

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

try:
    import pymupdf
except (ImportError, Exception):
    pymupdf = None

import pypdf

from scripts.textbook_extractor import (
    discover_course_textbook,
    extract_textbook_data,
    get_cache_path,
    load_config,
    _normalize_course_code,
)


def _create_minimal_valid_pdf(output_path: Path, title: str = "Test Book") -> Path:
    """Helper to generate a minimal valid single-page PDF with pypdf."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with open(output_path, "wb") as f:
        writer.write(f)
    return output_path


# ============================================================================
# 1. MALFORMED / CORRUPTED JSON CACHE HANDLING
# ============================================================================

class TestMalformedCacheHandling:
    """Adversarial tests for corrupted, partial, or malformed cache files."""

    def test_corrupt_cache_truncated_json_recovers_if_pdf_exists(self, tmp_path):
        """When cache JSON is truncated/broken, extract_textbook_data must re-extract from PDF."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        pdf_path = _create_minimal_valid_pdf(tmp_path / "valid_book.pdf")

        # Write truncated JSON
        cfile = get_cache_path("TEST 101", cache_dir=cache_dir)
        cfile.write_text('{"course_code": "TEST 101", "chapters": { "1":', encoding="utf-8")

        result = extract_textbook_data(
            "TEST 101",
            force_refresh=False,
            pdf_path=str(pdf_path),
            cache_dir=cache_dir,
        )
        assert result["course_code"] == "TEST 101"
        assert "chapters" in result
        # Cache file should have been rewritten with valid JSON
        with open(cfile, "r", encoding="utf-8") as f:
            re_saved = json.load(f)
        assert re_saved["course_code"] == "TEST 101"

    def test_corrupt_cache_empty_file_recovers_if_pdf_exists(self, tmp_path):
        """When cache JSON is 0 bytes, extract_textbook_data must re-extract from PDF."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        pdf_path = _create_minimal_valid_pdf(tmp_path / "valid_book.pdf")

        cfile = get_cache_path("TEST 102", cache_dir=cache_dir)
        cfile.write_text("", encoding="utf-8")

        result = extract_textbook_data(
            "TEST 102",
            force_refresh=False,
            pdf_path=str(pdf_path),
            cache_dir=cache_dir,
        )
        assert result["course_code"] == "TEST 102"
        assert "chapters" in result

    def test_corrupt_cache_binary_garbage_recovers_if_pdf_exists(self, tmp_path):
        """When cache file contains raw invalid non-UTF8 bytes, it must re-extract from PDF."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        pdf_path = _create_minimal_valid_pdf(tmp_path / "valid_book.pdf")

        cfile = get_cache_path("TEST 103", cache_dir=cache_dir)
        cfile.write_bytes(b"\x00\xff\xfe\xfa\x80\x99\x12\x34\xde\xad\xbe\xef")

        result = extract_textbook_data(
            "TEST 103",
            force_refresh=False,
            pdf_path=str(pdf_path),
            cache_dir=cache_dir,
        )
        assert result["course_code"] == "TEST 103"
        assert "chapters" in result

    def test_corrupt_cache_and_missing_pdf_raises_filenotfound(self, tmp_path):
        """When cache is corrupt and PDF does not exist, FileNotFoundError must be raised."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        cfile = get_cache_path("NO_PDF_COURSE", cache_dir=cache_dir)
        cfile.write_text("{broken json", encoding="utf-8")

        with pytest.raises(FileNotFoundError) as exc_info:
            extract_textbook_data(
                "NO_PDF_COURSE",
                force_refresh=False,
                pdf_path=str(tmp_path / "does_not_exist.pdf"),
                cache_dir=cache_dir,
            )
        assert "No textbook PDF found" in str(exc_info.value)

    def test_cache_containing_non_dict_json_vulnerability(self, tmp_path):
        """
        Adversarial edge case:
        If cache file has valid JSON syntax, but root is a list, int, or string,
        line 547 returns data directly without verifying dictionary schema.
        Empirically document this behavior.
        """
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        cfile = get_cache_path("LIST_CACHE", cache_dir=cache_dir)
        cfile.write_text("[1, 2, 3]", encoding="utf-8")

        data = extract_textbook_data("LIST_CACHE", cache_dir=cache_dir)
        # Empirical finding: returns list instead of validating schema/dict
        assert isinstance(data, list)
        assert data == [1, 2, 3]

    def test_cache_unwritable_directory_still_returns_data(self, tmp_path):
        """
        When cache directory is unwriteable (e.g. read-only permissions),
        the extraction completes and returns result dictionary without unhandled crash.
        """
        cache_dir = tmp_path / "readonly_cache"
        cache_dir.mkdir()
        pdf_path = _create_minimal_valid_pdf(tmp_path / "valid_book.pdf")

        orig_open = open

        def guarded_open(file, mode="r", *args, **kwargs):
            if "w" in mode and str(cache_dir) in str(file):
                raise PermissionError("Access is denied: simulated read-only cache")
            return orig_open(file, mode, *args, **kwargs)

        with patch("builtins.open", side_effect=guarded_open):
            result = extract_textbook_data(
                "TEST_READONLY",
                pdf_path=str(pdf_path),
                cache_dir=cache_dir,
                force_refresh=True,
            )
            assert result["course_code"] == "TEST_READONLY"
            assert "chapters" in result

    def test_cache_hit_performance(self):
        """Verifies cache read completes sub-50ms without invoking PDF parsing."""
        t0 = time.perf_counter()
        data = extract_textbook_data("PSYC 2110", force_refresh=False)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert data["course_code"] == "PSYC 2110"
        assert elapsed_ms < 50.0, f"Cache retrieval took too long: {elapsed_ms:.2f}ms"


# ============================================================================
# 2. MISSING & INVALID TEXTBOOK PDF HANDLING
# ============================================================================

class TestMissingAndInvalidPdfHandling:
    """Adversarial tests for missing, directory, or unreadable PDF targets."""

    def test_missing_pdf_explicit_nonexistent_path(self, tmp_path):
        """Explicit path to nonexistent PDF raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            extract_textbook_data(
                "PSYC 2110",
                pdf_path=str(tmp_path / "nonexistent.pdf"),
                cache_dir=tmp_path,
                force_refresh=True,
            )

    def test_pdf_path_is_directory_handling(self, tmp_path):
        """When pdf_path points to an existing directory rather than a file, an error is raised."""
        dummy_dir = tmp_path / "fake_pdf_dir"
        dummy_dir.mkdir()

        with pytest.raises(Exception):  # pymupdf raises FileDataError or OSError
            extract_textbook_data(
                "TEST_DIR",
                pdf_path=str(dummy_dir),
                cache_dir=tmp_path,
                force_refresh=True,
            )

    def test_corrupted_empty_pdf_raises_filedataerror(self, tmp_path):
        """An empty 0-byte PDF raises an extraction error from PyMuPDF."""
        empty_pdf = tmp_path / "empty.pdf"
        empty_pdf.write_bytes(b"")

        with pytest.raises(Exception):
            extract_textbook_data(
                "TEST_EMPTY_PDF",
                pdf_path=str(empty_pdf),
                cache_dir=tmp_path,
                force_refresh=True,
            )

    def test_corrupted_garbage_pdf_raises_error(self, tmp_path):
        """A PDF containing random garbage bytes raises FileDataError upon opening."""
        garbage_pdf = tmp_path / "corrupt.pdf"
        garbage_pdf.write_bytes(b"THIS IS NOT A VALID PDF FILE AT ALL")

        with pytest.raises(Exception):
            extract_textbook_data(
                "TEST_CORRUPT_PDF",
                pdf_path=str(garbage_pdf),
                cache_dir=tmp_path,
                force_refresh=True,
            )

    def test_blank_or_whitespace_course_codes(self):
        """Blank or whitespace-only course codes return None in discover_course_textbook."""
        assert discover_course_textbook("") is None
        assert discover_course_textbook("   ") is None
        assert discover_course_textbook("\t\n") is None
        assert discover_course_textbook(None) is None


# ============================================================================
# 3. GROUND TRUTH VERIFICATION: PSYC 2110 CACHE
# ============================================================================

class TestPsyc2110GroundTruth:
    """Verifies that PSYC 2110 cached textbook data satisfies all curricular contracts."""

    @pytest.fixture(autouse=True)
    def setup_data(self):
        cache_path = Path("data/textbook_cache/PSYC_2110.json")
        assert cache_path.exists(), f"Expected cache file at {cache_path}"
        with open(cache_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    def test_all_16_chapters_present(self):
        """Tamis-LeMonda has 16 chapters. All must be present in cache."""
        chapters = self.data["chapters"]
        assert len(chapters) == 16
        for ch_num in range(1, 17):
            assert str(ch_num) in chapters
            ch_data = chapters[str(ch_num)]
            assert ch_data["chapter_number"] == ch_num
            assert f"Chapter {ch_num}" in ch_data["chapter_title"]

    def test_all_16_chapter_summaries_populated(self):
        """All 16 chapters must have non-empty summary text extracted from the TOC entries."""
        chapters = self.data["chapters"]
        for ch_num in range(1, 17):
            summary = chapters[str(ch_num)]["summary"]
            assert isinstance(summary, str)
            assert len(summary) > 50, f"Chapter {ch_num} summary is unexpectedly short: {len(summary)}"

    def test_developmental_niche_with_three_pillars(self):
        """
        Milestone M14 & R4 requirement:
        'developmental niche' must be in glossary and encompass all 3 core pillars:
        1. physical and social settings
        2. customs of childcare and child-rearing
        3. beliefs and views of caregivers (caretaker psychology / ethnotheories)
        """
        glossary = self.data["glossary"]
        assert "developmental niche" in glossary, "'developmental niche' missing from glossary"

        item = glossary["developmental niche"]
        assert item["chapter"] == 1
        defn = item["definition"].lower()

        # Pillar 1: Settings
        assert "physical and social settings" in defn or "settings of children" in defn, \
            "Pillar 1 (settings) missing from definition"

        # Pillar 2: Customs
        assert "customs" in defn, "Pillar 2 (customs) missing from definition"

        # Pillar 3: Caregiver beliefs / psychology
        assert "beliefs" in defn or "views of caregivers" in defn or "caretaker" in defn, \
            "Pillar 3 (caregiver beliefs) missing from definition"

        # Also verify authors cited
        assert "charles super" in defn or "super" in defn
        assert "sara harkness" in defn or "harkness" in defn

    def test_glossary_breadth_and_chapter_distribution(self):
        """Glossary must contain >= 750 total terms distributed across all 16 chapters."""
        glossary = self.data["glossary"]
        assert len(glossary) >= 750, f"Expected >= 750 terms, got {len(glossary)}"

        # Every chapter must have terms
        chapters = self.data["chapters"]
        for ch_num in range(1, 17):
            ch_terms = chapters[str(ch_num)]["glossary_terms"]
            assert len(ch_terms) > 0, f"Chapter {ch_num} has 0 glossary terms"

        # Non-empty definitions for at least 99.7% of terms (767 of 769)
        valid_defns = [v for v in glossary.values() if v["definition"].strip()]
        assert len(valid_defns) / len(glossary) >= 0.997

    def test_multiline_bold_wrapping_orphan_defect_documented(self):
        """
        Adversarial Finding:
        When a bold term wraps across two lines in the PDF, PyMuPDF emits two separate
        bold spans with regular_spans=[] on line 1.
        This creates an orphan entry with an empty definition for line 1, and assigns
        the definition to line 2.
        We empirically verify that exactly 2 terms exhibit this defect in the current cache:
        1. 'home observation for the measurement of the' (line 2 was 'Environment (HOME)')
        2. 'diagnostic and statistical manual of mental disorders' (line 2 was '(DSM-5)')
        """
        glossary = self.data["glossary"]
        empty_defns = {k: v for k, v in glossary.items() if not v["definition"].strip()}
        assert len(empty_defns) == 2
        expected_orphan_keys = {
            "home observation for the measurement of the",
            "diagnostic and statistical manual of mental disorders",
        }
        assert set(empty_defns.keys()) == expected_orphan_keys

        # Also verify the corresponding line-2 entries got the definitions:
        assert glossary["environment (home)"]["definition"].strip()
        assert glossary["(dsm-5)"]["definition"].strip()

    @pytest.mark.xfail(
        reason="Defect: Multi-line bold terms wrap into orphan entries with empty definitions in PSYC 2110",
        strict=True
    )
    def test_zero_empty_definitions_ideal_invariant(self):
        """Strict invariant: 100% of glossary terms should have non-empty definitions."""
        glossary = self.data["glossary"]
        empty_defns = [k for k, v in glossary.items() if not v["definition"].strip()]
        assert empty_defns == [], f"Found {len(empty_defns)} terms with empty definitions: {empty_defns}"


# ============================================================================
# 4. GROUND TRUTH VERIFICATION: PSYC 3590 CACHE & EXTRACTION GAPS
# ============================================================================

class TestPsyc3590GroundTruth:
    """Verifies PSYC 3590 cached textbook data (Drugs, Behaviour, and Society)."""

    @pytest.fixture(autouse=True)
    def setup_data(self):
        cache_path = Path("data/textbook_cache/PSYC_3590.json")
        assert cache_path.exists(), f"Expected cache file at {cache_path}"
        with open(cache_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    def test_all_18_chapters_present(self):
        """Drugs, Behaviour, and Society has 18 chapters. All must be present."""
        chapters = self.data["chapters"]
        assert len(chapters) == 18
        for ch_num in range(1, 19):
            assert str(ch_num) in chapters
            ch_data = chapters[str(ch_num)]
            assert ch_data["chapter_number"] == ch_num
            assert ch_data["chapter_title"].strip()

    def test_learning_objectives_across_all_18_chapters(self):
        """All 18 chapters must have non-empty learning objectives."""
        chapters = self.data["chapters"]
        for ch_num in range(1, 19):
            los = chapters[str(ch_num)]["learning_objectives"]
            assert len(los) >= 5, f"Chapter {ch_num} has fewer than 5 LOs: {len(los)}"
            for lo_item in los:
                assert lo_item["lo"].startswith("LO")
                assert len(lo_item["text"]) > 10

    def test_review_questions_across_all_18_chapters(self):
        """All 18 chapters must have numbered review questions."""
        chapters = self.data["chapters"]
        for ch_num in range(1, 19):
            rqs = chapters[str(ch_num)]["review_questions"]
            assert len(rqs) >= 3, f"Chapter {ch_num} has fewer than 3 review questions: {len(rqs)}"

    def test_summary_bullets_extraction_gap_documented(self):
        """
        Adversarial Finding:
        In the current implementation of _extract_psyc_3590_pymupdf:
        Chapters 1, 4, 6, 7, 9, 15, 16, 18 have summary bullets.
        However, chapters 2, 3, 5, 8, 10, 11, 12, 13, 14, 17 have empty summaries
        due to the bullet character '\\u2022' appearing on its own line in PyMuPDF text stream.
        This test documents and verifies the exact empirical distribution of summary coverage.
        """
        chapters = self.data["chapters"]
        populated_summaries = [ch for ch, data in chapters.items() if len(data["summary"].strip()) > 0]
        empty_summaries = [ch for ch, data in chapters.items() if len(data["summary"].strip()) == 0]

        expected_populated = ["1", "4", "6", "7", "9", "15", "16", "18"]
        assert set(populated_summaries) == set(expected_populated)

        expected_empty = ["2", "3", "5", "8", "10", "11", "12", "13", "14", "17"]
        assert set(empty_summaries) == set(expected_empty)

    @pytest.mark.xfail(
        reason="Defect: 10 of 18 chapters in PSYC 3590 currently lack summaries due to '\\u2022\\n' newline splits",
        strict=True
    )
    def test_all_18_chapters_have_summaries_ideal_invariant(self):
        """Strict invariant: All 18 chapters should have populated summaries."""
        chapters = self.data["chapters"]
        empty_summaries = [ch for ch, data in chapters.items() if len(data["summary"].strip()) == 0]
        assert empty_summaries == [], f"Found {len(empty_summaries)} chapters with empty summaries: {empty_summaries}"


# ============================================================================
# 5. DISCOVERY PRIORITY HIERARCHY
# ============================================================================

class TestDiscoveryPriorityHierarchy:
    """Verifies config override vs filesystem scan vs syllabus filtering."""

    def test_config_override_takes_precedence_over_filesystem(self, tmp_path):
        """
        When config.json points to file A, and filesystem has file B,
        discover_course_textbook MUST return file A regardless of ranking.
        """
        classes_dir = tmp_path / "Classes"
        course_dir = classes_dir / "F PSYC 1111 Introduction"
        course_dir.mkdir(parents=True)

        pdf_filesystem = course_dir / "9781111111111_Huge_Ranked_Textbook.pdf"
        _create_minimal_valid_pdf(pdf_filesystem, "Filesystem Ranked Textbook")

        pdf_config = tmp_path / "Config_Specified_Book.pdf"
        _create_minimal_valid_pdf(pdf_config, "Config Override Book")

        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "classes_base_directory": str(classes_dir),
            "textbooks": {
                "PSYC 1111": str(pdf_config)
            }
        }), encoding="utf-8")

        discovered = discover_course_textbook("PSYC 1111", config_path=cfg_file)
        assert discovered is not None
        assert Path(discovered).resolve() == pdf_config.resolve()

    def test_missing_config_path_falls_back_to_filesystem(self, tmp_path):
        """
        When config.json points to a file that does NOT exist on disk,
        discover_course_textbook must fall through and discover the filesystem candidate.
        """
        classes_dir = tmp_path / "Classes"
        course_dir = classes_dir / "F PSYC 1111 Introduction"
        course_dir.mkdir(parents=True)

        pdf_filesystem = course_dir / "9781111111111_Filesystem_Textbook.pdf"
        _create_minimal_valid_pdf(pdf_filesystem, "Filesystem Candidate")

        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "classes_base_directory": str(classes_dir),
            "textbooks": {
                "PSYC 1111": str(tmp_path / "nonexistent_override.pdf")
            }
        }), encoding="utf-8")

        discovered = discover_course_textbook("PSYC 1111", config_path=cfg_file)
        assert discovered is not None
        assert Path(discovered).resolve() == pdf_filesystem.resolve()

    def test_syllabus_and_administrative_files_strictly_filtered(self, tmp_path):
        """
        Files matching exclude patterns (syllabus, outline, rubric, exam, slides, handout)
        must never be returned as a textbook.
        """
        classes_dir = tmp_path / "Classes"
        course_dir = classes_dir / "F PSYC 2222 Cognitive Lab"
        course_dir.mkdir(parents=True)

        for name in [
            "PSYC 2222 Fall 2026 Syllabus.pdf",
            "Course Outline - PSYC 2222.pdf",
            "Assignment 1 Rubric.pdf",
            "Midterm Exam Study Guide.pdf",
            "Week 1 Lecture Slides.pdf",
            "Handout - Statistics Review.pdf",
            "Grading Scheme & Schedule.pdf",
        ]:
            _create_minimal_valid_pdf(course_dir / name, name)

        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "classes_base_directory": str(classes_dir),
            "textbooks": {}
        }), encoding="utf-8")

        discovered = discover_course_textbook("PSYC 2222", config_path=cfg_file)
        assert discovered is None

    def test_ranking_prefers_isbn_and_size_over_generic_pdf(self, tmp_path):
        """
        When multiple candidate PDFs exist, ranking prioritizes ISBN, textbook keyword, and file size.
        """
        classes_dir = tmp_path / "Classes"
        course_dir = classes_dir / "F PSYC 3333 Social"
        course_dir.mkdir(parents=True)

        small_pdf = course_dir / "reading_article.pdf"
        _create_minimal_valid_pdf(small_pdf, "Short Article")

        ranked_textbook = course_dir / "9780199999999_Social_Psychology_Textbook.pdf"
        _create_minimal_valid_pdf(ranked_textbook, "Full Textbook with ISBN")

        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "classes_base_directory": str(classes_dir),
            "textbooks": {}
        }), encoding="utf-8")

        discovered = discover_course_textbook("PSYC 3333", config_path=cfg_file)
        assert discovered is not None
        assert Path(discovered).resolve() == ranked_textbook.resolve()

    def test_fuzzy_course_code_variations(self):
        """
        Verifies discovery across various string variations:
        - Lowercase
        - Hyphenated
        - Leading/trailing whitespace
        - Bare numeric code
        """
        p1 = discover_course_textbook("psyc 2110")
        p2 = discover_course_textbook("PSYC-2110")
        p3 = discover_course_textbook("  PSYC 2110  ")
        p4 = discover_course_textbook("2110")
        assert p1 is not None
        assert p1 == p2 == p3 == p4


# ============================================================================
# 6. CONFIG LOADING & NORMALIZATION ROBUSTNESS
# ============================================================================

class TestConfigAndNormalizationRobustness:
    """Tests load_config and _normalize_course_code with adversarial inputs."""

    def test_load_config_nonexistent_file_returns_empty_dict(self, tmp_path):
        res = load_config(tmp_path / "nonexistent_config.json")
        assert res == {}

    def test_load_config_corrupted_json_returns_empty_dict(self, tmp_path):
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{broken", encoding="utf-8")
        res = load_config(bad_json)
        assert res == {}

    def test_load_config_directory_returns_empty_dict(self, tmp_path):
        res = load_config(tmp_path)
        assert res == {}

    def test_normalize_course_code_adversarial(self):
        assert _normalize_course_code("PSYC 2110") == "psyc2110"
        assert _normalize_course_code("psyc-3590!!") == "psyc3590"
        assert _normalize_course_code("  F PSYC   3031 \t") == "fpsyc3031"
        assert _normalize_course_code("") == ""
        assert _normalize_course_code(1234) == "1234"
