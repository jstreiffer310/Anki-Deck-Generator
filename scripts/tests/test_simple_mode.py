"""
Unit and Integration Tests for Simple Recall Mode (Green Definitions Only)
Verifies:
1. Pure Term ⇄ Definition extraction without robotic question wrappers
2. Extraction of explicit "Term: Definition" colon syntax
3. Disqualification of study notes (RECALL, NOTE, etc.)
4. Generation of genuine Anki Basic (and reversed card) notes with sibling burying
5. Proper packaging into .apkg with SIMPLE_ANKI_MODEL (ID: 1847291040)
"""

import pytest
import zipfile
import sqlite3
from pathlib import Path
from scripts.extract_and_generate import (
    synthesize_cards,
    create_deck_package,
    process_source_and_generate,
    SIMPLE_ANKI_MODEL
)

def test_simple_mode_colon_split():
    structured_data = [
        {
            "heading": "Lecture 1 – Psychoactive Drugs",
            "heading_hierarchy": ["Ch1", "Lecture 1", "Foundational Concepts"],
            "full_paragraph": "Drug: Any substance by which the chemical structure alters structure or function.",
            "highlights": [
                {
                    "category": "green",
                    "text": "Drug: Any substance (artificial OR natural) by which the chemical structure alters structure, or function, in the living organism."
                }
            ]
        }
    ]

    cards = synthesize_cards(structured_data, simple_mode=True)
    assert len(cards) == 1
    c = cards[0]
    assert c["card_type"] == "simple_bidirectional"
    assert c["front"] == "Drug"
    assert "Any substance (artificial OR natural)" in c["back"]
    assert c["category_badge"] == "badge-definition"
    assert "simple_mode" in c["tags"]

def test_simple_mode_typographic_dash_split():
    structured_data = [
        {
            "heading": "What is Culture?",
            "heading_hierarchy": ["Ch1", "Lecture 1"],
            "full_paragraph": "Culture – the shared physical, behavioural, or symbolic features of a community.",
            "highlights": [
                {
                    "category": "green",
                    "text": "Culture – the shared physical, behavioural, or symbolic features of a community."
                }
            ]
        }
    ]

    cards = synthesize_cards(structured_data, simple_mode=True)
    assert len(cards) == 1
    c = cards[0]
    assert c["card_type"] == "simple_bidirectional"
    assert c["front"] == "Culture"
    assert "The shared physical, behavioural, or symbolic features" in c["back"]

def test_simple_mode_ignores_study_notes():
    structured_data = [
        {
            "heading": "Lecture 1 – Important Terms",
            "heading_hierarchy": ["Ch1", "Lecture 1"],
            "full_paragraph": "RECALL (Ch1 Definition) Addiction: A chronic, relapsing condition...",
            "highlights": [
                {
                    "category": "yellow",
                    "text": "RECALL (Ch1 Definition)"
                },
                {
                    "category": "green",
                    "text": "Addiction: A chronic, relapsing condition characterized by impulsive drug seeking."
                }
            ]
        }
    ]

    cards = synthesize_cards(structured_data, simple_mode=True)
    assert len(cards) == 1
    c = cards[0]
    # The term MUST be Addiction, NOT the study note "RECALL (Ch1 Definition)"
    assert c["front"] == "Addiction"
    assert "A chronic, relapsing condition" in c["back"]

def test_simple_mode_paired_yellow_term():
    structured_data = [
        {
            "heading": "Neural Development Stages",
            "heading_hierarchy": ["Lecture 2", "Brain Development"],
            "full_paragraph": "Synaptogenesis is the formation of synapses between neurons in the nervous system.",
            "highlights": [
                {
                    "category": "yellow",
                    "text": "Synaptogenesis"
                },
                {
                    "category": "green",
                    "text": "The formation of synapses between neurons in the nervous system."
                }
            ]
        }
    ]

    cards = synthesize_cards(structured_data, simple_mode=True)
    assert len(cards) == 1
    c = cards[0]
    assert c["front"] == "Synaptogenesis"
    assert "The formation of synapses between neurons" in c["back"]

def test_simple_mode_skips_standalone_yellows_and_active_recall():
    structured_data = [
        {
            "heading": "The (Drug) Problem",
            "heading_hierarchy": ["Ch1", "The Problem"],
            "full_paragraph": "What constitutes Abuse????? (not so simple)",
            "highlights": [
                {
                    "category": "yellow",
                    "text": "What constitutes Abuse????? (not so simple)"
                }
            ]
        }
    ]

    cards = synthesize_cards(structured_data, simple_mode=True)
    # Simple mode MUST NOT generate active recall questions for yellow notes
    assert len(cards) == 0

def test_simple_deck_packaging_uses_two_card_model(tmp_path):
    cards = [
        {
            "card_type": "simple_bidirectional",
            "keyword": "Synaptogenesis",
            "descriptor": "The formation of synapses between neurons.",
            "front": "Synaptogenesis",
            "back": "The formation of synapses between neurons.",
            "question": "Synaptogenesis",
            "answer": "The formation of synapses between neurons.",
            "category_badge": "badge-definition",
            "context": "Brain Development",
            "tags": ["simple_mode", "definition", "Brain_Development"]
        }
    ]

    out_file = tmp_path / "simple_test.apkg"
    create_deck_package("Simple Test Deck", cards, output_filename=str(out_file))

    assert out_file.exists()

    # Inspect the .apkg zip archive
    with zipfile.ZipFile(out_file, "r") as z:
        z.extractall(tmp_path / "extracted")

    db_path = tmp_path / "extracted" / "collection.anki2"
    assert db_path.exists()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Check note count: exactly 1 note
    cur.execute("SELECT count(*) FROM notes")
    note_count = cur.fetchone()[0]
    assert note_count == 1

    # Check model ID matches SIMPLE_ANKI_MODEL
    cur.execute("SELECT mid, flds FROM notes LIMIT 1")
    mid, flds = cur.fetchone()
    assert mid == SIMPLE_ANKI_MODEL.model_id
    fields = flds.split("\x1f")
    assert fields[0] == "Synaptogenesis"
    assert fields[1] == "The formation of synapses between neurons."

    # Check cards count: exactly 2 cards generated from that 1 note (siblings!)
    cur.execute("SELECT count(*) FROM cards")
    card_count = cur.fetchone()[0]
    assert card_count == 2, "A single Basic (and reversed card) note must generate exactly 2 cards"

    conn.close()
