"""
Unit tests for Milestone M17: Curricular Challenger & Workflow Governor.
Verifies:
  - CurricularChallenger syntax auditing and syllabus coverage analysis.
  - WorkflowGovernor DSDS semantic depth scoring, Muda pruning, and Poka-Yoke error-proofing.
"""

from pathlib import Path
import pytest

from scripts.curricular_challenger import CurricularChallenger
from scripts.workflow_governor import WorkflowGovernor


class TestCurricularChallenger:
    """Verifies Curricular Challenger Agent capabilities."""

    def test_syntax_audit_catches_dangling_prepositions(self):
        challenger = CurricularChallenger("PSYC 2110")
        bad_cards = [
            {"keyword": "Term", "question": "What is the primary role of?", "answer": "Valid description."},
            {"keyword": "Term2", "question": "Valid question?", "answer": "The mechanism consists of in"}
        ]
        res = challenger.audit_syntax_and_linguistics(bad_cards)
        assert res["failed_cards"] == 2
        assert not res["is_clean"]
        rules = {d["rule"] for d in res["defects"]}
        assert "DANGLING_PREPOSITION_QUESTION" in rules
        assert "DANGLING_PREPOSITION_ANSWER" in rules

    def test_syntax_audit_catches_tautologies(self):
        challenger = CurricularChallenger("PSYC 2110")
        tautological_card = [
            {"keyword": "Synapse", "question": "What is a synapse?", "answer": "What is a synapse?"}
        ]
        res = challenger.audit_syntax_and_linguistics(tautological_card)
        assert res["failed_cards"] == 1
        assert res["defects"][0]["rule"] == "TAUTOLOGY"

    def test_syntax_audit_catches_banned_phrases(self):
        challenger = CurricularChallenger("PSYC 2110")
        banned_card = [
            {"keyword": "Concept", "question": "What is this concept?", "answer": "Valid explanation."}
        ]
        res = challenger.audit_syntax_and_linguistics(banned_card)
        assert res["failed_cards"] == 1
        assert res["defects"][0]["rule"] == "BANNED_GENERIC_PHRASE"

    def test_syntax_audit_catches_unclosed_html_tags(self):
        challenger = CurricularChallenger("PSYC 2110")
        unclosed_card = [
            {"keyword": "BoldTerm", "question": "What is <b>BoldTerm without close tag?", "answer": "Valid answer."}
        ]
        res = challenger.audit_syntax_and_linguistics(unclosed_card)
        assert res["failed_cards"] == 1
        assert res["defects"][0]["rule"] == "UNCLOSED_HTML_TAG"

    def test_syntax_audit_passes_clean_cards(self):
        challenger = CurricularChallenger("PSYC 2110")
        clean_cards = [
            {
                "keyword": "Developmental Niche",
                "question": "What is the theoretical definition and framework of the <b>Developmental Niche</b>?",
                "answer": "Framework conceptualizing how culture structures child development through three interacting subsystems.",
                "category_badge": "badge-definition",
                "tags": ["definition", "forward"]
            },
            {
                "keyword": "Physical and Social Settings",
                "question": "What constitutes the <b>Physical and Social Settings</b> subsystem?",
                "answer": "The physical and social environment shaping daily life.",
                "category_badge": "badge-important",
                "tags": ["decomposed_subcomponent"]
            }
        ]
        res = challenger.audit_syntax_and_linguistics(clean_cards)
        assert res["failed_cards"] == 0
        assert res["is_clean"]

    def test_coverage_gap_analysis(self):
        challenger = CurricularChallenger("PSYC 2110")
        cards = [
            {"keyword": "Developmental Niche", "question": "What is the developmental niche?", "answer": "Cultural framework."},
            {"keyword": "Bronfenbrenner", "question": "What is ecological systems theory?", "answer": "Microsystem, mesosystem, etc."},
            {"keyword": "Piaget", "question": "What are Piaget's stages of cognitive development?", "answer": "Sensorimotor and preoperational."},
            {"keyword": "Attachment", "question": "What is attachment theory and strange situation?", "answer": "Ainsworth classifications."},
        ]
        res = challenger.audit_coverage(cards)
        assert res["covered_topics_count"] >= 4
        assert res["coverage_score"] > 0.20
        assert "Developmental niche (Super & Harkness)" in res["covered_topics"]
        assert "Bronfenbrenner's ecological systems theory" in res["covered_topics"]


class TestWorkflowGovernor:
    """Verifies Kaizen Workflow Governor continuous improvement operations."""

    def test_detect_and_prune_muda(self):
        gov = WorkflowGovernor()
        mixed_cards = [
            {"keyword": "Valid Concept", "question": "What is ADME?", "answer": "Absorption, distribution, metabolism, excretion."},
            {"keyword": "Exam Logistics", "question": "When is the midterm date?", "answer": "Midterm date is on October 24 via Zoom link."},
            {"keyword": "Textbook Info", "question": "Textbook purchasing", "answer": "Purchase the textbook at the bookstore or see page 42."},
        ]
        clean, pruned = gov.detect_and_prune_muda(mixed_cards)
        assert len(clean) == 1
        assert len(pruned) == 2
        assert clean[0]["keyword"] == "Valid Concept"

    def test_dsds_scoring_depth_metrics(self):
        gov = WorkflowGovernor(target_dsds=0.85)
        rich_cards = [
            {
                "keyword": "Colchicine",
                "question": "What is the physiological mechanism of <b>Colchicine</b>?",
                "answer": "Binds to tubulin dimers to prevent microtubule polymerization.<br><br><b>Example/Application:</b> Gout treatment.",
                "tags": ["applied", "pharmacology", "definition"],
                "taxonomy": "concept_mechanism"
            },
            {
                "keyword": "Developmental Niche",
                "question": "What constitutes the Physical Settings subsystem?",
                "answer": "Household density and living arrangement.<br><br><b>Concrete Examples:</b> Co-sleeping arrangements.",
                "tags": ["applied", "decomposed_subcomponent", "umbrella_model"],
                "taxonomy": "term_definition"
            },
            {
                "keyword": "Therapeutic Index",
                "card_type": "cloze",
                "question": "Identify the missing parameter: TI = {{c1::LD50 / ED50}}",
                "answer": "LD50 / ED50",
                "tags": ["cloze", "high_yield"]
            }
        ]
        dsds = gov.compute_dsds(rich_cards)
        assert dsds["dsds_score"] >= 0.85
        assert dsds["meets_target"]
        assert dsds["breakdown"]["applied_examples_rate"] >= 0.60

    def test_poka_yoke_verifies_clean_deck(self):
        gov = WorkflowGovernor()
        cards = [
            {"keyword": "TermA", "question": "Q1", "answer": "A1", "tags": ["Chapter_1"]},
            {"keyword": "TermB", "question": "Q2", "answer": "A2", "tags": ["Chapter_1"]},
            {"keyword": "TermA", "question": "Q3", "answer": "A3", "tags": ["Chapter_1"]},
        ]
        py = gov.poka_yoke_audit(cards)
        assert py["status"] == "PASS"
        assert py["distance_1_pairs"] == 0
        assert py["chapter_tagged_rate"] == 1.0
        assert py["veto_violations"] == 0

    def test_poka_yoke_catches_distance_one_and_veto_defects(self):
        gov = WorkflowGovernor()
        defective_cards = [
            {"keyword": "IdenticalTerm", "question": "What is IdenticalTerm?", "answer": "Def 1"},
            {"keyword": "IdenticalTerm", "question": "What term means Def 1?", "answer": "IdenticalTerm"},
            {"keyword": "BannedPhrase", "question": "What is this concept?", "answer": "Def"}
        ]
        py = gov.poka_yoke_audit(defective_cards)
        assert py["status"] == "FAIL"
        assert py["distance_1_pairs"] == 1
        assert py["veto_violations"] == 1

    def test_governance_cycle_generates_markdown_report(self, tmp_path):
        gov = WorkflowGovernor(target_dsds=0.85)
        cards = [
            {
                "keyword": "Cocaine",
                "question": "What is the synaptic mechanism of <b>Cocaine</b>?",
                "answer": "Blocks DAT to increase synaptic dopamine concentration.<br><br><b>Example/Application:</b> High abuse potential.",
                "tags": ["Chapter_4", "applied", "pharmacology"],
                "taxonomy": "concept_mechanism"
            }
        ]
        report_file = tmp_path / "kaizen_report.md"
        report = gov.run_governance_cycle(cards, output_report_path=report_file)

        assert report["overall_status"] in ("PASS", "WARN")
        assert report_file.exists()
        content = report_file.read_text(encoding="utf-8")
        assert "Domain Semantic Depth Score" in content
        assert "Poka-Yoke" in content
