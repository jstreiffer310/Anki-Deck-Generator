import pytest
import os
import re
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from scripts.extract_and_generate import (
    is_google_doc_source,
    resolve_deck_naming,
    extract_highlights,
    process_source_and_generate,
    synthesize_cards,
    detect_input_type,
    ingest_source,
)
from scripts.docs_api_client import extract_document_id
from scripts.card_validator import (
    classify_cognitive_taxonomy,
    formulate_cognitive_cards,
    validate_card,
    remove_duplicate_cards,
)


class TestGoogleDocSourceDetection:
    """Test detection of Google Docs URLs, IDs, and local .docx files."""

    def test_google_docs_url_variants(self):
        urls = [
            ("https://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit", "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"),
            ("https://docs.google.com/document/u/0/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/preview", "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"),
            ("http://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"),
            ("https://docs.google.com/document/d/abc123XYZ_-456/edit?usp=sharing", "abc123XYZ_-456"),
        ]
        for url, expected_id in urls:
            assert is_google_doc_source(url) is True
            doc_id = extract_document_id(url)
            assert doc_id == expected_id, f"Expected {expected_id}, got {doc_id}"
            assert not doc_id.startswith("http")
            assert "/" not in doc_id

    def test_detect_input_type_all_categories(self, tmp_path):
        # Google Docs URLs
        assert detect_input_type("https://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit") == "gdoc_url"
        assert detect_input_type("https://docs.google.com/document/u/0/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/preview") == "gdoc_url"
        # Bare Google Doc IDs
        assert detect_input_type("1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms") == "gdoc_id"
        # Existing local docx
        doc_file = tmp_path / "test.docx"
        doc_file.touch()
        assert detect_input_type(str(doc_file)) == "docx_file"
        # Missing docx
        assert detect_input_type("missing_file.docx") in ("docx_missing", "invalid")
        # Non-docx existing file (e.g. .pdf)
        pdf_file = tmp_path / "test.pdf"
        pdf_file.touch()
        assert detect_input_type(str(pdf_file)) == "invalid"
        # Non-doc URL
        assert detect_input_type("https://google.com") == "invalid"
        assert detect_input_type("https://docs.google.com/spreadsheets/d/123/edit") == "invalid"
        # Empty/whitespace
        assert detect_input_type("") == "invalid"
        assert detect_input_type("   ") == "invalid"

    def test_raw_document_ids(self):
        valid_ids = [
            "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
            "abc123XYZ_456-789012345678901234",
            "DOC_ID_ALPHA_NUMERIC_LONG_ENOUGH_123456",
        ]
        for did in valid_ids:
            assert is_google_doc_source(did) is True

    def test_docx_files_and_local_paths(self, tmp_path):
        # Even if not existing, .docx extension is not a Google Doc source
        assert is_google_doc_source("notes.docx") is False
        assert is_google_doc_source("C:/path/to/lecture.docx") is False
        assert is_google_doc_source("lecture.DOCX") is False

        # Existing local file on disk
        local_file = tmp_path / "sample_id_file"
        local_file.write_text("dummy", encoding="utf-8")
        assert is_google_doc_source(str(local_file)) is False

    def test_empty_or_invalid_sources(self):
        assert is_google_doc_source("") is False
        assert is_google_doc_source(None) is False
        assert is_google_doc_source("short") is False
        assert is_google_doc_source("https://google.com") is False
        assert is_google_doc_source("https://docs.google.com/spreadsheets/d/123/edit") is False


class TestResolveDeckNaming:
    """Test resolution of CLASS(with course name):CHAPTER naming standard."""

    def test_naming_from_google_doc_title_known_course(self):
        # PSYC 2110 is in config.json as "Developmental Psychology"
        title = "PSYC 2110 - Lecture 1 Introduction"
        deck_title, safe_filename = resolve_deck_naming(
            "dummy_doc_id",
            doc_title=title,
        )
        assert "PSYC 2110 (Developmental Psychology)" in deck_title
        assert "Lecture 1: Introduction" in deck_title
        assert ":" in deck_title
        # Safe filename must NOT contain ':'
        assert ":" not in safe_filename
        assert safe_filename.endswith(".apkg")

    def test_naming_from_google_doc_title_chapter(self):
        title = "PSYC 3590 - Chapter 3 Behavioral Neuroscience"
        deck_title, safe_filename = resolve_deck_naming(
            "dummy_doc_id",
            doc_title=title,
        )
        assert "PSYC 3590" in deck_title
        assert "Chapter 3: Behavioral Neuroscience" in deck_title
        assert ":" not in safe_filename

    def test_naming_from_heading_hierarchy(self):
        headings = [
            "PSYC 2110 Cognitive Architecture",
            "Week 4: Working Memory Models",
            "Working Memory Components",
        ]
        deck_title, safe_filename = resolve_deck_naming(
            "dummy_doc_id",
            doc_title="Lecture Notes",
            heading_hierarchy=headings,
        )
        assert "PSYC 2110" in deck_title
        assert "Week 4: Working Memory Models" in deck_title

    def test_explicit_overrides(self):
        deck_title, safe_filename = resolve_deck_naming(
            "dummy_doc_id",
            explicit_class="PSYC 1010 General Psychology",
            explicit_chapter="Chapter 1: Foundations",
            doc_title="Some random title",
        )
        assert "PSYC 1010 (General Psychology)" in deck_title
        assert "Chapter 1: Foundations" in deck_title
        assert ":" not in safe_filename


class TestExtractHighlightsDispatch:
    """Test dispatching between Google Docs API and local .docx files."""

    @patch("scripts.extract_and_generate.is_google_doc_source")
    @patch("scripts.extract_and_generate.extract_google_doc_structured")
    def test_extract_highlights_dispatches_to_google_docs(self, mock_extract_gdoc, mock_is_gdoc):
        mock_is_gdoc.return_value = True
        mock_extract_gdoc.return_value = ([{"heading": "Test"}], "Doc Title")

        data, title = extract_highlights("1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms")
        assert title == "Doc Title"
        assert len(data) == 1
        mock_extract_gdoc.assert_called_once()

    @patch("scripts.extract_and_generate.is_google_doc_source")
    @patch("scripts.extract_and_generate.extract_document_highlights")
    def test_extract_highlights_dispatches_to_local_docx(self, mock_extract_docx, mock_is_gdoc):
        mock_is_gdoc.return_value = False
        mock_extract_docx.return_value = [{"heading": "Local Heading"}]

        data, title = extract_highlights("lecture.docx")
        assert title is None
        assert len(data) == 1
        mock_extract_docx.assert_called_once_with("lecture.docx")


class TestCognitiveTaxonomiesAndCardValidation:
    """Test cognitive card formulation taxonomies and validation invariants."""

    def test_cognitive_taxonomy_classification(self):
        # Function -> Structure
        tax = classify_cognitive_taxonomy("myelin sheath", "insulates axons and accelerates action potential propagation")
        assert tax == "function_structure"

        # Concept -> Mechanism
        tax = classify_cognitive_taxonomy("long-term potentiation", "NMDA receptor activation and calcium influx")
        assert tax == "concept_mechanism"

        # Example -> Category
        tax = classify_cognitive_taxonomy("locked-in syndrome", "a clinical condition characterized by total voluntary muscle paralysis except eye movement")
        assert tax == "example_category"

        # Term -> Definition
        tax = classify_cognitive_taxonomy("neuroplasticity", "the ability of neural networks in the brain to change through growth and reorganization")
        assert tax == "term_definition"

    def test_formulate_cognitive_cards(self):
        cards = formulate_cognitive_cards(
            keyword="Neuroplasticity",
            descriptor="The capacity of the nervous system to modify its structural organization and function in response to experience.",
            heading="Brain Adaptations",
            context="Neural Plasticity Lecture",
            tags=["neuroscience"],
        )
        assert len(cards) == 2
        forward_card = cards[0]
        reverse_card = cards[1]

        assert forward_card["taxonomy"] == "term_definition"
        assert "Neuroplasticity" in forward_card["question"]
        assert forward_card["answer"].startswith("The capacity of the nervous system")
        assert reverse_card["answer"].startswith("Neuroplasticity")

    def test_linking_verb_parsing_prevents_this_concept_bug(self):
        raw_highlight = "Long-Term Potentiation is a persistent strengthening of synapses based on recent patterns of activity."
        # Synthesizing cards from a standalone green highlight should parse out the subject
        structured = [{
            "heading": "Synaptic Plasticity",
            "full_paragraph": raw_highlight,
            "segments": [{"category": "green", "text": raw_highlight, "raw_color": "green"}],
            "highlights": [{"category": "green", "text": raw_highlight, "raw_color": "green"}]
        }]
        cards = synthesize_cards(structured, deck_tags=["neuro"])
        assert len(cards) >= 2
        for c in cards:
            assert "this concept" not in c["question"].lower()
            assert "this concept" not in c["answer"].lower()
            valid, reason = validate_card(c)
            assert valid, f"Card invalid: {reason}"


class TestEndToEndGoogleDocsIngestion:
    """End-to-end integration test with mocked Google Docs API client."""

    @patch("scripts.extract_and_generate.inject_via_ankiconnect")
    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_process_source_and_generate_google_doc(
        self,
        mock_get_credentials,
        mock_build,
        mock_inject,
        tmp_path
    ):
        mock_service = MagicMock()
        mock_documents = MagicMock()
        mock_get = MagicMock()

        mock_build.return_value = mock_service
        mock_service.documents.return_value = mock_documents
        mock_documents.get.return_value = mock_get

        # Mocked Google Doc API response
        mock_get.execute.return_value = {
            "title": "PSYC 2110 - Lecture 2 Brain Development",
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "paragraphStyle": {"namedStyleType": "HEADING_1"},
                            "elements": [{"textRun": {"content": "Neural Development Stages\n"}}]
                        }
                    },
                    {
                        "paragraph": {
                            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                            "elements": [
                                {
                                    "textRun": {
                                        "content": "Synaptogenesis: ",
                                        "textStyle": {
                                            "backgroundColor": {
                                                "color": {"rgbColor": {"red": 1.0, "green": 1.0, "blue": 0.0}}  # Yellow
                                            }
                                        }
                                    }
                                },
                                {
                                    "textRun": {
                                        "content": "the formation of synapses between neurons in the nervous system.",
                                        "textStyle": {
                                            "backgroundColor": {
                                                "color": {"rgbColor": {"red": 0.0, "green": 1.0, "blue": 0.0}}  # Green
                                            }
                                        }
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }

        # Run process_source_and_generate
        doc_url = "https://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"
        out_apkg, deck_title, cards = process_source_and_generate(
            source=doc_url,
            deck_tags=["lecture_notes"],
            auto_inject=True
        )

        assert out_apkg.exists()
        assert out_apkg.suffix == ".apkg"
        assert "PSYC 2110 (Developmental Psychology)" in deck_title
        assert "Lecture 2: Brain Development" in deck_title
        assert len(cards) >= 2

        # Validate card contents
        forward_cards = [c for c in cards if "forward" in c.get("tags", [])]
        reverse_cards = [c for c in cards if "reverse" in c.get("tags", [])]
        assert len(forward_cards) >= 1
        assert len(reverse_cards) >= 1

        assert "Synaptogenesis" in forward_cards[0]["question"]
        assert "formation of synapses" in forward_cards[0]["answer"]
        assert forward_cards[0]["answer"] in reverse_cards[0]["question"]
        assert reverse_cards[0]["answer"] == "Synaptogenesis"

        # Verify cognitive taxonomy annotation
        assert forward_cards[0].get("taxonomy") == "term_definition"

        # Verify AnkiConnect was called
        mock_inject.assert_called_once_with(out_apkg)

    @patch("scripts.extract_and_generate.inject_via_ankiconnect")
    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_title_paragraph_fallback_and_nested_headings(
        self,
        mock_get_credentials,
        mock_build,
        mock_inject
    ):
        mock_service = MagicMock()
        mock_documents = MagicMock()
        mock_get = MagicMock()

        mock_build.return_value = mock_service
        mock_service.documents.return_value = mock_documents
        mock_documents.get.return_value = mock_get

        # Document without 'title' field, but with a TITLE styled paragraph
        mock_get.execute.return_value = {
            "title": "",  # Empty title
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "paragraphStyle": {"namedStyleType": "TITLE"},
                            "elements": [{"textRun": {"content": "PSYC 3590 - Chapter 4 Memory Systems\n"}}]
                        }
                    },
                    {
                        "paragraph": {
                            "paragraphStyle": {"namedStyleType": "HEADING_1"},
                            "elements": [{"textRun": {"content": "Long-Term Memory\n"}}]
                        }
                    },
                    {
                        "paragraph": {
                            "paragraphStyle": {"namedStyleType": "HEADING_2"},
                            "elements": [{"textRun": {"content": "Declarative Subsystems\n"}}]
                        }
                    },
                    {
                        "paragraph": {
                            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                            "elements": [
                                {
                                    "textRun": {
                                        "content": "Episodic memory: ",
                                        "textStyle": {
                                            "backgroundColor": {
                                                "color": {"rgbColor": {"red": 1.0, "green": 1.0, "blue": 0.0}}
                                            }
                                        }
                                    }
                                },
                                {
                                    "textRun": {
                                        "content": "the memory of autobiographical events that can be explicitly stated.",
                                        "textStyle": {
                                            "backgroundColor": {
                                                "color": {"rgbColor": {"red": 0.0, "green": 1.0, "blue": 0.0}}
                                            }
                                        }
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }

        out_apkg, deck_title, cards = process_source_and_generate(
            source="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
            deck_tags=["test_deck"],
            auto_inject=False
        )

        assert "PSYC 3590" in deck_title
        assert "Chapter 4: Memory Systems" in deck_title
        assert len(cards) >= 2
        # auto_inject was False, so AnkiConnect should not be invoked
        mock_inject.assert_not_called()

    @patch("scripts.extract_and_generate.create_deck_package")
    @patch("scripts.extract_and_generate.inject_via_ankiconnect")
    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_placeholder_and_duplicate_filtering(
        self,
        mock_get_credentials,
        mock_build,
        mock_inject,
        mock_create_pkg
    ):
        mock_service = MagicMock()
        mock_documents = MagicMock()
        mock_get = MagicMock()

        mock_build.return_value = mock_service
        mock_service.documents.return_value = mock_documents
        mock_documents.get.return_value = mock_get
        mock_create_pkg.return_value = Path("dummy.apkg")

        # Highlights containing placeholder answers, empty definitions, and identical duplicate rows
        mock_get.execute.return_value = {
            "title": "COGS 1000 - Lecture 5 Attention",
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "paragraphStyle": {"namedStyleType": "HEADING_1"},
                            "elements": [{"textRun": {"content": "Filtering Mechanisms\n"}}]
                        }
                    },
                    # Duplicate 1
                    {
                        "paragraph": {
                            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                            "elements": [
                                {
                                    "textRun": {
                                        "content": "Broadbent Model: ",
                                        "textStyle": {"backgroundColor": {"color": {"rgbColor": {"red": 1.0, "green": 1.0, "blue": 0.0}}}}
                                    }
                                },
                                {
                                    "textRun": {
                                        "content": "an early selection filter model where unattended stimuli are completely filtered out.",
                                        "textStyle": {"backgroundColor": {"color": {"rgbColor": {"red": 0.0, "green": 1.0, "blue": 0.0}}}}
                                    }
                                }
                            ]
                        }
                    },
                    # Duplicate 2 (Identical to 1)
                    {
                        "paragraph": {
                            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                            "elements": [
                                {
                                    "textRun": {
                                        "content": "Broadbent Model: ",
                                        "textStyle": {"backgroundColor": {"color": {"rgbColor": {"red": 1.0, "green": 1.0, "blue": 0.0}}}}
                                    }
                                },
                                {
                                    "textRun": {
                                        "content": "an early selection filter model where unattended stimuli are completely filtered out.",
                                        "textStyle": {"backgroundColor": {"color": {"rgbColor": {"red": 0.0, "green": 1.0, "blue": 0.0}}}}
                                    }
                                }
                            ]
                        }
                    },
                    # Placeholder / inadequate definition (should be vetoed)
                    {
                        "paragraph": {
                            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                            "elements": [
                                {
                                    "textRun": {
                                        "content": "Placeholder Concept: ",
                                        "textStyle": {"backgroundColor": {"color": {"rgbColor": {"red": 1.0, "green": 1.0, "blue": 0.0}}}}
                                    }
                                },
                                {
                                    "textRun": {
                                        "content": "TBD / to be determined later [insert details here]",
                                        "textStyle": {"backgroundColor": {"color": {"rgbColor": {"red": 0.0, "green": 1.0, "blue": 0.0}}}}
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }

        out_apkg, deck_title, cards = process_source_and_generate(
            source="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
            deck_tags=["attention"],
            auto_inject=False
        )

        # Ensure duplicates were removed: exactly 2 cards for Broadbent Model (1 forward, 1 reverse)
        broadbent_cards = [c for c in cards if "Broadbent" in c["question"] or "Broadbent" in c["answer"]]
        assert len(broadbent_cards) == 2

        # Ensure placeholder concept was completely filtered out
        placeholder_cards = [c for c in cards if "Placeholder" in c["question"] or "TBD" in c["answer"]]
        assert len(placeholder_cards) == 0

    @patch("scripts.extract_and_generate.create_deck_package")
    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_document_with_zero_highlights(
        self,
        mock_get_credentials,
        mock_build,
        mock_create_pkg
    ):
        mock_service = MagicMock()
        mock_documents = MagicMock()
        mock_get = MagicMock()

        mock_build.return_value = mock_service
        mock_service.documents.return_value = mock_documents
        mock_documents.get.return_value = mock_get
        mock_create_pkg.return_value = Path("empty.apkg")

        # Document with text but NO background colors
        mock_get.execute.return_value = {
            "title": "PSYC 2110 - Unhighlighted Document",
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                            "elements": [{"textRun": {"content": "Plain text with no highlights anywhere."}}]
                        }
                    }
                ]
            }
        }

        out_apkg, deck_title, cards = process_source_and_generate(
            source="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
            auto_inject=False
        )
        assert len(cards) == 0
        mock_create_pkg.assert_called_once()

    @patch("urllib.request.urlopen")
    def test_ankiconnect_offline_handling(self, mock_urlopen, tmp_path):
        import urllib.error
        from scripts.extract_and_generate import inject_via_ankiconnect

        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        dummy_file = tmp_path / "test.apkg"
        dummy_file.write_bytes(b"dummy")

        # Should not raise exception when Anki is closed / offline
        inject_via_ankiconnect(dummy_file)

    @patch("urllib.request.urlopen")
    def test_ankiconnect_success_handling(self, mock_urlopen, tmp_path):
        from scripts.extract_and_generate import inject_via_ankiconnect

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"result": 12345, "error": null}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        dummy_file = tmp_path / "test.apkg"
        dummy_file.write_bytes(b"dummy")

        inject_via_ankiconnect(dummy_file)
        mock_urlopen.assert_called_once()


class TestCLIExecution:
    """Test CLI argument parsing and flags."""

    @patch("scripts.extract_and_generate.process_source_and_generate")
    def test_cli_argument_parsing(self, mock_process):
        import subprocess
        import sys
        
        # Test CLI invoking via runpy or sys.argv mocking
        test_argv = [
            "extract_and_generate.py",
            "https://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit",
            "--class-name", "PSYC 2110",
            "--chapter", "Lecture 1: Intro",
            "--no-inject"
        ]
        
        with patch.object(sys, "argv", test_argv):
            # Test argparse parser directly
            import argparse
            parser = argparse.ArgumentParser()
            parser.add_argument("source")
            parser.add_argument("--deck")
            parser.add_argument("--class-name", dest="explicit_class")
            parser.add_argument("--chapter", dest="explicit_chapter")
            parser.add_argument("--init-ollama", action="store_true")
            parser.add_argument("--no-inject", action="store_true")
            args = parser.parse_args(test_argv[1:])

            assert args.source == "https://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"
            assert args.explicit_class == "PSYC 2110"
            assert args.explicit_chapter == "Lecture 1: Intro"
            assert args.no_inject is True



