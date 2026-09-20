"""
Unit Test Suite for SemanticCardParser & SuperMemo 20 Rules Engine
Tests local AI (Ollama) decomposition, 64-pattern deterministic fallback,
multi-tier subject resolution, Cloze generation, and 0% 'this concept' enforcement.
"""

import re
import pytest
from unittest.mock import MagicMock
from scripts.semantic_parser import (
    SemanticCardParser,
    split_highlight_fallback,
    split_compound_yellow,
    create_cloze_card,
    clean_phrase,
    strip_leading_articles,
    check_veto_violations,
    is_valid_card,
    COPULA_LEXICON_COUNT,
    DEFINITIONAL_COPULAS,
    EQUATIVE_COPULAS,
    FUNCTIONAL_COPULAS,
    TYPOGRAPHIC_COPULAS,
    SUPERMEMO_SYSTEM_PROMPT,
    CARD_DECOMPOSITION_JSON_SCHEMA,
    LINKING_VERBS_REGEX,
)


# ============================================================================
# 1. Copula Lexicon Tests
# ============================================================================

class TestCopulaLexicon:
    def test_lexicon_count_exceeds_64(self):
        """Verifies the regex lexicon has at least 64 distinct linking patterns."""
        assert COPULA_LEXICON_COUNT >= 64
        assert len(DEFINITIONAL_COPULAS) >= 20
        assert len(EQUATIVE_COPULAS) >= 15
        assert len(FUNCTIONAL_COPULAS) >= 20
        assert len(TYPOGRAPHIC_COPULAS) >= 4

    def test_longest_match_precedence(self):
        """Ensures composite copulas match before short copulas (e.g. 'is defined as' before 'is')."""
        sample = "Synaptic plasticity is defined as the ability of synapses to strengthen or weaken."
        m = LINKING_VERBS_REGEX.search(sample)
        assert m is not None
        assert m.group(1).strip().lower() == "is defined as"

    def test_refers_to_process_precedence(self):
        sample = "Long-term depression refers to the process of activity-dependent reduction in efficacy."
        m = LINKING_VERBS_REGEX.search(sample)
        assert m is not None
        assert m.group(1).strip().lower() == "refers to the process of"


# ============================================================================
# 2. ANKI_SOP Test Sentences & Bidirectionality
# ============================================================================

class TestANKISOPCoreSentences:
    @pytest.fixture
    def parser(self):
        return SemanticCardParser(runtime_manager=None)

    def test_basic_developmental_science_sop(self, parser):
        """
        Tests ANKI_SOP.md benchmark sentence:
        'Basic developmental science focuses on description, explanation, and optimization of intra-individual change.'
        Must generate forward and reverse cards with clean Keyword and Descriptor.
        """
        text = "Basic developmental science focuses on description, explanation, and optimization of intra-individual change."
        cards = parser.parse_highlight(text, highlight_color="green", heading="Developmental Psychology")

        assert len(cards) == 2
        fwd, rev = cards[0], cards[1]

        # Forward Card (Recall)
        assert fwd["card_type"] == "bidirectional_definition"
        assert fwd["keyword"] == "Basic developmental science"
        assert "What is the definition of <b>Basic developmental science</b>?" in fwd["question"]
        assert fwd["answer"] == "Description, explanation, and optimization of intra-individual change."
        assert fwd["category_badge"] == "badge-definition"
        assert "forward" in fwd["tags"]

        # Reverse Card (Recognition)
        assert rev["card_type"] == "bidirectional_definition"
        assert rev["keyword"] == "Basic developmental science"
        assert "What term is defined by:<br><i>Description, explanation, and optimization of intra-individual change.</i>" in rev["question"]
        assert rev["answer"] == "Basic developmental science"
        assert rev["category_badge"] == "badge-definition"
        assert "reverse" in rev["tags"]

        # Zero 'this concept'
        assert not check_veto_violations(fwd["question"])
        assert not check_veto_violations(fwd["answer"])
        assert not check_veto_violations(rev["question"])
        assert not check_veto_violations(rev["answer"])

    def test_therapeutic_index_with_leading_article(self, parser):
        """Tests stripping of leading article 'The' from scientific definition."""
        text = "The therapeutic index is defined as the ratio of toxic dose to effective dose."
        cards = parser.parse_highlight(text, highlight_color="green", heading="Pharmacology")

        assert len(cards) == 2
        fwd = cards[0]
        assert fwd["keyword"] == "Therapeutic index"
        assert "What is the definition of <b>Therapeutic index</b>?" in fwd["question"]
        assert fwd["answer"] == "The ratio of toxic dose to effective dose."

    def test_lowercase_input_handling(self, parser):
        """Tests that lowercase runs from Google Docs are parsed and capitalized correctly."""
        text = "mitochondria are the powerhouses of the cell."
        cards = parser.parse_highlight(text, highlight_color="green", heading="Cell Biology")

        assert len(cards) == 2
        fwd, rev = cards[0], cards[1]
        assert fwd["keyword"] == "Mitochondria"
        assert rev["answer"] == "Mitochondria"

    def test_typographic_colon_definition(self, parser):
        """Tests parsing definitions formatted with a colon 'Term: Definition'."""
        text = "Receptor downregulation: Chronic agonist stimulation induces endocytosis of cell surface receptors."
        cards = parser.parse_highlight(text, highlight_color="green", heading="Pharmacodynamics")

        assert len(cards) == 2
        fwd = cards[0]
        assert fwd["keyword"] == "Receptor downregulation"
        assert "Chronic agonist stimulation induces endocytosis" in fwd["answer"]


# ============================================================================
# 3. Multi-Tier Subject Resolution Tests
# ============================================================================

class TestMultiTierSubjectResolution:
    def test_tier1_internal_verb(self):
        term, desc, tier = split_highlight_fallback(
            "Retrograde amnesia is characterized by the loss of memories formed prior to brain injury.",
            heading_context="Memory Disorders"
        )
        assert tier == "tier1_internal"
        assert term == "Retrograde amnesia"
        assert desc.startswith("The loss of memories")

    def test_tier2_prefix_with_colon(self):
        term, desc, tier = split_highlight_fallback(
            highlight_text="Rapid electrical impulse propagating along the axon.",
            paragraph_prefix="Action Potential:",
            heading_context="Neurophysiology"
        )
        assert tier.startswith("tier2_prefix")
        assert term == "Action Potential"
        assert "Rapid electrical impulse" in desc

    def test_tier2_prefix_with_copula(self):
        term, desc, tier = split_highlight_fallback(
            highlight_text="Primary inhibitory neurotransmitter in the central nervous system.",
            paragraph_prefix="GABA is defined as",
            heading_context="Neurotransmitters"
        )
        assert tier == "tier2_prefix_copula"
        assert term == "GABA"
        assert "Primary inhibitory neurotransmitter" in desc

    def test_tier2_prefix_trailing_noun(self):
        term, desc, tier = split_highlight_fallback(
            highlight_text="Regulates mood, sleep, cognition, and appetite.",
            paragraph_prefix="Monoamines. Serotonin.",
            heading_context="Neurotransmitters"
        )
        assert tier == "tier2_prefix_trailing"
        assert term == "Serotonin"

    def test_tier3_structural_anchor_heading(self):
        """When highlight has no copula and prefix is empty, resolves to heading anchor."""
        term, desc, tier = split_highlight_fallback(
            highlight_text="Degenerates progressively in Parkinson's disease leading to severe motor deficits.",
            paragraph_prefix="",
            heading_context="Substantia Nigra"
        )
        assert tier == "tier3_heading_anchor"
        assert term == "Substantia Nigra"
        assert "Degenerates progressively" in desc

    def test_tier3_short_standalone_term(self):
        """Standalone highlight without verb becomes concept keyword."""
        term, desc, tier = split_highlight_fallback(
            highlight_text="Positive Mutations",
            paragraph_prefix="",
            heading_context="Evolutionary Genetics"
        )
        assert tier == "tier3_short_term"
        assert term == "Positive Mutations"
        assert "Positive Mutations — core concept" in desc


# ============================================================================
# 4. SuperMemo Atomicity & Cloze Generation Tests (Rule 4 & 5)
# ============================================================================

class TestSuperMemoAtomicityAndCloze:
    @pytest.fixture
    def parser(self):
        return SemanticCardParser(runtime_manager=None)

    def test_compound_yellow_split_whereas(self, parser):
        """
        Tests compound yellow highlight decomposition on 'whereas':
        'Dopamine D2 receptor occupancy between 65% and 80% is required for clinical therapeutic response,
        whereas occupancy exceeding 80% sharply increases the risk of extrapyramidal symptoms (EPS).'
        """
        text = (
            "Dopamine D2 receptor occupancy between 65% and 80% is required for clinical therapeutic response, "
            "whereas occupancy exceeding 80% sharply increases the risk of extrapyramidal symptoms (EPS)."
        )
        cards = parser.parse_highlight(text, highlight_color="yellow", heading="Antipsychotic Pharmacology")

        # Decomposed into at least 2 cards (Rule 4: Atomicity)
        assert len(cards) >= 2

        # Card 1 should target the 65% to 80% therapeutic window
        c1 = cards[0]
        assert "cloze" in c1["card_type"]
        assert "{{c1::between 65% and 80%}}" in c1["cloze_text"]
        assert c1["answer"] == "between 65% and 80%"

        # Card 2 should target exceeding 80% EPS threshold
        c2 = cards[1]
        assert "cloze" in c2["card_type"]
        assert "{{c1::exceeding 80%}}" in c2["cloze_text"]
        assert c2["answer"] == "exceeding 80%"

        # Atomicity check: answer must be concise (<= 15 words)
        for c in cards:
            assert len(c["answer"].split()) <= 15
            assert not check_veto_violations(c["question"])
            assert not check_veto_violations(c["answer"])

    def test_compound_yellow_split_while(self, parser):
        """Tests clause splitting on 'while'."""
        text = (
            "Agonists stimulate receptor activity by mimicking endogenous ligands, "
            "while antagonists bind to receptors without activation and block agonist binding."
        )
        atomic = split_compound_yellow(text)
        assert len(atomic) == 2
        assert atomic[0].startswith("Agonists stimulate")
        assert atomic[1].startswith("antagonists bind")

    def test_cloze_card_dosage_units(self):
        """Tests cloze generation for numerical dosage with units."""
        text = "The initial therapeutic dose of sertraline is typically between 50 to 200 mg daily."
        card = create_cloze_card(text, heading="Pharmacotherapy")
        assert card is not None
        assert card["card_type"] == "cloze"
        assert "{{c1::between 50 to 200 mg}}" in card["cloze_text"]
        assert card["answer"] == "between 50 to 200 mg"
        assert "badge-important" == card["category_badge"]


# ============================================================================
# 5. Ollama LLM Parsing & Schema Decomposition Tests
# ============================================================================

class TestOllamaIntegration:
    def test_supermemo_system_prompt_rules(self):
        """Verifies system prompt contains SuperMemo 20 Rules directives."""
        assert "MINIMUM INFORMATION PRINCIPLE (ATOMICITY - Rule 4)" in SUPERMEMO_SYSTEM_PROMPT
        assert "CLOZE DELETION (Rule 5)" in SUPERMEMO_SYSTEM_PROMPT
        assert "AVOID SETS AND ENUMERATIONS (Rules 9 & 10)" in SUPERMEMO_SYSTEM_PROMPT
        assert "CONTEXT ANCHORING (Rules 11 & 16)" in SUPERMEMO_SYSTEM_PROMPT
        assert "KEYWORD-DESCRIPTOR FORMAT" in SUPERMEMO_SYSTEM_PROMPT
        assert "this concept" in SUPERMEMO_SYSTEM_PROMPT

    def test_json_schema_definition(self):
        """Verifies JSON schema has required structure and fields."""
        assert CARD_DECOMPOSITION_JSON_SCHEMA["type"] == "object"
        assert "cards" in CARD_DECOMPOSITION_JSON_SCHEMA["properties"]
        items = CARD_DECOMPOSITION_JSON_SCHEMA["properties"]["cards"]["items"]
        assert "card_type" in items["properties"]
        assert "question" in items["required"]
        assert "answer" in items["required"]

    def test_ollama_mock_successful_bidirectional_parse(self):
        """Tests parsing when Ollama returns valid bidirectional JSON."""
        mock_mgr = MagicMock()
        mock_mgr.is_service_ready.return_value = True
        mock_mgr.generate_json.return_value = {
            "cards": [
                {
                    "card_type": "bidirectional_definition",
                    "keyword": "Long-Term Potentiation (LTP)",
                    "descriptor": "Persistent strengthening of synapses based on recent patterns of activity.",
                    "question": "What is the definition of <b>Long-Term Potentiation (LTP)</b>?",
                    "answer": "Persistent strengthening of synapses based on recent patterns of activity.",
                    "reverse_question": "What synaptic process is defined by:<br><i>Persistent strengthening of synapses based on recent patterns of activity.</i>",
                    "category_badge": "badge-definition",
                    "context": "Synaptic Plasticity",
                    "tags": ["neuroscience", "plasticity"]
                }
            ]
        }

        parser = SemanticCardParser(runtime_manager=mock_mgr)
        cards = parser.parse_highlight(
            "Long-Term Potentiation (LTP) is persistent strengthening of synapses based on recent patterns of activity.",
            highlight_color="green",
            heading="Synaptic Plasticity"
        )

        assert len(cards) == 2
        fwd, rev = cards[0], cards[1]
        assert fwd["keyword"] == "Long-Term Potentiation (LTP)"
        assert rev["answer"] == "Long-Term Potentiation (LTP)"
        assert "forward" in fwd["tags"]
        assert "reverse" in rev["tags"]

    def test_ollama_mock_veto_filter_triggers_fallback(self):
        """
        Tests that if Ollama hallucinates 'this concept', the parser
        rejects the card and falls back to deterministic parsing.
        """
        mock_mgr = MagicMock()
        mock_mgr.is_service_ready.return_value = True
        mock_mgr.generate_json.return_value = {
            "cards": [
                {
                    "card_type": "active_recall_qa",
                    "question": "What is this concept?",  # Banned phrase!
                    "answer": "Basic developmental science",
                    "category_badge": "badge-definition",
                    "context": "Developmental Psychology",
                    "tags": ["psych"]
                }
            ]
        }

        parser = SemanticCardParser(runtime_manager=mock_mgr)
        cards = parser.parse_highlight(
            "Basic developmental science focuses on description, explanation, and optimization of intra-individual change.",
            highlight_color="green",
            heading="Developmental Psychology"
        )

        # Fallback executed: produces 2 valid bidirectional cards without 'this concept'
        assert len(cards) == 2
        for c in cards:
            assert "this concept" not in c["question"].lower()
            assert "this concept" not in c["answer"].lower()


# ============================================================================
# 6. Zero 'this concept' Veto & Robustness Fuzzing
# ============================================================================

class TestZeroThisConceptMandate:
    @pytest.fixture
    def parser(self):
        return SemanticCardParser(runtime_manager=None)

    def test_veto_checker_detects_all_banned_phrases(self):
        assert check_veto_violations("Define / What is this concept?")
        assert check_veto_violations("Explain what is this concept.")
        assert check_veto_violations("What is this term used in psychology?")
        assert check_veto_violations("Describe this phenomenon in biology.")
        assert not check_veto_violations("What is the definition of <b>Dopamine</b>?")

    def test_card_validation_empty_and_tautology(self):
        assert not is_valid_card({"question": "", "answer": "Answer"})[0]
        assert not is_valid_card({"question": "Question", "answer": ""})[0]
        assert not is_valid_card({"question": "Tautology", "answer": "Tautology"})[0]
        assert is_valid_card({"question": "What is X?", "answer": "X is Y."})[0]

    @pytest.mark.parametrize("fuzz_input", [
        "",
        "   ",
        "Dopamine",
        "Action potential propagation along myelinated axons",
        "Occurs when calcium enters the presynaptic terminal triggering exocytosis.",
        "12345 !@#$%^&*()",
        "• Epigenetics — modifications to DNA that regulate expression without altering sequence.",
        "When an action potential arrives, neurotransmitters are released into the synaptic cleft.",
        "Synaptic vesicle.",
        "G-protein coupled receptors (GPCRs)",
        "The",
        "A",
        "Is",
        "Whereas",
        "Whereas dopamine mediates reward, serotonin regulates mood and satiety.",
        "Phase 1 clinical trials evaluate safety and pharmacokinetics in healthy volunteers.",
    ])
    def test_fuzz_never_emits_this_concept(self, parser, fuzz_input):
        """
        Fuzzes parser across edge-case inputs.
        Verifies that NO card ever contains 'this concept' or empty fields.
        """
        for color in ["green", "yellow", "other"]:
            cards = parser.parse_highlight(fuzz_input, highlight_color=color, heading="Neurobiology")
            for c in cards:
                # 1. Non-empty fields
                assert c["question"].strip() != ""
                assert c["answer"].strip() != ""
                # 2. Never 'this concept'
                assert not check_veto_violations(c["question"])
                assert not check_veto_violations(c["answer"])
                # 3. Non-tautological
                assert c["question"].strip().lower() != c["answer"].strip().lower()
                # 4. Valid badge and context
                assert c["category_badge"] in ("badge-definition", "badge-important")
                assert c["context"] != ""


# ============================================================================
# 7. Agent-as-Judge 30-Point Rubric Evaluation
# ============================================================================

class SuperMemoCardJudge:
    """Agent-as-Judge evaluation harness based on explorer_survey_3 specification."""
    def __init__(self):
        self.banned_phrases = [
            r"\bthis\s+concept\b",
            r"\bthis\s+term\b",
            r"\bthis\s+phenomenon\b",
            r"\bwhat\s+is\s+this\s+concept\b",
            r"\bdefine\s+this\s+concept\b",
        ]
        self.set_phrases = [
            r"\blist\s+the\b",
            r"\bwhat\s+are\s+the\s+\d+\b",
            r"\bname\s+the\s+\d+\b",
        ]

    def evaluate_card(self, card):
        q = card.get("question", "").strip()
        a = card.get("answer", "").strip()
        badge = card.get("category_badge", "").strip()
        ctx = card.get("context", "").strip()
        tags = card.get("tags", [])

        # Vetoes
        if not q or not a:
            return {"score": 0, "passed": False, "veto": "EMPTY_FIELD"}
        for pat in self.banned_phrases:
            if re.search(pat, q, re.IGNORECASE) or re.search(pat, a, re.IGNORECASE):
                return {"score": 0, "passed": False, "veto": "BANNED_PHRASE"}
        if q.lower() == a.lower():
            return {"score": 0, "passed": False, "veto": "TAUTOLOGY"}

        scores = {}
        # D1: Atomicity (Rule 4)
        word_count = len(a.split())
        scores["D1"] = 5 if word_count <= 25 else (3 if word_count <= 40 else 1)

        # D2: Absence of Vague Prompts (Rule 12)
        if re.search(r'^(What|Which|Why|How|Define|Identify|Explain the mechanism)\b', q, re.IGNORECASE):
            scores["D2"] = 5
        elif "<br>" in q:
            scores["D2"] = 4
        else:
            scores["D2"] = 3

        # D3: Keyword-Descriptor (SOP)
        has_bold = bool(re.search(r'<b>([^<]+)</b>', q))
        if has_bold or "cloze" in tags or "{{c1::" in q:
            scores["D3"] = 5
        else:
            scores["D3"] = 3

        # D4: Avoid Sets (Rule 9 & 10)
        scores["D4"] = 0 if any(re.search(p, q, re.IGNORECASE) for p in self.set_phrases) else 5

        # D5: Active Recall (Rule 17)
        if "reverse" in tags:
            scores["D5"] = 5 if len(a.split()) <= 6 else 3
        else:
            scores["D5"] = 5

        # D6: Contextual Anchoring (Rule 16)
        scores["D6"] = (2 if badge else 0) + (2 if ctx else 0) + (1 if tags else 0)

        total = sum(scores.values())
        return {"score": total, "passed": total >= 25, "veto": None, "scores": scores}


class TestAgentAsJudgeEvaluation:
    @pytest.fixture
    def judge(self):
        return SuperMemoCardJudge()

    @pytest.fixture
    def parser(self):
        return SemanticCardParser(runtime_manager=None)

    def test_benchmark_cards_pass_judge_rubric(self, parser, judge):
        """
        Runs cards generated from representative lecture highlights through
        the 30-point judge rubric. Every card must pass (score >= 25) with zero vetoes.
        """
        test_inputs = [
            ("Basic developmental science focuses on description, explanation, and optimization of intra-individual change.", "green", "Developmental Science"),
            ("The therapeutic index is defined as the ratio of toxic dose to effective dose.", "green", "Pharmacology"),
            ("Receptor downregulation: Chronic agonist stimulation induces endocytosis of cell surface receptors.", "green", "Pharmacodynamics"),
            ("Dopamine D2 receptor occupancy between 65% and 80% is required for clinical therapeutic response, whereas occupancy exceeding 80% sharply increases the risk of extrapyramidal symptoms (EPS).", "yellow", "Pharmacodynamics"),
            ("Positive Mutations", "green", "Evolutionary Biology"),
        ]

        total_tested = 0
        for text, color, heading in test_inputs:
            cards = parser.parse_highlight(text, highlight_color=color, heading=heading)
            assert len(cards) > 0
            for card in cards:
                res = judge.evaluate_card(card)
                assert res["veto"] is None, f"Card triggered veto: {res['veto']} for card {card}"
                assert res["passed"] is True, f"Card failed rubric (score: {res['score']}/30) for card {card}"
                assert res["score"] >= 25
                total_tested += 1

        assert total_tested >= 8
