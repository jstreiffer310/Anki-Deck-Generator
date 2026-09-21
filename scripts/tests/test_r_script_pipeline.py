"""
scripts/tests/test_r_script_pipeline.py — Unit & Integration Tests for R Script Ingestion & Flashcard Synthesis
Verifies:
1. Polymorphic detection (detect_input_type, ingest_source, extract_highlights) for .R and .Rmd files.
2. High-fidelity extraction of headings, data types, tasks, indexing rules, dplyr verbs, and pipes.
3. Card synthesis adhering to SuperMemo 20 Rules with zero 'this concept' or 'Define this concept' emissions.
4. Complete CardValidator pass rate with zero fatal errors or corruptions.
"""

import pytest
from pathlib import Path

from scripts.docs_api_client import detect_input_type, ingest_source
from scripts.extract_and_generate import (
    extract_r_script_highlights,
    extract_highlights,
    synthesize_cards,
    process_source_and_generate,
)
from scripts.card_validator import CardValidator, ContentShield


WEEK1_R_PATH = Path(r"H:\My Drive\Classes\F PSYC 3031  Intermediate Statistics I\3031 - R Projects\Week 1_2026.R")
WEEK2_R_PATH = Path(r"H:\My Drive\Classes\F PSYC 3031  Intermediate Statistics I\3031 - R Projects\Week2_2026.R")


class TestRScriptPolymorphicDetection:
    """Tests polymorphic input type detection and dispatch for R scripts."""

    def test_detect_input_type_r_scripts(self, tmp_path):
        r_file = tmp_path / "analysis.R"
        r_file.write_text("x <- 1:10\nmean(x)", encoding="utf-8")
        assert detect_input_type(str(r_file)) == "r_script"

        rmd_file = tmp_path / "report.Rmd"
        rmd_file.write_text("# Report\n```{r}\nsummary(cars)\n```", encoding="utf-8")
        assert detect_input_type(str(rmd_file)) == "r_script"

    def test_detect_input_type_r_missing(self):
        assert detect_input_type("nonexistent_script_123.R") == "r_missing"
        assert detect_input_type("missing_notebook.rmd") == "r_missing"

    def test_ingest_source_r_script(self, tmp_path):
        sample_r = tmp_path / "sample.R"
        sample_r.write_text(
            "# Week 1 - Basics\n"
            "#' Numeric (dbl or num): Numbers with decimals and can include negative values.\n"
            "#' **TASK: calculate the mean of 1:10**\n"
            "mean(1:10)\n",
            encoding="utf-8"
        )
        data, title = ingest_source(str(sample_r))
        assert title == "sample"
        assert len(data) >= 2
        assert any(item.get("heading") == "Week 1 - Basics" for item in data)

    def test_extract_highlights_polymorphic_dispatch(self, tmp_path):
        sample_r = tmp_path / "poly_test.R"
        sample_r.write_text(
            "# TOPIC 1 - Data types\n"
            "#' Logical (lgl): TRUE and FALSE values.\n",
            encoding="utf-8"
        )
        data, title = extract_highlights(str(sample_r))
        assert len(data) >= 1
        assert title == "poly_test"
        assert data[0]["heading"] == "TOPIC 1 - Data types"


class TestRScriptHighlightExtraction:
    """Verifies targeted extraction of headings, data types, tasks, indexing, and dplyr verbs."""

    def test_mock_r_script_complete_extraction(self, tmp_path):
        r_code = (
            "# Week 2 - Data Structures and Manipulation\n"
            "# TOPIC 2 - Data types\n"
            "#' Main Data types:\n"
            "#' Numeric (dbl or num): Numbers with decimals and can include negative values\n"
            "#' Integer (int): Whole numbers\n"
            "#' Logical (lgl): TRUE and FALSE values\n"
            "#' Character (chr): Values with quotation marks; text strings\n"
            "# TOPIC 3 - Data Structures\n"
            "#' Vectors: a string of values of the SAME data type\n"
            "#' Coercion: R converts all items in a vector to the highest type\n"
            "#' **TASK: extract the third column of hsb_10**\n"
            "hsb_10[, 3]\n"
            "# TOPIC 4 - Data manipulation\n"
            "#' Filtering: extracting rows that meet a certain criteria\n"
            "#' **TASK: extract participants with write score <= 50**\n"
            "hsb_10 %>%\n"
            "  filter(write <= 50)\n"
            "#' Creating a new variable: manipulating existing variables in data\n"
            "#' **TASK: create average_score column**\n"
            "mutate(complete_math_write, average_score = (math + write)/2)\n"
            "# TOPIC 5 - Piping\n"
            "#' Pipes: shorthand for chaining commands in R (|> or %>%)\n"
        )
        test_file = tmp_path / "test_week2.R"
        test_file.write_text(r_code, encoding="utf-8")

        highlights = extract_r_script_highlights(test_file)
        assert len(highlights) >= 8

        # 1. Verify headings
        headings = {h["heading"] for h in highlights}
        assert "TOPIC 2 - Data types" in headings
        assert "TOPIC 3 - Data Structures" in headings
        assert "TOPIC 4 - Data manipulation" in headings

        # 2. Verify data types extracted
        texts = [hl["text"] for h in highlights for hl in h["highlights"]]
        assert any("Numeric (dbl or num)" in t for t in texts)
        assert any("Integer (int)" in t for t in texts)
        assert any("Logical (lgl)" in t for t in texts)
        assert any("Character (chr)" in t for t in texts)

        # 3. Verify tasks extracted
        tasks = [h for h in highlights if h.get("is_r_task")]
        assert len(tasks) >= 3
        assert any("extract the third column" in t["descriptor"].lower() for t in tasks)
        assert any("hsb_10[, 3]" in t["answer"] for t in tasks)
        assert any("filter(write <= 50)" in t["answer"] for t in tasks)
        assert any("mutate" in t["answer"] for t in tasks)

    @pytest.mark.skipif(not WEEK1_R_PATH.exists(), reason="Week 1_2026.R not accessible on this system")
    def test_real_week1_course_file_extraction(self):
        highlights = extract_r_script_highlights(WEEK1_R_PATH)
        assert len(highlights) >= 20

        # Check for core Week 1 concepts and tasks
        texts = [hl["text"] for h in highlights for hl in h["highlights"]]
        assert any("R Object" in t or "Object" in t for t in texts)
        assert any("Working Directory" in t or "getwd" in t for t in texts)
        assert any("R Function" in t or "Functions" in t for t in texts)
        assert any("R Package" in t or "Packages" in t for t in texts)

    @pytest.mark.skipif(not WEEK2_R_PATH.exists(), reason="Week2_2026.R not accessible on this system")
    def test_real_week2_course_file_extraction(self):
        highlights = extract_r_script_highlights(WEEK2_R_PATH)
        assert len(highlights) >= 30

        # Check for Week 2 data types, indexing, and dplyr verbs
        texts = [hl["text"] for h in highlights for hl in h["highlights"]]
        assert any("Numeric (dbl or num)" in t for t in texts)
        assert any("Integer (int)" in t for t in texts)
        assert any("Logical (lgl)" in t for t in texts)
        assert any("Character (chr)" in t for t in texts)
        assert any("Coercion" in t for t in texts)
        assert any("Indexing" in t or "ObjectName" in t for t in texts)
        assert any("filter" in t.lower() for t in texts)
        assert any("select" in t.lower() for t in texts)
        assert any("mutate" in t.lower() for t in texts)


class TestRScriptCardSynthesisAndValidation:
    """Verifies that flashcards synthesized from R scripts adhere strictly to SuperMemo 20 Rules and CardValidator."""

    @pytest.mark.skipif(not WEEK1_R_PATH.exists(), reason="Week 1_2026.R not accessible on this system")
    def test_synthesize_week1_deck_quality(self):
        highlights = extract_r_script_highlights(WEEK1_R_PATH)
        cards = synthesize_cards(highlights, deck_tags=["psyc3031", "week1"], domain="statistics")
        assert len(cards) >= 30

        validator = CardValidator()
        for idx, card in enumerate(cards, 1):
            # 1. Zero 'this concept' or 'Define this concept' emissions
            assert "this concept" not in card["question"].lower()
            assert "this concept" not in card["answer"].lower()
            assert not card["question"].lower().startswith("define this concept")

            # 2. Strict validation
            res = validator.validate_card(card)
            assert res.is_valid is True, f"Card #{idx} failed validation: {res.issues} for card: {card}"

            # 3. Tags and domain badges
            assert "statistics" in card.get("tags", [])
            assert card.get("category_badge") in ("badge-code", "badge-definition", "badge-important")

    @pytest.mark.skipif(not WEEK2_R_PATH.exists(), reason="Week2_2026.R not accessible on this system")
    def test_synthesize_week2_deck_quality(self):
        highlights = extract_r_script_highlights(WEEK2_R_PATH)
        cards = synthesize_cards(highlights, deck_tags=["psyc3031", "week2"], domain="statistics")
        assert len(cards) >= 40

        validator = CardValidator()
        for idx, card in enumerate(cards, 1):
            # 1. Zero 'this concept'
            assert "this concept" not in card["question"].lower()
            assert "this concept" not in card["answer"].lower()

            # 2. Strict validation
            res = validator.validate_card(card)
            assert res.is_valid is True, f"Card #{idx} failed validation: {res.issues} for card: {card}"

            # 3. Tags
            assert "statistics" in card.get("tags", [])


class TestContentShieldHtmlCodeAndAnkiMath:
    """Verifies that ContentShield safely protects HTML <code>/<pre> blocks and Anki math notation."""

    def test_content_shield_protects_html_code_blocks(self):
        shield = ContentShield()
        text = "Execute <pre><code>hsb_10 %>% filter(write <= 50)</code></pre> to subset rows."
        shielded = shield.shield(text)
        assert "<pre><code>" not in shielded
        assert "____SHIELD_CODE_HTML_" in shielded
        unshielded = shield.unshield(shielded)
        assert unshielded == text

    def test_content_shield_protects_anki_math_notation(self):
        shield = ContentShield()
        text = "Formula: [$]\\bar{X} = \\frac{\\sum X}{N}[/$] and display [$$]s^2 = \\frac{SS}{N-1}[/$$]."
        shielded = shield.shield(text)
        assert "[$]" not in shielded
        assert "[$$]" not in shielded
        assert "____SHIELD_MATH_ANKI_" in shielded
        unshielded = shield.unshield(shielded)
        assert unshielded == text
