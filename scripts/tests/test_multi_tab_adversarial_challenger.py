"""
Empirical Adversarial Challenge Test Suite: Multi-Tab Google Docs Ingestion & Cuing Sheets Invariants
======================================================================================================
Adversarially stress-tests scripts/docs_api_client.py:
1. Deeply nested child tabs (3+ levels, 4 levels, 6 levels, branching tree DFS isolation).
2. Empty tabs, empty content lists, empty structural elements (tables, TOCs, paragraphs), whitespace runs.
3. Unhighlighted paragraphs and noise rejection across multiple tabs (zero false positives).
4. Strict heading hierarchy isolation across tabs and sibling child branches (zero leakage).
5. Cuing Sheets (C:\\Users\\jstre\\Projects\\Cuing_Sheets\\gdocs_reader.py) exact schema invariants and live interop.
6. Pathological formatting, table cells, Unicode/emojis/Greek math symbols, and scale stress.
"""

import sys
import copy
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.docs_api_client import (
    extract_document_id,
    extract_google_doc_structured,
    fetch_highlighted_text,
    default_classify_color,
    rgb_to_hex,
)


# ============================================================================
# Adversarial Mock Generators & Helpers
# ============================================================================

def _make_run(text: str, bg_rgb: dict = None) -> dict:
    """Creates a textRun structural element."""
    run = {"content": text}
    if bg_rgb is not None:
        run["textStyle"] = {
            "backgroundColor": {
                "color": {
                    "rgbColor": bg_rgb
                }
            }
        }
    return {"textRun": run}


def _make_paragraph(runs: list, named_style: str = "NORMAL_TEXT") -> dict:
    """Creates a paragraph structural element."""
    return {
        "paragraph": {
            "paragraphStyle": {"namedStyleType": named_style},
            "elements": runs
        }
    }


def _make_table_cell(paragraphs: list) -> dict:
    """Creates a tableCell element containing structural elements."""
    return {"content": paragraphs}


def _make_table(rows_of_cells: list) -> dict:
    """Creates a table structural element."""
    return {
        "table": {
            "tableRows": [
                {
                    "tableCells": [
                        _make_table_cell(cell_paragraphs)
                        for cell_paragraphs in row
                    ]
                }
                for row in rows_of_cells
            ]
        }
    }


def _make_tab(
    tab_id: str,
    title: str,
    body_elements: list = None,
    child_tabs: list = None,
    headers: dict = None,
    footers: dict = None,
    footnotes: dict = None
) -> dict:
    """Builds a complete Google Docs API Tab object."""
    tab = {
        "tabProperties": {
            "tabId": tab_id,
            "title": title
        },
        "documentTab": {
            "body": {
                "content": body_elements or []
            }
        }
    }
    if child_tabs:
        tab["childTabs"] = child_tabs
    if headers:
        tab["documentTab"]["headers"] = headers
    if footers:
        tab["documentTab"]["footers"] = footers
    if footnotes:
        tab["documentTab"]["footnotes"] = footnotes
    return tab


def _mock_docs_service(document_dict: dict):
    """Context manager / patch helper returning a mock Google Docs service."""
    mock_service = MagicMock()
    mock_docs = MagicMock()
    mock_get = MagicMock()
    mock_service.documents.return_value = mock_docs
    mock_docs.get.return_value = mock_get
    mock_get.execute.return_value = document_dict
    return mock_service, mock_get


# Standard RGB test palettes
YELLOW_RGB = {"red": 1.0, "green": 1.0, "blue": 0.0}
GREEN_RGB = {"red": 0.0, "green": 1.0, "blue": 0.0}
CYAN_RGB = {"red": 0.0, "green": 1.0, "blue": 1.0}


# ============================================================================
# 1. Deeply Nested Child Tabs (3+ Levels)
# ============================================================================

class TestDeeplyNestedChildTabs:
    """Adversarially tests multi-tab traversal through deep trees and complex branching."""

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_three_level_nested_child_tabs(self, mock_get_creds, mock_build):
        """Verifies 3-level hierarchy: Course -> Unit -> Section."""
        leaf_tab = _make_tab(
            "t.leaf", "Section 1.1: Foundations",
            body_elements=[
                _make_paragraph([_make_run("Core Concept\n")], named_style="HEADING_1"),
                _make_paragraph([
                    _make_run("Concept X: ", bg_rgb=YELLOW_RGB),
                    _make_run("Autonomous mechanism.", bg_rgb=GREEN_RGB),
                ])
            ]
        )
        mid_tab = _make_tab(
            "t.mid", "Unit 1: Cognitive Systems",
            body_elements=[],
            child_tabs=[leaf_tab]
        )
        root_tab = _make_tab(
            "t.root", "PSYC 2110 Developmental Psychology",
            body_elements=[],
            child_tabs=[mid_tab]
        )

        doc = {"title": "3-Level Course Doc", "tabs": [root_tab]}
        service, mock_get = _mock_docs_service(doc)
        mock_build.return_value = service

        data, title = extract_google_doc_structured("doc_3_levels")
        assert title == "3-Level Course Doc"
        assert len(data) == 1

        item = data[0]
        # Hierarchy must include all 3 tab levels PLUS the heading inside the leaf
        expected_hierarchy = [
            "PSYC 2110 Developmental Psychology",
            "Unit 1: Cognitive Systems",
            "Section 1.1: Foundations",
            "Core Concept"
        ]
        assert item["heading_hierarchy"] == expected_hierarchy
        assert item["heading"] == "Core Concept"
        assert "Concept X" in item["full_paragraph"]

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_six_level_extreme_deep_recursion(self, mock_get_creds, mock_build):
        """Stress-tests 6 levels of deeply nested tabs."""
        current_tab = _make_tab(
            "t.lvl6", "Level 6: Micro-Process",
            body_elements=[
                _make_paragraph([_make_run("Synaptic Plasticity\n")], named_style="HEADING_2"),
                _make_paragraph([
                    _make_run("LTP: ", bg_rgb=YELLOW_RGB),
                    _make_run("Long-term potentiation of synapses.", bg_rgb=GREEN_RGB)
                ])
            ]
        )
        # Wrap from 5 down to 1
        for i in range(5, 0, -1):
            current_tab = _make_tab(f"t.lvl{i}", f"Level {i}: Container", child_tabs=[current_tab])

        doc = {"title": "Extreme 6-Level Doc", "tabs": [current_tab]}
        service, _ = _mock_docs_service(doc)
        mock_build.return_value = service

        data, _ = extract_google_doc_structured("doc_6_levels")
        assert len(data) == 1
        expected_hierarchy = [
            "Level 1: Container",
            "Level 2: Container",
            "Level 3: Container",
            "Level 4: Container",
            "Level 5: Container",
            "Level 6: Micro-Process",
            "Synaptic Plasticity"
        ]
        assert data[0]["heading_hierarchy"] == expected_hierarchy
        assert data[0]["heading"] == "Synaptic Plasticity"

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_complex_branching_tree_branch_isolation(self, mock_get_creds, mock_build):
        """Verifies multi-branch tree: Root with 2 units, each with 2 sections.
        Ensures siblings do not cross-contaminate their tab paths.
        """
        # Unit A
        uA_s1 = _make_tab("t.uA_s1", "Section A1", body_elements=[
            _make_paragraph([
                _make_run("A1 Term: ", bg_rgb=YELLOW_RGB),
                _make_run("A1 Def.", bg_rgb=GREEN_RGB)
            ])
        ])
        uA_s2 = _make_tab("t.uA_s2", "Section A2", body_elements=[
            _make_paragraph([
                _make_run("A2 Term: ", bg_rgb=YELLOW_RGB),
                _make_run("A2 Def.", bg_rgb=GREEN_RGB)
            ])
        ])
        unit_A = _make_tab("t.uA", "Unit A", child_tabs=[uA_s1, uA_s2])

        # Unit B
        uB_s1 = _make_tab("t.uB_s1", "Section B1", body_elements=[
            _make_paragraph([
                _make_run("B1 Term: ", bg_rgb=YELLOW_RGB),
                _make_run("B1 Def.", bg_rgb=GREEN_RGB)
            ])
        ])
        uB_s2 = _make_tab("t.uB_s2", "Section B2", body_elements=[
            _make_paragraph([
                _make_run("B2 Term: ", bg_rgb=YELLOW_RGB),
                _make_run("B2 Def.", bg_rgb=GREEN_RGB)
            ])
        ])
        unit_B = _make_tab("t.uB", "Unit B", child_tabs=[uB_s1, uB_s2])

        root = _make_tab("t.root", "Course Root", child_tabs=[unit_A, unit_B])

        doc = {"title": "Branching Tree Doc", "tabs": [root]}
        service, _ = _mock_docs_service(doc)
        mock_build.return_value = service

        data, _ = extract_google_doc_structured("doc_tree")
        assert len(data) == 4

        assert data[0]["heading_hierarchy"] == ["Course Root", "Unit A", "Section A1"]
        assert data[1]["heading_hierarchy"] == ["Course Root", "Unit A", "Section A2"]
        assert data[2]["heading_hierarchy"] == ["Course Root", "Unit B", "Section B1"]
        assert data[3]["heading_hierarchy"] == ["Course Root", "Unit B", "Section B2"]

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_nested_child_tabs_fetch_highlighted_text(self, mock_get_creds, mock_build):
        """Verifies fetch_highlighted_text extracts highlights across all depths and sections."""
        leaf = _make_tab("t.leaf", "Leaf", body_elements=[
            _make_paragraph([_make_run("Leaf Highlight", bg_rgb=GREEN_RGB)])
        ], footnotes={
            "fn1": {"content": [_make_paragraph([_make_run("Footnote Highlight", bg_rgb=YELLOW_RGB)])]}
        })
        parent = _make_tab("t.parent", "Parent", body_elements=[
            _make_paragraph([_make_run("Parent Highlight", bg_rgb=YELLOW_RGB)])
        ], headers={
            "h1": {"content": [_make_paragraph([_make_run("Header Highlight", bg_rgb=CYAN_RGB)])]}
        }, child_tabs=[leaf])

        doc = {"title": "Nested Highlights Doc", "tabs": [parent]}
        service, _ = _mock_docs_service(doc)
        mock_build.return_value = service

        highlights = fetch_highlighted_text("doc_nested_highlights")
        assert len(highlights) == 4
        texts = [h["text"] for h in highlights]
        assert "Parent Highlight" in texts
        assert "Header Highlight" in texts
        assert "Leaf Highlight" in texts
        assert "Footnote Highlight" in texts


# ============================================================================
# 2. Empty Tabs and Pathological Empty Structures
# ============================================================================

class TestEmptyTabsAndPathologicalStructures:
    """Stress-tests empty tabs, missing content keys, empty structural elements."""

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_completely_empty_document_with_empty_tabs_list(self, mock_get_creds, mock_build):
        """Empty tabs list and empty body content."""
        doc = {"title": "Blank Doc", "tabs": [], "body": {"content": []}}
        service, _ = _mock_docs_service(doc)
        mock_build.return_value = service

        data, title = extract_google_doc_structured("blank_doc")
        assert title == "Blank Doc"
        assert data == []

        highlights = fetch_highlighted_text("blank_doc")
        assert highlights == []

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_tabs_with_missing_document_tab_or_empty_body(self, mock_get_creds, mock_build):
        """Tabs where documentTab is {} or body is {} or content is []."""
        tab1 = {"tabProperties": {"title": "No DocumentTab"}}
        tab2 = {"tabProperties": {"title": "No Body"}, "documentTab": {}}
        tab3 = {"tabProperties": {"title": "Empty Body Content"}, "documentTab": {"body": {"content": []}}}
        tab4 = _make_tab("t.real", "Real Tab", body_elements=[
            _make_paragraph([
                _make_run("Real Item: ", bg_rgb=YELLOW_RGB),
                _make_run("Real content.", bg_rgb=GREEN_RGB)
            ])
        ])

        doc = {"title": "Empty Structures Doc", "tabs": [tab1, tab2, tab3, tab4]}
        service, _ = _mock_docs_service(doc)
        mock_build.return_value = service

        data, title = extract_google_doc_structured("empty_struct_doc")
        assert len(data) == 1
        assert data[0]["heading_hierarchy"] == ["Real Tab"]
        assert "Real Item" in data[0]["full_paragraph"]

        highlights = fetch_highlighted_text("empty_struct_doc")
        assert len(highlights) == 2
        assert highlights[0]["text"] == "Real Item:"
        assert highlights[1]["text"] == "Real content."

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_tabs_with_empty_tables_empty_tocs_and_empty_paragraphs(self, mock_get_creds, mock_build):
        """Tabs containing structural elements that are completely empty."""
        empty_table = _make_table([[]])
        table_with_empty_cell = _make_table([[[]]])
        empty_toc = {"tableOfContents": {"content": []}}
        empty_p = {"paragraph": {"paragraphStyle": {"namedStyleType": "NORMAL_TEXT"}, "elements": []}}
        whitespace_p = _make_paragraph([_make_run("   \n\t  ")])
        
        tab_junk = _make_tab("t.junk", "Junk Tab", body_elements=[
            empty_table,
            table_with_empty_cell,
            empty_toc,
            empty_p,
            whitespace_p
        ])
        tab_valid = _make_tab("t.valid", "Valid Tab", body_elements=[
            _make_paragraph([
                _make_run("Valid Highlight: ", bg_rgb=YELLOW_RGB),
                _make_run("Valid Definition.", bg_rgb=GREEN_RGB)
            ])
        ])

        doc = {"title": "Empty Elements Doc", "tabs": [tab_junk, tab_valid]}
        service, _ = _mock_docs_service(doc)
        mock_build.return_value = service

        data, _ = extract_google_doc_structured("junk_doc")
        assert len(data) == 1
        assert data[0]["heading_hierarchy"] == ["Valid Tab"]

        highlights = fetch_highlighted_text("junk_doc")
        assert len(highlights) == 2

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_whitespace_only_tab_titles_handled_safely(self, mock_get_creds, mock_build):
        """Tab title has only whitespace or is empty."""
        tab_no_title = _make_tab("t.blank_title", "   ", body_elements=[
            _make_paragraph([_make_run("Topic Heading\n")], named_style="HEADING_1"),
            _make_paragraph([
                _make_run("Key: ", bg_rgb=YELLOW_RGB),
                _make_run("Val.", bg_rgb=GREEN_RGB)
            ])
        ])

        doc = {"title": "Blank Tab Title Doc", "tabs": [tab_no_title]}
        service, _ = _mock_docs_service(doc)
        mock_build.return_value = service

        data, _ = extract_google_doc_structured("blank_title_doc")
        assert len(data) == 1
        # Blank tab title is stripped and skipped from tab_path, heading stack picks up HEADING_1
        assert data[0]["heading_hierarchy"] == ["Topic Heading"]
        assert data[0]["heading"] == "Topic Heading"


# ============================================================================
# 3. Unhighlighted Paragraphs and Noise Rejection
# ============================================================================

class TestUnhighlightedParagraphsAndNoiseRejection:
    """Tests that unhighlighted paragraphs across multiple tabs produce 0 false cards."""

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_unhighlighted_dense_text_across_tabs_zero_false_positives(self, mock_get_creds, mock_build):
        """Multiple tabs filled with unhighlighted lecture text, syllabus text, and notes."""
        tab1_paras = [
            _make_paragraph([_make_run("Course Syllabus & Policies\n")], named_style="HEADING_1"),
            _make_paragraph([_make_run("Late submissions will be penalized by 5% per day. Please attend office hours.")]),
            _make_paragraph([_make_run("Instructor: Dr. Smith. Email: dsmith@university.edu.")]),
            _make_paragraph([_make_run("Required textbook: Tamis-LeMonda 2021.")]),
        ]
        tab1 = _make_tab("t.1", "Syllabus Tab", body_elements=tab1_paras)

        tab2_paras = [
            _make_paragraph([_make_run("Chapter 1 Reading Notes\n")], named_style="HEADING_1"),
            _make_paragraph([_make_run("Developmental science has changed over the last century.")]),
            _make_paragraph([_make_run("Methods include longitudinal and cross-sectional designs.")]),
            _make_paragraph([_make_run("Researchers must ensure ethical standards are met.")]),
            # Exactly one highlighted concept in Tab 2
            _make_paragraph([
                _make_run("Cohort Effect: ", bg_rgb=YELLOW_RGB),
                _make_run("Differences between groups attributable to shared historical experiences.", bg_rgb=GREEN_RGB)
            ]),
            _make_paragraph([_make_run("More unhighlighted discussion on cohorts and attrition.")]),
        ]
        tab2 = _make_tab("t.2", "Chapter 1 Notes", body_elements=tab2_paras)

        tab3_paras = [
            _make_paragraph([_make_run("References and Index\n")], named_style="HEADING_1"),
            _make_paragraph([_make_run("Index of key names: Bowlby, Piaget, Vygotsky.")]),
            _make_paragraph([_make_run("All citations conform to APA 7th edition.")]),
        ]
        tab3 = _make_tab("t.3", "References Tab", body_elements=tab3_paras)

        doc = {"title": "Dense Unhighlighted Lecture Notes", "tabs": [tab1, tab2, tab3]}
        service, _ = _mock_docs_service(doc)
        mock_build.return_value = service

        data, title = extract_google_doc_structured("unhighlighted_doc")
        assert len(data) == 1
        item = data[0]
        assert item["heading_hierarchy"] == ["Chapter 1 Notes", "Chapter 1 Reading Notes"]
        assert "Cohort Effect" in item["full_paragraph"]

        highlights = fetch_highlighted_text("unhighlighted_doc")
        assert len(highlights) == 2
        assert highlights[0]["text"] == "Cohort Effect:"
        assert highlights[1]["text"] == "Differences between groups attributable to shared historical experiences."

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_highlighted_punctuation_and_whitespace_discarded(self, mock_get_creds, mock_build):
        """Highlights that contain only punctuation, spaces, or empty strings are discarded."""
        tab = _make_tab("t.punct", "Punctuation Tab", body_elements=[
            _make_paragraph([
                _make_run("    ", bg_rgb=YELLOW_RGB),
                _make_run("... - ; :", bg_rgb=GREEN_RGB),
            ]),
            _make_paragraph([
                _make_run("Valid Term: ", bg_rgb=YELLOW_RGB),
                _make_run("Valid meaning.", bg_rgb=GREEN_RGB),
            ])
        ])

        doc = {"title": "Punctuation Test", "tabs": [tab]}
        service, _ = _mock_docs_service(doc)
        mock_build.return_value = service

        data, _ = extract_google_doc_structured("punct_doc")
        # First paragraph only had whitespace and punctuation highlights, so it must NOT produce an item
        assert len(data) == 1
        assert "Valid Term" in data[0]["full_paragraph"]


# ============================================================================
# 4. Heading Hierarchy Never Leaking Across Tabs
# ============================================================================

class TestHeadingHierarchyIsolationAcrossTabs:
    """Adversarially tests heading stack isolation between tabs and branches."""

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_deep_headings_in_tab1_do_not_bleed_into_tab2(self, mock_get_creds, mock_build):
        """Tab 1 has H1 -> H2 -> H3 -> H4 -> H5. Tab 2 has NO headings."""
        tab1_paras = [
            _make_paragraph([_make_run("H1 Title\n")], named_style="HEADING_1"),
            _make_paragraph([_make_run("H2 Section\n")], named_style="HEADING_2"),
            _make_paragraph([_make_run("H3 Topic\n")], named_style="HEADING_3"),
            _make_paragraph([_make_run("H4 Subtopic\n")], named_style="HEADING_4"),
            _make_paragraph([_make_run("H5 Detail\n")], named_style="HEADING_5"),
            _make_paragraph([
                _make_run("Tab 1 Term: ", bg_rgb=YELLOW_RGB),
                _make_run("Tab 1 Def.", bg_rgb=GREEN_RGB),
            ])
        ]
        tab1 = _make_tab("t.1", "Tab One (Deep)", body_elements=tab1_paras)

        tab2_paras = [
            # No headings whatsoever in Tab 2
            _make_paragraph([_make_run("Plain paragraph without any heading style.")]),
            _make_paragraph([
                _make_run("Tab 2 Term: ", bg_rgb=YELLOW_RGB),
                _make_run("Tab 2 Def.", bg_rgb=GREEN_RGB),
            ])
        ]
        tab2 = _make_tab("t.2", "Tab Two (No Headings)", body_elements=tab2_paras)

        doc = {"title": "Leakage Adversarial Test", "tabs": [tab1, tab2]}
        service, _ = _mock_docs_service(doc)
        mock_build.return_value = service

        data, _ = extract_google_doc_structured("leakage_doc")
        assert len(data) == 2

        # Tab 1 item check
        assert data[0]["heading_hierarchy"] == [
            "Tab One (Deep)", "H1 Title", "H2 Section", "H3 Topic", "H4 Subtopic", "H5 Detail"
        ]
        assert data[0]["heading"] == "H5 Detail"

        # Tab 2 item check: MUST NOT contain any of Tab 1's headings!
        assert data[1]["heading_hierarchy"] == ["Tab Two (No Headings)"]
        assert data[1]["heading"] == "Tab Two (No Headings)"
        for leaked in ["H1 Title", "H2 Section", "H3 Topic", "H4 Subtopic", "H5 Detail"]:
            assert leaked not in data[1]["heading_hierarchy"]

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_tab2_starting_with_h3_does_not_inherit_tab1_h1(self, mock_get_creds, mock_build):
        """Tab 1 ends with H1. Tab 2 starts with H3 without H1/H2."""
        tab1 = _make_tab("t.1", "Tab 1", body_elements=[
            _make_paragraph([_make_run("Tab 1 Major Heading\n")], named_style="HEADING_1"),
            _make_paragraph([_make_run("T1: ", bg_rgb=YELLOW_RGB), _make_run("D1", bg_rgb=GREEN_RGB)])
        ])
        tab2 = _make_tab("t.2", "Tab 2", body_elements=[
            _make_paragraph([_make_run("Isolated Subheading\n")], named_style="HEADING_3"),
            _make_paragraph([_make_run("T2: ", bg_rgb=YELLOW_RGB), _make_run("D2", bg_rgb=GREEN_RGB)])
        ])

        doc = {"title": "H3 Isolation Doc", "tabs": [tab1, tab2]}
        service, _ = _mock_docs_service(doc)
        mock_build.return_value = service

        data, _ = extract_google_doc_structured("h3_iso_doc")
        assert len(data) == 2
        assert data[0]["heading_hierarchy"] == ["Tab 1", "Tab 1 Major Heading"]
        assert data[1]["heading_hierarchy"] == ["Tab 2", "Isolated Subheading"]
        assert "Tab 1 Major Heading" not in data[1]["heading_hierarchy"]

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_sibling_child_tabs_heading_isolation(self, mock_get_creds, mock_build):
        """Sibling tabs under the same parent do not leak headings to each other."""
        child_a = _make_tab("t.cA", "Child A", body_elements=[
            _make_paragraph([_make_run("Child A Heading 1\n")], named_style="HEADING_1"),
            _make_paragraph([_make_run("Child A Heading 2\n")], named_style="HEADING_2"),
            _make_paragraph([_make_run("A Term: ", bg_rgb=YELLOW_RGB), _make_run("A Def", bg_rgb=GREEN_RGB)])
        ])
        child_b = _make_tab("t.cB", "Child B", body_elements=[
            _make_paragraph([_make_run("B Term: ", bg_rgb=YELLOW_RGB), _make_run("B Def", bg_rgb=GREEN_RGB)])
        ])
        parent = _make_tab("t.p", "Parent Tab", child_tabs=[child_a, child_b])

        doc = {"title": "Sibling Isolation Doc", "tabs": [parent]}
        service, _ = _mock_docs_service(doc)
        mock_build.return_value = service

        data, _ = extract_google_doc_structured("sibling_doc")
        assert len(data) == 2
        assert data[0]["heading_hierarchy"] == ["Parent Tab", "Child A", "Child A Heading 1", "Child A Heading 2"]
        # Child B must NOT have Child A Heading 1 or Child A Heading 2
        assert data[1]["heading_hierarchy"] == ["Parent Tab", "Child B"]
        assert data[1]["heading"] == "Child B"


# ============================================================================
# 5. Cuing Sheets Schema Invariants and Interoperability
# ============================================================================

class TestCuingSheetsSchemaInvariantsAndInteroperability:
    """Strictly validates schema invariants required by Cuing Sheets gdocs_reader.py."""

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_strict_dict_schema_invariants_across_multiple_tabs(self, mock_get_creds, mock_build):
        """Every single structured_data item and fetch_highlighted_text item conforms strictly."""
        tab1 = _make_tab("t.1", "Course Module 1", body_elements=[
            _make_paragraph([_make_run("Topic 1: Neuroanatomy\n")], named_style="HEADING_1"),
            _make_paragraph([
                _make_run("Hippocampus: ", bg_rgb=YELLOW_RGB),
                _make_run("Memory consolidation center.", bg_rgb=GREEN_RGB),
            ])
        ])
        tab2 = _make_tab("t.2", "Course Module 2", body_elements=[
            _make_paragraph([_make_run("Topic 2: Neurotransmitters\n")], named_style="HEADING_2"),
            _make_paragraph([
                _make_run("GABA: ", bg_rgb=YELLOW_RGB),
                _make_run("Primary inhibitory neurotransmitter.", bg_rgb=GREEN_RGB),
            ])
        ])

        doc = {"title": "Cuing Sheets Course Notes", "tabs": [tab1, tab2]}
        service, _ = _mock_docs_service(doc)
        mock_build.return_value = service

        structured_data, doc_title = extract_google_doc_structured("cuing_test_doc")

        # 1. Output tuple contract
        assert isinstance(structured_data, list)
        assert isinstance(doc_title, str)
        assert doc_title == "Cuing Sheets Course Notes"
        assert len(structured_data) == 2

        # 2. Strict item schema validation
        expected_root_keys = {"heading", "heading_hierarchy", "full_paragraph", "segments", "highlights"}

        for item in structured_data:
            assert expected_root_keys.issubset(item.keys()), f"Missing keys in {item.keys()}"
            assert isinstance(item["heading"], str)
            assert len(item["heading"]) > 0
            assert isinstance(item["heading_hierarchy"], list)
            assert len(item["heading_hierarchy"]) > 0
            for h in item["heading_hierarchy"]:
                assert isinstance(h, str)

            assert isinstance(item["full_paragraph"], str)
            assert len(item["full_paragraph"]) > 0

            # 3. Segments schema
            assert isinstance(item["segments"], list)
            assert len(item["segments"]) >= 2
            for seg in item["segments"]:
                assert "raw_color" in seg
                assert "category" in seg
                assert "text" in seg
                assert isinstance(seg["text"], str)
                if seg["category"] is not None:
                    assert seg["category"] in {"green", "yellow", "other"}

            # 4. Highlights schema
            assert isinstance(item["highlights"], list)
            assert len(item["highlights"]) >= 2
            for hl in item["highlights"]:
                assert "raw_color" in hl
                assert "category" in hl
                assert "text" in hl
                assert isinstance(hl["text"], str)
                assert hl["category"] in {"green", "yellow", "other"}
                # Category in highlights cannot be None per filter
                assert hl["category"] is not None
                assert len(hl["text"].strip()) > 0

        # 5. Highlights extraction contract
        raw_highlights = fetch_highlighted_text("cuing_test_doc")
        assert isinstance(raw_highlights, list)
        assert len(raw_highlights) == 4
        for hl in raw_highlights:
            assert {"text", "color", "rgb"}.issubset(hl.keys())
            assert isinstance(hl["text"], str)
            assert isinstance(hl["color"], str)
            assert hl["color"].startswith("#")
            assert isinstance(hl["rgb"], dict)
            assert "red" in hl["rgb"] or "green" in hl["rgb"] or "blue" in hl["rgb"]

    def test_live_cuing_sheets_gdocs_reader_integration(self):
        """Simulates actual call into Cuing_Sheets/gdocs_reader.py."""
        cuing_sheets_path = Path(r"C:\Users\jstre\Projects\Cuing_Sheets")
        if not cuing_sheets_path.exists():
            pytest.skip("Cuing_Sheets directory not present")

        verify_script = (
            "import sys\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, r'C:\\Users\\jstre\\Projects\\Cuing_Sheets')\n"
            "import gdocs_reader\n"
            "from unittest.mock import patch, MagicMock\n"
            "assert hasattr(gdocs_reader, 'fetch_course_notes')\n"
            "assert hasattr(gdocs_reader, 'fetch_exam_highlights')\n"
            "with patch('docs_api_client.build') as mock_build, patch('docs_api_client.get_credentials'):\n"
            "    mock_service = MagicMock()\n"
            "    mock_build.return_value = mock_service\n"
            "    mock_service.documents.return_value.get.return_value.execute.return_value = {\n"
            "        'title': 'Test Doc',\n"
            "        'tabs': [{'tabProperties': {'title': 'T1'}, 'documentTab': {'body': {'content': [\n"
            "            {'paragraph': {'paragraphStyle': {'namedStyleType': 'HEADING_1'}, 'elements': [{'textRun': {'content': 'H1\\n'}}]}},\n"
            "            {'paragraph': {'elements': [{'textRun': {'content': 'Term: ', 'textStyle': {'backgroundColor': {'color': {'rgbColor': {'red': 1.0, 'green': 1.0, 'blue': 0.0}}}}}}, {'textRun': {'content': 'Def.', 'textStyle': {'backgroundColor': {'color': {'rgbColor': {'red': 0.0, 'green': 1.0, 'blue': 0.0}}}}}} ]}}\n"
            "        ]}}}]\n"
            "    }\n"
            "    notes, title = gdocs_reader.fetch_course_notes('https://docs.google.com/document/d/123456789012345678901234567890/edit')\n"
            "    assert title == 'Test Doc'\n"
            "    assert len(notes) == 1\n"
            "    assert notes[0]['heading_hierarchy'] == ['T1', 'H1']\n"
            "    hl = gdocs_reader.fetch_exam_highlights('123456789012345678901234567890')\n"
            "    assert len(hl) == 2\n"
            "print('SUCCESS')\n"
        )

        res = subprocess.run([sys.executable, "-c", verify_script], capture_output=True, text=True)
        assert res.returncode == 0, f"Error in Cuing Sheets runtime test: {res.stderr}"
        assert "SUCCESS" in res.stdout


# ============================================================================
# 7. Non-Monotonic Headings, Special Documents & Multi-Category Highlights
# ============================================================================

class TestAdvancedTabEdgeCases:
    """Stress-tests non-monotonic heading jumps, doc titles, and multi-category merging across tabs."""

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_non_monotonic_heading_jumps_within_and_across_tabs(self, mock_get_creds, mock_build):
        """H1 -> H3 -> H2 -> H1 -> H4 -> H2 non-monotonic heading sequence."""
        paras = [
            _make_paragraph([_make_run("H1 Initial\n")], named_style="HEADING_1"),
            _make_paragraph([_make_run("H3 Jumped\n")], named_style="HEADING_3"),
            _make_paragraph([
                _make_run("Item 1: ", bg_rgb=YELLOW_RGB), _make_run("Def 1", bg_rgb=GREEN_RGB)
            ]),
            _make_paragraph([_make_run("H2 Popped H3\n")], named_style="HEADING_2"),
            _make_paragraph([
                _make_run("Item 2: ", bg_rgb=YELLOW_RGB), _make_run("Def 2", bg_rgb=GREEN_RGB)
            ]),
            _make_paragraph([_make_run("H1 New Root\n")], named_style="HEADING_1"),
            _make_paragraph([_make_run("H4 Deep\n")], named_style="HEADING_4"),
            _make_paragraph([
                _make_run("Item 3: ", bg_rgb=YELLOW_RGB), _make_run("Def 3", bg_rgb=GREEN_RGB)
            ]),
            _make_paragraph([_make_run("H2 Popped H4\n")], named_style="HEADING_2"),
            _make_paragraph([
                _make_run("Item 4: ", bg_rgb=YELLOW_RGB), _make_run("Def 4", bg_rgb=GREEN_RGB)
            ]),
        ]
        tab = _make_tab("t.headings", "Non-Monotonic Tab", body_elements=paras)
        doc = {"title": "Heading Dynamics", "tabs": [tab]}
        service, _ = _mock_docs_service(doc)
        mock_build.return_value = service

        data, _ = extract_google_doc_structured("dynamic_headings_doc")
        assert len(data) == 4

        # Item 1 under H1 -> H3
        assert data[0]["heading_hierarchy"] == ["Non-Monotonic Tab", "H1 Initial", "H3 Jumped"]
        assert data[0]["heading"] == "H3 Jumped"

        # Item 2 under H1 -> H2 (H3 correctly popped)
        assert data[1]["heading_hierarchy"] == ["Non-Monotonic Tab", "H1 Initial", "H2 Popped H3"]
        assert data[1]["heading"] == "H2 Popped H3"

        # Item 3 under H1 New Root -> H4
        assert data[2]["heading_hierarchy"] == ["Non-Monotonic Tab", "H1 New Root", "H4 Deep"]
        assert data[2]["heading"] == "H4 Deep"

        # Item 4 under H1 New Root -> H2 Popped H4 (H4 correctly popped)
        assert data[3]["heading_hierarchy"] == ["Non-Monotonic Tab", "H1 New Root", "H2 Popped H4"]
        assert data[3]["heading"] == "H2 Popped H4"

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_title_fallback_from_tab_content_when_metadata_title_missing(self, mock_get_creds, mock_build):
        """When document metadata title is empty, extracts title from TITLE styled paragraph in first tab."""
        tab1 = _make_tab("t.1", "Tab With Title", body_elements=[
            _make_paragraph([_make_run("Dynamic Extracted Title\n")], named_style="TITLE"),
            _make_paragraph([_make_run("H1 Header\n")], named_style="HEADING_1"),
            _make_paragraph([_make_run("Term: ", bg_rgb=YELLOW_RGB), _make_run("Def", bg_rgb=GREEN_RGB)])
        ])
        doc = {"title": "", "tabs": [tab1]}
        service, _ = _mock_docs_service(doc)
        mock_build.return_value = service

        data, title = extract_google_doc_structured("missing_title_doc")
        assert title == "Dynamic Extracted Title"
        assert len(data) == 1
        assert data[0]["heading_hierarchy"] == ["Tab With Title", "Dynamic Extracted Title", "H1 Header"]

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_multi_category_highlights_and_gap_merging_across_tabs(self, mock_get_creds, mock_build):
        """Highlights of same color separated by colon/space gap are merged, while distinct colors are preserved."""
        tab = _make_tab("t.merge", "Merging Tab", body_elements=[
            _make_paragraph([
                # Yellow part 1, colon gap, yellow part 2 -> should merge into one yellow highlight
                _make_run("Dopamine", bg_rgb=YELLOW_RGB),
                _make_run(": "),
                _make_run("Transmitter", bg_rgb=YELLOW_RGB),
                _make_run(" modulates "),
                # Green highlight
                _make_run("reward pathway and motor control.", bg_rgb=GREEN_RGB)
            ])
        ])
        doc = {"title": "Merging Test", "tabs": [tab]}
        service, _ = _mock_docs_service(doc)
        mock_build.return_value = service

        data, _ = extract_google_doc_structured("merge_doc")
        assert len(data) == 1
        item = data[0]
        # Highlights must have merged the yellow span into "Dopamine: Transmitter"
        assert len(item["highlights"]) == 2
        assert item["highlights"][0]["category"] == "yellow"
        assert item["highlights"][0]["text"] == "Dopamine: Transmitter"
        assert item["highlights"][1]["category"] == "green"
        assert item["highlights"][1]["text"] == "reward pathway and motor control."


# ============================================================================
# 6. Pathological Formatting, Tables, and Unicode Resilience
# ============================================================================

class TestPathologicalFormattingAndUnicodeResilience:
    """Stress-tests tables across tabs, Unicode/emojis/Greek math, and adjacent colors."""

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_tables_with_highlighted_cells_in_multiple_tabs(self, mock_get_creds, mock_build):
        """Highlights inside table cells across multiple tabs."""
        table1 = _make_table([
            [
                [_make_paragraph([_make_run("Cell A1: ", bg_rgb=YELLOW_RGB), _make_run("Def A1", bg_rgb=GREEN_RGB)])],
                [_make_paragraph([_make_run("Cell B1 Unhighlighted")])]
            ]
        ])
        tab1 = _make_tab("t.1", "Table Tab 1", body_elements=[table1])

        table2 = _make_table([
            [
                [_make_paragraph([_make_run("Cell A2: ", bg_rgb=YELLOW_RGB), _make_run("Def A2", bg_rgb=GREEN_RGB)])]
            ]
        ])
        tab2 = _make_tab("t.2", "Table Tab 2", body_elements=[table2])

        doc = {"title": "Tables Multi-Tab", "tabs": [tab1, tab2]}
        service, _ = _mock_docs_service(doc)
        mock_build.return_value = service

        data, _ = extract_google_doc_structured("table_doc")
        assert len(data) == 2
        assert data[0]["heading_hierarchy"] == ["Table Tab 1"]
        assert "Cell A1" in data[0]["full_paragraph"]
        assert data[1]["heading_hierarchy"] == ["Table Tab 2"]
        assert "Cell A2" in data[1]["full_paragraph"]

        highlights = fetch_highlighted_text("table_doc")
        assert len(highlights) == 4

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_unicode_emojis_greek_and_math_symbols_across_tabs(self, mock_get_creds, mock_build):
        """Tab titles, headings, and highlights containing emojis, Greek letters, math symbols."""
        tab1 = _make_tab("t.1", "🧬 Molecular Neuroscience 🧠", body_elements=[
            _make_paragraph([_make_run("Section 1: 5-HT2A & GABA_A Receptors (α1β2γ2)\n")], named_style="HEADING_1"),
            _make_paragraph([
                _make_run("Δ⁹-THC: ", bg_rgb=YELLOW_RGB),
                _make_run("Partial agonist at CB₁ (Ki = 10 ± 2 nM) & CB₂ (Ki = 24 ± 4 nM).", bg_rgb=GREEN_RGB)
            ])
        ])
        tab2 = _make_tab("t.2", "📊 Statistical Mechanics (μ ± 1.96σ)", body_elements=[
            _make_paragraph([_make_run("Hypothesis Test (H₀: μ₁ = μ₂ vs H₁: μ₁ ≠ μ₂)\n")], named_style="HEADING_1"),
            _make_paragraph([
                _make_run("p-value threshold (α ≤ 0.05): ", bg_rgb=YELLOW_RGB),
                _make_run("Probability of observing data under H₀.", bg_rgb=GREEN_RGB)
            ])
        ])

        doc = {"title": "Unicode Science Doc", "tabs": [tab1, tab2]}
        service, _ = _mock_docs_service(doc)
        mock_build.return_value = service

        data, _ = extract_google_doc_structured("unicode_doc")
        assert len(data) == 2

        assert data[0]["heading_hierarchy"] == ["🧬 Molecular Neuroscience 🧠", "Section 1: 5-HT2A & GABA_A Receptors (α1β2γ2)"]
        assert "Δ⁹-THC" in data[0]["full_paragraph"]

        assert data[1]["heading_hierarchy"] == ["📊 Statistical Mechanics (μ ± 1.96σ)", "Hypothesis Test (H₀: μ₁ = μ₂ vs H₁: μ₁ ≠ μ₂)"]
        assert "p-value threshold (α ≤ 0.05)" in data[1]["full_paragraph"]

    @patch("scripts.docs_api_client.build")
    @patch("scripts.docs_api_client.get_credentials")
    def test_large_scale_25_tabs_traversal_performance(self, mock_get_creds, mock_build):
        """Simulates a large 25-tab document with alternating empty, populated, and nested tabs."""
        tabs = []
        for i in range(1, 26):
            if i % 5 == 0:
                # Nested child tab
                child = _make_tab(f"t.{i}.sub", f"Module {i} Child", body_elements=[
                    _make_paragraph([_make_run(f"Child {i} Term: ", bg_rgb=YELLOW_RGB), _make_run(f"Child {i} Def", bg_rgb=GREEN_RGB)])
                ])
                tab = _make_tab(f"t.{i}", f"Module {i} Parent", child_tabs=[child])
            elif i % 2 == 0:
                # Populated tab
                tab = _make_tab(f"t.{i}", f"Module {i}", body_elements=[
                    _make_paragraph([_make_run(f"Heading {i}\n")], named_style="HEADING_1"),
                    _make_paragraph([_make_run(f"Term {i}: ", bg_rgb=YELLOW_RGB), _make_run(f"Def {i}", bg_rgb=GREEN_RGB)])
                ])
            else:
                # Empty tab
                tab = _make_tab(f"t.{i}", f"Module {i} Empty", body_elements=[])
            tabs.append(tab)

        doc = {"title": "Massive 25-Tab Doc", "tabs": tabs}
        service, _ = _mock_docs_service(doc)
        mock_build.return_value = service

        data, title = extract_google_doc_structured("massive_doc")
        assert title == "Massive 25-Tab Doc"
        # 12 even tabs (2, 4, 6, 8, 12, 14, 16, 18, 22, 24) + 5 child tabs (5, 10, 15, 20, 25)
        # Note: 10, 20 are divisible by both 5 and 2; line `if i % 5 == 0:` catches them as parent+child.
        # So even tabs not divisible by 5 are: 2, 4, 6, 8, 12, 14, 16, 18, 22, 24 -> 10 tabs.
        # Divisible by 5 child tabs: 5, 10, 15, 20, 25 -> 5 child tabs. Total = 15.
        assert len(data) == 15

        highlights = fetch_highlighted_text("massive_doc")
        assert len(highlights) == 30
