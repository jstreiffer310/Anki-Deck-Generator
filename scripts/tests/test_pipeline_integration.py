"""
test_pipeline_integration.py — Integration Test Suite for AnkiDeckCreator Pipeline
Verifies end-to-end integration across:
- Highlight extraction and color classification (extract_and_generate.py)
- Semantic parsing and SuperMemo knowledge formulation (semantic_parser.py)
- Anki package compilation with Standard and Cloze models (genanki)
- Agent-as-Judge 30-point evaluation and hard veto verification (evaluate_cards_judge.py)
- CLI invocation for pipeline compilation and judge evaluation
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

# Ensure project root and scripts dir are on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from scripts.extract_and_generate import (
    extract_document_highlights,
    synthesize_cards,
    create_deck_package,
    resolve_deck_naming,
    clean_phrase,
    ANKI_MODEL,
    ANKI_CLOZE_MODEL,
    CONFIG,
)
from scripts.evaluate_cards_judge import CardJudgeRubric
from scripts.semantic_parser import SemanticCardParser
from scripts.ollama_runtime import OllamaRuntimeManager


@pytest.fixture
def sample_docx_path():
    """Returns absolute path to sample_lecture_notes.docx."""
    p = SCRIPTS_DIR / "tests" / "sample_lecture_notes.docx"
    assert p.exists(), f"Missing sample lecture notes at {p}"
    return p


@pytest.fixture
def judge():
    """Returns an instance of CardJudgeRubric."""
    return CardJudgeRubric()


class TestPipelineExtractionAndSynthesis:
    """Tests highlight extraction and semantic card synthesis."""

    def test_extract_sample_lecture_notes(self, sample_docx_path):
        """Verifies that sample_lecture_notes.docx extracts 4 highlighted paragraphs."""
        data = extract_document_highlights(str(sample_docx_path))
        assert len(data) == 4, f"Expected 4 highlighted sections, found {len(data)}"
        for item in data:
            assert "heading" in item
            assert "full_paragraph" in item
            assert "highlights" in item
            assert len(item["highlights"]) >= 1

    def test_synthesize_cards_generates_standard_and_cloze(self, sample_docx_path):
        """Verifies synthesis generates both Q/A and Cloze cards adhering to 20 rules."""
        data = extract_document_highlights(str(sample_docx_path))
        cards = synthesize_cards(data, deck_tags=["integration_test"])

        assert len(cards) >= 6, f"Expected at least 6 cards, got {len(cards)}"

        cloze_cards = [c for c in cards if c.get("card_type") == "cloze" or "{{c1::" in c.get("question", "")]
        bidirectional_cards = [c for c in cards if c.get("card_type") == "bidirectional_definition"]
        active_recall_cards = [c for c in cards if c.get("card_type") == "active_recall_qa"]

        assert len(cloze_cards) >= 1, "Expected at least 1 cloze deletion card"
        assert len(bidirectional_cards) >= 2, "Expected at least 2 bidirectional definition cards"
        assert len(active_recall_cards) >= 1, "Expected at least 1 active recall card"

    def test_synthesize_cards_zero_this_concept(self, sample_docx_path):
        """Guarantees 0% occurrence of banned phrase 'this concept' across all generated cards."""
        data = extract_document_highlights(str(sample_docx_path))
        cards = synthesize_cards(data)

        banned_phrases = ["this concept", "this term", "this phenomenon"]
        for i, c in enumerate(cards, 1):
            q = c["question"].lower()
            a = c["answer"].lower()
            for bp in banned_phrases:
                assert bp not in q, f"Card {i} question contains banned phrase '{bp}': {c['question']}"
                assert bp not in a, f"Card {i} answer contains banned phrase '{bp}': {c['answer']}"

    def test_synthesize_cards_zero_heading_dumps(self, sample_docx_path):
        """Guarantees 0% occurrence of raw heading dump prompts in generated cards."""
        data = extract_document_highlights(str(sample_docx_path))
        cards = synthesize_cards(data)

        for i, c in enumerate(cards, 1):
            q = c["question"]
            if "<b>Key Concept / Mechanism:</b><br>" in q:
                assert any(w in q for w in ["What", "Which", "Why", "How", "Identify", "Explain"]), (
                    f"Card {i} is a raw heading prompt dump: {q}"
                )


class TestAgentAsJudgeEvaluation:
    """Validates generated cards against the Agent-as-Judge 30-point rubric."""

    def test_all_sample_cards_pass_judge(self, sample_docx_path, judge):
        """Evaluates all synthesized cards from sample lecture notes against judge rubric."""
        data = extract_document_highlights(str(sample_docx_path))
        cards = synthesize_cards(data)

        report = judge.evaluate_deck(cards)

        assert report["total_cards"] == len(cards)
        assert report["veto_count"] == 0, f"Judge reported {report['veto_count']} hard vetoes: {report}"
        assert report["average_score"] >= 25.0, f"Average card score {report['average_score']} < 25.0"
        assert report["passed_cards"] == report["total_cards"]
        assert report["deck_passed"] is True

    def test_judge_evaluates_card_dimensions(self, judge):
        """Verifies individual dimension scoring across all 6 cognitive dimensions."""
        card = {
            "card_type": "bidirectional_definition",
            "keyword": "Tolerance",
            "descriptor": "A state of progressively decreasing responsiveness to repeated drug doses.",
            "question": "What is the definition of <b>Tolerance</b>?",
            "answer": "A state of progressively decreasing responsiveness to repeated drug doses.",
            "category_badge": "badge-definition",
            "context": "PSYC 3590 | Pharmacodynamics",
            "tags": ["definition", "forward", "psyc3590"]
        }
        res = judge.evaluate_card(card)
        assert res["passed"] is True
        assert res["total_score"] >= 25
        assert res["vetoes"] == []
        assert "D1_Atomicity" in res["dimension_scores"]
        assert "D2_Wording" in res["dimension_scores"]
        assert "D3_Keyword_Descriptor" in res["dimension_scores"]
        assert "D4_Avoid_Sets" in res["dimension_scores"]
        assert "D5_Recall_Recognition" in res["dimension_scores"]
        assert "D6_Context_Anchoring" in res["dimension_scores"]


class TestDeckPackagingAndArchiveIntegrity:
    """Verifies SQLite database and genanki packaging of standard and cloze models."""

    def test_create_deck_package_generates_valid_apkg(self, sample_docx_path, tmp_path):
        """Compiles deck to .apkg and inspects the internal SQLite database."""
        data = extract_document_highlights(str(sample_docx_path))
        cards = synthesize_cards(data, deck_tags=["psyc3590"])
        deck_title = "PSYC 3590 (Drugs & Behaviour):Lecture 2"
        out_filename = "integration_test_deck.apkg"

        # Temporarily override output directory to tmp_path
        original_out = CONFIG.get("output_directory")
        CONFIG["output_directory"] = str(tmp_path)
        try:
            out_path = create_deck_package(deck_title, cards, output_filename=out_filename)
            assert out_path.exists()
            assert out_path.is_file()

            # Verify ZIP structure
            with zipfile.ZipFile(out_path, "r") as zf:
                namelist = zf.namelist()
                assert "collection.anki2" in namelist

                # Extract and query SQLite database
                with tempfile.TemporaryDirectory() as extract_dir:
                    zf.extract("collection.anki2", extract_dir)
                    db_file = Path(extract_dir) / "collection.anki2"
                    conn = sqlite3.connect(db_file)
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(*) FROM notes")
                    note_count = cur.fetchone()[0]
                    assert note_count >= 6

                    cur.execute("SELECT flds, tags FROM notes")
                    notes = cur.fetchall()
                    has_cloze_note = False
                    has_qa_note = False

                    for flds, tags_str in notes:
                        fields = flds.split("\x1f")
                        assert len(fields) >= 4
                        if "{{c1::" in fields[0]:
                            has_cloze_note = True
                        if "What" in fields[0]:
                            has_qa_note = True

                    assert has_cloze_note, "Expected at least one note with cloze field syntax in SQLite database"
                    assert has_qa_note, "Expected at least one note with active recall Q/A in SQLite database"
                    conn.close()
        finally:
            if original_out:
                CONFIG["output_directory"] = original_out
            else:
                CONFIG.pop("output_directory", None)


class TestCLIExecutionAndJudgeIntegration:
    """Verifies end-to-end command line invocations of both scripts."""

    def test_extract_and_generate_cli_execution(self, sample_docx_path, tmp_path):
        """Runs scripts/extract_and_generate.py via subprocess and asserts exit code 0."""
        cmd = [
            sys.executable,
            str(SCRIPTS_DIR / "extract_and_generate.py"),
            str(sample_docx_path),
            "--class-name", "PSYC 3590",
            "--chapter", "Lecture 2",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        assert res.returncode == 0, f"CLI failed with error:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        assert "Synthesized" in res.stdout
        assert "Successfully generated Anki deck" in res.stdout

    def test_evaluate_cards_judge_cli_on_apkg(self, sample_docx_path, tmp_path, judge):
        """Runs evaluate_cards_judge.py on the compiled .apkg and asserts 100% pass."""
        data = extract_document_highlights(str(sample_docx_path))
        cards = synthesize_cards(data)
        out_apkg = tmp_path / "judge_cli_test.apkg"

        original_out = CONFIG.get("output_directory")
        CONFIG["output_directory"] = str(tmp_path)
        try:
            create_deck_package("PSYC 3590:Judge CLI Test", cards, output_filename="judge_cli_test.apkg")
            assert out_apkg.exists()

            cmd = [
                sys.executable,
                str(SCRIPTS_DIR / "evaluate_cards_judge.py"),
                "--deck", str(out_apkg),
                "--json",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            assert res.returncode == 0, f"Judge CLI returned non-zero code:\n{res.stdout}\n{res.stderr}"

            report = json.loads(res.stdout)
            assert report["deck_passed"] is True
            assert report["veto_count"] == 0
            assert report["average_score"] >= 25.0
            assert report["passed_cards"] == report["total_cards"]
        finally:
            if original_out:
                CONFIG["output_directory"] = original_out
            else:
                CONFIG.pop("output_directory", None)
