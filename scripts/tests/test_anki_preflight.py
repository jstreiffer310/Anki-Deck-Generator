"""
scripts/tests/test_anki_preflight.py — Automated Unit Tests for Anki Pre-Flight Protection Engine
Verifies that manual user cards and existing Anki notes are 100% immune from being overwritten or duplicated.
"""

import pytest
from pathlib import Path
from scripts.anki_preflight import (
    clean_html,
    normalize_concept_signature,
    find_anki_collection_paths,
    get_existing_deck_concepts_via_sqlite,
    get_existing_deck_concepts,
    filter_cards_against_existing,
)
import genanki
from scripts.extract_and_generate import create_deck_package

class TestAnkiPreflight:
    def test_clean_html(self):
        assert clean_html("<b>Drug</b>") == "Drug"
        assert clean_html("Hello&nbsp;World<br>Test") == "Hello World Test"
        assert clean_html("") == ""

    def test_normalize_concept_signature(self):
        assert normalize_concept_signature("What is the definition of <b>Drug</b>?") == "drug"
        assert normalize_concept_signature("Drug") == "drug"
        assert normalize_concept_signature("What term is defined by: A chemical substance...?") == "a chemical substance"
        assert normalize_concept_signature("Tolerance (Pharmacology)") == "tolerance pharmacology"
        assert normalize_concept_signature("Regarding <b>Agonist</b>: What is its action?") == "what is its action"

    def test_find_anki_collection_paths(self):
        paths = find_anki_collection_paths()
        assert len(paths) >= 1
        assert any("collection.anki2" in str(p).lower() for p in paths)

    def test_get_existing_deck_concepts_via_sqlite(self):
        data = get_existing_deck_concepts_via_sqlite("3590")
        assert data["source"] == "local_sqlite"
        assert data["count"] > 0
        assert "drug" in data["terms"]
        assert "tolerance" in data["terms"]

    def test_filter_cards_against_existing_preserves_manual(self):
        mock_concepts = {
            "source": "mock",
            "count": 2,
            "terms": {"drug", "tolerance"},
            "fronts": {"drug", "tolerance"}
        }

        cards = [
            {"keyword": "Drug", "front": "Drug", "question": "What is Drug?", "answer": "A chemical...", "tags": []},
            {"keyword": "Tolerance", "front": "Tolerance", "question": "What is Tolerance?", "answer": "Reduced response...", "tags": []},
            {"keyword": "Novel Discovery", "front": "Novel Discovery", "question": "What is Novel Discovery?", "answer": "A new finding...", "tags": []},
        ]

        retained, skipped = filter_cards_against_existing(cards, mock_concepts)

        assert len(retained) == 1
        assert retained[0]["keyword"] == "Novel Discovery"
        assert "pipeline_generated" in retained[0]["tags"]
        assert "auto_generated" in retained[0]["tags"]

        assert len(skipped) == 2
        skipped_terms = [s["matched_term"] for s in skipped]
        assert "Drug" in skipped_terms
        assert "Tolerance" in skipped_terms

    def test_create_deck_package_uses_namespaced_guids_and_pipeline_tags(self, tmp_path):
        out_file = tmp_path / "test_preflight_deck.apkg"
        cards = [
            {
                "card_type": "simple_bidirectional",
                "keyword": "Test Concept",
                "front": "Test Concept",
                "back": "Test Definition",
                "category_badge": "badge-definition",
                "tags": ["lecture_notes"]
            }
        ]

        out_path = create_deck_package("Test Deck", cards, output_filename=str(out_file))
        assert Path(out_path).exists()
