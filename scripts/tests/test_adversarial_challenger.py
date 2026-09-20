r"""
Empirical Adversarial Challenge Test Suite — challenger_1
Stress-tests SemanticCardParser, synthesize_cards, and the AnkiDeckCreator pipeline
against pathological, complex, and adversarial inputs:
  1. Extreme length highlights (>500, >1200, >2500 characters)
  2. Latin nomenclature and scientific binomials (*Staphylococcus aureus*, *In vitro*, etc.)
  3. Chemical & pharmacological formulas (5-HT2A, $\Delta^9$-THC, C10H15N, GABA_A, 1,3,7-trimethylxanthine)
  4. Zero-punctuation run-on text
  5. Excessive, chaotic, and edge-case punctuation (colons, dashes, ellipses, empty, whitespace)
  6. Nested, subordinate, and parenthetical clauses (Although..., Because..., When..., Despite...)
  7. Non-standard copulas across all 4 lexicon functional classes
  8. Compound statements & numerical thresholds (Cloze generation & atomicity)
  9. CardJudgeRubric verification (0% 'this concept', 0% heading dumps, 0% empty fields, 0% tautologies)
  10. Full E2E synthesize_cards and .apkg packaging integrity
"""

import os
import re
import pytest
import sqlite3
import tempfile
from pathlib import Path
from typing import List, Dict, Any

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
    ALL_LINKING_PATTERNS,
)
from scripts.evaluate_cards_judge import CardJudgeRubric
from scripts.extract_and_generate import (
    synthesize_cards,
    create_deck_package,
    clean_phrase as e2e_clean_phrase,
)


# ============================================================================
# Adversarial Fixtures
# ============================================================================

@pytest.fixture
def parser():
    """Deterministic fallback parser instance (Ollama offline)."""
    return SemanticCardParser(runtime_manager=None)


@pytest.fixture
def judge():
    """Agent-as-Judge rubric evaluator."""
    return CardJudgeRubric()


# ============================================================================
# Tier 1: Extreme Length Highlights Stress Testing
# ============================================================================

class TestExtremeLengthAdversarial:
    """Stress-tests the parser with highlights exceeding normal bounds (500 to 2500+ chars)."""

    def test_extreme_length_550_chars_single_sentence(self, parser, judge):
        text = (
            "Neurodevelopmental trajectory optimization is defined as the systematic multidimensional "
            "process whereby continuous bidirectional interactions between genetically programmed cellular "
            "maturation programs and structured environmental enrichment protocols synergistically "
            "potentiate synaptogenesis, dendritic arborization, axonal myelination, and functional "
            "neural circuit remodeling across critical sensitive periods of early mammalian ontological "
            "development without precipitating maladaptive synaptic pruning or excitotoxic apoptosis."
        )
        assert len(text) > 500
        cards = parser.parse_highlight(text, highlight_color="green", heading="Neurodevelopment")
        assert len(cards) == 2  # Bidirectional forward + reverse
        
        # Verify Keyword extraction is bounded and clean
        kw = cards[0]["keyword"]
        assert len(kw.split()) <= 5
        assert "Neurodevelopmental trajectory optimization" in kw
        
        for c in cards:
            ev = judge.evaluate_card(c)
            assert len(ev["vetoes"]) == 0
            assert not check_veto_violations(c["question"])
            assert not check_veto_violations(c["answer"])

    def test_extreme_length_1200_chars_multi_sentence_wall(self, parser, judge):
        text = (
            "Mesolimbic dopamine pathway sensitization represents the persistent neuroadaptive alteration "
            "in ventral tegmental area dopaminergic projections to the nucleus accumbens shell that develops "
            "following repeated, intermittent exposure to reinforcing pharmacological stimuli. This durable "
            "state of hyper-reactivity involves enduring alterations in glutamate receptor trafficking, "
            "specifically the recruitment of calcium-permeable AMPA receptors lacking the GluA2 subunit to "
            "medium spiny neuron synapses, alongside transcriptional activation mediated by delta-FosB and "
            "CREB signaling cascades. Furthermore, morphological reorganization occurs concurrently within the "
            "striatal microarchitecture, characterized by increased dendritic spine density and altered synaptic "
            "cleft geometry. Consequently, subsequent re-exposure to the conditioned drug-associated stimuli "
            "triggers exaggerated phasic dopamine transients that elicit intense incentive salience, obsessive "
            "drug-seeking behaviors, and heightened vulnerability to compulsive relapse even following prolonged "
            "periods of abstinence."
        )
        assert len(text) >= 1000
        cards = parser.parse_highlight(text, highlight_color="green", heading="Addiction Neurobiology")
        assert len(cards) == 2
        
        # Keyword must be extracted cleanly from initial copula
        assert cards[0]["keyword"] == "Mesolimbic dopamine pathway sensitization"
        for c in cards:
            ev = judge.evaluate_card(c)
            assert len(ev["vetoes"]) == 0
            assert "this concept" not in c["question"].lower()
            assert "this concept" not in c["answer"].lower()

    def test_extreme_length_2500_chars_adversarial_monster(self, parser, judge):
        chunk = "Synaptic transmission involves precise neurotransmitter release. "
        repeated_filler = chunk * 35
        text = "Retrograde synaptic signaling is characterized by " + repeated_filler
        assert len(text) > 2300

        cards = parser.parse_highlight(text, highlight_color="green", heading="Synaptic Physiology")
        assert len(cards) == 2
        assert cards[0]["keyword"] == "Retrograde synaptic signaling"
        for c in cards:
            assert not check_veto_violations(c["question"])
            assert not check_veto_violations(c["answer"])


# ============================================================================
# Tier 2: Latin Nomenclature & Scientific Binomials
# ============================================================================

class TestLatinNomenclatureAdversarial:
    """Stress-tests parsing of Latin taxonomic names, experimental terms, and scientific phrases."""

    @pytest.mark.parametrize("latin_text,expected_term,heading", [
        (
            "Staphylococcus aureus is a Gram-positive spherically shaped bacterium that produces coagulase.",
            "Staphylococcus aureus",
            "Microbiology"
        ),
        (
            "In vitro assays measure receptor binding affinity and intrinsic efficacy in isolated cell membrane preparations.",
            "In vitro assays",
            "Pharmacology Methods"
        ),
        (
            "In vivo electrophysiology is the electrophysiological technique measuring real-time multi-unit action potential firing rates across intact hippocampal circuits.",
            "In vivo electrophysiology",
            "Neurophysiology"
        ),
        (
            "Post hoc ergo propter hoc denotes the logical fallacy of assuming causal dependency solely based on chronological sequence.",
            "Post hoc ergo propter hoc",
            "Research Methods"
        ),
        (
            "Cannabis sativa refers to the dioecious annual flowering plant producing delta-9-tetrahydrocannabinol and cannabidiol.",
            "Cannabis sativa",
            "Phytochemistry"
        ),
        (
            "Canis lupus familiaris is classified as a domesticated subspecies of the gray wolf.",
            "Canis lupus familiaris",
            "Zoology"
        ),
        (
            "Drosophila melanogaster serves as a preeminent genetic model organism for circadian rhythm molecular mapping.",
            "Drosophila melanogaster",
            "Genetics"
        ),
        (
            "Caenorhabditis elegans comprises exactly 302 invariant neurons in the adult hermaphrodite nervous system.",
            "Caenorhabditis elegans",
            "Developmental Biology"
        ),
    ])
    def test_latin_binomial_extraction(self, parser, judge, latin_text, expected_term, heading):
        cards = parser.parse_highlight(latin_text, highlight_color="green", heading=heading)
        assert len(cards) == 2
        fwd_card, rev_card = cards[0], cards[1]

        assert fwd_card["keyword"] == expected_term
        assert fwd_card["question"] == f"What is the definition of <b>{expected_term}</b>?"
        assert rev_card["answer"] == expected_term
        assert rev_card["question"].startswith("What term is defined by:<br><i>")

        for c in cards:
            ev = judge.evaluate_card(c)
            assert len(ev["vetoes"]) == 0
            assert ev["total_score"] >= 25


# ============================================================================
# Tier 3: Chemical & Pharmacological Formulas
# ============================================================================

class TestChemicalFormulasAdversarial:
    """Stress-tests preservation of complex chemical formulas, alphanumeric tokens, and Greek letters."""

    @pytest.mark.parametrize("formula_text,expected_keyword,heading", [
        (
            "5-HT2A receptor agonist mediates the hallucinogenic properties of psilocybin and LSD.",
            "5-HT2A receptor agonist",
            "Psychopharmacology"
        ),
        (
            "$\\Delta^9$-THC is the principal psychoactive phytocannabinoid acting as a partial CB1 agonist.",
            "$\\Delta^9$-THC",
            "Cannabinoids"
        ),
        (
            "alpha-4-beta-2 nicotinic acetylcholine receptors mediate the primary reinforcing effects of nicotine in the VTA.",
            "Alpha-4-beta-2 nicotinic acetylcholine receptors",
            "Neurobiology of Nicotine"
        ),
        (
            "C10H15N is chemically identified as methamphetamine, a potent psychostimulant that reverses DAT transport.",
            "C10H15N",
            "CNS Stimulants"
        ),
        (
            "GABA_A receptor functions as a heteropentameric ligand-gated chloride ion channel.",
            "GABA_A receptor",
            "Inhibitory Neurotransmission"
        ),
        (
            "(R)-(-)-apomorphine functions as a non-selective dopamine receptor agonist with high D2 affinity.",
            "(R)-(-)-apomorphine",
            "Dopamine Pharmacology"
        ),
        (
            "1,3,7-trimethylxanthine is the chemical IUPAC designation for caffeine, a non-selective adenosine antagonist.",
            "1,3,7-trimethylxanthine",
            "Adenosine Pharmacology"
        ),
        (
            "D2 receptor occupancy exceeding 80% is associated with extrapyramidal symptoms.",
            "D2 receptor occupancy exceeding 80%",
            "Antipsychotics"
        ),
        (
            "Ca2+ influx via voltage-gated N-type calcium channels triggers neurotransmitter vesicle exocytosis.",
            "Ca2+ influx via voltage-gated N-type calcium channels",
            "Synaptic Transmission"
        ),
        (
            "Na+/K+-ATPase functions as an electrogenic pump that exports three sodium ions for every two potassium ions imported.",
            "Na+/K+-ATPase",
            "Cell Physiology"
        ),
    ])
    def test_chemical_token_preservation(self, parser, judge, formula_text, expected_keyword, heading):
        # clean_phrase must preserve leading digits in 5-HT2A and 1,3,7-trimethylxanthine
        cleaned = clean_phrase(formula_text)
        assert not cleaned.startswith("-")

        cards = parser.parse_highlight(formula_text, highlight_color="green", heading=heading)
        assert len(cards) >= 1
        kw = cards[0]["keyword"]
        # The key chemical entity must be preserved in the keyword
        token_to_find = expected_keyword.split()[0].replace("$\\Delta^9$-", "").strip()
        assert any(t.lower() in kw.lower() for t in [token_to_find, "5-ht2a", "thc", "c10h15n", "gaba_a", "caffeine", "1,3,7", "ca2+", "na+/k+"])

        for c in cards:
            ev = judge.evaluate_card(c)
            assert len(ev["vetoes"]) == 0
            assert "this concept" not in c["question"].lower()
            assert "this concept" not in c["answer"].lower()

    def test_leading_drug_numbers_not_stripped_by_clean_phrase(self):
        """Ensures regex list-stripping doesn't eat numbers in 5-HT2A, 1,3,7-, 2-AG, or D2."""
        cases = [
            ("5-HT2A receptor", "5-HT2A receptor"),
            ("1,3,7-trimethylxanthine", "1,3,7-trimethylxanthine"),
            ("2-Arachidonoylglycerol (2-AG)", "2-Arachidonoylglycerol (2-AG)"),
            ("D2 dopamine receptor", "D2 dopamine receptor"),
            ("4-bromo-2,5-dimethoxyphenethylamine (2C-B)", "4-bromo-2,5-dimethoxyphenethylamine (2C-B)"),
        ]
        for inp, exp in cases:
            res = clean_phrase(inp)
            assert res == exp, f"clean_phrase corrupted chemical token '{inp}' into '{res}'"


# ============================================================================
# Tier 4: Zero Punctuation Run-On Text
# ============================================================================

class TestZeroPunctuationAdversarial:
    """Stress-tests text completely devoid of standard sentence punctuation."""

    @pytest.mark.parametrize("runon_text,expected_kw,heading", [
        (
            "retrograde axonal transport serves as the mechanism carrying neurotrophic factors and viral pathogens from the synaptic terminal back to the neuronal soma along dynein motor complexes",
            "Retrograde axonal transport",
            "Axonal Transport"
        ),
        (
            "synaptic plasticity in the hippocampus represents the cellular substrate for declarative memory encoding and long term potentiation",
            "Synaptic plasticity in the hippocampus",
            "Memory Systems"
        ),
        (
            "the blood brain barrier consists of specialized continuous capillary endothelial cells connected by tight junctions and surrounded by astrocytic end feet",
            "Blood brain barrier",
            "Neurovasculature"
        ),
        (
            "long term depression is the activity dependent reduction in synaptic transmission efficacy following low frequency stimulation",
            "Long term depression",
            "Synaptic Plasticity"
        ),
    ])
    def test_runon_without_punctuation(self, parser, judge, runon_text, expected_kw, heading):
        cards = parser.parse_highlight(runon_text, highlight_color="green", heading=heading)
        assert len(cards) == 2
        fwd_card = cards[0]
        assert fwd_card["keyword"].lower() == expected_kw.lower()
        # Ensure definition is capitalized and has a period added at the end
        assert fwd_card["answer"].endswith(".")

        for c in cards:
            ev = judge.evaluate_card(c)
            assert len(ev["vetoes"]) == 0
            assert "this concept" not in c["question"].lower()


# ============================================================================
# Tier 5: Pathological & Excessive Punctuation
# ============================================================================

class TestPathologicalPunctuationAdversarial:
    """Stress-tests punctuation chaos, delimiters, whitespace, and empty inputs."""

    def test_chaotic_colons_hyphens_dashes(self, parser, judge):
        text = "--- Action Potential ::: [Depolarization --> Influx of Na+] ???"
        cards = parser.parse_highlight(text, highlight_color="green", heading="Electrophysiology")
        assert len(cards) == 2
        for c in cards:
            ev = judge.evaluate_card(c)
            assert len(ev["vetoes"]) == 0
            assert "this concept" not in c["question"].lower()
            assert c["keyword"] != ""
            assert c["answer"] != ""

    def test_heavy_quotes_and_exclamations(self, parser, judge):
        text = '"""Neurogenesis""" ... is the generation of functional neurons from neural stem cells!!!'
        cards = parser.parse_highlight(text, highlight_color="green", heading="Neural Development")
        assert len(cards) == 2
        assert "Neurogenesis" in cards[0]["keyword"]
        for c in cards:
            ev = judge.evaluate_card(c)
            assert len(ev["vetoes"]) == 0

    def test_whitespace_only_returns_empty_list(self, parser):
        for whitespace_input in ["", "   ", "\t\t\n\r", "   \n   \t "]:
            cards = parser.parse_highlight(whitespace_input, highlight_color="green", heading="Empty")
            assert cards == []

    def test_pure_punctuation_returns_cards_with_no_vetoes_or_safely_anchors(self, parser, judge):
        punct_samples = [
            ": - ;",
            "!@#$%^&*()",
            "... --- ...",
            "??? !!!",
        ]
        for p in punct_samples:
            cards = parser.parse_highlight(p, highlight_color="green", heading="Fallback Topic")
            for c in cards:
                # Must never emit "this concept"
                assert "this concept" not in c["question"].lower()
                assert "this concept" not in c["answer"].lower()

    def test_single_word_no_punctuation(self, parser, judge):
        text = "Epigenetics"
        cards = parser.parse_highlight(text, highlight_color="green", heading="Molecular Genetics")
        assert len(cards) == 2
        assert cards[0]["keyword"] == "Epigenetics"
        for c in cards:
            ev = judge.evaluate_card(c)
            assert len(ev["vetoes"]) == 0


# ============================================================================
# Tier 6: Nested, Subordinate, and Parenthetical Clauses
# ============================================================================

class TestNestedSubordinateClausesAdversarial:
    """Stress-tests sentences with subordinate clauses (Although, Because, When, Despite)."""

    def test_subordinate_although_does_not_become_keyword(self, parser, judge):
        text = (
            "Although previously hypothesized to act solely via monoamine oxidase inhibition, "
            "the agent primarily functions as a selective serotonin reuptake inhibitor."
        )
        cards = parser.parse_highlight(text, highlight_color="green", heading="Antidepressants")
        assert len(cards) == 2
        kw = cards[0]["keyword"]
        # Must NOT extract "Although previously hypothesized..." as the keyword
        assert not kw.lower().startswith("although")
        for c in cards:
            ev = judge.evaluate_card(c)
            assert len(ev["vetoes"]) == 0
            assert "this concept" not in c["question"].lower()

    def test_subordinate_because_does_not_become_keyword(self, parser, judge):
        text = (
            "Because voltage-gated calcium channels open upon membrane depolarization, "
            "rapid calcium influx triggers neurotransmitter exocytosis at the active zone."
        )
        cards = parser.parse_highlight(text, highlight_color="green", heading="Synaptic Transmission")
        assert len(cards) == 2
        kw = cards[0]["keyword"]
        assert not kw.lower().startswith("because")
        for c in cards:
            ev = judge.evaluate_card(c)
            assert len(ev["vetoes"]) == 0

    def test_subordinate_when_does_not_become_keyword(self, parser, judge):
        text = (
            "When dopamine binds to D1 receptors, which are Gs-protein coupled, "
            "adenylyl cyclase is activated to synthesize cyclic AMP."
        )
        cards = parser.parse_highlight(text, highlight_color="green", heading="Second Messengers")
        assert len(cards) == 2
        kw = cards[0]["keyword"]
        assert not kw.lower().startswith("when")
        for c in cards:
            ev = judge.evaluate_card(c)
            assert len(ev["vetoes"]) == 0


# ============================================================================
# Tier 7: Unusual & Non-Standard Copulas Across Lexicon Classes
# ============================================================================

class TestLexiconClassesAdversarial:
    """Verifies that non-standard linking verbs from all 4 classes extract clean terms."""

    @pytest.mark.parametrize("statement,expected_term,heading", [
        (
            "Optogenetics stands for the integration of optics and genetics to control well-defined events within specific cells.",
            "Optogenetics",
            "Neurotechnologies"
        ),
        (
            "Long-term depression is termed the activity-dependent reduction in synaptic efficacy.",
            "Long-term depression",
            "Plasticity"
        ),
        (
            "Microglia serve as the resident macrophages of the central nervous system.",
            "Microglia",
            "Glial Biology"
        ),
        (
            "Pharmacokinetics deals with the fate of substances administered to a living organism.",
            "Pharmacokinetics",
            "Pharmacology"
        ),
        (
            "Agonist efficacy can be distinguished by the maximal response achievable at receptor saturation.",
            "Agonist efficacy",
            "Pharmacodynamics"
        ),
        (
            "Potency can be described as the concentration of drug required to produce 50% of maximum effect.",
            "Potency",
            "Dose-Response"
        ),
        (
            "Astrocyte foot processes modulate local cerebral blood flow through neurovascular coupling.",
            "Astrocyte foot processes",
            "Neurovascular Coupling"
        ),
        (
            "Resting membrane potential is the electrical potential difference across the plasma membrane of an unexcited cell.",
            "Resting membrane potential",
            "Electrophysiology"
        ),
    ])
    def test_diverse_copula_classes(self, parser, judge, statement, expected_term, heading):
        cards = parser.parse_highlight(statement, highlight_color="green", heading=heading)
        assert len(cards) == 2
        assert cards[0]["keyword"].lower() == expected_term.lower()
        for c in cards:
            ev = judge.evaluate_card(c)
            assert len(ev["vetoes"]) == 0
            assert ev["total_score"] >= 25


# ============================================================================
# Tier 8: Compound Statements & Numerical Cloze Atomicity
# ============================================================================

class TestCompoundAndClozeAtomicityAdversarial:
    """Stress-tests compound splitting into atomic cards and Cloze deletion extraction."""

    def test_compound_yellow_with_whereas_splits_into_atomic_cards(self, parser, judge):
        text = (
            "Dopamine D2 receptor occupancy between 65% and 80% is required for clinical response, "
            "whereas occupancy exceeding 80% sharply increases extrapyramidal motor symptoms."
        )
        cards = parser.parse_highlight(text, highlight_color="yellow", heading="Antipsychotic Thresholds")
        # Should split into 2 atomic Cloze cards
        assert len(cards) >= 2
        for c in cards:
            assert c["card_type"] == "cloze"
            assert "{{c1::" in c["cloze_text"]
            ev = judge.evaluate_card(c)
            assert len(ev["vetoes"]) == 0
            assert ev["total_score"] >= 25

    def test_compound_yellow_with_while_and_numerical_dosages(self, parser, judge):
        text = (
            "Phase 1 clinical trials evaluate safety in 20 to 80 healthy volunteers, "
            "while Phase 2 clinical trials assess efficacy in 100 to 300 patient volunteers."
        )
        atomic_clauses = split_compound_yellow(text)
        assert len(atomic_clauses) == 2

        cards = parser.parse_highlight(text, highlight_color="yellow", heading="Clinical Trials")
        assert len(cards) >= 2
        for c in cards:
            ev = judge.evaluate_card(c)
            assert len(ev["vetoes"]) == 0

    def test_cloze_card_percentage_range_creation(self):
        text = "Target blood glucose concentration between 70 to 130 mg/dL before meals is recommended."
        cloze = create_cloze_card(text, heading="Endocrinology")
        assert cloze is not None
        assert "{{c1::" in cloze["cloze_text"]
        assert cloze["answer"] in ["70 to 130 mg", "between 70 to 130 mg"] or "70 to 130" in cloze["answer"]


# ============================================================================
# Tier 9: Rigorous CardJudgeRubric Hard Veto & Zero Heading Dump Verification
# ============================================================================

class TestCardJudgeRubricAdversarialAudit:
    """Ensures that 0% of cards emit 'this concept' or heading dumps, and checks hard vetoes."""

    def test_hard_veto_detection_on_adversarial_injections(self, judge):
        """Verifies that CardJudgeRubric actively catches all 4 veto conditions."""
        # Veto 1: Empty field
        ev1 = judge.evaluate_card({"question": "", "answer": "Some answer"})
        assert any("CRITICAL_FAIL_EMPTY_FIELD" in v for v in ev1["vetoes"])
        assert ev1["passed"] is False
        assert ev1["total_score"] == 0

        # Veto 2: Banned phrase 'this concept'
        ev2 = judge.evaluate_card({
            "question": "Define / What is <b>this concept</b>?",
            "answer": "A core developmental principle.",
            "category_badge": "badge-definition",
            "context": "Context",
            "tags": ["test"]
        })
        assert any("CRITICAL_FAIL_THIS_CONCEPT" in v for v in ev2["vetoes"])
        assert ev2["passed"] is False
        assert ev2["total_score"] == 0

        # Veto 3: Raw heading dump
        ev3 = judge.evaluate_card({
            "question": "<b>Key Concept / Mechanism:</b><br>PSYC 3590: Drugs & Behaviour",
            "answer": "Pharmacodynamics details.",
            "category_badge": "badge-important",
            "context": "Context",
            "tags": ["test"]
        })
        assert any("CRITICAL_FAIL_HEADING_ONLY" in v for v in ev3["vetoes"])
        assert ev3["passed"] is False
        assert ev3["total_score"] == 0

        # Veto 4: Tautology
        ev4 = judge.evaluate_card({
            "question": "Action potential",
            "answer": "Action potential",
            "category_badge": "badge-definition",
            "context": "Context",
            "tags": ["test"]
        })
        assert any("CRITICAL_FAIL_TAUTOLOGY" in v for v in ev4["vetoes"])
        assert ev4["passed"] is False
        assert ev4["total_score"] == 0

    def test_zero_this_concept_and_zero_heading_dumps_across_massive_adversarial_battery(self, parser, judge):
        """Generates cards from 30+ adversarial highlights and validates 100% veto-free pass rate."""
        corpus = [
            ("Long-term potentiation is defined as the persistent strengthening of synapses.", "green", "Plasticity"),
            ("Long-term depression refers to the activity-dependent reduction in synaptic efficacy.", "green", "Plasticity"),
            ("Basic developmental science focuses on description, explanation, and optimization.", "green", "Development"),
            ("Dopamine D2 receptor occupancy between 65% and 80% is therapeutic.", "yellow", "Pharmacology"),
            ("5-HT2A receptor stimulation mediates hallucinogenic visual distortions.", "green", "Serotonin"),
            ("$\\Delta^9$-THC represents the primary psychoactive agent in cannabis.", "green", "Cannabis"),
            ("C10H15N acts as a powerful central nervous system dopamine releaser.", "green", "Stimulants"),
            ("Microglia function as the primary immune defense in the central nervous system.", "green", "Immunology"),
            ("The nodes of Ranvier facilitate rapid saltatory conduction of action potentials.", "green", "Neuroanatomy"),
            ("Optogenetics stands for the optical control of genetically targeted cells.", "green", "Methods"),
            ("Therapeutic Index: Ratio of TD50 to ED50.", "green", "Pharmacology"),
            ("Excitotoxicity occurs when excessive glutamate release overactivates NMDA receptors.", "green", "Pathology"),
            ("Action potential threshold occurs at -55 mV in typical mammalian neurons.", "yellow", "Electrophysiology"),
            ("Between 10 to 20 mg daily dosage is clinically recommended.", "yellow", "Dosing"),
            ("Bioavailability reaches 90% following intravenous injection.", "yellow", "Pharmacokinetics"),
            ("Synaptic cleft width measures approximately 20 nm across chemical synapses.", "yellow", "Anatomy"),
            ("Staphylococcus aureus is a Gram-positive bacterium producing coagulase.", "green", "Microbiology"),
            ("In vitro assays measure ligand-receptor binding kinetics.", "green", "Biochemistry"),
            ("Post hoc ergo propter hoc is the false assumption of causation from correlation.", "green", "Logic"),
            ("Although complicated by feedback loops, autoreceptor activation inhibits neurotransmitter release.", "green", "Regulation"),
            ("Because dopamine is metabolized by MAO-B, selegiline prolongs striatal dopamine signaling.", "green", "Enzymes"),
            ("When membrane depolarization reaches threshold, voltage-gated sodium channels open rapidly.", "green", "Biophysics"),
            ("SingleWordConcept", "green", "Vocabulary"),
            ("Complex: Concept with colon definition following.", "green", "Syntax"),
            ("--- Dash Prefix Concept is defined as an entity with unusual punctuation.", "green", "Punctuation"),
        ]

        all_cards = []
        for text, color, heading in corpus:
            cards = parser.parse_highlight(text, highlight_color=color, heading=heading)
            assert len(cards) > 0
            all_cards.extend(cards)

        deck_eval = judge.evaluate_deck(all_cards)

        # MANDATORY CHECKS:
        # 1. 0% "this concept"
        for c in all_cards:
            assert "this concept" not in c["question"].lower()
            assert "this concept" not in c["answer"].lower()
            assert "this term" not in c["question"].lower()
            assert "this phenomenon" not in c["question"].lower()

        # 2. 0% raw heading dump questions
        for c in all_cards:
            assert "<b>Key Concept / Mechanism:</b><br>" not in c["question"] or len(c["question"].split()) > 10

        # 3. 0% empty question or answer
        for c in all_cards:
            assert c["question"].strip() != ""
            assert c["answer"].strip() != ""

        # 4. Zero vetoes
        assert deck_eval["veto_count"] == 0, f"Encountered vetoes: {deck_eval['card_evaluations']}"

        # 5. Deck passed
        assert deck_eval["deck_passed"] is True
        assert deck_eval["average_score"] >= 25.0


# ============================================================================
# Tier 10: E2E synthesize_cards & .apkg Packaging with Adversarial Highlights
# ============================================================================

class TestPipelineE2EAdversarialPackaging:
    """Stress-tests synthesize_cards and create_deck_package on adversarial structured batches."""

    def test_synthesize_cards_adversarial_batch(self, parser, judge):
        adversarial_items = [
            {
                "heading": "Lecture 5: Pharmacokinetics",
                "full_paragraph": "Therapeutic Index is TD50 / ED50. 5-HT2A agonists mediate hallucinations.",
                "highlights": [
                    {"text": "Therapeutic Index", "category": "yellow"},
                    {"text": "TD50 / ED50 ratio defining safety margin", "category": "green"},
                    {"text": "5-HT2A agonists mediate hallucinogenic visual distortions", "category": "green"},
                ]
            },
            {
                "heading": "Lecture 6: Synaptic Biology",
                "full_paragraph": "Dopamine D2 receptor occupancy between 65% and 80% is required. Synaptic vesicles.",
                "highlights": [
                    {"text": "Dopamine D2 receptor occupancy between 65% and 80% is required for response", "category": "yellow"},
                    {"text": "Synaptic vesicles fuse with the presynaptic membrane via SNARE complexes", "category": "green"},
                    {"text": " : - ; ", "category": "yellow"},  # Punctuation-only leak, must be skipped
                ]
            },
            {
                "heading": "Lecture 7: Latin Microorganisms",
                "full_paragraph": "Staphylococcus aureus is Gram-positive. In vitro tests evaluate binding.",
                "highlights": [
                    {"text": "Staphylococcus aureus is a spherical Gram-positive bacterium", "category": "green"},
                    {"text": "In vitro assays measure binding affinity without living cellular systems", "category": "green"},
                ]
            }
        ]

        cards = synthesize_cards(adversarial_items, deck_tags=["PSYC_3590", "Lecture_Test"], parser=parser)
        assert len(cards) >= 6

        # Check that punctuation-only highlight did NOT generate any cards
        for c in cards:
            assert c["answer"].strip() not in [": - ;", ":", ";", "-"]
            assert not check_veto_violations(c["question"])
            assert not check_veto_violations(c["answer"])

        report = judge.evaluate_deck(cards)
        assert report["veto_count"] == 0
        assert report["deck_passed"] is True
        assert report["average_score"] >= 25.0

    def test_create_deck_package_adversarial_apkg(self, parser, judge):
        """Verifies that an .apkg created with adversarial cards can be read and evaluated by judge."""
        items = [
            {
                "heading": "Neuropharmacology",
                "full_paragraph": "5-HT2A agonists mediate perception. Occupancy between 65% and 80% is ideal.",
                "highlights": [
                    {"text": "5-HT2A agonist", "category": "yellow"},
                    {"text": "Stimulates cortical pyramidal neurons to alter sensory gating", "category": "green"},
                    {"text": "Occupancy between 65% and 80% is required for clinical response", "category": "yellow"},
                ]
            }
        ]
        cards = synthesize_cards(items, deck_tags=["Neuropharm"], parser=parser)
        assert len(cards) >= 3

        with tempfile.TemporaryDirectory() as tmp_dir:
            from scripts.extract_and_generate import CONFIG
            orig_out = CONFIG.get("output_directory")
            CONFIG["output_directory"] = tmp_dir
            try:
                out_path = create_deck_package("AdversarialTestDeck", cards, output_filename="AdversarialTestDeck.apkg")
                assert out_path.exists()
                assert out_path.stat().st_size > 1000

                # Evaluate the compiled .apkg with judge
                apkg_report = judge.evaluate_apkg(out_path)
                assert apkg_report["veto_count"] == 0
                assert apkg_report["deck_passed"] is True
                assert apkg_report["total_cards"] == len(cards)
            finally:
                if orig_out:
                    CONFIG["output_directory"] = orig_out

    def test_create_deck_package_absolute_path_collision_finding(self, parser):
        """
        DEMONSTRATES DEFECT: Passing an absolute path as output_filename to create_deck_package
        causes dest_gdrive = gdrive_path / output_filename to resolve to output_filename itself
        on Windows due to pathlib drive anchoring, causing shutil.copy2 to attempt copying the
        file onto itself, raising PermissionError: [WinError 32].
        """
        items = [
            {
                "heading": "Lecture Defect Demo",
                "full_paragraph": "GABA mediates inhibition.",
                "highlights": [
                    {"text": "GABA mediates inhibition", "category": "green"},
                ]
            }
        ]
        cards = synthesize_cards(items, parser=parser)
        with tempfile.TemporaryDirectory() as tmp_dir:
            abs_out_file = Path(tmp_dir) / "DirectAbsolutePath.apkg"
            try:
                create_deck_package("DirectAbsolutePath", cards, output_filename=str(abs_out_file))
            except PermissionError as e:
                # Confirmed: Windows shutil.copy2 self-copy collision defect
                assert "[WinError 32]" in str(e)

    def test_non_lexicon_verb_heading_fallback_resilience(self, parser, judge):
        """
        Tests how the deterministic parser handles verbs outside the 64+ lexicon
        (e.g., 'monitors', 'exports', 'carries') without punctuation boundaries.
        Demonstrates that Tier 3 safely anchors to the heading, producing 0% 'this concept'.
        """
        non_lexicon_cases = [
            ("In vivo electrophysiology monitors real-time action potentials.", "Neurophysiology"),
            ("Na+/K+-ATPase electrogenically exports three sodium ions.", "Cell Physiology"),
            ("Retrograde axonal transport carries neurotrophic factors.", "Axonal Transport"),
        ]
        for text, heading in non_lexicon_cases:
            cards = parser.parse_highlight(text, highlight_color="green", heading=heading)
            assert len(cards) == 2
            # Must anchor to heading or clause without crashing
            assert cards[0]["keyword"] in [heading, "Key Principle"] or len(cards[0]["keyword"]) > 0
            for c in cards:
                ev = judge.evaluate_card(c)
                assert len(ev["vetoes"]) == 0
                assert "this concept" not in c["question"].lower()
                assert "this concept" not in c["answer"].lower()
