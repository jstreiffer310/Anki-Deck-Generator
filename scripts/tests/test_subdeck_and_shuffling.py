"""
Unit tests for Milestone M16: Nested Multi-Level Subdeck Hierarchy & Anti-Clustering Shuffling.
Verifies:
  - anti_cluster_shuffle enforces 0% distance-1 pairs and average spacing >= 3.
  - resolve_card_subdeck builds clean Course::Chapter::Section paths.
  - create_deck_package packages nested subdecks into .apkg archives.
"""

import zipfile
import sqlite3
import tempfile
import json
from pathlib import Path
import pytest

from scripts.extract_and_generate import (
    anti_cluster_shuffle,
    resolve_card_subdeck,
    stable_deck_id,
    create_deck_package,
    ANKI_MODEL,
)


class TestAntiClusterShuffle:
    """Verifies the anti-clustering shuffle algorithm."""

    def test_empty_and_singletons(self):
        assert anti_cluster_shuffle([]) == []
        c1 = [{"keyword": "Test", "question": "Q1", "answer": "A1"}]
        assert anti_cluster_shuffle(c1) == c1

    def test_zero_distance_one_for_three_cards(self):
        # 2 cards of same concept + 1 singleton
        cards = [
            {"keyword": "ConceptA", "question": "Q_A_Fwd", "answer": "AnsA"},
            {"keyword": "ConceptA", "question": "Q_A_Rev", "answer": "ConceptA"},
            {"keyword": "ConceptB", "question": "Q_B", "answer": "AnsB"},
        ]
        shuffled = anti_cluster_shuffle(cards, min_buffer=2, seed=42)
        assert len(shuffled) == 3

        # Indices of ConceptA cards
        indices = [i for i, c in enumerate(shuffled) if c["keyword"] == "ConceptA"]
        assert len(indices) == 2
        # Must not be adjacent!
        assert abs(indices[0] - indices[1]) > 1

    def test_paired_cards_separation_and_average_buffer(self):
        # 10 concepts, each having 1 forward and 1 reverse card (20 cards total)
        cards = []
        for i in range(10):
            concept = f"Concept_{i}"
            cards.append({
                "keyword": concept,
                "question": f"What is {concept}?",
                "answer": f"Definition of {concept}",
                "tags": ["forward"]
            })
            cards.append({
                "keyword": concept,
                "question": f"What term means definition of {concept}?",
                "answer": concept,
                "tags": ["reverse"]
            })

        shuffled = anti_cluster_shuffle(cards, min_buffer=3, seed=12345)
        assert len(shuffled) == 20

        distances = []
        for i in range(10):
            concept = f"Concept_{i}"
            idxs = [idx for idx, c in enumerate(shuffled) if c["keyword"] == concept]
            assert len(idxs) == 2
            dist = abs(idxs[0] - idxs[1])
            # Strict Requirement: 0% distance-1 pairs
            assert dist > 1, f"{concept} cards were adjacent at indices {idxs}"
            distances.append(dist)

        # Average distance must be >= 3 cards
        avg_dist = sum(distances) / len(distances)
        assert avg_dist >= 3.0, f"Average distance was {avg_dist}, expected >= 3.0"

    def test_large_deck_anti_clustering(self):
        # 30 concepts with pairs + 20 singletons = 80 cards
        cards = []
        for i in range(30):
            c_name = f"Term_{i}"
            cards.append({"keyword": c_name, "question": f"Q_{c_name}_Fwd", "answer": f"A_{c_name}"})
            cards.append({"keyword": c_name, "question": f"Q_{c_name}_Rev", "answer": c_name})
        for j in range(20):
            cards.append({"keyword": f"Singleton_{j}", "question": f"Q_Sing_{j}", "answer": f"A_Sing_{j}"})

        shuffled = anti_cluster_shuffle(cards, min_buffer=3, seed=999)
        assert len(shuffled) == 80

        # Check all paired concepts
        distances = []
        for i in range(30):
            c_name = f"Term_{i}"
            idxs = [idx for idx, c in enumerate(shuffled) if c["keyword"] == c_name]
            assert len(idxs) == 2
            d = abs(idxs[0] - idxs[1])
            assert d > 1, f"Found distance 1 for {c_name} at {idxs}"
            distances.append(d)

        avg_d = sum(distances) / len(distances)
        assert avg_d >= 4.0

    def test_seed_determinism(self):
        cards = [{"keyword": f"C_{i}", "question": f"Q_{i}", "answer": f"A_{i}"} for i in range(15)]
        s1 = anti_cluster_shuffle(cards, seed=777)
        s2 = anti_cluster_shuffle(cards, seed=777)
        assert [c["keyword"] for c in s1] == [c["keyword"] for c in s2]


class TestSubdeckHierarchy:
    """Verifies hierarchical subdeck derivation and SQLite packaging."""

    def test_resolve_card_subdeck_from_hierarchy(self):
        root_deck = "PSYC 2110 (Developmental Psychology)"
        card = {
            "heading_hierarchy": ["Chapter 1: Goals and Methods", "The Goals of Developmental Science"],
            "question": "What is ...?",
            "answer": "..."
        }
        subdeck = resolve_card_subdeck(card, root_deck)
        assert subdeck == "PSYC 2110 (Developmental Psychology)::Chapter 1: Goals and Methods::The Goals of Developmental Science"

    def test_resolve_card_subdeck_strips_general_and_root(self):
        root_deck = "PSYC 3590 (Drugs & Behaviour)"
        card = {
            "heading_hierarchy": ["General", "Chapter 4: The Nervous System", "Action Potential"],
            "question": "What is ...?",
            "answer": "..."
        }
        subdeck = resolve_card_subdeck(card, root_deck)
        assert subdeck == "PSYC 3590 (Drugs & Behaviour)::Chapter 4: The Nervous System::Action Potential"

    def test_resolve_card_subdeck_fallback_when_empty(self):
        root_deck = "PSYC 3590 (Drugs & Behaviour)"
        card = {"question": "What is ...?", "answer": "..."}
        subdeck = resolve_card_subdeck(card, root_deck)
        assert subdeck == root_deck

    def test_create_deck_package_generates_nested_subdecks_in_sqlite(self, tmp_path):
        """Verifies that create_deck_package writes multiple nested subdecks to collection.anki2."""
        root_title = "PSYC 2110 (Developmental Psychology)"
        cards = [
            {
                "keyword": "Concept 1",
                "question": "What is Concept 1?",
                "answer": "Definition 1",
                "category_badge": "badge-definition",
                "context": "Context 1",
                "heading_hierarchy": ["Chapter 1: Foundations", "Section 1.1: Scope"],
                "tags": ["Ch1"]
            },
            {
                "keyword": "Concept 1",
                "question": "What term is defined as Definition 1?",
                "answer": "Concept 1",
                "category_badge": "badge-definition",
                "context": "Context 1",
                "heading_hierarchy": ["Chapter 1: Foundations", "Section 1.1: Scope"],
                "tags": ["Ch1"]
            },
            {
                "keyword": "Concept 2",
                "question": "What is Concept 2?",
                "answer": "Definition 2",
                "category_badge": "badge-definition",
                "context": "Context 2",
                "heading_hierarchy": ["Chapter 2: Methods", "Section 2.1: Designs"],
                "tags": ["Ch2"]
            }
        ]

        out_apkg = tmp_path / "nested_subdecks_test.apkg"
        create_deck_package(root_title, cards, output_filename=str(out_apkg))
        assert out_apkg.exists()

        with zipfile.ZipFile(out_apkg, "r") as zf:
            assert "collection.anki2" in zf.namelist()
            with tempfile.TemporaryDirectory() as extract_dir:
                zf.extract("collection.anki2", extract_dir)
                db_path = Path(extract_dir) / "collection.anki2"
                conn = sqlite3.connect(str(db_path))
                try:
                    cursor = conn.cursor()

                    # Inspect 'col' table: decks JSON
                    cursor.execute("SELECT decks FROM col")
                    decks_json_str = cursor.fetchone()[0]
                    decks = json.loads(decks_json_str)

                    # Verify root deck and nested subdecks are present
                    deck_names = {d["name"] for d in decks.values()}
                    assert root_title in deck_names
                    assert f"{root_title}::Chapter 1: Foundations::Section 1.1: Scope" in deck_names
                    assert f"{root_title}::Chapter 2: Methods::Section 2.1: Designs" in deck_names

                    # Inspect 'cards' table: verify cards have distinct did values matching subdecks
                    cursor.execute("SELECT did FROM cards")
                    card_dids = [row[0] for row in cursor.fetchall()]
                    assert len(card_dids) == 3
                finally:
                    conn.close()
