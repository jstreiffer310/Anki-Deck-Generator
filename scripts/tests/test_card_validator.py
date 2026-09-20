"""
scripts/tests/test_card_validator.py — Comprehensive Unit Tests for Milestone M6.
Tests CardSanitizer, CardValidator, CardDeduplicator, and DeckQualityPipeline.
"""

import sys
from pathlib import Path
import pytest

# Ensure project root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.card_validator import (
    CardSanitizer,
    CardValidator,
    CardDeduplicator,
    DeckQualityPipeline,
    CardValidationResult,
    DeckValidationSummary,
    ValidationIssue,
    strip_html_tags,
)


class TestCardSanitizer:
    """Tests for CardSanitizer: formatting, CSS, citations, index runs, and punctuation."""

    @pytest.fixture
    def sanitizer(self):
        return CardSanitizer()

    def test_whitespace_normalization(self, sanitizer):
        raw = "What   is  \t  dopamine?\r\n\r\nIt   is   a    neurotransmitter.\n\n\n\nNotes here."
        cleaned = sanitizer.normalize_whitespace(raw)
        assert "   " not in cleaned
        assert "\t" not in cleaned
        assert "\r" not in cleaned
        assert "\n\n\n" not in cleaned
        assert cleaned == "What is dopamine?\n\nIt is a neurotransmitter.\n\nNotes here."

    def test_quote_normalization(self, sanitizer):
        raw = '“Smart quotes” and ‘single quotes’ and `backticks`.'
        cleaned = sanitizer.normalize_quotes(raw)
        assert cleaned == '"Smart quotes" and \'single quotes\' and \'backticks\'.'

    def test_strip_css_blocks(self, sanitizer):
        raw = """
        .card { font-family: Arial; font-size: 14px; }
        .nightMode.card { background-color: #121212; }
        HIGH Priority What is dopamine?
        """
        cleaned = sanitizer.strip_css(raw)
        assert ".card" not in cleaned
        assert "font-family" not in cleaned
        assert "HIGH Priority" not in cleaned
        assert "What is dopamine?" in cleaned

    def test_strip_parenthetical_figure_citations(self, sanitizer):
        raw = "Action potentials depolarize the axonal membrane (Figure 3.2)."
        cleaned = sanitizer.strip_figure_citations(raw)
        assert "(Figure 3.2)" not in cleaned
        assert "Action potentials depolarize the axonal membrane ." in cleaned

        raw_fig = "Synthesized in vesicles (Fig. 1.4, page 12) for release."
        cleaned_fig = sanitizer.strip_figure_citations(raw_fig)
        assert "Fig. 1.4" not in cleaned_fig

        raw_table = "Binding affinities vary [Table 2.1] across sub-receptors."
        cleaned_table = sanitizer.strip_figure_citations(raw_table)
        assert "Table 2.1" not in cleaned_table

    def test_strip_index_runs(self, sanitizer):
        # Trailing index runs should be stripped
        raw = "Neurotransmitters in the basal ganglia, 59, 71, 377."
        cleaned = sanitizer.strip_index_runs(raw)
        assert ", 59, 71, 377" not in cleaned
        assert "Neurotransmitters in the basal ganglia." in cleaned

        # Pure index runs must NOT be stripped so validator can flag them
        pure_index = ", 59, 71, 377, 412"
        preserved = sanitizer.strip_index_runs(pure_index)
        assert preserved == pure_index

    def test_normalize_punctuation_question(self, sanitizer):
        # Interrogative words get ?
        assert sanitizer.normalize_punctuation("What is dopamine", is_question=True) == "What is dopamine?"
        assert sanitizer.normalize_punctuation("How does GABA inhibit neurons", is_question=True) == "How does GABA inhibit neurons?"
        assert sanitizer.normalize_punctuation("Why does action potential propagate", is_question=True) == "Why does action potential propagate?"
        assert sanitizer.normalize_punctuation("Where is serotonin synthesized", is_question=True) == "Where is serotonin synthesized?"
        assert sanitizer.normalize_punctuation("Explain the role of acetylcholine", is_question=True) == "Explain the role of acetylcholine?"

        # Replace trailing period with question mark for questions
        assert sanitizer.normalize_punctuation("What is dopamine.", is_question=True) == "What is dopamine?"

        # Preserves existing question mark
        assert sanitizer.normalize_punctuation("What is dopamine?", is_question=True) == "What is dopamine?"

        # Handles trailing HTML tag
        assert sanitizer.normalize_punctuation("What is <b>dopamine</b>", is_question=True) == "What is <b>dopamine</b>?"

    def test_normalize_punctuation_answer(self, sanitizer):
        # Declarative answers receive terminal period
        assert sanitizer.normalize_punctuation("A monoamine neurotransmitter", is_question=False) == "A monoamine neurotransmitter."
        assert sanitizer.normalize_punctuation("A monoamine neurotransmitter.", is_question=False) == "A monoamine neurotransmitter."
        assert sanitizer.normalize_punctuation("Involved in motor control!", is_question=False) == "Involved in motor control!"
        assert sanitizer.normalize_punctuation("Does it cross BBB?", is_question=False) == "Does it cross BBB?"
        assert sanitizer.normalize_punctuation("A <b>neurotransmitter</b>", is_question=False) == "A <b>neurotransmitter</b>."

    def test_sanitize_full_card(self, sanitizer):
        card = {
            "question": "  .card { font-size: 12px; } What is <b>dopamine</b>  ",
            "answer": "A neurotransmitter regulating motor control (Figure 3.2)  ",
            "context": "Lecture 4 (Figure 1.1) notes",
            "keyword": "  “Dopamine”  ",
            "descriptor": "A neurotransmitter regulating motor control (Figure 3.2)",
            "tags": ["neuroscience", "lecture4"]
        }
        sanitized = sanitizer.sanitize(card)
        assert sanitized["question"] == "What is <b>dopamine</b>?"
        assert sanitized["answer"] == "A neurotransmitter regulating motor control."
        assert "(Figure 3.2)" not in sanitized["answer"]
        assert "(Figure 1.1)" not in sanitized["context"]
        assert sanitized["keyword"] == '"Dopamine"'
        assert sanitized["descriptor"] == "A neurotransmitter regulating motor control."


class TestCardValidator:
    """Tests for CardValidator: thresholds, placeholders, vague prompts, corruption, and cloze."""

    @pytest.fixture
    def validator(self):
        return CardValidator()

    def test_valid_bidirectional_cards_pass(self, validator):
        # Forward card: Term -> Def
        card_forward = {
            "card_type": "bidirectional_definition",
            "question": "What is the definition of <b>Dopamine</b>?",
            "answer": "A catecholamine neurotransmitter associated with reward and motor function.",
            "category_badge": "badge-definition",
            "tags": ["definition", "forward"]
        }
        res_f = validator.validate_card(card_forward)
        assert res_f.is_valid is True
        assert len([i for i in res_f.issues if i.severity == "ERROR"]) == 0

        # Reverse card: Def -> Term
        card_reverse = {
            "card_type": "bidirectional_definition",
            "question": "What term is defined by:<br><i>A catecholamine neurotransmitter associated with reward.</i>",
            "answer": "Dopamine",
            "category_badge": "badge-definition",
            "tags": ["definition", "reverse"]
        }
        res_r = validator.validate_card(card_reverse)
        assert res_r.is_valid is True
        assert len([i for i in res_r.issues if i.severity == "ERROR"]) == 0

    def test_empty_question_rejected(self, validator):
        card = {"question": "", "answer": "Valid substantive answer text."}
        res = validator.validate_card(card)
        assert res.is_valid is False
        assert any(i.rule_id == "EMPTY_FIELD" for i in res.issues)

        card_spaces = {"question": "     ", "answer": "Valid substantive answer text."}
        res_spaces = validator.validate_card(card_spaces)
        assert res_spaces.is_valid is False
        assert any(i.rule_id == "EMPTY_FIELD" for i in res_spaces.issues)

    def test_empty_answer_rejected(self, validator):
        card = {"question": "What is the primary role of dopamine?", "answer": ""}
        res = validator.validate_card(card)
        assert res.is_valid is False
        assert any(i.rule_id == "EMPTY_FIELD" for i in res.issues)

        card_spaces = {"question": "What is the primary role of dopamine?", "answer": "   "}
        res_spaces = validator.validate_card(card_spaces)
        assert res_spaces.is_valid is False
        assert any(i.rule_id == "EMPTY_FIELD" for i in res_spaces.issues)

    def test_tautology_rejected(self, validator):
        card = {"question": "Dopamine", "answer": "Dopamine"}
        res = validator.validate_card(card)
        assert res.is_valid is False
        assert any(i.rule_id == "TAUTOLOGY" for i in res.issues)

        card_tags = {"question": "<b>Dopamine</b>", "answer": "dopamine."}
        res_tags = validator.validate_card(card_tags)
        assert res_tags.is_valid is False
        assert any(i.rule_id == "TAUTOLOGY" for i in res_tags.issues)

    def test_question_too_short_rejected(self, validator):
        card = {"question": "Why?", "answer": "Because action potentials occur."}
        res = validator.validate_card(card)
        assert res.is_valid is False
        assert any(i.rule_id == "QUESTION_TOO_SHORT" for i in res.issues)

    def test_question_too_long_rejected(self, validator):
        long_q = "What is the detailed physiological mechanism " + ("and pathway " * 30) + "?"
        assert len(long_q) > 250
        card = {"question": long_q, "answer": "A complex physiological pathway."}
        res = validator.validate_card(card)
        assert res.is_valid is False
        assert any(i.rule_id == "QUESTION_TOO_LONG" for i in res.issues)

    def test_answer_too_short_rejected(self, validator):
        card = {"question": "What is dopamine?", "answer": "No."}
        res = validator.validate_card(card)
        assert res.is_valid is False
        assert any(i.rule_id == "ANSWER_TOO_SHORT" for i in res.issues)

    def test_answer_too_long_rejected(self, validator):
        long_a = "This neurotransmitter operates by " + ("modulating receptor channels in synapses " * 20) + "."
        assert len(long_a) > 500
        card = {"question": "What is dopamine?", "answer": long_a}
        res = validator.validate_card(card)
        assert res.is_valid is False
        assert any(i.rule_id == "ANSWER_TOO_LONG" for i in res.issues)

    def test_length_boundaries(self, validator):
        # 10 chars question passes
        q_10 = "What is it?"
        a_5 = "Valid."
        res = validator.validate_card({"question": q_10, "answer": a_5})
        assert res.is_valid is True

        # Exactly 250 chars question passes
        q_250 = "What is the function of " + "x" * (250 - len("What is the function of ") - 1) + "?"
        assert len(q_250) == 250
        res_250 = validator.validate_card({"question": q_250, "answer": a_5})
        assert not any(i.rule_id == "QUESTION_TOO_LONG" for i in res_250.issues)

        # Exactly 500 chars answer passes
        a_500 = "Valid answer explanation: " + "y" * (500 - len("Valid answer explanation: ") - 1) + "."
        assert len(a_500) == 500
        res_500 = validator.validate_card({"question": q_10, "answer": a_500})
        assert not any(i.rule_id == "ANSWER_TOO_LONG" for i in res_500.issues)

    def test_placeholder_answer_rejected(self, validator):
        placeholders = [
            "Review this concept in your textbook",
            "Content needs verification - check chapter 3",
            "Please check the textbook for details",
            "Answer to be extracted from slide notes",
            "Review this answer before exams",
            "This content needs review",
            "Requires specific course material review",
        ]
        for p in placeholders:
            card = {"question": "What is the primary role of dopamine?", "answer": p}
            res = validator.validate_card(card)
            assert res.is_valid is False, f"Failed to reject placeholder: {p}"
            assert any(i.rule_id == "PLACEHOLDER_ANSWER" for i in res.issues)

    def test_banned_vague_prompt_rejected(self, validator):
        vague_prompts = [
            "What is this concept?",
            "Define this concept in full.",
            "Explain this term and its effects.",
            "What brain structure or concept is being tested here?",
            "What is this phenomenon called?",
        ]
        for v in vague_prompts:
            card = {"question": v, "answer": "A substantive neurotransmitter description."}
            res = validator.validate_card(card)
            assert res.is_valid is False, f"Failed to reject vague prompt: {v}"
            assert any(i.rule_id == "BANNED_VAGUE_PROMPT" for i in res.issues)

    def test_heading_only_prompt_rejected(self, validator):
        # Heading dump without active interrogative
        card_bad = {
            "question": "Key Concept / Mechanism:<br>Neural Transmission",
            "answer": "Transmission of electrical signals along neurons."
        }
        res_bad = validator.validate_card(card_bad)
        assert res_bad.is_valid is False
        assert any(i.rule_id == "HEADING_ONLY_PROMPT" for i in res_bad.issues)

        # Valid prompt with Key Concept heading and active interrogative
        card_good = {
            "question": "Key Concept / Mechanism:<br>What is neural transmission?",
            "answer": "Transmission of electrical signals along neurons."
        }
        res_good = validator.validate_card(card_good)
        assert res_good.is_valid is True
        assert not any(i.rule_id == "HEADING_ONLY_PROMPT" for i in res_good.issues)

    def test_textbook_index_corruption_rejected(self, validator):
        corrupted = [
            ", 59, 71, 377, 412",
            ", 378 Tower",
            "42, 45 Brain",
            "test, 142",
        ]
        for c in corrupted:
            card = {"question": "What is cognitive function?", "answer": c}
            res = validator.validate_card(card)
            assert res.is_valid is False, f"Failed to reject index corruption: {c}"
            assert any(i.rule_id == "CORRUPTED_INDEX_TEXT" for i in res.issues)

    def test_figure_marker_corruption_rejected(self, validator):
        corrupted = [
            "250f Toxins in the brainstem",
            "f Toxins and neural lesions",
        ]
        for c in corrupted:
            card = {"question": "What causes neurodegeneration?", "answer": c}
            res = validator.validate_card(card)
            assert res.is_valid is False, f"Failed to reject figure corruption: {c}"
            assert any(i.rule_id == "CORRUPTED_FIGURE_TEXT" for i in res.issues)

    def test_cloze_valid_preserved(self, validator):
        card = {
            "card_type": "cloze",
            "question": "{{c1::Dopamine}} controls movement and reward signaling."
        }
        res = validator.validate_card(card)
        assert res.is_valid is True
        assert len([i for i in res.issues if i.severity == "ERROR"]) == 0

    def test_cloze_missing_token_rejected(self, validator):
        card = {
            "card_type": "cloze",
            "question": "Dopamine controls movement and reward signaling."
        }
        res = validator.validate_card(card)
        assert res.is_valid is False
        assert any(i.rule_id == "CLOZE_MISSING_TOKEN" for i in res.issues)

    def test_cloze_empty_deletion_rejected(self, validator):
        card = {
            "card_type": "cloze",
            "question": "{{c1::}} controls movement and reward signaling."
        }
        res = validator.validate_card(card)
        assert res.is_valid is False
        assert any(i.rule_id == "CLOZE_EMPTY_DELETION" for i in res.issues)

    def test_cloze_length_bounds(self, validator):
        # Too short (<15)
        card_short = {
            "card_type": "cloze",
            "question": "{{c1::GABA}} acts."
        }
        res_short = validator.validate_card(card_short)
        assert res_short.is_valid is False
        assert any(i.rule_id == "CLOZE_TOO_SHORT" for i in res_short.issues)

        # Too long (>500)
        long_cloze = "{{c1::Dopamine}} is a vital chemical " + ("and synaptic messenger in the human brain " * 20) + "."
        assert len(long_cloze) > 500
        card_long = {
            "card_type": "cloze",
            "question": long_cloze
        }
        res_long = validator.validate_card(card_long)
        assert res_long.is_valid is False
        assert any(i.rule_id == "CLOZE_TOO_LONG" for i in res_long.issues)

    def test_wordiness_warning(self, validator):
        verbose_answer = (
            "This neurotransmitter operates by modulating ionotropic channels across multiple synaptic junctions, "
            "facilitating depolarization and hyperpolarization cascades that govern executive control, working memory, "
            "locomotor initiation, cognitive flexibility, emotion regulation, reward anticipation, and complex behavioral decision making processes."
        )
        assert len(verbose_answer.split()) > 35
        card = {
            "question": "What is the primary function of dopamine?",
            "answer": verbose_answer
        }
        res = validator.validate_card(card)
        assert res.is_valid is True  # Warning does not reject card
        assert any(i.severity == "WARNING" and i.rule_id == "ANSWER_WORDY" for i in res.issues)

    def test_tuple_unpacking_interface(self, validator):
        card = {"question": "What is dopamine?", "answer": "A neurotransmitter."}
        is_valid, issues = validator.validate_card(card)
        assert is_valid is True
        assert isinstance(issues, list)


class TestCardDeduplicator:
    """Tests for CardDeduplicator: signature matching, tag merging, and bidirectional safety."""

    @pytest.fixture
    def deduplicator(self):
        return CardDeduplicator()

    def test_exact_duplicate_deduplicated(self, deduplicator):
        cards = [
            {
                "question": "What is the definition of <b>Dopamine</b>?",
                "answer": "A neurotransmitter regulating movement and reward.",
                "tags": ["lecture1", "biology"],
                "context": "Chapter 4"
            },
            {
                "question": "What is the definition of <b>Dopamine</b>?",
                "answer": "A neurotransmitter regulating movement and reward.",
                "tags": ["lecture2", "high_yield"],
                "context": "Slide 12"
            }
        ]
        unique_cards, removed = deduplicator.deduplicate(cards, return_count=True)
        assert len(unique_cards) == 1
        assert removed == 1
        assert deduplicator.duplicates_removed_count == 1
        # Merged tags
        assert set(unique_cards[0]["tags"]) == {"lecture1", "biology", "lecture2", "high_yield"}
        # Preserved context
        assert unique_cards[0]["context"] == "Chapter 4"

    def test_bidirectional_cards_not_falsely_deduplicated(self, deduplicator):
        card_forward = {
            "card_type": "bidirectional_definition",
            "question": "What is the definition of <b>Dopamine</b>?",
            "answer": "A neurotransmitter regulating movement and reward.",
            "tags": ["definition", "forward"]
        }
        card_reverse = {
            "card_type": "bidirectional_definition",
            "question": "What term is defined by:<br><i>A neurotransmitter regulating movement and reward.</i>",
            "answer": "Dopamine",
            "tags": ["definition", "reverse"]
        }
        unique_cards = deduplicator.deduplicate([card_forward, card_reverse])
        assert len(unique_cards) == 2
        assert deduplicator.duplicates_removed_count == 0

    def test_multiple_duplicates_count(self, deduplicator):
        base_card = {
            "question": "What is acetylcholine?",
            "answer": "A neurotransmitter involved in autonomic function.",
            "tags": ["neuro"]
        }
        deck = [base_card.copy() for _ in range(5)]
        unique_cards = deduplicator.deduplicate(deck)
        assert len(unique_cards) == 1
        assert deduplicator.duplicates_removed_count == 4

    def test_cloze_deduplication(self, deduplicator):
        c1 = {"card_type": "cloze", "question": "{{c1::Dopamine}} regulates reward.", "tags": ["tagA"]}
        c2 = {"card_type": "cloze", "question": "{{c1::Dopamine}} regulates reward.", "tags": ["tagB"]}
        c3 = {"card_type": "cloze", "question": "Dopamine regulates {{c1::reward}}.", "tags": ["tagC"]}

        unique = deduplicator.deduplicate([c1, c2, c3])
        assert len(unique) == 2
        assert deduplicator.duplicates_removed_count == 1
        assert set(unique[0]["tags"]) == {"tagA", "tagB"}


class TestDeckQualityPipeline:
    """Tests for DeckQualityPipeline: end-to-end flow, telemetry, strict mode, and edge cases."""

    @pytest.fixture
    def pipeline(self):
        return DeckQualityPipeline()

    def test_pipeline_full_flow(self, pipeline):
        deck = [
            # 1. Valid forward card
            {
                "question": "What is the definition of <b>Dopamine</b>?",
                "answer": "A neurotransmitter regulating motor control.",
                "tags": ["lecture1"]
            },
            # 2. Valid reverse card (must NOT be deduplicated with forward)
            {
                "question": "What term is defined by:<br><i>A neurotransmitter regulating motor control.</i>",
                "answer": "Dopamine",
                "tags": ["lecture1"]
            },
            # 3. Duplicate of forward card (should be merged)
            {
                "question": "What is the definition of <b>Dopamine</b>?",
                "answer": "A neurotransmitter regulating motor control.",
                "tags": ["lecture2"]
            },
            # 4. Inadequate placeholder card (should be rejected)
            {
                "question": "What is serotonin?",
                "answer": "Review this concept in your textbook"
            },
            # 5. Corrupted index card (should be rejected)
            {
                "question": "What is the basal ganglia?",
                "answer": ", 59, 71, 377, 412"
            },
            # 6. Messy card with CSS that should be sanitized and accepted
            {
                "question": ".card { font-family: Arial; } What is <b>GABA</b>?",
                "answer": "The primary inhibitory neurotransmitter."
            }
        ]

        clean_cards, summary = pipeline.process(deck, strict=False)

        # Expected:
        # Total input: 6
        # Rejected: 2 (card 4 placeholder, card 5 index corruption)
        # Valid cards before dedup: 4 (card 1, card 2, card 3, card 6)
        # Deduplicated: card 3 merged into card 1 (1 duplicate removed)
        # Final approved: 3 cards
        assert summary.total_input_cards == 6
        assert summary.rejected_cards_count == 2
        assert summary.duplicates_removed_count == 1
        assert summary.valid_cards_count == 3
        assert len(clean_cards) == 3

        # Check telemetry keys
        telemetry = summary.to_dict()
        assert telemetry["total_input"] == 6
        assert telemetry["rejected"] == 2
        assert telemetry["valid"] == 3
        assert telemetry["duplicates_removed"] == 1
        assert telemetry.get("PLACEHOLDER_ANSWER", 0) >= 1
        assert telemetry.get("CORRUPTED_INDEX_TEXT", 0) >= 1

        # Check merged tags on Card 1
        card_1 = [c for c in clean_cards if "Dopamine" in c["question"] and "definition" in c["question"]][0]
        assert set(card_1["tags"]) == {"lecture1", "lecture2"}

    def test_pipeline_strict_mode(self, pipeline):
        deck = [
            {"question": "What is dopamine?", "answer": "Review this concept in your textbook"}
        ]
        with pytest.raises(ValueError, match="Strict deck quality validation failed"):
            pipeline.process(deck, strict=True)

    def test_pipeline_empty_deck(self, pipeline):
        clean_cards, summary = pipeline.process([], strict=False)
        assert len(clean_cards) == 0
        assert summary.total_input_cards == 0
        assert summary.valid_cards_count == 0
        assert summary.rejected_cards_count == 0

    def test_pipeline_all_invalid(self, pipeline):
        deck = [
            {"question": "", "answer": ""},
            {"question": "Why?", "answer": "No"},
            {"question": "What is this concept?", "answer": "Check textbook"},
        ]
        clean_cards, summary = pipeline.process(deck, strict=False)
        assert len(clean_cards) == 0
        assert summary.rejected_cards_count == 3
        assert summary.valid_cards_count == 0

    def test_process_deck_contract(self, pipeline):
        deck = [
            {"question": "What is acetylcholine?", "answer": "A neurotransmitter in neuromuscular junctions."}
        ]
        cards_out, telemetry = pipeline.process_deck(deck)
        assert len(cards_out) == 1
        assert isinstance(telemetry, dict)
        assert telemetry["total_input"] == 1
        assert telemetry["valid"] == 1
        assert telemetry["rejected"] == 0
