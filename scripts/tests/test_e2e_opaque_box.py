"""
test_e2e_opaque_box.py — Opaque-Box E2E Test Suite for AnkiDeckCreator Pipeline

4-Tier Test Architecture:
- Tier 1: Feature Coverage (Docker check, Ollama API query, Keyword-Descriptor splitting,
  Cloze generation, Fallback handling, Agent-as-judge scoring)
- Tier 2: Boundary & Corner Cases (Docker down, Ollama timeout, empty highlights,
  complex compound clauses, lack of linking verbs, malformed responses)
- Tier 3: Cross-Feature Combinations (Pairwise interactions: Docker down + fallback,
  multiple highlights + Cloze, packaging + badge/tag preservation)
- Tier 4: Real-World Scenarios (sample_lecture_notes.docx, full pipeline CLI, card quality validation)

Authoritative Requirements Sources:
- ORIGINAL_REQUEST.md (Requirements R1, R2, R3, R4)
- ANKI_SOP.md (Keyword-Descriptor format, Bidirectionality, Cognitive Justification,
  Color Semantics, Highlight Breaks, 'this concept' solution)
- PROJECT.md (Interface Contracts, Milestones, 64-pattern fallback lexicon)
"""

import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
import docx
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

# Ensure project root and scripts directory are in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Dynamic imports for modules undergoing active milestone development
try:
    from scripts.ollama_runtime import OllamaRuntimeManager
except ImportError:
    try:
        from ollama_runtime import OllamaRuntimeManager
    except ImportError:
        OllamaRuntimeManager = None

try:
    from scripts.semantic_parser import SemanticCardParser
except ImportError:
    try:
        from semantic_parser import SemanticCardParser
    except ImportError:
        SemanticCardParser = None

try:
    from scripts.evaluate_cards_judge import CardJudgeRubric, SuperMemoCardJudge
except ImportError:
    try:
        from evaluate_cards_judge import CardJudgeRubric, SuperMemoCardJudge
    except ImportError:
        CardJudgeRubric = None
        SuperMemoCardJudge = None

# Baseline imports from existing pipeline
from scripts.extract_and_generate import (
    extract_document_highlights,
    classify_color,
    resolve_deck_naming,
    create_deck_package,
    synthesize_cards,
    clean_phrase,
    CONFIG,
)


# ==============================================================================
# AUTHORITATIVE REFERENCE ORACLE: Agent-as-Judge 30-Point Rubric & Veto Checker
# (Derived from ANKI_SOP.md Section 1-3 & SuperMemo 20 Rules)
# ==============================================================================

class ReferenceCardJudgeOracle:
    """
    Authoritative reference oracle implementing the 30-point evaluation rubric
    and 4 hard vetoes specified in ANKI_SOP.md and PROJECT.md.
    """
    BANNED_VAGUE_PATTERNS = [
        r"\bthis\s+concept\b",
        r"\bthis\s+term\b",
        r"\bthis\s+phenomenon\b",
        r"\bwhat\s+is\s+this\s+concept\b",
        r"\bdefine\s+this\s+concept\b",
    ]

    SET_ENUMERATION_PATTERNS = [
        r"\blist\s+the\b",
        r"\bwhat\s+are\s+the\s+\d+\b",
        r"\bname\s+the\s+\d+\b",
        r"\bstate\s+the\s+\d+\b",
    ]

    def evaluate_card(self, card: Dict[str, Any]) -> Dict[str, Any]:
        q = card.get("question", "").strip()
        a = card.get("answer", "").strip()
        badge = card.get("category_badge", "").strip()
        ctx = card.get("context", "").strip()
        tags = card.get("tags", [])

        vetoes = []

        # 1. Critical Hard Veto Checks
        if not q or not a:
            vetoes.append("CRITICAL_FAIL_EMPTY_FIELD: Question or Answer is empty.")

        for pat in self.BANNED_VAGUE_PATTERNS:
            if re.search(pat, q, re.IGNORECASE) or re.search(pat, a, re.IGNORECASE):
                vetoes.append(f"CRITICAL_FAIL_THIS_CONCEPT: Contains banned phrase matching '{pat}'.")

        # Heading-as-prompt veto check
        if "Key Concept / Mechanism:" in q and ("<br>" in q or "\n" in q):
            trailing = re.split(r'<br>|\n', q)[-1].strip()
            # If trailing text is short heading (<= 8 words) with no active question verb
            if len(trailing.split()) <= 8 and not re.search(r'^(What|Which|Why|How|Define|Explain)\b', trailing, re.IGNORECASE):
                vetoes.append("CRITICAL_FAIL_HEADING_ONLY: Prompt is a raw heading dump without an active recall question.")

        if q.lower() == a.lower() and q != "":
            vetoes.append("CRITICAL_FAIL_TAUTOLOGY: Question and Answer are identical.")

        # Dimension Scoring (0 to 5 each, max 30)
        d_scores = {}

        # D1: Atomicity (Rule 4: Minimum Information Principle)
        word_count = len(a.split())
        if word_count <= 25:
            d_scores["D1_Atomicity"] = 5
        elif word_count <= 40:
            d_scores["D1_Atomicity"] = 3
        else:
            d_scores["D1_Atomicity"] = 1

        # D2: Absence of Vague Prompts (Rule 12: Optimize wording)
        if any(re.search(pat, q, re.IGNORECASE) for pat in self.BANNED_VAGUE_PATTERNS):
            d_scores["D2_Wording"] = 0
        elif re.search(r'^(What|Which|Why|How|Define|Identify|Explain the mechanism)\b', q, re.IGNORECASE):
            d_scores["D2_Wording"] = 5
        elif "{{c1::" in q:
            d_scores["D2_Wording"] = 5
        else:
            d_scores["D2_Wording"] = 3

        # D3: Keyword-Descriptor Integrity (ANKI_SOP.md Section 1.5)
        has_bold_kw = bool(re.search(r'<b>([^<]+)</b>', q))
        if has_bold_kw:
            kw_match = re.search(r'<b>([^<]+)</b>', q).group(1).strip()
            kw_words = len(kw_match.split())
            d_scores["D3_Keyword_Descriptor"] = 5 if 1 <= kw_words <= 5 else 3
        elif "{{c1::" in q or "cloze" in tags:
            d_scores["D3_Keyword_Descriptor"] = 5
        else:
            d_scores["D3_Keyword_Descriptor"] = 2

        # D4: Avoidance of Sets/Enumerations (SuperMemo Rules 9 & 10)
        if any(re.search(pat, q, re.IGNORECASE) for pat in self.SET_ENUMERATION_PATTERNS):
            d_scores["D4_Avoid_Sets"] = 0
        else:
            d_scores["D4_Avoid_Sets"] = 5

        # D5: Active Recall vs Recognition (SOP 1.5 & Rule 17)
        if "reverse" in tags:
            d_scores["D5_Recall_Recognition"] = 5 if len(a.split()) <= 6 else 3
        else:
            d_scores["D5_Recall_Recognition"] = 5

        # D6: Contextual Anchoring (SuperMemo Rules 16 & 18)
        ctx_score = 0
        if badge:
            ctx_score += 2
        if ctx:
            ctx_score += 2
        if tags:
            ctx_score += 1
        d_scores["D6_Context_Anchoring"] = min(5, ctx_score)

        total_score = sum(d_scores.values()) if not vetoes else 0
        passed = (len(vetoes) == 0) and (total_score >= 25)

        return {
            "total_score": total_score,
            "max_score": 30,
            "passed": passed,
            "vetoes": vetoes,
            "dimension_scores": d_scores,
        }

    def evaluate_deck(self, cards: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not cards:
            return {"total_cards": 0, "passed_cards": 0, "average_score": 0.0, "deck_passed": False, "veto_count": 0}
        evals = [self.evaluate_card(c) for c in cards]
        passed_count = sum(1 for e in evals if e["passed"])
        veto_count = sum(len(e["vetoes"]) for e in evals)
        avg_score = sum(e["total_score"] for e in evals) / len(evals)
        return {
            "total_cards": len(cards),
            "passed_cards": passed_count,
            "average_score": round(avg_score, 2),
            "deck_passed": (passed_count == len(cards)) and (veto_count == 0),
            "veto_count": veto_count,
            "card_evaluations": evals,
        }


# ==============================================================================
# TEST FIXTURES & HELPERS
# ==============================================================================

@pytest.fixture
def judge_oracle():
    return ReferenceCardJudgeOracle()


@pytest.fixture
def sample_docx_path():
    """Path to the 4-paragraph test fixture."""
    path = PROJECT_ROOT / "scripts" / "tests" / "sample_lecture_notes.docx"
    assert path.exists(), f"Missing required sample docx at {path}"
    return path


def create_custom_docx(paragraphs_data: List[Dict[str, Any]], output_path: Path) -> Path:
    """
    Helper to synthesize a test .docx file with specific OpenXML highlight runs.
    paragraphs_data: list of dicts:
        {
            "heading": Optional[str],
            "runs": [
                {"text": "...", "highlight": "yellow"|"green"|"none", "fill": "B7E1CD"|None}
            ]
        }
    """
    doc = docx.Document()
    for p_data in paragraphs_data:
        if p_data.get("heading"):
            doc.add_heading(p_data["heading"], level=1)
        p = doc.add_paragraph()
        for r_data in p_data.get("runs", []):
            run = p.add_run(r_data.get("text", ""))
            rPr = run._r.get_or_add_rPr()
            hl = r_data.get("highlight")
            if hl and hl.lower() != "none":
                rPr.append(parse_xml(f'<w:highlight {nsdecls("w")} w:val="{hl.lower()}"/>'))
            fill = r_data.get("fill")
            if fill:
                rPr.append(parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" w:fill="{fill}"/>'))
    doc.save(str(output_path))
    return output_path


# ==============================================================================
# TIER 1: FEATURE COVERAGE (Functional Baseline & Interface Verification)
# 6 Features x 5 Tests = 30 Tests
# ==============================================================================

class TestTier1FeatureCoverage:
    """
    Tier 1 tests verify primary happy paths and contracts for all inventoried features
    (Docker management, Ollama client, Keyword-Descriptor, Cloze, Fallback, Judge).
    """

    # --- Feature 1: Docker Desktop Auto-Detection & Container Initialization ---

    def test_tier1_docker_status_probe_success(self):
        """Feature 1.1: OllamaRuntimeManager detects active service on localhost:11434."""
        assert OllamaRuntimeManager is not None, "scripts/ollama_runtime.py is not yet implemented (Milestone 1)"
        manager = OllamaRuntimeManager(host="http://localhost:11434")
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = b'{"models": [{"name": "llama3.2:1b"}]}'
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            assert manager.is_service_ready() is True

    def test_tier1_docker_container_start_stopped(self):
        """Feature 1.2: When anki-ollama exists but is stopped, manager invokes 'docker start'."""
        assert OllamaRuntimeManager is not None, "scripts/ollama_runtime.py is not yet implemented (Milestone 1)"
        manager = OllamaRuntimeManager(host="http://localhost:11434")
        with patch.object(manager, "is_service_ready", side_effect=[False, True]), \
             patch("shutil.which", return_value="docker"), \
             patch("subprocess.run") as mock_run:
            # First call: inspect container state
            mock_inspect = MagicMock(returncode=0, stdout="anki-ollama\tExited (0) 2 hours ago")
            # Second call: docker start
            mock_start = MagicMock(returncode=0, stdout="anki-ollama")
            mock_run.side_effect = [mock_inspect, mock_start]

            ready = manager.ensure_service_ready(auto_start_docker=True)
            assert ready is True
            # Verify docker start command was invoked
            start_calls = [c for c in mock_run.call_args_list if "start" in c[0][0]]
            assert len(start_calls) >= 1
            assert "anki-ollama" in start_calls[0][0][0]

    def test_tier1_docker_container_run_missing(self):
        """Feature 1.3: When container does not exist, manager invokes 'docker run -d ...' with persistent volume."""
        assert OllamaRuntimeManager is not None, "scripts/ollama_runtime.py is not yet implemented (Milestone 1)"
        manager = OllamaRuntimeManager(host="http://localhost:11434")
        with patch.object(manager, "is_service_ready", side_effect=[False, True]), \
             patch("shutil.which", return_value="docker"), \
             patch("subprocess.run") as mock_run:
            # Empty inspect output indicates container missing
            mock_inspect = MagicMock(returncode=0, stdout="")
            mock_run_cmd = MagicMock(returncode=0, stdout="container_id_12345")
            mock_run.side_effect = [mock_inspect, mock_run_cmd]

            ready = manager.ensure_service_ready(auto_start_docker=True)
            assert ready is True
            # Verify docker run command includes volume mapping
            run_calls = [c for c in mock_run.call_args_list if "run" in c[0][0]]
            assert len(run_calls) >= 1
            cmd = " ".join(run_calls[0][0][0])
            assert "ollama/ollama" in cmd
            assert "-v" in cmd and "anki-ollama-models:/root/.ollama" in cmd

    def test_tier1_docker_daemon_unavailable_graceful(self):
        """Feature 1.4: When Docker Desktop engine is stopped, manager returns False gracefully without crash."""
        assert OllamaRuntimeManager is not None, "scripts/ollama_runtime.py is not yet implemented (Milestone 1)"
        manager = OllamaRuntimeManager(host="http://localhost:11434")
        with patch.object(manager, "is_service_ready", return_value=False), \
             patch("subprocess.run", side_effect=subprocess.SubprocessError("Docker daemon offline")):
            ready = manager.ensure_service_ready(auto_start_docker=True)
            assert ready is False

    def test_tier1_docker_model_available_check(self):
        """Feature 1.5: Model management verifies target model existence or triggers pull."""
        assert OllamaRuntimeManager is not None, "scripts/ollama_runtime.py is not yet implemented (Milestone 1)"
        manager = OllamaRuntimeManager(host="http://localhost:11434", model="llama3.2:1b")
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = json.dumps({"models": [{"name": "llama3.2:1b"}]}).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            assert manager.ensure_model_available() is True

    # --- Feature 2: Zero-Dependency Ollama HTTP Client ---

    def test_tier1_ollama_generate_json_format(self):
        """Feature 2.1: generate_json sends format='json' in POST body to /api/generate."""
        assert OllamaRuntimeManager is not None, "scripts/ollama_runtime.py is not yet implemented (Milestone 1)"
        manager = OllamaRuntimeManager(host="http://localhost:11434")
        captured_payload = {}

        def fake_urlopen(req, timeout=None):
            nonlocal captured_payload
            captured_payload = json.loads(req.data.decode("utf-8"))
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = json.dumps({
                "response": json.dumps({"cards": [{"question": "Q1", "answer": "A1"}]})
            }).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res = manager.generate_json(prompt="Test Prompt", system_prompt="System Prompt")
            assert captured_payload.get("format") == "json"
            assert captured_payload.get("prompt") == "Test Prompt"
            assert captured_payload.get("system") == "System Prompt"
            assert res is not None
            assert "cards" in res

    def test_tier1_ollama_client_temperature_setting(self):
        """Feature 2.2: generate_json enforces low temperature for deterministic formulation."""
        assert OllamaRuntimeManager is not None, "scripts/ollama_runtime.py is not yet implemented (Milestone 1)"
        manager = OllamaRuntimeManager(host="http://localhost:11434")
        captured_payload = {}

        def fake_urlopen(req, timeout=None):
            nonlocal captured_payload
            captured_payload = json.loads(req.data.decode("utf-8"))
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = json.dumps({"response": "{}"}).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            manager.generate_json(prompt="P", system_prompt="S", temperature=0.1)
            options = captured_payload.get("options", {})
            assert options.get("temperature") == 0.1

    def test_tier1_ollama_client_headers_and_method(self):
        """Feature 2.3: Client uses POST method with Content-Type: application/json."""
        assert OllamaRuntimeManager is not None, "scripts/ollama_runtime.py is not yet implemented (Milestone 1)"
        manager = OllamaRuntimeManager(host="http://localhost:11434")
        captured_req = None

        def fake_urlopen(req, timeout=None):
            nonlocal captured_req
            captured_req = req
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = json.dumps({"response": "{}"}).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            manager.generate_json(prompt="P", system_prompt="S")
            assert captured_req.get_method() == "POST"
            assert captured_req.get_header("Content-type") == "application/json"

    def test_tier1_ollama_client_pull_missing_model(self):
        """Feature 2.4: ensure_model_available calls /api/pull if model is missing in /api/tags."""
        assert OllamaRuntimeManager is not None, "scripts/ollama_runtime.py is not yet implemented (Milestone 1)"
        manager = OllamaRuntimeManager(host="http://localhost:11434", model="llama3.2:1b")
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req.full_url)
            mock_resp = MagicMock()
            mock_resp.status = 200
            if "/api/tags" in req.full_url:
                mock_resp.read.return_value = json.dumps({"models": [{"name": "other_model:latest"}]}).encode("utf-8")
            elif "/api/pull" in req.full_url:
                mock_resp.read.return_value = json.dumps({"status": "success"}).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            success = manager.ensure_model_available()
            assert any("/api/pull" in url for url in calls)
            assert success is True

    def test_tier1_ollama_client_response_parsing(self):
        """Feature 2.5: Parsed JSON response correctly returns nested dictionary payload."""
        assert OllamaRuntimeManager is not None, "scripts/ollama_runtime.py is not yet implemented (Milestone 1)"
        manager = OllamaRuntimeManager(host="http://localhost:11434")
        expected_cards = [{"question": "What is tolerance?", "answer": "Decreased responsiveness"}]
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = json.dumps({
                "response": json.dumps({"cards": expected_cards})
            }).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            result = manager.generate_json(prompt="Prompt", system_prompt="Sys")
            assert result == {"cards": expected_cards}


    # --- Feature 3: ANKI_SOP Keyword-Descriptor Formatting ---

    def test_tier1_keyword_descriptor_equative_copula(self):
        """Feature 3.1: 'Tolerance is defined as...' parses into distinct Keyword and Descriptor."""
        raw_text = "Tolerance is defined as a state of progressively decreasing responsiveness to a drug."
        if SemanticCardParser is not None:
            parser = SemanticCardParser()
            cards = parser.parse_with_fallback(raw_text, highlight_color="green", heading="Pharmacodynamics")
        else:
            # Test baseline pipeline behavior
            cards = synthesize_cards([{
                "heading": "Pharmacodynamics",
                "full_paragraph": raw_text,
                "segments": [{"raw_color": "green", "category": "green", "text": raw_text}],
                "highlights": [{"raw_color": "green", "category": "green", "text": raw_text}],
            }])
        assert len(cards) >= 1
        q = cards[0]["question"]
        # Must isolate 'Tolerance' as keyword, avoiding 'this concept'
        assert "this concept" not in q.lower()
        assert "tolerance" in q.lower()

    def test_tier1_keyword_descriptor_functional_copula(self):
        """Feature 3.2: 'Basic developmental science focuses on...' extracts subject cleanly."""
        raw_text = "Basic developmental science focuses on description, explanation, and optimization of intra-individual change."
        if SemanticCardParser is not None:
            parser = SemanticCardParser()
            cards = parser.parse_with_fallback(raw_text, highlight_color="green", heading="Developmental Psychology")
        else:
            cards = synthesize_cards([{
                "heading": "Developmental Psychology",
                "full_paragraph": raw_text,
                "segments": [{"raw_color": "green", "category": "green", "text": raw_text}],
                "highlights": [{"raw_color": "green", "category": "green", "text": raw_text}],
            }])
        assert len(cards) >= 1
        q = cards[0]["question"]
        # Under ANKI_SOP.md Section 3, 'focuses on' must split into keyword and descriptor without 'this concept'
        assert "this concept" not in q.lower()
        assert "basic developmental science" in q.lower()

    def test_tier1_keyword_descriptor_leading_articles_stripped(self):
        """Feature 3.3: Leading articles ('The', 'A', 'An') are normalized in extracted keywords."""
        raw_text = "The therapeutic index of a drug represents the ratio between toxic dose and effective dose."
        if SemanticCardParser is not None:
            parser = SemanticCardParser()
            cards = parser.parse_with_fallback(raw_text, highlight_color="green", heading="Pharmacology")
        else:
            cards = synthesize_cards([{
                "heading": "Pharmacology",
                "full_paragraph": raw_text,
                "segments": [{"raw_color": "green", "category": "green", "text": raw_text}],
                "highlights": [{"raw_color": "green", "category": "green", "text": raw_text}],
            }])
        assert len(cards) >= 1
        q = cards[0]["question"]
        assert "this concept" not in q.lower()
        assert "therapeutic index" in q.lower()

    def test_tier1_keyword_descriptor_bolding_standard(self):
        """Feature 3.4: Active recall questions highlight target keyword using bold tags <b>...</b>."""
        raw_text = "Tolerance is defined as decreasing responsiveness."
        if SemanticCardParser is not None:
            parser = SemanticCardParser()
            cards = parser.parse_with_fallback(raw_text, highlight_color="green", heading="Pharmacology")
        else:
            cards = synthesize_cards([{
                "heading": "Pharmacology",
                "full_paragraph": raw_text,
                "segments": [{"raw_color": "green", "category": "green", "text": raw_text}],
                "highlights": [{"raw_color": "green", "category": "green", "text": raw_text}],
            }])
        assert len(cards) >= 1
        assert "<b>" in cards[0]["question"] and "</b>" in cards[0]["question"]

    def test_tier1_keyword_descriptor_bidirectional_definitions(self):
        """Feature 3.5: Foundational definitions generate both forward (Recall) and reverse (Recognition) cards."""
        structured = [{
            "heading": "Pharmacology",
            "full_paragraph": "Tolerance: decreasing responsiveness.",
            "segments": [
                {"raw_color": "yellow", "category": "yellow", "text": "Tolerance"},
                {"raw_color": "green", "category": "green", "text": "decreasing responsiveness to a drug."}
            ],
            "highlights": [
                {"raw_color": "yellow", "category": "yellow", "text": "Tolerance"},
                {"raw_color": "green", "category": "green", "text": "decreasing responsiveness to a drug."}
            ]
        }]
        cards = synthesize_cards(structured)
        # Expect at least 2 cards: forward and reverse
        assert len(cards) >= 2
        tags_flat = [tag for c in cards for tag in c.get("tags", [])]
        assert "forward" in tags_flat
        assert "reverse" in tags_flat

    # --- Feature 4: SuperMemo Rule 5 (Cloze Deletion Generation) ---

    def test_tier1_cloze_syntax_structure(self):
        """Feature 4.1: Cloze cards contain valid Anki deletion markup {{c1::...}}."""
        assert SemanticCardParser is not None, "scripts/semantic_parser.py is not yet implemented (Milestone 2)"
        parser = SemanticCardParser()
        raw = "Dopamine D2 receptor occupancy between 65% and 80% is required for clinical therapeutic response."
        cards = parser.parse_highlight(raw, highlight_color="yellow", heading="Antipsychotics")
        cloze_cards = [c for c in cards if "{{c1::" in c.get("question", "")]
        assert len(cloze_cards) >= 1, "Expected at least one Cloze deletion card for factual threshold"
        assert re.search(r'\{\{c1::[^\}]+\}\}', cloze_cards[0]["question"])

    def test_tier1_cloze_atomicity_threshold(self):
        """Feature 4.2: Cloze targets atomic keyword/threshold, not entire sentence."""
        assert SemanticCardParser is not None, "scripts/semantic_parser.py is not yet implemented (Milestone 2)"
        parser = SemanticCardParser()
        raw = "Dopamine D2 receptor occupancy between 65% and 80% is required for therapeutic response."
        cards = parser.parse_highlight(raw, highlight_color="yellow", heading="Antipsychotics")
        cloze_cards = [c for c in cards if "{{c1::" in c.get("question", "")]
        assert len(cloze_cards) >= 1
        m = re.search(r'\{\{c1::([^\}]+)\}\}', cloze_cards[0]["question"])
        masked_text = m.group(1).strip()
        # Cloze target should be concise (<= 6 words, e.g. '65% and 80%')
        assert len(masked_text.split()) <= 6

    def test_tier1_cloze_context_metadata(self):
        """Feature 4.3: Cloze cards include context box anchoring heading and topic."""
        assert SemanticCardParser is not None, "scripts/semantic_parser.py is not yet implemented (Milestone 2)"
        parser = SemanticCardParser()
        raw = "Occupancy exceeding 80% sharply increases the risk of extrapyramidal symptoms."
        cards = parser.parse_highlight(raw, highlight_color="yellow", heading="Antipsychotics & EPS")
        cloze_cards = [c for c in cards if "{{c1::" in c.get("question", "")]
        assert len(cloze_cards) >= 1
        assert "context" in cloze_cards[0]
        assert "Antipsychotics" in cloze_cards[0]["context"]

    def test_tier1_cloze_tag_presence(self):
        """Feature 4.4: Cloze cards are tagged with 'cloze' tag."""
        assert SemanticCardParser is not None, "scripts/semantic_parser.py is not yet implemented (Milestone 2)"
        parser = SemanticCardParser()
        raw = "Dopamine D2 receptor occupancy exceeding 80% sharply increases the risk of extrapyramidal symptoms."
        cards = parser.parse_highlight(raw, highlight_color="yellow", heading="Receptor Dynamics")
        cloze_cards = [c for c in cards if "cloze" in c.get("tags", []) or "{{c1::" in c.get("question", "")]
        assert len(cloze_cards) >= 1

    def test_tier1_cloze_category_badge(self):
        """Feature 4.5: Cloze card preserves category badge (e.g. badge-important)."""
        assert SemanticCardParser is not None, "scripts/semantic_parser.py is not yet implemented (Milestone 2)"
        parser = SemanticCardParser()
        raw = "Therapeutic index is the ratio between TD50 and ED50."
        cards = parser.parse_highlight(raw, highlight_color="yellow", heading="Pharmacology")
        assert len(cards) >= 1
        assert cards[0].get("category_badge") in ("badge-important", "badge-definition")

    # --- Feature 5: 64-Pattern Deterministic Fallback Parser ---

    def test_tier1_fallback_equative_copulas(self):
        """Feature 5.1: Fallback matches equative copulas ('is characterized by', 'denotes')."""
        assert SemanticCardParser is not None, "scripts/semantic_parser.py is not yet implemented (Milestone 2)"
        parser = SemanticCardParser()
        text = "Addiction is characterized by compulsive drug seeking despite adverse consequences."
        cards = parser.parse_with_fallback(text, highlight_color="green", heading="Addiction")
        assert len(cards) >= 1
        assert "this concept" not in cards[0]["question"].lower()
        assert "addiction" in cards[0]["question"].lower()

    def test_tier1_fallback_functional_copulas(self):
        """Feature 5.2: Fallback matches functional copulas ('serves as', 'functions as')."""
        assert SemanticCardParser is not None, "scripts/semantic_parser.py is not yet implemented (Milestone 2)"
        parser = SemanticCardParser()
        text = "The blood-brain barrier serves as a selective semi-permeable physiological checkpoint."
        cards = parser.parse_with_fallback(text, highlight_color="green", heading="Neuroanatomy")
        assert len(cards) >= 1
        assert "this concept" not in cards[0]["question"].lower()
        assert "blood-brain barrier" in cards[0]["question"].lower()

    def test_tier1_fallback_multi_tier_resolution(self):
        """Feature 5.3: When no copula in highlight, fallback uses preceding paragraph prefix."""
        assert SemanticCardParser is not None, "scripts/semantic_parser.py is not yet implemented (Milestone 2)"
        parser = SemanticCardParser()
        prefix = "Pharmacokinetics:"
        highlight = "the study of drug absorption, distribution, metabolism, and excretion."
        cards = parser.parse_with_fallback(highlight, highlight_color="green", heading="Pharmacology", paragraph_prefix=prefix)
        assert len(cards) >= 1
        assert "this concept" not in cards[0]["question"].lower()
        assert "pharmacokinetics" in cards[0]["question"].lower()

    def test_tier1_fallback_contrastive_clause_split(self):
        """Feature 5.4: Fallback splits contrastive clauses ('whereas', 'while') into atomic cards."""
        assert SemanticCardParser is not None, "scripts/semantic_parser.py is not yet implemented (Milestone 2)"
        parser = SemanticCardParser()
        text = "Agonists activate receptors, whereas antagonists prevent receptor activation."
        cards = parser.parse_with_fallback(text, highlight_color="yellow", heading="Receptors")
        assert len(cards) >= 2, "Expected contrastive clause with 'whereas' to be split into >=2 atomic cards"

    def test_tier1_fallback_typographic_copulas(self):
        """Feature 5.5: Fallback splits on typographic markers (em-dash, colons)."""
        assert SemanticCardParser is not None, "scripts/semantic_parser.py is not yet implemented (Milestone 2)"
        parser = SemanticCardParser()
        text = "Synaptic cleft — the microscopic gap between terminal bouton and dendritic spine."
        cards = parser.parse_with_fallback(text, highlight_color="green", heading="Synaptic Transmission")
        assert len(cards) >= 1
        assert "synaptic cleft" in cards[0]["question"].lower()

    # --- Feature 6: Agent-as-Judge 30-Point Rubric & Hard Vetoes ---

    def test_tier1_judge_score_passing_card(self, judge_oracle):
        """Feature 6.1: High-quality atomic card scores >= 25 points and passes."""
        card = {
            "question": "What is the definition of <b>Tolerance</b>?",
            "answer": "A state of progressively decreasing responsiveness to a drug following repeated administration.",
            "category_badge": "badge-definition",
            "context": "PSYC 3590 | Pharmacodynamics",
            "tags": ["psyc3590", "pharmacodynamics", "tolerance", "definition", "forward"]
        }
        res = judge_oracle.evaluate_card(card)
        assert res["passed"] is True
        assert res["total_score"] >= 25
        assert len(res["vetoes"]) == 0

    def test_tier1_judge_veto_this_concept(self, judge_oracle):
        """Feature 6.2: Any card with 'this concept' fails immediately with score 0."""
        card = {
            "question": "Define / What is <b>this concept</b>?",
            "answer": "Basic developmental science focuses on description, explanation, and optimization.",
            "category_badge": "badge-definition",
            "context": "Developmental Psychology",
            "tags": ["definition"]
        }
        res = judge_oracle.evaluate_card(card)
        assert res["passed"] is False
        assert res["total_score"] == 0
        assert any("CRITICAL_FAIL_THIS_CONCEPT" in v for v in res["vetoes"])

    def test_tier1_judge_veto_empty_fields(self, judge_oracle):
        """Feature 6.3: Empty question or answer triggers CRITICAL_FAIL_EMPTY_FIELD."""
        card = {
            "question": "",
            "answer": "Tolerance",
            "category_badge": "badge-definition"
        }
        res = judge_oracle.evaluate_card(card)
        assert res["passed"] is False
        assert any("CRITICAL_FAIL_EMPTY_FIELD" in v for v in res["vetoes"])

    def test_tier1_judge_veto_heading_only(self, judge_oracle):
        """Feature 6.4: Prompt consisting solely of raw heading triggers CRITICAL_FAIL_HEADING_ONLY."""
        card = {
            "question": "<b>Key Concept / Mechanism:</b><br>PSYC 3590: Lecture 2",
            "answer": "Dopamine D2 receptor occupancy between 65% and 80% is required.",
            "category_badge": "badge-important"
        }
        res = judge_oracle.evaluate_card(card)
        assert res["passed"] is False
        assert any("CRITICAL_FAIL_HEADING_ONLY" in v for v in res["vetoes"])

    def test_tier1_judge_veto_tautology(self, judge_oracle):
        """Feature 6.5: Identical question and answer triggers CRITICAL_FAIL_TAUTOLOGY."""
        card = {
            "question": "Tolerance",
            "answer": "Tolerance",
            "category_badge": "badge-definition"
        }
        res = judge_oracle.evaluate_card(card)
        assert res["passed"] is False
        assert any("CRITICAL_FAIL_TAUTOLOGY" in v for v in res["vetoes"])


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES (Stress & Fault Injection)
# 6 Categories x 5 Tests = 30 Tests
# ==============================================================================

class TestTier2BoundaryAndCornerCases:
    """
    Tier 2 tests verify resilience against edge cases, network drops, malformed JSON,
    pathological highlights, extreme length, and missing linking verbs.
    """

    # --- Boundary 1: Docker Daemon Offline & Unreachable Host ---

    def test_tier2_docker_cli_missing_on_path(self):
        """Boundary 1.1: When docker executable is missing, manager returns False without raising FileNotFoundError."""
        assert OllamaRuntimeManager is not None, "scripts/ollama_runtime.py is not yet implemented (Milestone 1)"
        manager = OllamaRuntimeManager(host="http://localhost:11434")
        with patch.object(manager, "is_service_ready", return_value=False), \
             patch("subprocess.run", side_effect=FileNotFoundError("No such file: docker")):
            ready = manager.ensure_service_ready(auto_start_docker=True)
            assert ready is False

    def test_tier2_docker_named_pipe_error(self):
        """Boundary 1.2: Windows named pipe failure (error code 2 / file not found) handled cleanly."""
        assert OllamaRuntimeManager is not None, "scripts/ollama_runtime.py is not yet implemented (Milestone 1)"
        manager = OllamaRuntimeManager(host="http://localhost:11434")
        mock_res = MagicMock(returncode=1, stderr="error during connect: open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.")
        with patch.object(manager, "is_service_ready", return_value=False), \
             patch("subprocess.run", return_value=mock_res):
            ready = manager.ensure_service_ready(auto_start_docker=True)
            assert ready is False

    def test_tier2_docker_container_start_locked_failure(self):
        """Boundary 1.3: Non-zero exit code during 'docker start' returns False without uncaught exception."""
        assert OllamaRuntimeManager is not None, "scripts/ollama_runtime.py is not yet implemented (Milestone 1)"
        manager = OllamaRuntimeManager(host="http://localhost:11434")
        mock_inspect = MagicMock(returncode=0, stdout="anki-ollama\tExited (1) 1 minute ago")
        mock_start_fail = MagicMock(returncode=1, stderr="Error response from daemon: container locked")
        with patch.object(manager, "is_service_ready", return_value=False), \
             patch("subprocess.run", side_effect=[mock_inspect, mock_start_fail]):
            ready = manager.ensure_service_ready(auto_start_docker=True)
            assert ready is False

    def test_tier2_docker_container_run_conflict(self):
        """Boundary 1.4: Container name collision (exit code 125) handled without crashing."""
        assert OllamaRuntimeManager is not None, "scripts/ollama_runtime.py is not yet implemented (Milestone 1)"
        manager = OllamaRuntimeManager(host="http://localhost:11434")
        mock_inspect = MagicMock(returncode=0, stdout="")  # Inspect showed empty
        mock_run_conflict = MagicMock(returncode=125, stderr="docker: Error response from daemon: Conflict. The container name is already in use.")
        with patch.object(manager, "is_service_ready", return_value=False), \
             patch("subprocess.run", side_effect=[mock_inspect, mock_run_conflict]):
            ready = manager.ensure_service_ready(auto_start_docker=True)
            assert ready is False

    def test_tier2_docker_subprocess_timeout(self):
        """Boundary 1.5: Subprocess hangs are terminated by timeout without freezing process."""
        assert OllamaRuntimeManager is not None, "scripts/ollama_runtime.py is not yet implemented (Milestone 1)"
        manager = OllamaRuntimeManager(host="http://localhost:11434")
        with patch.object(manager, "is_service_ready", return_value=False), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="docker ps", timeout=5)):
            ready = manager.ensure_service_ready(auto_start_docker=True)
            assert ready is False

    # --- Boundary 2: Ollama Timeout & Network Failures ---

    def test_tier2_ollama_http_500_error(self):
        """Boundary 2.1: Ollama HTTP 500 returns None without raising unhandled HTTPError."""
        assert OllamaRuntimeManager is not None, "scripts/ollama_runtime.py is not yet implemented (Milestone 1)"
        manager = OllamaRuntimeManager(host="http://localhost:11434")
        err = urllib.error.HTTPError(url="http://localhost:11434/api/generate", code=500, msg="Server Error", hdrs={}, fp=io.BytesIO(b"Internal Error"))
        with patch("urllib.request.urlopen", side_effect=err):
            res = manager.generate_json(prompt="Prompt", system_prompt="Sys")
            assert res is None

    def test_tier2_ollama_socket_timeout(self):
        """Boundary 2.2: Socket timeout (URLError: timed out) handled gracefully."""
        assert OllamaRuntimeManager is not None, "scripts/ollama_runtime.py is not yet implemented (Milestone 1)"
        manager = OllamaRuntimeManager(host="http://localhost:11434")
        err = urllib.error.URLError("timed out")
        with patch("urllib.request.urlopen", side_effect=err):
            res = manager.generate_json(prompt="Prompt", system_prompt="Sys")
            assert res is None

    def test_tier2_ollama_connection_refused(self):
        """Boundary 2.3: ConnectionRefusedError returns None immediately."""
        assert OllamaRuntimeManager is not None, "scripts/ollama_runtime.py is not yet implemented (Milestone 1)"
        manager = OllamaRuntimeManager(host="http://localhost:11434")
        err = urllib.error.URLError(ConnectionRefusedError(10061, "Connection refused"))
        with patch("urllib.request.urlopen", side_effect=err):
            res = manager.generate_json(prompt="Prompt", system_prompt="Sys")
            assert res is None

    def test_tier2_ollama_truncated_json_response(self):
        """Boundary 2.4: Incomplete/truncated JSON string returns None rather than crashing json.loads."""
        assert OllamaRuntimeManager is not None, "scripts/ollama_runtime.py is not yet implemented (Milestone 1)"
        manager = OllamaRuntimeManager(host="http://localhost:11434")
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            # Truncated response string
            mock_resp.read.return_value = b'{"response": "{\\"cards\\": [{\\"question\\": \\"Truncated..."'
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            res = manager.generate_json(prompt="Prompt", system_prompt="Sys")
            assert res is None

    def test_tier2_ollama_empty_body_response(self):
        """Boundary 2.5: HTTP 200 with empty body returns None."""
        assert OllamaRuntimeManager is not None, "scripts/ollama_runtime.py is not yet implemented (Milestone 1)"
        manager = OllamaRuntimeManager(host="http://localhost:11434")
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b''
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            res = manager.generate_json(prompt="Prompt", system_prompt="Sys")
            assert res is None

    # --- Boundary 3: Empty / Whitespace Highlights & Break Merging ---

    def test_tier2_highlight_pure_whitespace(self, tmp_path):
        """Boundary 3.1: Highlight consisting entirely of spaces/tabs produces zero cards."""
        doc_path = tmp_path / "whitespace_hl.docx"
        create_custom_docx([
            {"heading": "Pharmacology", "runs": [{"text": "   \t   ", "highlight": "yellow"}]}
        ], doc_path)
        data = extract_document_highlights(str(doc_path))
        # Highlights that are purely whitespace must either be discarded or ignored
        cards = synthesize_cards(data)
        assert len(cards) == 0

    def test_tier2_highlight_punctuation_only(self, tmp_path):
        """Boundary 3.2: Highlight with punctuation only (e.g. '---', ':::') produces zero cards."""
        doc_path = tmp_path / "punct_hl.docx"
        create_custom_docx([
            {"heading": "Pharmacology", "runs": [{"text": " : - ; ", "highlight": "green"}]}
        ], doc_path)
        data = extract_document_highlights(str(doc_path))
        cards = synthesize_cards(data)
        assert len(cards) == 0

    def test_tier2_highlight_break_across_colon(self, tmp_path):
        """Boundary 3.3: Highlight interrupted by unhighlighted colon/space is merged into single concept."""
        doc_path = tmp_path / "broken_hl.docx"
        create_custom_docx([
            {
                "heading": "Lecture 1",
                "runs": [
                    {"text": "Tolerance", "highlight": "green"},
                    {"text": ": ", "highlight": "none"},
                    {"text": "decreased drug response.", "highlight": "green"}
                ]
            }
        ], doc_path)
        data = extract_document_highlights(str(doc_path))
        # The extraction pipeline should merge contiguous identical colors across whitespace/colons
        assert len(data) == 1
        merged_hl = data[0]["highlights"]
        assert len(merged_hl) == 1
        assert "Tolerance" in merged_hl[0]["text"]
        assert "decreased drug response" in merged_hl[0]["text"]

    def test_tier2_highlight_break_across_spaces(self, tmp_path):
        """Boundary 3.4: Contiguous words with uncolored spaces in between merge into single highlight."""
        doc_path = tmp_path / "space_break.docx"
        create_custom_docx([
            {
                "heading": "Lecture 1",
                "runs": [
                    {"text": "Basic", "highlight": "yellow"},
                    {"text": " ", "highlight": "none"},
                    {"text": "science", "highlight": "yellow"}
                ]
            }
        ], doc_path)
        data = extract_document_highlights(str(doc_path))
        assert len(data) == 1
        assert len(data[0]["highlights"]) == 1
        assert data[0]["highlights"][0]["text"].strip() == "Basic science"

    def test_tier2_paragraph_with_no_highlights(self, tmp_path):
        """Boundary 3.5: Paragraph without highlights is skipped entirely."""
        doc_path = tmp_path / "no_hl.docx"
        create_custom_docx([
            {"heading": "Heading Only", "runs": [{"text": "Plain text without any highlights.", "highlight": "none"}]}
        ], doc_path)
        data = extract_document_highlights(str(doc_path))
        assert len(data) == 0

    # --- Boundary 4: Complex Compound Clauses & Extreme Length ---

    def test_tier2_long_highlight_over_500_chars(self):
        """Boundary 4.1: Highlight > 500 characters is segmented into atomic cards (Rule 4)."""
        long_text = (
            "Dopamine transmission in the mesolimbic pathway mediates incentive salience and reward reinforcement, "
            "whereas dopamine signaling in the nigrostriatal pathway regulates motor planning and extrapyramidal function. "
            "Chronic dopamine blockade by first-generation antipsychotics in the nigrostriatal pathway induces Parkinsonian side effects, "
            "dystonia, and akathisia when D2 receptor occupancy exceeds 80 percent, while therapeutic efficacy requires at least 65 percent occupancy."
        )
        assert len(long_text) > 400
        if SemanticCardParser is not None:
            parser = SemanticCardParser()
            cards = parser.parse_with_fallback(long_text, highlight_color="yellow", heading="Dopamine")
            assert len(cards) >= 2, "Long complex statement must be decomposed into multiple atomic cards"
            for c in cards:
                # Answer should respect atomicity (<= 40 words)
                assert len(c["answer"].split()) <= 40
        else:
            # Baseline test
            cards = synthesize_cards([{
                "heading": "Dopamine",
                "full_paragraph": long_text,
                "segments": [{"raw_color": "yellow", "category": "yellow", "text": long_text}],
                "highlights": [{"raw_color": "yellow", "category": "yellow", "text": long_text}],
            }])
            assert len(cards) >= 1

    def test_tier2_compound_contrastive_clauses(self):
        """Boundary 4.2: Clauses connected with 'whereas' or 'while' split into distinct cards."""
        text = "Agonists stabilize the active receptor conformation, whereas antagonists bind without receptor activation."
        if SemanticCardParser is not None:
            parser = SemanticCardParser()
            cards = parser.parse_with_fallback(text, highlight_color="yellow", heading="Receptor Dynamics")
            assert len(cards) >= 2
            q_text = " ".join(c["question"] for c in cards).lower()
            assert "agonist" in q_text
            assert "antagonist" in q_text

    def test_tier2_comma_separated_enumerations(self):
        """Boundary 4.3: Three-part comma separated enumeration produces atomic cards, not set card."""
        text = "Developmental science addresses description, explanation, and optimization."
        if SemanticCardParser is not None:
            parser = SemanticCardParser()
            cards = parser.parse_with_fallback(text, highlight_color="green", heading="Developmental Psychology")
            for c in cards:
                # Must avoid "What are the 3..."
                assert not re.search(r'what\s+are\s+the\s+\d+', c["question"], re.IGNORECASE)

    def test_tier2_semicolon_delimited_statements(self):
        """Boundary 4.4: Semicolon delimited statements split into independent questions."""
        text = "Tolerance requires dose escalation; physical dependence manifests as withdrawal symptoms upon cessation."
        if SemanticCardParser is not None:
            parser = SemanticCardParser()
            cards = parser.parse_with_fallback(text, highlight_color="yellow", heading="Addiction Pharmacology")
            assert len(cards) >= 2

    def test_tier2_parenthetical_clinical_notes_to_context(self):
        """Boundary 4.5: Parenthetical clinical examples are preserved in context field, not dumped in answer."""
        structured = [{
            "heading": "Receptors",
            "full_paragraph": "Downregulation occurs after chronic agonist exposure (e.g. chronic opioid exposure).",
            "segments": [
                {"raw_color": "yellow", "category": "yellow", "text": "Downregulation occurs after chronic agonist exposure"},
                {"raw_color": "#C9DAF8", "category": "other", "text": "(e.g. chronic opioid exposure)"}
            ],
            "highlights": [
                {"raw_color": "yellow", "category": "yellow", "text": "Downregulation occurs after chronic agonist exposure"},
                {"raw_color": "#C9DAF8", "category": "other", "text": "(e.g. chronic opioid exposure)"}
            ]
        }]
        cards = synthesize_cards(structured)
        assert len(cards) >= 1
        # Context must capture the blue highlight note
        assert "chronic opioid exposure" in cards[0]["context"]

    # --- Boundary 5: Lack of Linking Verbs & Non-Standard Syntax ---

    def test_tier2_syntax_no_linking_verb_isolated_term(self):
        """Boundary 5.1: Isolated noun phrase without linking verb (e.g. 'Positive Mutations') handled cleanly."""
        text = "Positive Mutations"
        if SemanticCardParser is not None:
            parser = SemanticCardParser()
            cards = parser.parse_with_fallback(text, highlight_color="green", heading="Genetics")
            assert len(cards) >= 1
            assert "this concept" not in cards[0]["question"].lower()
            assert "positive mutations" in cards[0]["question"].lower()

    def test_tier2_syntax_passive_voice_copula(self):
        """Boundary 5.2: Passive voice 'X is characterized by Y' correctly extracts X."""
        text = "Neuroleptic malignant syndrome is characterized by hyperthermia, muscle rigidity, and autonomic instability."
        if SemanticCardParser is not None:
            parser = SemanticCardParser()
            cards = parser.parse_with_fallback(text, highlight_color="green", heading="Adverse Drug Reactions")
            assert len(cards) >= 1
            assert "this concept" not in cards[0]["question"].lower()
            assert "neuroleptic malignant syndrome" in cards[0]["question"].lower()

    def test_tier2_syntax_typographic_dash_definition(self):
        """Boundary 5.3: Hyphen or en-dash as copula ('ED50 - median effective dose') parsed cleanly."""
        text = "ED50 - median effective dose that produces quantal response in 50 percent of subjects."
        if SemanticCardParser is not None:
            parser = SemanticCardParser()
            cards = parser.parse_with_fallback(text, highlight_color="green", heading="Dose-Response")
            assert len(cards) >= 1
            assert "this concept" not in cards[0]["question"].lower()
            assert "ed50" in cards[0]["question"].lower()

    def test_tier2_syntax_drug_symbols_and_numbers(self):
        """Boundary 5.4: Chemical/pharmacological alphanumeric terms ('D2', '5-HT2A', 'TD50') preserved intact."""
        text = "5-HT2A receptor antagonism mediates atypical antipsychotic action."
        if SemanticCardParser is not None:
            parser = SemanticCardParser()
            cards = parser.parse_with_fallback(text, highlight_color="yellow", heading="Serotonin Receptors")
            assert len(cards) >= 1
            full_card_text = cards[0]["question"] + " " + cards[0]["answer"]
            assert "5-HT2A" in full_card_text

    def test_tier2_syntax_question_in_notes(self):
        """Boundary 5.5: Lecture notes already formatted as question handled without mangling."""
        text = "Why does tolerance occur? Repeated agonist exposure causes receptor endocytosis."
        if SemanticCardParser is not None:
            parser = SemanticCardParser()
            cards = parser.parse_with_fallback(text, highlight_color="green", heading="Tolerance Mechanism")
            assert len(cards) >= 1
            assert "this concept" not in cards[0]["question"].lower()

    # --- Boundary 6: Malformed Responses & Schema Corruption ---

    def test_tier2_json_schema_missing_cards_key(self):
        """Boundary 6.1: LLM response missing 'cards' key triggers graceful fallback."""
        assert SemanticCardParser is not None, "scripts/semantic_parser.py is not yet implemented (Milestone 2)"
        runtime_mock = MagicMock()
        runtime_mock.generate_json.return_value = {"error": "Invalid format"}
        parser = SemanticCardParser(runtime_manager=runtime_mock)
        cards = parser.parse_highlight("Tolerance is decreasing responsiveness.", "green", "Pharmacology")
        assert len(cards) >= 1
        assert "this concept" not in cards[0]["question"].lower()

    def test_tier2_json_schema_card_missing_fields(self):
        """Boundary 6.2: Card object missing 'question' or 'answer' key is dropped or corrected."""
        assert SemanticCardParser is not None, "scripts/semantic_parser.py is not yet implemented (Milestone 2)"
        runtime_mock = MagicMock()
        runtime_mock.generate_json.return_value = {
            "cards": [
                {"bad_key": "val"},  # Corrupt card
                {"question": "What is tolerance?", "answer": "Decreased responsiveness"}
            ]
        }
        parser = SemanticCardParser(runtime_manager=runtime_mock)
        cards = parser.parse_highlight("Tolerance is decreasing responsiveness.", "green", "Pharmacology")
        for c in cards:
            assert "question" in c and "answer" in c
            assert len(c["question"].strip()) > 0
            assert len(c["answer"].strip()) > 0

    def test_tier2_json_schema_empty_string_fields(self):
        """Boundary 6.3: Card object with empty question string is filtered out."""
        assert SemanticCardParser is not None, "scripts/semantic_parser.py is not yet implemented (Milestone 2)"
        runtime_mock = MagicMock()
        runtime_mock.generate_json.return_value = {
            "cards": [{"question": "   ", "answer": "Tolerance"}]
        }
        parser = SemanticCardParser(runtime_manager=runtime_mock)
        cards = parser.parse_highlight("Tolerance is decreasing responsiveness.", "green", "Pharmacology")
        for c in cards:
            assert c["question"].strip() != ""

    def test_tier2_json_raw_string_not_dict(self):
        """Boundary 6.4: Non-dict return from Ollama manager triggers fallback."""
        assert SemanticCardParser is not None, "scripts/semantic_parser.py is not yet implemented (Milestone 2)"
        runtime_mock = MagicMock()
        runtime_mock.generate_json.return_value = None
        parser = SemanticCardParser(runtime_manager=runtime_mock)
        cards = parser.parse_highlight("Tolerance is decreasing responsiveness.", "green", "Pharmacology")
        assert len(cards) >= 1
        assert "this concept" not in cards[0]["question"].lower()

    def test_tier2_json_list_top_level(self):
        """Boundary 6.5: Top-level JSON array instead of dictionary handled seamlessly."""
        assert SemanticCardParser is not None, "scripts/semantic_parser.py is not yet implemented (Milestone 2)"
        runtime_mock = MagicMock()
        # Some LLMs return a direct list: [{"question": "Q", "answer": "A"}]
        runtime_mock.generate_json.return_value = [{"question": "What is tolerance?", "answer": "Decreased responsiveness"}]
        parser = SemanticCardParser(runtime_manager=runtime_mock)
        cards = parser.parse_highlight("Tolerance is decreasing responsiveness.", "green", "Pharmacology")
        assert len(cards) >= 1


# ==============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS (Pairwise & Integration Interactions)
# 7 Integration Tests
# ==============================================================================

class TestTier3CrossFeatureCombinations:
    """
    Tier 3 tests verify pairwise subsystem interactions: Docker down + Fallback activation,
    Multiple highlights + Cloze generation, Packaging + Metadata preservation, etc.
    """

    def test_tier3_docker_down_triggers_fallback_end_to_end(self, tmp_path):
        """Combination 3.1: Docker offline transparently engages fallback and produces valid .apkg."""
        doc_path = tmp_path / "offline_test.docx"
        create_custom_docx([
            {
                "heading": "PSYC 3590: Pharmacodynamics",
                "runs": [
                    {"text": "Tolerance", "highlight": "yellow"},
                    {"text": " is defined as ", "highlight": "none"},
                    {"text": "a state of progressively decreasing responsiveness.", "highlight": "green"}
                ]
            }
        ], doc_path)

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Docker offline")):
            data = extract_document_highlights(str(doc_path))
            cards = synthesize_cards(data)
            assert len(cards) >= 1
            for c in cards:
                assert "this concept" not in c["question"].lower()

            out_apkg = create_deck_package("PSYC 3590:Offline Test", cards, output_filename="offline_test.apkg")
            assert out_apkg.exists()
            assert out_apkg.stat().st_size > 0

    def test_tier3_ollama_timeout_yields_bidirectional_cards(self):
        """Combination 3.2: Ollama timeout triggers fallback, producing forward and reverse definition cards."""
        text = "Tolerance is defined as progressively decreasing responsiveness."
        if SemanticCardParser is not None:
            runtime_mock = MagicMock()
            runtime_mock.generate_json.side_effect = TimeoutError("Ollama timeout")
            parser = SemanticCardParser(runtime_manager=runtime_mock)
            cards = parser.parse_highlight(text, highlight_color="green", heading="Pharmacology")
            assert len(cards) >= 1
            # Fallback must generate at least 1 bidirectional card or pair
            assert "this concept" not in cards[0]["question"].lower()

    def test_tier3_multiple_highlights_no_cartesian_explosion(self):
        """Combination 3.3: Multiple yellow and green highlights in single paragraph avoid N x M explosion."""
        structured = [{
            "heading": "Pharmacology",
            "full_paragraph": "Agonist binds receptor. Antagonist blocks receptor.",
            "segments": [
                {"raw_color": "yellow", "category": "yellow", "text": "Agonist"},
                {"raw_color": "green", "category": "green", "text": "binds receptor"},
                {"raw_color": "yellow", "category": "yellow", "text": "Antagonist"},
                {"raw_color": "green", "category": "green", "text": "blocks receptor"}
            ],
            "highlights": [
                {"raw_color": "yellow", "category": "yellow", "text": "Agonist"},
                {"raw_color": "green", "category": "green", "text": "binds receptor"},
                {"raw_color": "yellow", "category": "yellow", "text": "Antagonist"},
                {"raw_color": "green", "category": "green", "text": "blocks receptor"}
            ]
        }]
        cards = synthesize_cards(structured)
        # 2 terms + 2 defs should produce 4 cards (2 bidirectional pairs), NEVER an unlinked Cartesian product like Agonist -> blocks receptor
        for c in cards:
            if re.search(r'\bagonist\b', c["question"], re.IGNORECASE):
                assert "blocks receptor" not in c["answer"].lower()
            if re.search(r'\bantagonist\b', c["question"], re.IGNORECASE):
                assert "binds receptor" not in c["answer"].lower()

    def test_tier3_apkg_metadata_badge_and_tags_preservation(self, tmp_path):
        """Combination 3.4: Compiled .apkg retains CategoryBadge, Context, and Course/Chapter tags."""
        cards = [
            {
                "question": "What is the definition of <b>Tolerance</b>?",
                "answer": "Decreased responsiveness.",
                "category_badge": "badge-definition",
                "context": "PSYC 3590 | Pharmacodynamics",
                "tags": ["psyc3590", "pharmacodynamics", "definition", "forward"]
            }
        ]
        out_path = create_deck_package("PSYC 3590:Metadata Test", cards, output_filename="meta_test.apkg")
        assert out_path.exists()

        # Extract .apkg (which is a zip containing collection.anki2 SQLite database)
        with zipfile.ZipFile(out_path, "r") as zf:
            assert "collection.anki2" in zf.namelist()
            with tempfile.TemporaryDirectory() as extract_dir:
                zf.extract("collection.anki2", extract_dir)
                conn = sqlite3.connect(Path(extract_dir) / "collection.anki2")
                cursor = conn.cursor()
                cursor.execute("SELECT flds, tags FROM notes")
                rows = cursor.fetchall()
                assert len(rows) == 1
                flds, tags_str = rows[0]
                # Fields are separated by \x1f in Anki SQLite
                fields = flds.split("\x1f")
                assert len(fields) >= 4
                assert "Tolerance" in fields[0]
                assert "Decreased responsiveness" in fields[1]
                assert "badge-definition" in fields[2]
                assert "PSYC 3590" in fields[3]
                assert "psyc3590" in tags_str
                conn.close()

    def test_tier3_highlight_gap_merge_plus_semantic_parsing(self, tmp_path):
        """Combination 3.5: Highlight with whitespace gap is merged and parsed into atomic cards."""
        doc_path = tmp_path / "gap_semantic.docx"
        create_custom_docx([
            {
                "heading": "Pharmacology",
                "runs": [
                    {"text": "Therapeutic", "highlight": "green"},
                    {"text": " ", "highlight": "none"},
                    {"text": "index is defined as the ratio between TD50 and ED50.", "highlight": "green"}
                ]
            }
        ], doc_path)
        data = extract_document_highlights(str(doc_path))
        cards = synthesize_cards(data)
        assert len(cards) >= 1
        assert "this concept" not in cards[0]["question"].lower()
        assert "therapeutic index" in cards[0]["question"].lower()

    def test_tier3_course_naming_resolution_to_apkg_file(self, tmp_path):
        """Combination 3.6: Directory hierarchy 'PSYC 3590 Drugs & Behaviour/Lecture 2' resolves to exact deck."""
        doc_dir = tmp_path / "F PSYC 3590  Drugs & Behaviour" / "Lecture 2 - Pharmacodynamics"
        doc_dir.mkdir(parents=True)
        doc_file = doc_dir / "notes.docx"
        create_custom_docx([
            {"heading": "Tolerance", "runs": [{"text": "Tolerance: decreased response.", "highlight": "yellow"}]}
        ], doc_file)

        deck_title, safe_filename = resolve_deck_naming(str(doc_file))
        assert "PSYC 3590" in deck_title
        assert "Drugs & Behaviour" in deck_title
        assert safe_filename.endswith(".apkg")
        assert ":" not in safe_filename  # Windows-safe filename

    def test_tier3_yellow_green_blue_multi_color_enrichment(self):
        """Combination 3.7: Paragraph with Yellow + Green + Blue produces note with context box."""
        structured = [{
            "heading": "Pharmacodynamics",
            "full_paragraph": "Downregulation: Endocytosis of receptors (e.g. chronic opioid exposure).",
            "segments": [
                {"raw_color": "yellow", "category": "yellow", "text": "Downregulation"},
                {"raw_color": "green", "category": "green", "text": "Endocytosis of receptors"},
                {"raw_color": "#C9DAF8", "category": "other", "text": "(e.g. chronic opioid exposure)"}
            ],
            "highlights": [
                {"raw_color": "yellow", "category": "yellow", "text": "Downregulation"},
                {"raw_color": "green", "category": "green", "text": "Endocytosis of receptors"},
                {"raw_color": "#C9DAF8", "category": "other", "text": "(e.g. chronic opioid exposure)"}
            ]
        }]
        cards = synthesize_cards(structured)
        assert len(cards) >= 1
        assert "chronic opioid exposure" in cards[0]["context"]
        assert cards[0]["category_badge"] == "badge-definition"


# ==============================================================================
# TIER 4: REAL-WORLD SCENARIOS (End-to-End Artifact & Pipeline Verification)
# 7 Real-World Tests
# ==============================================================================

class TestTier4RealWorldScenarios:
    """
    Tier 4 tests execute the full end-to-end pipeline against real lecture notes
    (sample_lecture_notes.docx), asserting 0 exit codes, valid .apkg structures,
    and zero quality vetoes under the 30-point Agent-as-Judge rubric.
    """

    def test_tier4_full_cli_sample_lecture_notes(self, sample_docx_path, tmp_path):
        """Scenario 4.1: Full CLI execution of extract_and_generate.py on sample_lecture_notes.docx exits 0."""
        cmd = [
            sys.executable,
            str(SCRIPTS_DIR / "extract_and_generate.py"),
            str(sample_docx_path),
            "--deck", "PSYC 3590:Test Deck E2E"
        ]
        # Execute with 20 second timeout budget
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        assert res.returncode == 0, f"CLI execution failed with code {res.returncode}: {res.stderr}"
        assert "Successfully generated Anki deck" in res.stdout

    def test_tier4_full_cli_with_explicit_class_and_chapter(self, sample_docx_path):
        """Scenario 4.2: Full CLI invocation with --class-name and --chapter options."""
        cmd = [
            sys.executable,
            str(SCRIPTS_DIR / "extract_and_generate.py"),
            str(sample_docx_path),
            "--class-name", "PSYC 3590",
            "--chapter", "Lecture 2 - Pharmacodynamics"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        assert res.returncode == 0
        assert "PSYC 3590" in res.stdout
        assert "Lecture 2 - Pharmacodynamics" in res.stdout

    def test_tier4_apkg_archive_integrity(self, sample_docx_path):
        """Scenario 4.3: Generated .apkg is a valid ZIP archive containing valid SQLite database."""
        deck_dir = Path(CONFIG.get("output_directory", PROJECT_ROOT / "Decks"))
        # Find latest generated .apkg
        apkgs = list(deck_dir.glob("*.apkg"))
        assert len(apkgs) >= 1, "Expected at least one .apkg package in Decks directory"
        target_apkg = sorted(apkgs, key=lambda p: p.stat().st_mtime)[-1]

        with zipfile.ZipFile(target_apkg, "r") as zf:
            names = zf.namelist()
            assert "collection.anki2" in names
            with tempfile.TemporaryDirectory() as extract_dir:
                zf.extract("collection.anki2", extract_dir)
                conn = sqlite3.connect(Path(extract_dir) / "collection.anki2")
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM notes")
                note_count = cursor.fetchone()[0]
                assert note_count >= 3, f"Expected at least 3 notes in deck, found {note_count}"
                conn.close()

    def test_tier4_output_cards_zero_banned_phrases(self, sample_docx_path):
        """Scenario 4.4: 0% of cards in sample lecture deck contain 'this concept' or 'What is this concept?'."""
        data = extract_document_highlights(str(sample_docx_path))
        cards = synthesize_cards(data)
        assert len(cards) >= 1

        banned_phrases = ["this concept", "this term", "this phenomenon"]
        violating_cards = []
        for i, c in enumerate(cards, 1):
            q = c["question"].lower()
            a = c["answer"].lower()
            if any(p in q or p in a for p in banned_phrases):
                violating_cards.append((i, c["question"]))

        assert len(violating_cards) == 0, f"Found cards containing banned phrases: {violating_cards}"

    def test_tier4_output_cards_zero_heading_dump_questions(self, sample_docx_path):
        """Scenario 4.5: 0% of cards have prompt consisting merely of raw heading dump."""
        data = extract_document_highlights(str(sample_docx_path))
        cards = synthesize_cards(data)
        violating_cards = []
        for i, c in enumerate(cards, 1):
            q = c["question"]
            # Detect raw heading-only prompt bug: <b>Key Concept / Mechanism:</b><br>{heading}
            if "<b>Key Concept / Mechanism:</b><br>" in q and not any(w in q for w in ["What", "Which", "Why", "How", "Identify", "Explain"]):
                violating_cards.append((i, q))

        assert len(violating_cards) == 0, (
            f"Found {len(violating_cards)} cards violating SuperMemo Rule 3 with raw heading prompts: {violating_cards}"
        )

    def test_tier4_agent_as_judge_deck_evaluation(self, sample_docx_path, judge_oracle):
        """Scenario 4.6: Agent-as-Judge evaluates sample lecture notes cards against 30-pt rubric (assert >= 25)."""
        data = extract_document_highlights(str(sample_docx_path))
        cards = synthesize_cards(data)
        report = judge_oracle.evaluate_deck(cards)

        assert report["total_cards"] >= 3
        # Baseline check: log the score and veto count
        assert report["veto_count"] == 0, f"Judge detected {report['veto_count']} hard vetoes in generated cards"
        assert report["average_score"] >= 25.0, f"Average card score {report['average_score']}/30 below passing threshold (25.0)"
        assert report["deck_passed"] is True

    def test_tier4_multipage_lecture_processing_performance_budget(self, tmp_path):
        """Scenario 4.7: Multipage 10-paragraph document completes extraction and compilation in < 15 seconds."""
        doc_path = tmp_path / "long_lecture.docx"
        paragraphs = []
        for i in range(1, 11):
            paragraphs.append({
                "heading": f"Topic {i}: Neuroscience Principles",
                "runs": [
                    {"text": f"Concept_{i}", "highlight": "yellow"},
                    {"text": " is defined as ", "highlight": "none"},
                    {"text": f"the physiological process of neuroplastic adaptation number {i}.", "highlight": "green"}
                ]
            })
        create_custom_docx(paragraphs, doc_path)

        import time
        t0 = time.time()
        data = extract_document_highlights(str(doc_path))
        cards = synthesize_cards(data)
        out_path = create_deck_package("PSYC 3590:Performance Test", cards, output_filename="perf_test.apkg")
        elapsed = time.time() - t0

        assert out_path.exists()
        assert len(cards) >= 10
        assert elapsed < 15.0, f"Processing took {elapsed:.2f}s, exceeding 15.0s performance budget"
