"""
scripts/tests/test_m9_adversarial_challenger.py — Empirical Adversarial Stress Harness for Milestone M9.
Authored by Challenger 1 (challenger_m9_1).

Tests the failure mode defenses in scripts/semantic_parser.py and scripts/extract_and_generate.py:
1. Complex theorist critiques:
   - "Chomsky (1959) REJECTED and CRITICIZED Skinner's verbal behavior model"
   - "Piaget CONTRASTS with Vygotsky"
   - "ARGUING THAT behaviorism is insufficient"
   - Author + year citation variants: "Chomsky (1959) REJECTED", "Piaget (1952) CONTRASTS", etc.
2. Complex definitional relative clauses:
   - "The unique biological process in which stem cells differentiate into mature neurons"
   - "A pathological state of continuous synaptic depression"
   - "A state of continuous synaptic depression"
   - "A mechanism that regulates dopamine release"
   - "A condition where synaptic transmission is impaired"
   - "A formation of amyloid plaques"
3. Pathological interrogatives:
   - "What is the difference between Type I and Type II errors?????? (hint: alpha vs beta)"
   - "Why do SSRIs take 2-4 weeks to produce clinical efficacy?"
   - Standalone and paired interrogatives
4. Inverted highlights:
   - 30-word definitions in yellow with 1-word terms in green
   - 6-word definitional phrases in yellow with 4-word terms in green
"""

import re
import pytest
from typing import List, Dict, Any

from scripts.semantic_parser import (
    is_valid_concept_keyword,
    resolve_keyword_descriptor_pair,
    split_highlight_fallback,
    SemanticCardParser,
    is_interrogative_note,
    CRITIQUE_STANDALONE_WORDS,
    CRITIQUE_ACTION_REGEX,
    DEFINITIONAL_FRAMING_REGEX,
    RELATIVE_CLAUSE_REGEX,
)
from scripts.extract_and_generate import synthesize_cards
from scripts.card_validator import CardValidator, strip_html_tags


# ============================================================================
# 1. Complex Theorist Critiques
# ============================================================================

class TestAdversarialTheoristCritiques:
    """Stress-tests critique verbs, compound critiques, and author-citation combinations."""

    @pytest.mark.parametrize("critique_input", [
        "Chomsky (1959) REJECTED and CRITICIZED",
        "Chomsky (1959) REJECTED",
        "Chomsky (1959) CRITICIZED",
        "Piaget (1952) CONTRASTS",
        "Vygotsky (1978) CHALLENGED",
        "Popper (1963) REFUTED",
        "Kahneman & Tversky (1979) CRITICIZE",
        "Chomsky et al. REJECTS",
    ])
    def test_theorist_with_citation_year_disqualified_as_keyword(self, critique_input):
        """
        Adversarial Test: Academic notes routinely include publication years or co-authors
        (e.g., 'Chomsky (1959) REJECTED'). These MUST NOT qualify as concept keywords.
        """
        assert not is_valid_concept_keyword(critique_input), (
            f"Critique with publication citation '{critique_input}' was incorrectly evaluated "
            f"as a valid concept keyword!"
        )

    def test_piaget_contrasts_with_vygotsky(self):
        """Verify 'Piaget CONTRASTS with Vygotsky' is disqualified and matches critique pattern."""
        phrase = "Piaget CONTRASTS with Vygotsky"
        assert not is_valid_concept_keyword(phrase)
        assert CRITIQUE_ACTION_REGEX.search(phrase) is not None

    def test_arguing_that_behaviorism_is_insufficient(self):
        """Verify 'ARGUING THAT behaviorism is insufficient' is disqualified and matches critique pattern."""
        phrase = "ARGUING THAT behaviorism is insufficient"
        assert not is_valid_concept_keyword(phrase)
        assert CRITIQUE_ACTION_REGEX.search(phrase) is not None

    def test_compound_critique_with_citation_synthesize_cards(self):
        """
        When notes contain a critique highlight with citation year paired with a substantive target,
        synthesize_cards MUST NOT create a bidirectional definition card where the keyword is the critique.
        """
        structured = [{
            "heading": "Linguistic Theory",
            "full_paragraph": "Chomsky (1959) REJECTED and CRITICIZED Skinner's verbal behavior model.",
            "highlights": [
                {"raw_color": "yellow", "category": "yellow", "text": "Chomsky (1959) REJECTED and CRITICIZED"},
                {"raw_color": "green", "category": "green", "text": "Skinner's verbal behavior model"}
            ]
        }]
        cards = synthesize_cards(structured)
        for c in cards:
            kw = c.get("keyword", "")
            assert "REJECTED" not in kw, f"Action verb emitted as concept keyword: '{kw}'"
            assert "CRITICIZED" not in kw, f"Action verb emitted as concept keyword: '{kw}'"
            assert not c.get("question", "").startswith("What is the definition of <b>Chomsky (1959)"), (
                f"Generated bogus definition card for critique: {c.get('question')}"
            )

    def test_card_validator_rejects_citation_critique_keyword(self):
        """CardValidator MUST reject cards that have a citation critique keyword."""
        validator = CardValidator()
        bad_card = {
            "card_type": "bidirectional_definition",
            "keyword": "Chomsky (1959) REJECTED and CRITICIZED",
            "descriptor": "Skinner's verbal behavior model.",
            "question": "What is the definition of <b>Chomsky (1959) REJECTED and CRITICIZED</b>?",
            "answer": "Skinner's verbal behavior model.",
            "category_badge": "badge-definition",
            "context": "Linguistics",
            "tags": ["definition"]
        }
        res = validator.validate_card(bad_card)
        assert not res.is_valid, (
            "CardValidator failed to reject card with 'Chomsky (1959) REJECTED and CRITICIZED' as keyword!"
        )


# ============================================================================
# 2. Complex Definitional Relative Clauses
# ============================================================================

class TestAdversarialDefinitionalRelativeClauses:
    """Stress-tests relative clauses and definitional framing phrases with articles and modifiers."""

    @pytest.mark.parametrize("framing_input", [
        "The unique biological process in which stem cells differentiate into mature neurons",
        "A pathological state of continuous synaptic depression",
        "A state of continuous synaptic depression",
        "A mechanism that regulates dopamine release",
        "A condition where synaptic transmission is impaired",
        "A formation of amyloid plaques",
        "A movement of calcium ions across membranes",
    ])
    def test_framing_with_indefinite_article_disqualified_as_keyword(self, framing_input):
        """
        Adversarial Test: Framing phrases beginning with 'A ' or 'An ' or containing modifiers
        MUST NOT be accepted as valid concept keywords.
        """
        assert not is_valid_concept_keyword(framing_input), (
            f"Definitional framing phrase '{framing_input}' was incorrectly evaluated as a valid concept keyword!"
        )

    @pytest.mark.parametrize("framing_clause,copula", [
        ("A mechanism that regulates dopamine release", "regulates"),
        ("A condition where synaptic transmission is impaired", "is"),
        ("A state of continuous synaptic depression", "state of"),
    ])
    def test_split_highlight_fallback_does_not_emit_framing_keyword(self, framing_clause, copula):
        """
        split_highlight_fallback MUST NOT split on subordinate verbs inside relative/framing clauses
        to emit fragments like 'Mechanism that' or 'Condition where synaptic transmission'.
        """
        term, descriptor, tier = split_highlight_fallback(
            highlight_text=framing_clause,
            paragraph_prefix="",
            heading_context="Neuroscience"
        )
        assert term != "Mechanism that", "Emitted broken 'Mechanism that' as concept keyword!"
        assert "Condition where" not in term, f"Emitted broken condition framing as keyword: '{term}'"
        assert term != "State of continuous synaptic depression", (
            f"Emitted full definitional framing phrase as keyword: '{term}'"
        )
        assert is_valid_concept_keyword(term), f"Emitted invalid concept keyword: '{term}'"

    def test_framing_yellow_paired_with_term_green_synthesize_cards(self):
        """
        When yellow is a 6-word definitional phrase and green is a 4-word term:
        synthesize_cards MUST NOT produce an inverted card with the definition as the keyword.
        """
        structured = [{
            "heading": "Neuroscience",
            "full_paragraph": "",
            "highlights": [
                {"raw_color": "yellow", "category": "yellow", "text": "A mechanism that regulates dopamine release"},
                {"raw_color": "green", "category": "green", "text": "Presynaptic autoreceptor feedback control"}
            ]
        }]
        cards = synthesize_cards(structured)
        assert len(cards) >= 1, "synthesize_cards dropped the highlight pair!"
        for c in cards:
            kw = c.get("keyword", "")
            assert kw != "A mechanism that regulates dopamine release", (
                f"Definitional framing was emitted as the concept keyword: '{kw}'"
            )
            assert "Mechanism that" not in kw, f"Broken clause emitted as keyword: '{kw}'"
            assert kw == "Presynaptic autoreceptor feedback control", (
                f"Expected term 'Presynaptic autoreceptor feedback control' as keyword, got '{kw}'"
            )


# ============================================================================
# 3. Pathological Interrogatives
# ============================================================================

class TestAdversarialPathologicalInterrogatives:
    """Stress-tests questions with hint parentheticals, excessive punctuation, and paired answers."""

    def test_interrogative_with_hints_and_excessive_question_marks(self):
        """
        'What is the difference between Type I and Type II errors?????? (hint: alpha vs beta)'
        must be recognized as an interrogative note, have ??? collapsed, and extract the hint as answer.
        """
        raw_text = "What is the difference between Type I and Type II errors?????? (hint: alpha vs beta)"
        assert is_interrogative_note(raw_text)

        parser = SemanticCardParser(runtime_manager=None)
        cards = parser.parse_with_fallback(raw_text, highlight_color="yellow", heading="Hypothesis Testing")
        assert len(cards) >= 1
        card = cards[0]
        assert "??????" not in card["question"]
        assert card["question"].endswith("?")
        assert "Regarding <b>Hypothesis Testing</b>: What is the difference between Type I and Type II errors?" in card["question"]
        assert "hint: alpha vs beta" in card["answer"]

    def test_why_do_ssris_take_weeks_standalone(self):
        """
        'Why do SSRIs take 2-4 weeks to produce clinical efficacy?'
        must be recognized as an interrogative note and formatted cleanly without double prompt.
        """
        raw_text = "Why do SSRIs take 2-4 weeks to produce clinical efficacy?"
        assert is_interrogative_note(raw_text)

        parser = SemanticCardParser(runtime_manager=None)
        cards = parser.parse_with_fallback(raw_text, highlight_color="yellow", heading="Pharmacology")
        assert len(cards) >= 1
        card = cards[0]
        assert not re.search(r'What is the [a-z\s]+ of <b>Why', card["question"]), (
            f"Double prompt detected: {card['question']}"
        )
        assert "Regarding <b>Pharmacology</b>: Why do SSRIs take 2-4 weeks to produce clinical efficacy?" in card["question"]

    def test_why_question_paired_with_substantive_green_answer(self):
        """
        When a yellow interrogative is paired with a green substantive answer,
        synthesize_cards MUST use the question as active recall query and green as answer,
        NOT discard the question to create a generic definition of the heading.
        """
        structured = [{
            "heading": "Antidepressant Pharmacology",
            "full_paragraph": "",
            "highlights": [
                {"raw_color": "yellow", "category": "yellow", "text": "Why do SSRIs take 2-4 weeks to produce clinical efficacy?"},
                {"raw_color": "green", "category": "green", "text": "Downregulation of 5-HT1A autoreceptors and enhanced neurogenesis in hippocampus"}
            ]
        }]
        cards = synthesize_cards(structured)
        assert len(cards) >= 1
        found_active_q = False
        for c in cards:
            q = c.get("question", "")
            # Must NOT be a generic definition of heading
            assert q != "What is the definition of <b>Antidepressant Pharmacology</b>?", (
                "Interrogative question was discarded and replaced with generic heading definition!"
            )
            if "Why do SSRIs take" in q:
                found_active_q = True
                assert "Downregulation of 5-HT1A" in c.get("answer", "")
        assert found_active_q, f"No card retained the student's question prompt in: {cards}"


# ============================================================================
# 4. Inverted Highlights (Wordy Definition Yellow, Term Green)
# ============================================================================

class TestAdversarialInvertedHighlights:
    """Stress-tests dynamic role resolution on inverted highlight pairs."""

    def test_30_word_definition_yellow_with_1_word_term_green(self):
        """
        30-word definition in yellow and 1-word term in green:
        resolve_keyword_descriptor_pair MUST swap them so the 1-word term is the keyword.
        """
        def_30 = (
            "The cellular and molecular mechanism whereby synaptic connections between neurons are "
            "persistently strengthened following high-frequency stimulation, serving as a primary "
            "biological substrate for learning and memory formation across mammalian brains"
        )
        term_1 = "Neuroplasticity"
        assert len(def_30.split()) == 29 or len(def_30.split()) == 30

        kw, desc = resolve_keyword_descriptor_pair(def_30, term_1, term_color="yellow", def_color="green")
        assert kw == "Neuroplasticity", f"Inverted swap failed: got keyword '{kw}'"
        assert desc == def_30

    def test_6_word_state_phrase_yellow_with_4_word_term_green(self):
        """
        6-word state phrase in yellow and 4-word scientific term in green:
        resolve_keyword_descriptor_pair MUST swap them and never emit 'A state of...' as the keyword.
        """
        yellow_def = "A state of continuous synaptic depression"
        green_term = "Hippocampal long-term depression mechanism"

        kw, desc = resolve_keyword_descriptor_pair(yellow_def, green_term, term_color="yellow", def_color="green")
        assert kw == green_term, (
            f"Failed to swap 6-word state phrase! Expected keyword '{green_term}', got '{kw}'"
        )
        assert desc == yellow_def
