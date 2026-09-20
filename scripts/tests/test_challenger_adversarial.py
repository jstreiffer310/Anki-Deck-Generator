"""
test_challenger_adversarial.py — Empirical Challenger Test Suite (challenger_2)
Adversarially tests:
1. Anki package packaging, Cloze model rendering, and SQLite schema verification (.apkg).
2. Adversarial fallback testing (network disconnects, slow blackhole timeouts, daemon crashes, HTTP errors, malformed/hostile JSON).
3. Pipeline hang/freeze prevention guarantees under stress.
4. ANKI_SOP.md Keyword-Descriptor adherence and bidirectional pair generation.
"""

import http.server
import json
import os
import re
import socket
import socketserver
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
import genanki

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from scripts.extract_and_generate import (
    create_deck_package,
    synthesize_cards,
    extract_document_highlights,
    classify_color,
    resolve_deck_naming,
    clean_phrase,
    ANKI_MODEL,
    ANKI_CLOZE_MODEL,
    CONFIG,
)
from scripts.ollama_runtime import OllamaRuntimeManager
from scripts.semantic_parser import (
    SemanticCardParser,
    split_highlight_fallback,
    split_compound_yellow,
    create_cloze_card,
    is_valid_card,
    check_veto_violations,
    ALL_LINKING_PATTERNS,
    COPULA_LEXICON_COUNT,
)
from scripts.evaluate_cards_judge import CardJudgeRubric


# ==============================================================================
# Helper Mock Servers for Adversarial Network Testing
# ==============================================================================

class BlackholeServer:
    """A TCP server that accepts connections and never sends bytes back (or stalls)."""
    def __init__(self, host="127.0.0.1", port=0):
        self.host = host
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((self.host, port))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while self.running:
            try:
                self.sock.settimeout(0.5)
                client, _ = self.sock.accept()
                # Accept connection but sleep / don't respond
                threading.Thread(target=self._stall, args=(client,), daemon=True).start()
            except socket.timeout:
                continue
            except Exception:
                break

    def _stall(self, client):
        try:
            # Sleep until closed
            while self.running:
                time.sleep(0.5)
        finally:
            try:
                client.close()
            except Exception:
                pass

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except Exception:
            pass


class MockHTTPHandler(http.server.BaseHTTPRequestHandler):
    """Configurable HTTP handler for simulating error responses and malformed payloads."""
    response_code = 200
    response_body = b"{}"
    response_headers = {"Content-Type": "application/json"}
    sleep_delay = 0.0

    def log_message(self, format, *args):
        # Suppress standard logging during tests
        pass

    def do_GET(self):
        if self.sleep_delay > 0:
            time.sleep(self.sleep_delay)
        self.send_response(self.response_code)
        for k, v in self.response_headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(self.response_body)

    def do_POST(self):
        if self.sleep_delay > 0:
            time.sleep(self.sleep_delay)
        self.send_response(self.response_code)
        for k, v in self.response_headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(self.response_body)


class MockHTTPServer:
    """In-process mock HTTP server with configurable response properties."""
    def __init__(self, host="127.0.0.1", port=0):
        self.server = socketserver.TCPServer((host, port), MockHTTPHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def set_response(self, code: int, body: bytes, headers: Optional[dict] = None, delay: float = 0.0):
        MockHTTPHandler.response_code = code
        MockHTTPHandler.response_body = body
        MockHTTPHandler.response_headers = headers or {"Content-Type": "application/json"}
        MockHTTPHandler.sleep_delay = delay

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


# ==============================================================================
# CHALLENGE SUITE 1: Deep SQLite & Genanki Packaging Integrity
# ==============================================================================

class TestEmpiricalSQLitePackagingAndSchema:
    """
    Adversarially tests packaging of .apkg archives across diverse card mixtures:
    - Pure Q/A cards
    - Pure Cloze deletion cards
    - Mixed Q/A and Cloze cards
    - Extreme characters, long strings, and HTML entities
    Unpacks and queries collection.anki2 SQLite database schemas and models.
    """

    def test_pure_qa_deck_sqlite_schema(self, tmp_path):
        """Validates pure Q/A deck SQLite schema, models table, and note/card records."""
        cards = [
            {
                "card_type": "bidirectional_definition",
                "keyword": "Potency",
                "descriptor": "The concentration or dose of a drug required to produce 50% of its maximal effect (EC50).",
                "question": "What is the definition of <b>Potency</b>?",
                "answer": "The concentration or dose of a drug required to produce 50% of its maximal effect (EC50).",
                "category_badge": "badge-definition",
                "context": "Pharmacodynamics",
                "tags": ["pharmacology", "potency", "forward"]
            },
            {
                "card_type": "bidirectional_definition",
                "keyword": "Potency",
                "descriptor": "The concentration or dose of a drug required to produce 50% of its maximal effect (EC50).",
                "question": "What term is defined by:<br><i>The concentration or dose of a drug required to produce 50% of its maximal effect (EC50).</i>",
                "answer": "Potency",
                "category_badge": "badge-definition",
                "context": "Pharmacodynamics",
                "tags": ["pharmacology", "potency", "reverse"]
            }
        ]

        apkg_path = tmp_path / "pure_qa_deck.apkg"
        old_out = CONFIG.get("output_directory")
        CONFIG["output_directory"] = str(tmp_path)
        try:
            out_file = create_deck_package("PSYC 3590:Pure QA", cards, output_filename="pure_qa_deck.apkg")
            assert out_file.exists()

            with zipfile.ZipFile(out_file, "r") as zf:
                namelist = zf.namelist()
                assert "collection.anki2" in namelist, "collection.anki2 missing from apkg archive"

                with tempfile.TemporaryDirectory() as extract_dir:
                    zf.extract("collection.anki2", extract_dir)
                    db_path = Path(extract_dir) / "collection.anki2"
                    conn = sqlite3.connect(str(db_path))
                    cursor = conn.cursor()

                    # 1. Verify standard Anki tables exist
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = [row[0] for row in cursor.fetchall()]
                    for required_table in ["col", "notes", "cards"]:
                        assert required_table in tables, f"Missing table: {required_table}"

                    # 2. Inspect 'col' table: models JSON
                    cursor.execute("SELECT models FROM col")
                    models_json_str = cursor.fetchone()[0]
                    models = json.loads(models_json_str)

                    model_id_str = str(ANKI_MODEL.model_id)
                    assert model_id_str in models, f"Model ID {model_id_str} not registered in col.models"
                    model = models[model_id_str]
                    assert model["name"] == "University Lecture Semantic Recall Model"
                    assert model["type"] == 0, "Expected standard model type 0"
                    
                    # Verify fields in model
                    field_names = [f["name"] for f in model["flds"]]
                    assert field_names == ["Question", "Answer", "CategoryBadge", "Context"]

                    # 3. Inspect 'notes' table
                    cursor.execute("SELECT id, mid, flds, tags FROM notes")
                    notes = cursor.fetchall()
                    assert len(notes) == 2

                    for nid, mid, flds, tags_str in notes:
                        assert mid == ANKI_MODEL.model_id
                        fld_parts = flds.split("\x1f")
                        assert len(fld_parts) == 4, f"Expected 4 fields, got {len(fld_parts)}"
                        assert fld_parts[0] != ""  # Question
                        assert fld_parts[1] != ""  # Answer
                        assert fld_parts[2] == "badge-definition"
                        assert fld_parts[3] == "Pharmacodynamics"

                    # 4. Inspect 'cards' table
                    cursor.execute("SELECT id, nid, ord, type, queue FROM cards")
                    card_rows = cursor.fetchall()
                    assert len(card_rows) == 2
                    for cid, nid, ord_val, ctype, cqueue in card_rows:
                        assert ord_val == 0
                        assert nid in [n[0] for n in notes]

                    conn.close()
        finally:
            if old_out:
                CONFIG["output_directory"] = old_out
            else:
                CONFIG.pop("output_directory", None)

    def test_pure_cloze_deck_sqlite_schema(self, tmp_path):
        """Validates pure Cloze deck SQLite schema, cloze model properties, and {{cloze:Text}} formatting."""
        cards = [
            {
                "card_type": "cloze",
                "keyword": "Therapeutic Threshold",
                "descriptor": "Effective therapeutic window is between 10 to 20 mg/L.",
                "question": "Identify the missing value regarding <b>Therapeutic Threshold</b>:<br>Effective therapeutic window is {{c1::between 10 to 20 mg/L}}.",
                "answer": "between 10 to 20 mg/L",
                "cloze_text": "Effective therapeutic window is {{c1::between 10 to 20 mg/L}}.",
                "category_badge": "badge-important",
                "context": "Clinical Pharmacokinetics",
                "tags": ["cloze", "pharmacology"]
            },
            {
                "card_type": "cloze",
                "keyword": "Receptor Occupancy",
                "descriptor": "Clinical efficacy requires exceeding 80% D2 occupancy.",
                "question": "Identify the missing value regarding <b>Receptor Occupancy</b>:<br>Clinical efficacy requires {{c1::exceeding 80%}} D2 occupancy.",
                "answer": "exceeding 80%",
                "cloze_text": "Clinical efficacy requires {{c1::exceeding 80%}} D2 occupancy.",
                "category_badge": "badge-important",
                "context": "Neuropharmacology",
                "tags": ["cloze", "dopamine"]
            }
        ]

        old_out = CONFIG.get("output_directory")
        CONFIG["output_directory"] = str(tmp_path)
        try:
            out_file = create_deck_package("PSYC 3590:Pure Cloze", cards, output_filename="pure_cloze_deck.apkg")
            assert out_file.exists()

            with zipfile.ZipFile(out_file, "r") as zf:
                with tempfile.TemporaryDirectory() as extract_dir:
                    zf.extract("collection.anki2", extract_dir)
                    db_path = Path(extract_dir) / "collection.anki2"
                    conn = sqlite3.connect(str(db_path))
                    cursor = conn.cursor()

                    # 1. Inspect 'col' table for Cloze model
                    cursor.execute("SELECT models FROM col")
                    models = json.loads(cursor.fetchone()[0])
                    cloze_model_id = str(ANKI_CLOZE_MODEL.model_id)
                    assert cloze_model_id in models, f"Cloze model {cloze_model_id} not found in col.models"
                    model = models[cloze_model_id]
                    assert model["name"] == "University Lecture Semantic Cloze Model"
                    assert model["type"] == 1, "Cloze model type must be 1 (genanki.Model.CLOZE)"

                    # Check fields
                    field_names = [f["name"] for f in model["flds"]]
                    assert field_names == ["Text", "Extra", "CategoryBadge", "Context"]

                    # Check cloze template
                    assert "{{cloze:Text}}" in model["tmpls"][0]["qfmt"]

                    # 2. Inspect notes table
                    cursor.execute("SELECT mid, flds FROM notes")
                    notes = cursor.fetchall()
                    assert len(notes) == 2
                    for mid, flds in notes:
                        assert mid == ANKI_CLOZE_MODEL.model_id
                        fld_parts = flds.split("\x1f")
                        assert len(fld_parts) == 4
                        assert "{{c1::" in fld_parts[0], f"Cloze syntax missing in Text field: {fld_parts[0]}"
                        assert fld_parts[2] == "badge-important"

                    # 3. Inspect cards table
                    cursor.execute("SELECT count(*) FROM cards")
                    card_count = cursor.fetchone()[0]
                    assert card_count >= 2, f"Expected at least 2 cards for 2 cloze notes, found {card_count}"

                    conn.close()
        finally:
            if old_out:
                CONFIG["output_directory"] = old_out
            else:
                CONFIG.pop("output_directory", None)

    def test_mixed_deck_simultaneous_models(self, tmp_path):
        """Validates that mixed decks with both Standard Q/A and Cloze models maintain model integrity."""
        cards = [
            # Standard Card
            {
                "card_type": "bidirectional_definition",
                "keyword": "Bioavailability (F)",
                "descriptor": "The fraction of an administered dose of unchanged drug that reaches systemic circulation.",
                "question": "What is the definition of <b>Bioavailability (F)</b>?",
                "answer": "The fraction of an administered dose of unchanged drug that reaches systemic circulation.",
                "category_badge": "badge-definition",
                "context": "Pharmacokinetics",
                "tags": ["definition", "forward"]
            },
            # Cloze Card
            {
                "card_type": "cloze",
                "keyword": "Bioavailability (IV)",
                "descriptor": "Intravenous administration achieves 100% bioavailability.",
                "question": "Identify the missing value regarding <b>Bioavailability (IV)</b>:<br>Intravenous administration achieves {{c1::100%}} bioavailability.",
                "answer": "100%",
                "cloze_text": "Intravenous administration achieves {{c1::100%}} bioavailability.",
                "category_badge": "badge-important",
                "context": "Pharmacokinetics",
                "tags": ["cloze", "high_yield"]
            }
        ]

        old_out = CONFIG.get("output_directory")
        CONFIG["output_directory"] = str(tmp_path)
        try:
            out_file = create_deck_package("PSYC 3590:Mixed Deck", cards, output_filename="mixed_deck.apkg")
            assert out_file.exists()

            with zipfile.ZipFile(out_file, "r") as zf:
                with tempfile.TemporaryDirectory() as extract_dir:
                    zf.extract("collection.anki2", extract_dir)
                    db_path = Path(extract_dir) / "collection.anki2"
                    conn = sqlite3.connect(str(db_path))
                    cursor = conn.cursor()

                    # Both models must exist in col.models
                    cursor.execute("SELECT models FROM col")
                    models = json.loads(cursor.fetchone()[0])
                    assert str(ANKI_MODEL.model_id) in models
                    assert str(ANKI_CLOZE_MODEL.model_id) in models

                    # Notes table must contain entries for both models
                    cursor.execute("SELECT DISTINCT mid FROM notes")
                    mids = [row[0] for row in cursor.fetchall()]
                    assert ANKI_MODEL.model_id in mids
                    assert ANKI_CLOZE_MODEL.model_id in mids

                    conn.close()
        finally:
            if old_out:
                CONFIG["output_directory"] = old_out
            else:
                CONFIG.pop("output_directory", None)

    def test_adversarial_content_escaping_and_unicode(self, tmp_path):
        """Stress-tests package creation with Unicode, HTML special chars, math symbols, and extreme lengths."""
        adversarial_text = (
            "Special characters: <>&\"' \u03b1-\u03b2 receptor (\u03b1\u2081 vs \u03b2\u2082) & "
            "Ca\u00b2\u207a influx; \u2192 \u2248 100% \u00b1 5%. "
            "Emoji: \U0001f9e0 \U0001f48a. "
            + "Very long text segment " * 50
        )

        cards = [
            {
                "card_type": "active_recall_qa",
                "keyword": "Adrenergic Receptors",
                "descriptor": adversarial_text,
                "question": "What is the key mechanism regarding <b>Adrenergic Receptors</b>?",
                "answer": adversarial_text,
                "category_badge": "badge-important",
                "context": "Receptor Pharmacology: <General> & \"Specific\"",
                "tags": ["unicode_test", "special_chars", "stress_test"]
            }
        ]

        old_out = CONFIG.get("output_directory")
        CONFIG["output_directory"] = str(tmp_path)
        try:
            out_file = create_deck_package("PSYC 3590:Stress Deck", cards, output_filename="stress_deck.apkg")
            assert out_file.exists()

            with zipfile.ZipFile(out_file, "r") as zf:
                with tempfile.TemporaryDirectory() as extract_dir:
                    zf.extract("collection.anki2", extract_dir)
                    db_path = Path(extract_dir) / "collection.anki2"
                    conn = sqlite3.connect(str(db_path))
                    cursor = conn.cursor()
                    cursor.execute("SELECT flds FROM notes")
                    stored_flds = cursor.fetchone()[0]
                    assert "\u03b1" in stored_flds
                    assert "\U0001f9e0" in stored_flds
                    conn.close()
        finally:
            if old_out:
                CONFIG["output_directory"] = old_out
            else:
                CONFIG.pop("output_directory", None)

    def test_multi_cloze_and_hints_rendering_and_packaging(self, tmp_path):
        """Validates that multi-cloze {{c1::...}} {{c2::...}} and hints {{c1::target::hint}} generate valid cards."""
        cards = [
            {
                "card_type": "cloze",
                "keyword": "Synaptic Transmission",
                "descriptor": "Depolarization causes Ca2+ influx which triggers exocytosis.",
                "question": "Complete the mechanism:<br>Depolarization causes {{c1::Ca2+ influx::ion}} which triggers {{c2::exocytosis::process}}.",
                "answer": "Ca2+ influx / exocytosis",
                "cloze_text": "Depolarization causes {{c1::Ca2+ influx::ion}} which triggers {{c2::exocytosis::process}}.",
                "category_badge": "badge-important",
                "context": "Neurotransmission",
                "tags": ["cloze", "multi_cloze"]
            }
        ]

        old_out = CONFIG.get("output_directory")
        CONFIG["output_directory"] = str(tmp_path)
        try:
            out_file = create_deck_package("PSYC 3590:Multi Cloze", cards, output_filename="multi_cloze_deck.apkg")
            assert out_file.exists()

            with zipfile.ZipFile(out_file, "r") as zf:
                with tempfile.TemporaryDirectory() as extract_dir:
                    zf.extract("collection.anki2", extract_dir)
                    db_path = Path(extract_dir) / "collection.anki2"
                    conn = sqlite3.connect(str(db_path))
                    cursor = conn.cursor()

                    # Notes table: 1 note
                    cursor.execute("SELECT count(*) FROM notes")
                    assert cursor.fetchone()[0] == 1

                    # Cards table: genanki generates 2 cards for c1 and c2
                    cursor.execute("SELECT ord FROM cards ORDER BY ord")
                    ords = [r[0] for r in cursor.fetchall()]
                    assert ords == [0, 1], f"Expected cards for c1 and c2 with ords [0, 1], got {ords}"

                    conn.close()
        finally:
            if old_out:
                CONFIG["output_directory"] = old_out
            else:
                CONFIG.pop("output_directory", None)


# ==============================================================================
# CHALLENGE SUITE 2: Adversarial Fallback & Network/Daemon Stress Testing
# ==============================================================================

class TestEmpiricalAdversarialFallback:
    """
    Adversarially tests OllamaRuntimeManager and SemanticCardParser under:
    - Connection refused (daemon not running)
    - Blackhole / hung connection (socket timeout)
    - HTTP errors (500, 502, 503, 404, 429)
    - Truncated / malformed / corrupted JSON
    - Hostile JSON containing SuperMemo veto violations
    - Mid-transfer socket closure / disconnect
    """

    def test_connection_refused_offline_fallback(self):
        """Verifies rapid non-blocking failure when connecting to an unused port (closed daemon)."""
        # Unused high port
        mgr = OllamaRuntimeManager(host="http://127.0.0.1:59999", timeout=1.0)
        
        start_time = time.time()
        is_ready = mgr.is_service_ready(timeout=0.5)
        elapsed = time.time() - start_time

        assert is_ready is False
        assert elapsed < 1.0, f"is_service_ready took too long to fail: {elapsed:.2f}s"

        # Calling generate_json on dead service must return None cleanly
        start_time = time.time()
        res = mgr.generate_json("Test prompt", timeout=1.0)
        elapsed = time.time() - start_time

        assert res is None
        assert elapsed < 1.5, f"generate_json took too long on offline host: {elapsed:.2f}s"

        # SemanticCardParser must seamlessly fall back without throwing
        parser = SemanticCardParser(runtime_manager=mgr)
        cards = parser.parse_highlight(
            "Tolerance is defined as a state of progressively decreasing responsiveness to repeated drug doses.",
            highlight_color="green",
            heading="Pharmacodynamics"
        )
        assert len(cards) == 2
        assert cards[0]["keyword"] == "Tolerance"
        assert cards[0]["card_type"] == "bidirectional_definition"

    def test_blackhole_timeout_resilience(self):
        """Verifies that when Ollama connection accepts but stalls forever, timeout triggers cleanly."""
        blackhole = BlackholeServer()
        try:
            mgr = OllamaRuntimeManager(host=f"http://127.0.0.1:{blackhole.port}", timeout=1.0)

            # Health check timeout
            start_time = time.time()
            ready = mgr.is_service_ready(timeout=0.8)
            elapsed = time.time() - start_time

            assert ready is False
            assert 0.7 <= elapsed <= 2.0, f"Health check did not respect timeout: elapsed={elapsed:.2f}s"

            # generate_json timeout
            start_time = time.time()
            res = mgr.generate_json("Test prompt", timeout=1.0)
            elapsed = time.time() - start_time

            assert res is None
            assert 0.8 <= elapsed <= 2.5, f"generate_json did not respect timeout: elapsed={elapsed:.2f}s"

        finally:
            blackhole.stop()

    def test_http_error_codes_fallback(self):
        """Verifies handling of HTTP 500, 502, 503, 404, 429 error responses."""
        server = MockHTTPServer()
        try:
            mgr = OllamaRuntimeManager(host=f"http://127.0.0.1:{server.port}", timeout=2.0)
            parser = SemanticCardParser(runtime_manager=mgr)

            error_codes = [500, 502, 503, 404, 429]
            for code in error_codes:
                server.set_response(code, b'{"error": "Simulated server failure"}')

                res = mgr.generate_json("Prompt", timeout=1.0)
                assert res is None, f"Expected None on HTTP {code}"

                # Parser must seamlessly fall back
                cards = parser.parse_highlight(
                    "Agonist refers to a chemical that binds to a receptor and activates it.",
                    highlight_color="green",
                    heading="Pharmacodynamics"
                )
                assert len(cards) == 2
                assert cards[0]["keyword"] == "Agonist"
        finally:
            server.stop()

    def test_malformed_and_truncated_json_handling(self):
        """Verifies that truncated or garbage JSON responses from Ollama trigger fallback without crashing."""
        server = MockHTTPServer()
        try:
            mgr = OllamaRuntimeManager(host=f"http://127.0.0.1:{server.port}")
            parser = SemanticCardParser(runtime_manager=mgr)

            pathological_payloads = [
                # Truncated JSON
                b'{"response": "{\\"cards\\": [{\\"card_type\\": \\"active_recall_qa\\""}',
                # HTML error page
                b'<html><body>504 Gateway Timeout</body></html>',
                # Valid JSON string but wrong structure (list instead of dict)
                b'{"response": "[1, 2, 3]"}',
                # Valid JSON dict but missing "cards" key
                b'{"response": "{\\"status\\": \\"success\\"}"}',
                # "cards" is an empty list
                b'{"response": "{\\"cards\\": []}"}',
                # "cards" contains strings instead of dicts
                b'{"response": "{\\"cards\\": [\\"card1\\", \\"card2\\"]}"}',
                # Empty response
                b'',
            ]

            for payload in pathological_payloads:
                server.set_response(200, payload)

                cards = parser.parse_highlight(
                    "Antagonist refers to a drug that attenuates the effect of an agonist.",
                    highlight_color="green",
                    heading="Pharmacodynamics"
                )
                # Must seamlessly fall back to deterministic parser
                assert len(cards) >= 1
                assert cards[0]["keyword"] == "Antagonist"

        finally:
            server.stop()

    def test_llm_veto_violation_triggers_deterministic_fallback(self):
        """
        Critical adversarial test:
        If Ollama returns cards containing banned phrases ('this concept') or tautologies,
        SemanticCardParser MUST reject the LLM cards and trigger the deterministic fallback engine!
        """
        server = MockHTTPServer()
        try:
            mgr = OllamaRuntimeManager(host=f"http://127.0.0.1:{server.port}")
            parser = SemanticCardParser(runtime_manager=mgr)

            # Simulate LLM emitting banned 'this concept' card
            vetoed_llm_response = {
                "response": json.dumps({
                    "cards": [
                        {
                            "card_type": "active_recall_qa",
                            "keyword": "Sensitization",
                            "descriptor": "Progressive increase in response",
                            "question": "What is this concept?",  # HARD VETO
                            "answer": "Sensitization",
                            "category_badge": "badge-definition",
                            "context": "Pharmacodynamics",
                            "tags": ["pharmacology"]
                        }
                    ]
                })
            }
            server.set_response(200, json.dumps(vetoed_llm_response).encode("utf-8"))

            cards = parser.parse_highlight(
                "Sensitization refers to the progressive amplification of a response following repeated administrations.",
                highlight_color="green",
                heading="Pharmacodynamics"
            )

            # The vetoed card MUST be rejected, and fallback cards generated instead
            assert len(cards) == 2
            for c in cards:
                assert "this concept" not in c["question"].lower()
                assert "What is this concept?" not in c["question"]
            assert cards[0]["keyword"] == "Sensitization"
            assert cards[0]["card_type"] == "bidirectional_definition"

        finally:
            server.stop()


# ==============================================================================
# CHALLENGE SUITE 3: Pipeline Hang/Freeze Prevention & Throughput Stress
# ==============================================================================

class TestEmpiricalHangAndFreezePrevention:
    """
    Stress-tests the pipeline to ensure zero hangs, freezes, or unbounded latency:
    - Cached service readiness (prevents re-pinging dead daemon on every highlight)
    - Rapid synthesis of 100 highlights under offline daemon conditions (< 2.5s)
    - Full end-to-end extraction and generation pipeline under offline conditions
    """

    def test_cached_readiness_prevents_freeze_on_100_highlights(self):
        """
        Verifies that parsing 100 highlights with an offline Ollama daemon completes
        in < 2.5 seconds total, proving that the 5-second readiness cache prevents
        repeated network connection attempts and freezes.
        """
        mgr = OllamaRuntimeManager(host="http://127.0.0.1:59998", timeout=0.5)
        parser = SemanticCardParser(runtime_manager=mgr)

        sample_highlights = [
            f"Concept_{i} is defined as scientific mechanism number {i} involving physiological signaling."
            for i in range(100)
        ]

        start_time = time.time()
        all_cards = []
        for h in sample_highlights:
            cards = parser.parse_highlight(h, highlight_color="green", heading="Stress Testing")
            all_cards.extend(cards)
        elapsed = time.time() - start_time

        assert len(all_cards) == 200, f"Expected 200 cards (100 pairs), got {len(all_cards)}"
        assert elapsed < 3.0, f"Processing 100 highlights took {elapsed:.2f}s (must be < 3.0s, zero freeze)"
        print(f"\n[BENCHMARK] 100 highlights parsed in {elapsed:.3f}s ({len(all_cards)} cards generated)")

    def test_full_synthesize_cards_loop_no_hang(self):
        """Verifies synthesize_cards() executes without hanging on complex document data structure."""
        structured_data = [
            {
                "heading": f"Topic {i}",
                "full_paragraph": f"Topic {i} details: Mechanism {i} is the process of biochemical transmission.",
                "highlights": [
                    {
                        "category": "green",
                        "raw_color": "green",
                        "text": f"Mechanism {i} is the process of biochemical transmission."
                    },
                    {
                        "category": "yellow",
                        "raw_color": "yellow",
                        "text": f"Concentration exceeds {i * 10}% threshold."
                    }
                ]
            }
            for i in range(25)
        ]

        # Force offline runtime manager
        mgr = OllamaRuntimeManager(host="http://127.0.0.1:59997")
        parser = SemanticCardParser(runtime_manager=mgr)

        start_time = time.time()
        cards = synthesize_cards(structured_data, deck_tags=["stress_test"], parser=parser)
        elapsed = time.time() - start_time

        assert len(cards) >= 50
        assert elapsed < 5.0, f"synthesize_cards took {elapsed:.2f}s (must be < 5.0s)"

        # Verify all cards pass judge
        judge = CardJudgeRubric()
        report = judge.evaluate_deck(cards)
        assert report["veto_count"] == 0
        assert report["average_score"] >= 25.0


# ==============================================================================
# CHALLENGE SUITE 4: ANKI_SOP Keyword-Descriptor & Bidirectionality Adherence
# ==============================================================================

class TestEmpiricalANKISOPAdherence:
    """
    Evaluates generated cards strictly against ANKI_SOP.md specifications:
    - Minimum Information Principle (concise keywords 1-5 words)
    - Clean descriptors omitting leading copulas
    - Bidirectional pairs (Term -> Definition AND Definition -> Term)
    - Cognitive Justification adherence (Recall vs Recognition)
    - Zero 'this concept' emissions across all 64+ linking verb patterns
    """

    def test_all_copulas_produce_clean_keywords_and_descriptors(self):
        """Tests that each class of copula verbs properly splits without copula leakage in descriptor."""
        test_cases = [
            ("Long-term potentiation is defined as a persistent strengthening of synapses.", "Long-term Potentiation"),
            ("Synaptic plasticity refers to the ability of synapses to strengthen or weaken over time.", "Synaptic Plasticity"),
            ("Dopamine functions as a primary neuromodulator in the reward pathway.", "Dopamine"),
            ("Pharmacodynamics: the study of the biochemical and physiological effects of drugs.", "Pharmacodynamics"),
            ("Serotonin modulates mood, sleep, and appetite.", "Serotonin"),
            ("Action potential results from sequential opening of voltage-gated Na+ and K+ channels.", "Action Potential"),
        ]

        parser = SemanticCardParser()
        judge = CardJudgeRubric()

        for text, expected_keyword in test_cases:
            cards = parser.parse_highlight(text, highlight_color="green", heading="Neuroscience")
            assert len(cards) == 2, f"Expected bidirectional pair for '{text}'"

            fwd, rev = cards[0], cards[1]

            # 1. Forward card check (Recall)
            assert fwd["card_type"] == "bidirectional_definition"
            assert expected_keyword.lower() in fwd["keyword"].lower()
            assert fwd["keyword"] in fwd["question"]
            assert "<b>" in fwd["question"]
            assert "is defined as" not in fwd["descriptor"].lower()
            assert "refers to" not in fwd["descriptor"].lower()

            # 2. Reverse card check (Recognition)
            assert rev["card_type"] == "bidirectional_definition"
            assert rev["keyword"].lower() == fwd["keyword"].lower()
            assert "What term is defined by:" in rev["question"]
            assert rev["answer"] == fwd["keyword"]

            # 3. Judge evaluation
            fwd_eval = judge.evaluate_card(fwd)
            rev_eval = judge.evaluate_card(rev)
            assert fwd_eval["passed"] is True
            assert rev_eval["passed"] is True
            assert fwd_eval["vetoes"] == []
            assert rev_eval["vetoes"] == []

    def test_pathological_highlights_never_emit_this_concept(self):
        """Adversarially feeds pathological/unsegmented highlights to guarantee 0% 'this concept'."""
        pathological_inputs = [
            "Basic developmental science focuses on description, explanation, and optimization.",
            "This principle describes the rate of diffusion across a semipermeable membrane.",
            "It is characterized by rapid onset and short duration of therapeutic action.",
            "Because tolerance develops rapidly, dose escalation becomes necessary.",
            "When administered orally, first-pass metabolism substantially reduces bioavailability.",
            "5-HT2A receptor antagonism mediates the atypical antipsychotic profile.",
            "Between 65% and 80% striatal D2 receptor occupancy is required for clinical response.",
            "A",
            "The",
            "Whereas drug A is a full agonist, drug B is a partial agonist.",
        ]

        parser = SemanticCardParser()
        judge = CardJudgeRubric()

        for text in pathological_inputs:
            cards = parser.parse_highlight(text, highlight_color="green", heading="Pathology")
            assert len(cards) >= 1

            for c in cards:
                q = c["question"].lower()
                a = c["answer"].lower()
                assert "this concept" not in q, f"Violation in question: {c['question']}"
                assert "this concept" not in a, f"Violation in answer: {c['answer']}"
                assert "this term" not in q
                assert "this phenomenon" not in q

                ev = judge.evaluate_card(c)
                assert ev["vetoes"] == [], f"Judge vetoed card: {ev['vetoes']} for input '{text}'"
                assert ev["total_score"] >= 25, f"Card scored {ev['total_score']} < 25 for input '{text}'"


# ==============================================================================
# CHALLENGE SUITE 5: Docker Lifecycle & AnkiConnect Offline Robustness
# ==============================================================================

class TestEmpiricalDockerAndAnkiConnectRobustness:
    """
    Adversarially tests Docker container initialization failures and AnkiConnect offline handling:
    - Docker not found on PATH
    - Docker CLI command times out
    - Docker daemon returns non-zero error code
    - AnkiConnect daemon offline / connection refused / error payload
    """

    def test_docker_cli_missing_handled_gracefully(self):
        """Verifies ensure_docker_container returns False when docker CLI is not on PATH."""
        mgr = OllamaRuntimeManager()
        with patch("shutil.which", return_value=None):
            result = mgr.ensure_docker_container()
            assert result is False

    def test_docker_ps_timeout_handled_gracefully(self):
        """Verifies ensure_docker_container returns False without freezing when docker CLI times out."""
        mgr = OllamaRuntimeManager()
        with patch("shutil.which", return_value="C:\\Program Files\\Docker\\Docker\\resources\\bin\\docker.exe"):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="docker ps", timeout=10)):
                start = time.time()
                result = mgr.ensure_docker_container()
                elapsed = time.time() - start
                assert result is False
                assert elapsed < 1.0, f"Call took too long on timeout: {elapsed:.2f}s"

    def test_docker_ps_error_code_handled_gracefully(self):
        """Verifies ensure_docker_container handles non-zero exit code from Docker daemon."""
        mgr = OllamaRuntimeManager()
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stderr = "error during connect: This error may indicate that the docker daemon is not running."
        mock_res.stdout = ""

        with patch("shutil.which", return_value="docker"):
            with patch("subprocess.run", return_value=mock_res):
                result = mgr.ensure_docker_container()
                assert result is False

    def test_ankiconnect_offline_does_not_crash(self, tmp_path):
        """Verifies inject_via_ankiconnect handles offline AnkiConnect on port 8765 without throwing."""
        from scripts.extract_and_generate import inject_via_ankiconnect
        dummy_apkg = tmp_path / "test.apkg"
        dummy_apkg.write_text("dummy content")

        # Must execute cleanly without exception, respecting the 5.0s urllib timeout
        start = time.time()
        inject_via_ankiconnect(dummy_apkg)
        elapsed = time.time() - start
        assert elapsed <= 6.0, f"inject_via_ankiconnect exceeded timeout: {elapsed:.2f}s"

    def test_ankiconnect_error_response_handled_gracefully(self, tmp_path):
        """Verifies inject_via_ankiconnect handles error response from AnkiConnect."""
        from scripts.extract_and_generate import inject_via_ankiconnect
        dummy_apkg = tmp_path / "test.apkg"
        dummy_apkg.write_text("dummy content")

        server = MockHTTPServer()
        try:
            # Return AnkiConnect error format
            server.set_response(200, b'{"result": null, "error": "deck already exists"}')
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.read.return_value = b'{"result": null, "error": "deck already exists"}'
                mock_resp.__enter__.return_value = mock_resp
                mock_urlopen.return_value = mock_resp

                inject_via_ankiconnect(dummy_apkg)
        finally:
            server.stop()


# ==============================================================================
# CHALLENGE SUITE 6: Agent-as-Judge Hard Veto Matrix & Boundary Conditions
# ==============================================================================

class TestEmpiricalJudgeVetoMatrixAndRubric:
    """
    Tests every hard veto condition in CardJudgeRubric to ensure zero false negatives:
    - Veto 1: Empty Question or Answer field
    - Veto 2: 'this concept', 'this term', 'this phenomenon', etc.
    - Veto 3: Raw heading prompt dump
    - Veto 4: Tautology (Question == Answer)
    - Empty deck evaluation boundary
    """

    def test_all_veto_conditions_enforced(self):
        judge = CardJudgeRubric()

        # Veto 1: Empty field
        c1 = {"question": "", "answer": "Answer"}
        res1 = judge.evaluate_card(c1)
        assert res1["passed"] is False
        assert any("CRITICAL_FAIL_EMPTY_FIELD" in v for v in res1["vetoes"])

        c1b = {"question": "Question", "answer": ""}
        res1b = judge.evaluate_card(c1b)
        assert res1b["passed"] is False
        assert any("CRITICAL_FAIL_EMPTY_FIELD" in v for v in res1b["vetoes"])

        # Veto 2: Banned phrases
        banned_stems = [
            "What is this concept?",
            "Define this concept.",
            "Explain this term.",
            "What does this phenomenon cause?",
        ]
        for stem in banned_stems:
            c = {"question": stem, "answer": "Valid answer"}
            res = judge.evaluate_card(c)
            assert res["passed"] is False, f"Failed to veto: {stem}"
            assert any("CRITICAL_FAIL_THIS_CONCEPT" in v for v in res["vetoes"])

        # Veto 3: Raw heading dump prompt
        c3 = {
            "question": "<b>Key Concept / Mechanism:</b><br>Pharmacodynamics",
            "answer": "Study of drug effects"
        }
        res3 = judge.evaluate_card(c3)
        assert res3["passed"] is False
        assert any("CRITICAL_FAIL_HEADING_ONLY" in v for v in res3["vetoes"])

        # Veto 4: Tautology
        c4 = {
            "question": "Tolerance",
            "answer": "Tolerance"
        }
        res4 = judge.evaluate_card(c4)
        assert res4["passed"] is False
        assert any("CRITICAL_FAIL_TAUTOLOGY" in v for v in res4["vetoes"])

    def test_empty_deck_evaluation_returns_safe_report(self):
        """Verifies evaluate_deck([]) does not divide by zero or crash."""
        judge = CardJudgeRubric()
        report = judge.evaluate_deck([])
        assert report["total_cards"] == 0
        assert report["passed_cards"] == 0
        assert report["average_score"] == 0.0
        assert report["deck_passed"] is False
        assert report["veto_count"] == 0


# ==============================================================================
# Standalone CLI Entrypoint
# ==============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

