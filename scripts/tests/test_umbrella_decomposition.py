"""
Unit tests for Milestone M15: Contextual Sub-Component Expansion (SuperMemo Rule 6: Avoid Sets).
Verifies that high-level umbrella frameworks, models, and taxonomies (e.g., Developmental Niche,
ADME, Dopamine Pathways) are recursively decomposed into atomic cards for their constituent pillars.
"""

import pytest
from scripts.semantic_parser import (
    decompose_umbrella_model,
    UMBRELLA_MODELS,
    SemanticCardParser,
)
from scripts.extract_and_generate import synthesize_cards


class TestUmbrellaDecomposition:
    """Tests the umbrella model decomposition engine."""

    def test_developmental_niche_decomposition_pillars(self):
        """
        Concrete User Requirement:
        For 'Developmental Niche', the pipeline must generate both the overarching framework
        definition card AND separate, atomic cards for each of its 3 central components:
          1. Physical and Social Settings
          2. Culturally Regulated Customs
          3. Psychology of Caretakers (parental beliefs and ethnotheories)
        """
        text = "Super & Harkness (1986) developed the developmental niche framework to conceptualize culture's role in child development."
        result = decompose_umbrella_model(text, heading="Cultural Models", domain="developmental_psychology")

        assert result is not None
        assert result["canonical_name"] == "Developmental Niche"

        # Check framework cards
        fwd_fw = result["framework_cards"][0]
        assert "Developmental Niche" in fwd_fw["keyword"]
        assert "Super & Harkness" in fwd_fw["descriptor"]

        # Check that exactly 3 components are present
        comp_keywords = {c["keyword"] for c in result["component_cards"]}
        assert "Physical and Social Settings" in comp_keywords
        assert "Culturally Regulated Customs" in comp_keywords
        assert any("Psychology of Caretakers" in kw or "Parental Ethnotheories" in kw for kw in comp_keywords)

        # Rule 6 (Avoid Sets): ensure no question asks the student to list or recite all 3 components at once
        for card in result["all_cards"]:
            q_lower = card["question"].lower()
            assert "list all 3" not in q_lower
            assert "name the three" not in q_lower
            assert "what are the 3" not in q_lower

    def test_developmental_niche_heuristic_trigger_from_components(self):
        """Tests that text mentioning the 3 components triggers developmental niche even without the exact title."""
        text = "The child develops within physical settings, culturally regulated customs, and caretaker parental beliefs."
        result = decompose_umbrella_model(text, heading="Child Development", domain="developmental_psychology")

        assert result is not None
        assert result["canonical_name"] == "Developmental Niche"
        assert len(result["component_cards"]) == 6  # 3 components * 2 (fwd + rev)

    def test_pharmacokinetics_adme_decomposition(self):
        """Verifies ADME decomposition in pharmacology."""
        text = "Pharmacokinetics comprises ADME: the disposition of drugs within the human body."
        result = decompose_umbrella_model(text, heading="Pharmacokinetics", domain="pharmacology")

        assert result is not None
        assert "ADME" in result["canonical_name"] or "Pharmacokinetic" in result["canonical_name"]

        comp_keywords = {c["keyword"] for c in result["component_cards"]}
        assert "Absorption" in comp_keywords
        assert "Distribution" in comp_keywords
        assert any("Metabolism" in k for k in comp_keywords)
        assert any("Excretion" in k or "Elimination" in k for k in comp_keywords)

    def test_dopaminergic_pathways_decomposition(self):
        """Verifies decomposition of dopamine pathways."""
        text = "Four major ascending dopamine pathways project through the central nervous system."
        result = decompose_umbrella_model(text, heading="Neurotransmitters", domain="pharmacology")

        assert result is not None
        comp_keywords = {c["keyword"] for c in result["component_cards"]}
        assert "Mesolimbic Pathway" in comp_keywords
        assert "Mesocortical Pathway" in comp_keywords
        assert "Nigrostriatal Pathway" in comp_keywords
        assert "Tuberoinfundibular Pathway" in comp_keywords

    def test_autonomic_divisions_decomposition(self):
        """Verifies decomposition of autonomic nervous system divisions."""
        text = "The autonomic nervous system is divided into two reciprocal motor divisions."
        result = decompose_umbrella_model(text, heading="Autonomic Physiology", domain="pharmacology")

        assert result is not None
        comp_keywords = {c["keyword"] for c in result["component_cards"]}
        assert "Sympathetic Nervous System" in comp_keywords
        assert "Parasympathetic Nervous System" in comp_keywords

    def test_dynamic_unlisted_umbrella_extraction(self):
        """Verifies fallback regex for dynamic multi-part frameworks not in the curated registry."""
        text = (
            "Sternberg's Triarchic Model consists of three components: "
            "(1) Analytical Intelligence: internal information-processing mechanisms. "
            "(2) Creative Intelligence: ability to cope with novel situations. "
            "(3) Practical Intelligence: adapting to and shaping daily environments."
        )
        result = decompose_umbrella_model(text, heading="Intelligence Theories", domain="developmental_psychology")

        assert result is not None
        assert "Triarchic Model" in result["canonical_name"]
        comp_keywords = {c["keyword"] for c in result["component_cards"]}
        assert any("Analytical" in k for k in comp_keywords)
        assert any("Creative" in k for k in comp_keywords)
        assert any("Practical" in k for k in comp_keywords)

    def test_non_umbrella_text_returns_none(self):
        """Verifies regular factual and definitional statements do not falsely trigger umbrella decomposition."""
        text = "Colchicine is an alkaloid drug that inhibits microtubule polymerization."
        result = decompose_umbrella_model(text, heading="Drug Action", domain="pharmacology")
        assert result is None


class TestSynthesizeCardsUmbrellaIntegration:
    """Verifies that synthesize_cards seamlessly emits umbrella framework and decomposed subcomponents."""

    def test_synthesize_cards_standard_mode_developmental_niche(self):
        structured_data = [
            {
                "heading": "Chapter 2: Context and Culture",
                "heading_hierarchy": ["Chapter 2: Context and Culture", "The Cultural Ecology"],
                "full_paragraph": "The developmental niche (Super & Harkness) describes how culture structures child development.",
                "highlights": [
                    {
                        "category": "green",
                        "text": "The developmental niche is the theoretical framework conceptualizing cultural influences on child development."
                    }
                ]
            }
        ]

        cards = synthesize_cards(structured_data, domain="developmental_psychology", simple_mode=False)

        # Must contain framework card + 3 component pairs
        keywords = {c.get("keyword") for c in cards}
        assert "Developmental Niche" in keywords
        assert "Physical and Social Settings" in keywords
        assert "Culturally Regulated Customs" in keywords
        assert any("Psychology of Caretakers" in kw or "Parental Ethnotheories" in kw for kw in keywords)

        # Verify tagging
        decomposed_cards = [c for c in cards if "decomposed_subcomponent" in c.get("tags", [])]
        assert len(decomposed_cards) >= 6  # 3 pairs

    def test_synthesize_cards_simple_mode_developmental_niche(self):
        structured_data = [
            {
                "heading": "Chapter 2: Context and Culture",
                "heading_hierarchy": ["Chapter 2: Context and Culture", "The Cultural Ecology"],
                "full_paragraph": "The developmental niche (Super & Harkness) describes how culture structures child development.",
                "highlights": [
                    {
                        "category": "green",
                        "text": "The developmental niche is the framework structuring cultural influences."
                    }
                ]
            }
        ]

        cards = synthesize_cards(structured_data, domain="developmental_psychology", simple_mode=True)

        # In simple mode, each is a simple_bidirectional card
        for c in cards:
            assert c["card_type"] == "simple_bidirectional"
            assert "front" in c and "back" in c

        fronts = {c["front"] for c in cards}
        assert "Developmental Niche" in fronts
        assert "Physical and Social Settings (Developmental Niche)" in fronts or "Physical and Social Settings" in fronts
        assert "Culturally Regulated Customs (Developmental Niche)" in fronts or "Culturally Regulated Customs" in fronts
        assert any("Psychology of Caretakers" in f for f in fronts)
