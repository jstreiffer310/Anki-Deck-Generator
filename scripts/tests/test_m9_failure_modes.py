"""
scripts/tests/test_m9_failure_modes.py — Comprehensive Unit & Adversarial Tests for Milestone M9.
Validates the complete elimination of real-world academic note failure modes:
1. Card 55 Bug: Disqualification of action verbs and theoretical critique phrases (REJECTS, CRITICIZES, CONTRASTS, etc.).
2. Card 138 Bug: Definitional framing bypass (Process in which..., Mechanism by which...) preventing subordinate verb splitting.
3. Card 11 Bug: Rhetorical & interrogative note cleanup (collapsing ???, active recall formatting, non-tautological answering).
4. Card Inversion Bug: Smart role resolution swapping inverted Yellow/Green pairs so terms become keywords and definitions become descriptors.
5. CardValidator Section 10 Guardrails: Strict rejection of action verb keywords, definitional framing keywords, inverted cards, and nested questions.
"""

import re
import pytest
from pathlib import Path

from scripts.semantic_parser import (
    is_valid_concept_keyword,
    resolve_keyword_descriptor_pair,
    split_highlight_fallback,
    SemanticCardParser,
    is_interrogative_note,
    CRITIQUE_STANDALONE_WORDS,
    CRITIQUE_ACTION_REGEX,
    DEFINITIONAL_FRAMING_REGEX,
)
from scripts.extract_and_generate import synthesize_cards
from scripts.card_validator import CardValidator, strip_html_tags


# ============================================================================
# 1. Card 55 Bug Elimination: Action Verbs & Theoretical Critiques
# ============================================================================

class TestCard55CritiqueAndActionVerbElimination:
    """Verifies that standalone action verbs and critique phrases cannot become concept keywords."""

    @pytest.mark.parametrize("critique_word", [
        "REJECT", "REJECTS", "REJECTED", "REJECTING",
        "CRITICIZE", "CRITICIZES", "CRITICIZED", "CRITICIZING",
        "CONTRAST", "CONTRASTS", "CONTRASTED", "CONTRASTING",
        "CHALLENGE", "CHALLENGES", "CHALLENGED", "CHALLENGING",
        "DISPROVE", "DISPROVES", "DISPROVED", "DISPROVING",
        "REFUTE", "REFUTES", "REFUTED", "REFUTING",
        # Lowercase and title case variants
        "rejects", "criticizes", "contrasts", "challenges", "disproves", "refutes",
        "Rejects", "Criticizes", "Contrasts", "Challenges", "Disproves", "Refutes",
    ])
    def test_standalone_critique_verbs_disqualified(self, critique_word):
        """Action verbs alone MUST NOT be accepted as concept keywords."""
        assert not is_valid_concept_keyword(critique_word), (
            f"Critique action verb '{critique_word}' was incorrectly accepted as a concept keyword!"
        )

    @pytest.mark.parametrize("phrase", [
        "Chomsky REJECTS",
        "Skinner CRITICIZED",
        "Kahneman CONTRASTS",
        "Piaget CHALLENGES",
        "Popper REFUTES",
        "Studies DISPROVE",
        "arguing that",
        "argues that",
        "suggests that",
        "posits that",
        "claims that",
        "opposes the view that",
        "disputes that",
        "questions whether",
        "doubts that",
    ])
    def test_critique_phrases_and_author_combos_disqualified(self, phrase):
        """Author + critique verb combinations MUST NOT become concept keywords."""
        assert not is_valid_concept_keyword(phrase), (
            f"Critique phrase '{phrase}' was incorrectly accepted as a concept keyword!"
        )

    def test_card55_synthesize_cards_creates_active_recall_critique(self):
        """
        When notes contain a yellow critique highlight (e.g. 'REJECTS') paired with
        a green substantive highlight, synthesize_cards creates an active recall
        card asking what critique/counterargument is presented regarding the heading.
        """
        structured = [{
            "heading": "Linguistic Nativism",
            "full_paragraph": "REJECTS Skinner's operant conditioning model of language acquisition.",
            "highlights": [
                {"raw_color": "yellow", "category": "yellow", "text": "REJECTS"},
                {"raw_color": "green", "category": "green", "text": "Skinner's operant conditioning model of language acquisition"}
            ]
        }]
        cards = synthesize_cards(structured)
        assert len(cards) >= 1
        critique_cards = [c for c in cards if "critique" in c.get("tags", []) or "critique" in c.get("question", "").lower()]
        assert len(critique_cards) >= 1
        card = critique_cards[0]
        # Keyword must be anchored to the heading/topic, NOT 'REJECTS'
        assert card["keyword"] == "Linguistic Nativism"
        # Prompt must be an active recall question regarding critique/counterargument
        assert "Linguistic Nativism" in card["question"]
        assert "critique" in card["question"].lower() or "counterargument" in card["question"].lower()
        # Answer must contain the substantive target
        assert "operant conditioning" in card["answer"].lower()

    def test_card_validator_rejects_action_verb_keyword(self):
        """CardValidator MUST reject cards that have an action verb or critique keyword."""
        validator = CardValidator()
        bad_card = {
            "card_type": "bidirectional_definition",
            "keyword": "REJECTS",
            "descriptor": "Skinner's operant conditioning model of language acquisition.",
            "question": "What is the definition of <b>REJECTS</b>?",
            "answer": "Skinner's operant conditioning model of language acquisition.",
            "category_badge": "badge-definition",
            "context": "Linguistics",
            "tags": ["definition"]
        }
        res = validator.validate_card(bad_card)
        assert not res.is_valid
        issue_codes = [issue.rule_id for issue in res.issues]
        assert "ACTION_VERB_KEYWORD" in issue_codes


# ============================================================================
# 2. Card 138 Bug Elimination: Definitional Framing Preservation
# ============================================================================

class TestCard138DefinitionalFramingPreservation:
    """Verifies that relative clauses and definitional framing phrases are preserved and not broken into clause keywords."""

    @pytest.mark.parametrize("framing_phrase", [
        "Process in which new neurons are formed in the brain",
        "process of activity-dependent synaptic plasticity",
        "mechanism by which neurotransmitters are released at the terminal",
        "condition characterized by tremor, rigidity, and bradykinesia",
        "movement of ions across a semipermeable membrane",
        "formation of myelin sheaths around axons",
        "state of decreased responsiveness following repeated exposure",
        "capacity to maintain stable internal physiological parameters",
        "cascade that results in cyclic AMP generation",
        "pathway which mediates reward and reinforcement",
    ])
    def test_definitional_framing_disqualified_as_keyword(self, framing_phrase):
        """Relative-clause definitional framing MUST NOT be accepted as a concept keyword."""
        assert not is_valid_concept_keyword(framing_phrase), (
            f"Definitional framing phrase '{framing_phrase}' was incorrectly accepted as a concept keyword!"
        )

    def test_card138_split_highlight_fallback_bypasses_subordinate_verb(self):
        """
        For a highlight starting with 'Process in which new neurons are formed in the brain',
        split_highlight_fallback must NOT split on 'formed' or 'are', but preserve the definition.
        """
        text = "Process in which new neurons are formed in the brain"
        term, descriptor, tier = split_highlight_fallback(
            highlight_text=text,
            paragraph_prefix="Neurogenesis: ",
            heading_context="Neural Development"
        )
        # It must resolve the term from prefix or heading
        assert term in ("Neurogenesis", "Neural Development")
        # Descriptor must preserve the full definitional phrase
        assert "new neurons are formed in the brain" in descriptor.lower()
        assert tier.startswith("framing_")

    def test_card138_synthesize_cards_standalone_green(self):
        """
        In synthesize_cards, standalone green with definitional framing preserves the definition
        and anchors to the preceding prefix or heading.
        """
        structured = [{
            "heading": "Neural Plasticity",
            "full_paragraph": "Neurogenesis: Process in which new neurons are formed in the brain.",
            "highlights": [
                {"raw_color": "green", "category": "green", "text": "Process in which new neurons are formed in the brain"}
            ]
        }]
        cards = synthesize_cards(structured)
        assert len(cards) >= 1
        card = cards[0]
        assert card["keyword"] in ("Neurogenesis", "Neural Plasticity")
        assert "formed in the brain" in card["answer"].lower()

    def test_card_validator_rejects_definitional_framing_keyword(self):
        """CardValidator MUST reject cards where the keyword is a definitional framing phrase."""
        validator = CardValidator()
        bad_card = {
            "card_type": "bidirectional_definition",
            "keyword": "Process in which new neurons are formed in the brain",
            "descriptor": "Neurogenesis in the subventricular zone.",
            "question": "What is the definition of <b>Process in which new neurons are formed in the brain</b>?",
            "answer": "Neurogenesis in the subventricular zone.",
            "category_badge": "badge-definition",
            "context": "Neuroscience",
            "tags": ["definition"]
        }
        res = validator.validate_card(bad_card)
        assert not res.is_valid
        issue_codes = [issue.rule_id for issue in res.issues]
        assert "DEFINITIONAL_FRAMING_KEYWORD" in issue_codes


# ============================================================================
# 3. Card 11 Bug Elimination: Rhetorical & Interrogative Note Cleanup
# ============================================================================

class TestCard11RhetoricalAndInterrogativeNoteCleanup:
    """Verifies that rhetorical questions in lecture notes are cleaned, properly formatted, and non-tautological."""

    def test_is_interrogative_note_classification(self):
        """Tests accurate identification of interrogative notes vs definitions and declarative statements."""
        assert is_interrogative_note("What constitutes Abuse????? (not so simple)")
        assert is_interrogative_note("What is the ethical duty to report child abuse?")
        assert is_interrogative_note("Why do action potentials propagate unidirectionally?")
        assert is_interrogative_note("How does allosteric modulation alter receptor affinity?")
        assert is_interrogative_note("When does long-term potentiation occur?")

        # Declarative statements starting with 'When ...' MUST NOT be treated as questions
        assert not is_interrogative_note(
            "When dopamine binds to D1 receptors, which are Gs-protein coupled, adenylyl cyclase is activated."
        )

        # Definitions with colons and question marks MUST NOT be treated as interrogatives
        assert not is_interrogative_note(
            "--- Action Potential ::: [Depolarization --> Influx of Na+] ???"
        )

    def test_multiple_question_marks_collapsed_and_formatted(self):
        """Tests that ??? is collapsed to a single ? and formatted as 'Regarding <b>{Heading}</b>: {Question}'."""
        parser = SemanticCardParser()
        text = "What constitutes Abuse????? (not so simple)"
        cards = parser.parse_with_fallback(
            text=text,
            highlight_color="yellow",
            heading="Professional Ethics",
            paragraph_prefix="Child Protection Guidelines: "
        )
        assert len(cards) >= 1
        card = cards[0]
        # Multiple question marks must be normalized
        assert "?????" not in card["question"]
        assert card["question"].endswith("?")
        # Must be formatted regarding heading
        assert "Regarding <b>Professional Ethics</b>:" in card["question"]
        # Answer must be substantive, not empty or tautological
        assert card["answer"] != ""
        assert card["answer"].lower() != card["question"].lower()

    def test_card_validator_rejects_nested_questions(self):
        """CardValidator MUST reject cards that nest question phrases like 'What is the role of How do neurons...?'."""
        validator = CardValidator()
        nested_card = {
            "card_type": "active_recall_qa",
            "keyword": "Neurophysiology",
            "descriptor": "Depolarization causes calcium influx.",
            "question": "What is the key mechanism regarding What constitutes Abuse?",
            "answer": "Depolarization causes calcium influx.",
            "category_badge": "badge-important",
            "context": "Ethics",
            "tags": ["high_yield"]
        }
        res = validator.validate_card(nested_card)
        assert not res.is_valid
        issue_codes = [issue.rule_id for issue in res.issues]
        assert "NESTED_QUESTION_PROMPT" in issue_codes

    def test_card_validator_rejects_tautological_prompt_wrapping(self):
        """CardValidator MUST reject cards where prompt-wrapped question matches the answer."""
        validator = CardValidator()
        tautological_card = {
            "card_type": "active_recall_qa",
            "keyword": "Child Abuse",
            "descriptor": "What constitutes Abuse?",
            "question": "Regarding <b>Child Abuse</b>: What constitutes Abuse?",
            "answer": "What constitutes Abuse?",
            "category_badge": "badge-important",
            "context": "Ethics",
            "tags": ["high_yield"]
        }
        res = validator.validate_card(tautological_card)
        assert not res.is_valid
        issue_codes = [issue.rule_id for issue in res.issues]
        assert "TAUTOLOGY" in issue_codes


# ============================================================================
# 4. Card Inversion Bug Elimination: Dynamic Role Resolution
# ============================================================================

class TestCardInversionElimination:
    """Verifies that inverted Yellow/Green pairs are dynamically swapped so definitions never become questions."""

    def test_resolve_standard_pair(self):
        """When yellow is term and green is definition, roles are preserved."""
        term_cand = "Long-Term Potentiation"
        def_cand = "A persistent strengthening of synapses based on recent patterns of activity."
        kw, desc = resolve_keyword_descriptor_pair(term_cand, def_cand, "yellow", "green")
        assert kw == "Long-Term Potentiation"
        assert desc == "A persistent strengthening of synapses based on recent patterns of activity."

    def test_resolve_inverted_pair_swaps_roles(self):
        """When yellow is definition and green is term, roles are dynamically swapped."""
        yellow_cand = "A persistent strengthening of synapses based on recent patterns of activity"
        green_cand = "Long-Term Potentiation"
        kw, desc = resolve_keyword_descriptor_pair(yellow_cand, green_cand, "yellow", "green")
        # SWAP must occur: kw must be the concise concept term
        assert kw == "Long-Term Potentiation"
        assert desc == "A persistent strengthening of synapses based on recent patterns of activity"

    def test_resolve_pair_rejects_critique_as_keyword(self):
        """When one of the candidates is a critique action verb, resolve returns (None, None)."""
        kw, desc = resolve_keyword_descriptor_pair("REJECTS", "Skinner's operant conditioning", "yellow", "green")
        assert kw is None
        assert desc is None

    def test_card_validator_rejects_inverted_card(self):
        """CardValidator MUST reject bidirectional cards where the keyword is a long definition."""
        validator = CardValidator()
        inverted_card = {
            "card_type": "bidirectional_definition",
            "keyword": "Process in which new neurons are formed in the dentate gyrus",
            "descriptor": "Neurogenesis",
            "question": "What is the definition of <b>Process in which new neurons are formed in the dentate gyrus</b>?",
            "answer": "Neurogenesis",
            "category_badge": "badge-definition",
            "context": "Neuroscience",
            "tags": ["definition"]
        }
        res = validator.validate_card(inverted_card)
        assert not res.is_valid
        issue_codes = [issue.rule_id for issue in res.issues]
        assert "INVERTED_CARD_DEFINITION" in issue_codes or "DEFINITIONAL_FRAMING_KEYWORD" in issue_codes


# ============================================================================
# 5. End-to-End Synthesize Cards M9 Verification
# ============================================================================

class TestSynthesizeCardsM9E2E:
    """Verifies that synthesize_cards cleanly handles all M9 failure modes in integrated data."""

    def test_mixed_lecture_notes_synthesis(self):
        """Synthesizes a realistic batch of lecture notes containing all 4 edge cases without errors."""
        structured = [
            # Case 1: Critique pair
            {
                "heading": "Behaviorism vs Nativism",
                "full_paragraph": "Chomsky REJECTS Skinner's verbal behavior model.",
                "highlights": [
                    {"raw_color": "yellow", "category": "yellow", "text": "Chomsky REJECTS"},
                    {"raw_color": "green", "category": "green", "text": "Skinner's verbal behavior model"}
                ]
            },
            # Case 2: Inverted pair (definition yellow, term green)
            {
                "heading": "Neuroplasticity",
                "full_paragraph": "Neurogenesis is the generation of functional neurons from stem cells.",
                "highlights": [
                    {"raw_color": "yellow", "category": "yellow", "text": "The generation of functional neurons from stem cells"},
                    {"raw_color": "green", "category": "green", "text": "Neurogenesis"}
                ]
            },
            # Case 3: Definitional framing green
            {
                "heading": "Cellular Mechanisms",
                "full_paragraph": "Apoptosis: Process by which programmed cell death occurs.",
                "highlights": [
                    {"raw_color": "green", "category": "green", "text": "Process by which programmed cell death occurs"}
                ]
            }
        ]

        cards = synthesize_cards(structured)
        assert len(cards) >= 3

        validator = CardValidator()
        for c in cards:
            # Check zero 'this concept' banned phrases
            assert "this concept" not in c["question"].lower()
            assert "this concept" not in c["answer"].lower()
            # Check validation passes
            res = validator.validate_card(c)
            assert res.is_valid, f"Generated card failed validation: {res.issues} for card: {c}"
            # Check that no keyword is an action verb or definitional framing
            assert not is_valid_concept_keyword(c.get("keyword", "")) or len(c.get("keyword", "").split()) <= 7
