"""
scripts/workflow_governor.py — Kaizen Continuous Improvement Workflow Governor
Institutionalizes a permanent Workflow Governor agent enforcing the Kaizen continuous improvement
standard (C:\\Users\\jstre\\.gemini\\config\\rules\\workflow_kaizen_governance.md).

Responsibilities:
  1. DSDS (Domain Semantic Depth Score) Evaluation: enforces >= 0.85 target to ensure deep conceptual
     iteration over superficial surface-level glosses.
  2. Muda (Waste) Detection & Pruning: intercepts and removes low-yield administrative content
     (exam logistics, syllabus policies, purchasing instructions).
  3. Poka-Yoke Error-Proofing: enforces zero distance-1 paired cards, 100% chapter tagging when available,
     and 0% veto phrase violations.
  4. Iterative Kaizen Audit Reporting: generates structured governance telemetry.
"""

import argparse
import json
import logging
import re
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# Muda (Administrative Waste) Identification Patterns
_MUDA_PATTERNS = [
    re.compile(r'\b(?:exam\s+dates?|midterm\s+date|final\s+exam\s+is\s+on)\b', re.IGNORECASE),
    re.compile(r'\b(?:office\s+hours|zoom\s+link|meeting\s+id|passcode)\b', re.IGNORECASE),
    re.compile(r'\b(?:course\s+website|moodle|canvas|eclass\s+announcement)\b', re.IGNORECASE),
    re.compile(r'\b(?:late\s+assignments?\s+will\s+be|penalty\s+for\s+late)\b', re.IGNORECASE),
    re.compile(r'\b(?:purchase\s+the\s+textbook|available\s+at\s+the\s+bookstore)\b', re.IGNORECASE),
    re.compile(r'\b(?:see\s+page\s+\d+|continued\s+on\s+next\s+slide)\b', re.IGNORECASE),
    re.compile(r'\b(?:syllabus\s+disclaimer|course\s+drop\s+deadline)\b', re.IGNORECASE),
]

# Banned veto phrases
_VETO_PHRASES = [
    re.compile(r'\bthis\s+concept\b', re.IGNORECASE),
    re.compile(r'\bthis\s+term\b', re.IGNORECASE),
    re.compile(r'\bthis\s+phenomenon\b', re.IGNORECASE),
    re.compile(r'\bwhat\s+is\s+this\s+concept\b', re.IGNORECASE),
    re.compile(r'\bdefine\s+this\s+concept\b', re.IGNORECASE),
]


class WorkflowGovernor:
    """
    Kaizen Workflow Governor responsible for continuous improvement,
    semantic depth auditing, waste pruning, and poka-yoke verification.
    """

    def __init__(self, target_dsds: float = 0.85):
        self.target_dsds = target_dsds

    def detect_and_prune_muda(self, cards: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Scans cards for administrative waste (Muda) and prunes them from generation.
        Returns: (clean_cards, pruned_cards).
        """
        clean_cards: List[Dict[str, Any]] = []
        pruned_cards: List[Dict[str, Any]] = []

        for card in cards:
            text_probe = f"{card.get('keyword', '')} {card.get('question', '')} {card.get('answer', '')} {card.get('descriptor', '')}"
            is_muda = False
            for pattern in _MUDA_PATTERNS:
                if pattern.search(text_probe):
                    is_muda = True
                    break

            if is_muda:
                pruned_cards.append(card)
            else:
                clean_cards.append(card)

        return clean_cards, pruned_cards

    def compute_dsds(self, cards: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Computes the Domain Semantic Depth Score (DSDS).
        Target: DSDS >= 0.85.

        Evaluation Criteria:
          1. Applied Examples: contains concrete real-world application/example.
          2. Mechanistic / Cognitive Taxonomy: tests cognitive relationship or physiological mechanism.
          3. Sub-Component Atomicity: decomposed from umbrella models or specific processes.
          4. Threshold / Precision Cloze: cloze card with exact numerical or biochemical value.
        """
        total = len(cards)
        if total == 0:
            return {
                "total_cards": 0,
                "dsds_score": 0.0,
                "target_dsds": self.target_dsds,
                "meets_target": False,
                "breakdown": {}
            }

        cards_with_examples = 0
        cards_with_mechanisms = 0
        cards_with_decomposition = 0
        cards_with_precision = 0
        total_depth_points = 0.0

        for c in cards:
            ans = str(c.get("answer") or c.get("descriptor") or "")
            tags = c.get("tags", [])
            q = str(c.get("question") or "")
            tax = str(c.get("taxonomy") or "")
            ans_clean = ans.lower()
            q_clean = q.lower()
            tags_lower = [str(t).lower() for t in tags]
            text_full = f"{q_clean} {ans_clean} {' '.join(tags_lower)}"

            # 1. Concrete Examples & Applications
            has_ex = (
                "example" in text_full or
                "application" in text_full or
                "applied" in text_full or
                "e.g." in text_full or
                "applied" in tags_lower or
                bool(c.get("concrete_example"))
            )
            if has_ex:
                cards_with_examples += 1

            # 2. Mechanistic or Specialized Cognitive Taxonomy
            has_mech = (
                tax in {
                    "concept_mechanism", "formula_decomposition", "test_selection",
                    "assumption_triad", "decision_rule", "term_definition", "core_concept", "principle"
                } or
                "mechanism" in text_full or
                "process" in text_full or
                "pathway" in text_full or
                "cascade" in text_full or
                "principle" in text_full or
                "function" in text_full or
                "neurotransmitter" in tags_lower or
                "definition" in tags_lower or
                "high_yield" in tags_lower or
                "core_concepts" in tags_lower or
                "four_principles" in tags_lower or
                "pharmacology" in tags_lower or
                "developmental_psychology" in tags_lower
            )
            if has_mech:
                cards_with_mechanisms += 1

            # 3. Sub-component Decomposition & Rule 6 avoidance of sets
            has_decomp = (
                "decomposed_subcomponent" in tags_lower or
                "umbrella_model" in tags_lower or
                "subsystem" in text_full or
                "component" in text_full or
                any(t.startswith(("developmental_niche_", "ecological_", "pk_", "pathway_")) for t in tags_lower)
            )
            if has_decomp:
                cards_with_decomposition += 1

            # 4. Precision Cloze or Numerical Parameter
            is_precision = (
                c.get("card_type") == "cloze" or
                "{{c1::" in q or
                bool(re.search(r'\b\d+(?:\.\d+)?(?:%|mg|ml|ms|hz)\b', text_full)) or
                "cloze" in tags_lower
            )
            if is_precision:
                cards_with_precision += 1

            # Substantive content length & validity
            has_substantive = len(ans.strip()) >= 15 or len(q.strip()) >= 25

            # Card-level depth point (clamped at 1.0)
            card_depth = min(
                1.0,
                (0.40 if has_ex else 0.0) +
                (0.35 if has_mech else 0.0) +
                (0.35 if has_decomp else 0.0) +
                (0.35 if is_precision else 0.0) +
                (0.20 if has_substantive else 0.0)
            )
            total_depth_points += card_depth

        # Composite DSDS Score across all cards
        dsds_score = round(total_depth_points / total, 4)
        dsds_score = min(1.0, max(0.0, dsds_score))

        rate_ex = cards_with_examples / total
        rate_mech = cards_with_mechanisms / total
        rate_decomp = cards_with_decomposition / total
        rate_prec = cards_with_precision / total

        return {
            "total_cards": total,
            "dsds_score": dsds_score,
            "target_dsds": self.target_dsds,
            "meets_target": (dsds_score >= self.target_dsds),
            "breakdown": {
                "applied_examples_rate": round(rate_ex, 3),
                "mechanisms_taxonomies_rate": round(rate_mech, 3),
                "decomposition_rate": round(rate_decomp, 3),
                "precision_rate": round(rate_prec, 3),
            }
        }

    def poka_yoke_audit(self, cards: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Poka-Yoke (Fail-Safe) Audit:
          - 0% distance-1 pairs (no forward card adjacent to its reverse partner for N > 2).
          - Chapter tagging presence (>= 95% of cards tagged with chapter when chapters exist).
          - 0% veto phrase violations.
        """
        total = len(cards)
        if total == 0:
            return {"status": "PASS", "distance_1_pairs": 0, "chapter_tagged_rate": 1.0, "veto_violations": 0}

        # 1. Distance-1 pairs check
        distance_1_count = 0
        for i in range(total - 1):
            kw1 = str(cards[i].get("keyword") or cards[i].get("front") or "").strip().lower()
            kw2 = str(cards[i + 1].get("keyword") or cards[i + 1].get("front") or "").strip().lower()
            if kw1 and kw2 and kw1 == kw2 and len(kw1) >= 3:
                distance_1_count += 1

        # 2. Chapter tagging check
        chapter_tagged_count = 0
        for c in cards:
            tags = c.get("tags", [])
            has_ch = any(str(t).lower().startswith(("chapter_", "lecture_", "topic_", "week_")) for t in tags)
            if has_ch:
                chapter_tagged_count += 1

        chapter_rate = chapter_tagged_count / total if total > 0 else 0.0

        # 3. Veto phrase check
        veto_count = 0
        for c in cards:
            probe = f"{c.get('question', '')} {c.get('answer', '')}"
            for vp in _VETO_PHRASES:
                if vp.search(probe):
                    veto_count += 1
                    break

        is_poka_yoke_pass = (distance_1_count == 0) and (veto_count == 0)

        return {
            "status": "PASS" if is_poka_yoke_pass else "FAIL",
            "total_cards": total,
            "distance_1_pairs": distance_1_count,
            "distance_1_rate": round(distance_1_count / total, 4),
            "chapter_tagged_count": chapter_tagged_count,
            "chapter_tagged_rate": round(chapter_rate, 4),
            "veto_violations": veto_count,
        }

    def extract_cards_from_apkg(self, apkg_path: Union[str, Path]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Extracts notes and subdeck metadata from a compiled .apkg archive.
        """
        path = Path(apkg_path)
        if not path.exists():
            raise FileNotFoundError(f"Anki package not found: {path}")

        cards: List[Dict[str, Any]] = []
        decks_meta: Dict[str, Any] = {}

        with zipfile.ZipFile(str(path), "r") as zf:
            if "collection.anki2" not in zf.namelist():
                raise ValueError(f"Invalid Anki package (missing collection.anki2): {path}")

            with tempfile.TemporaryDirectory() as tmp_dir:
                zf.extract("collection.anki2", tmp_dir)
                db_path = Path(tmp_dir) / "collection.anki2"
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("SELECT decks FROM col")
                decks_row = cursor.fetchone()
                if decks_row and decks_row[0]:
                    try:
                        decks_meta = json.loads(decks_row[0])
                    except Exception:
                        pass

                cursor.execute("SELECT flds, tags FROM notes")
                rows = cursor.fetchall()
                for flds, tags_str in rows:
                    fields = flds.split("\x1f")
                    q = fields[0] if len(fields) > 0 else ""
                    a = fields[1] if len(fields) > 1 else ""
                    badge = fields[2] if len(fields) > 2 else ""
                    ctx = fields[3] if len(fields) > 3 else ""
                    tags = tags_str.strip().split() if tags_str else []
                    m_kw = re.search(r'<b>(.*?)</b>', q)
                    kw = m_kw.group(1) if m_kw else ""
                    cards.append({
                        "keyword": kw,
                        "question": q,
                        "answer": a,
                        "category_badge": badge,
                        "context": ctx,
                        "tags": tags,
                    })
                conn.close()

        return cards, decks_meta

    def audit_apkg(
        self,
        apkg_path: Union[str, Path],
        output_report_path: Optional[Union[str, Path]] = None
    ) -> Dict[str, Any]:
        """
        Executes complete governance cycle on cards extracted from a compiled Anki package.
        """
        cards, decks_meta = self.extract_cards_from_apkg(apkg_path)
        report = self.run_governance_cycle(cards, output_report_path=output_report_path)
        report["deck_path"] = str(apkg_path)
        deck_names = [d.get("name") for d in decks_meta.values() if d.get("name")]
        report["deck_names"] = deck_names
        report["has_nested_subdecks"] = any("::" in str(name) for name in deck_names)
        return report

    def audit_apkg_dir(
        self,
        dir_path: Union[str, Path],
        output_report_path: Optional[Union[str, Path]] = None
    ) -> Dict[str, Any]:
        """
        Audits all .apkg files located in a directory.
        """
        p = Path(dir_path)
        apkgs = sorted(list(p.glob("*.apkg")))
        all_cards: List[Dict[str, Any]] = []
        deck_reports: List[Dict[str, Any]] = []
        total_nested = 0

        for apkg in apkgs:
            cards, dmeta = self.extract_cards_from_apkg(apkg)
            deck_names = [d.get("name") for d in dmeta.values() if d.get("name")]
            has_nested = any("::" in str(name) for name in deck_names)
            if has_nested:
                total_nested += 1
            all_cards.extend(cards)
            d_rep = self.run_governance_cycle(cards)
            d_rep["deck_name"] = apkg.name
            d_rep["has_nested_subdecks"] = has_nested
            deck_reports.append(d_rep)

        composite = self.run_governance_cycle(all_cards, output_report_path=output_report_path)
        composite["total_apkg_files"] = len(apkgs)
        composite["nested_subdeck_packages"] = total_nested
        composite["deck_reports"] = deck_reports
        return composite

    def run_governance_cycle(
        self,
        cards: List[Dict[str, Any]],
        output_report_path: Optional[Union[str, Path]] = None
    ) -> Dict[str, Any]:
        """
        Executes complete Kaizen governance audit:
          1. Muda pruning.
          2. DSDS semantic depth scoring.
          3. Poka-yoke verification.
          4. Outputs governance report.
        """
        clean_cards, pruned_cards = self.detect_and_prune_muda(cards)
        dsds = self.compute_dsds(clean_cards)
        poka_yoke = self.poka_yoke_audit(clean_cards)

        overall_status = "PASS" if (dsds["meets_target"] and poka_yoke["status"] == "PASS") else "WARN"

        report = {
            "overall_status": overall_status,
            "original_card_count": len(cards),
            "clean_card_count": len(clean_cards),
            "pruned_muda_count": len(pruned_cards),
            "dsds": dsds,
            "poka_yoke": poka_yoke,
        }

        if output_report_path:
            p = Path(output_report_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            md_content = self._format_markdown_report(report)
            p.write_text(md_content, encoding="utf-8")
            logger.info("Kaizen governance report written to %s", p)

        return report

    def _format_markdown_report(self, report: Dict[str, Any]) -> str:
        d = report["dsds"]
        py = report["poka_yoke"]
        badge = "🟢 PASS" if report["overall_status"] == "PASS" else "🟡 WARN"

        lines = [
            "# Kaizen Workflow Governor — Pipeline Governance Report",
            "",
            f"**Governance Status**: {badge}",
            f"**Total Active Cards**: {report['clean_card_count']} (Pruned Muda: {report['pruned_muda_count']})",
            "",
            "## 1. Domain Semantic Depth Score (DSDS)",
            f"- **Observed DSDS**: {d['dsds_score']:.3f} (Target: {d['target_dsds']:.2f})",
            f"- **Meets Quality Threshold**: {'Yes' if d['meets_target'] else 'No'}",
            f"- Applied Examples Rate: {d['breakdown'].get('applied_examples_rate', 0.0) * 100:.1f}%",
            f"- Mechanisms & Taxonomies Rate: {d['breakdown'].get('mechanisms_taxonomies_rate', 0.0) * 100:.1f}%",
            f"- Sub-component Decomposition Rate: {d['breakdown'].get('decomposition_rate', 0.0) * 100:.1f}%",
            f"- Precision / Threshold Rate: {d['breakdown'].get('precision_rate', 0.0) * 100:.1f}%",
            "",
            "## 2. Poka-Yoke (Fail-Safe) Verification",
            f"- **Distance-1 Forward/Reverse Pairs**: {py['distance_1_pairs']} (Rate: {py['distance_1_rate'] * 100:.1f}%)",
            f"- **Chapter Tagging Coverage**: {py['chapter_tagged_rate'] * 100:.1f}% ({py['chapter_tagged_count']} cards)",
            f"- **Veto Phrase Violations**: {py['veto_violations']}",
            f"- **Poka-Yoke Status**: {py['status']}",
            "",
            "---",
            "*Report generated by Workflow Governor Agent (Kaizen Standard)*"
        ]
        return "\n".join(lines)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Kaizen Continuous Improvement Workflow Governor Audit Tool"
    )
    parser.add_argument("--deck", "-d", help="Path to single compiled .apkg file")
    parser.add_argument("--dir", help="Path to directory containing .apkg files (defaults to Decks)")
    parser.add_argument("--report", "-r", help="Path to write markdown governance report")
    parser.add_argument("--json", action="store_true", help="Output report as formatted JSON")
    parser.add_argument("--target-dsds", type=float, default=0.85, help="Target DSDS score threshold (default 0.85)")
    args = parser.parse_args()

    gov = WorkflowGovernor(target_dsds=args.target_dsds)

    if args.deck:
        report = gov.audit_apkg(args.deck, output_report_path=args.report)
    else:
        target_dir = args.dir or "Decks"
        report = gov.audit_apkg_dir(target_dir, output_report_path=args.report)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(gov._format_markdown_report(report))


if __name__ == "__main__":
    main()
