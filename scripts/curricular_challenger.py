"""
scripts/curricular_challenger.py — Automated Curricular Coverage & Syntax Challenger Agent
Audits generated Anki decks against course syllabi, lecture notes, and textbook chapter summaries.
Verifies:
  1. Curricular Coverage: performs gap analysis against core learning objectives and topics.
  2. Syntax & Linguistic Integrity: guarantees clean grammatical phrasing, eliminating dangling
     prepositions, unclosed tags, tautological definitions, and banned generic phrasing.
"""

import sys
import os
import re
import json
import zipfile
import sqlite3
import tempfile
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple, Union

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logger = logging.getLogger(__name__)

# Core Curricular Topics Ontology (Ground-Truth Benchmarks)
CURRICULAR_BENCHMARKS: Dict[str, List[str]] = {
    "PSYC 2110": [
        "Goals of developmental science",
        "Theories of child development",
        "Research methods in developmental psychology",
        "Genetics and epigenetics",
        "Context and culture in development",
        "Developmental niche (Super & Harkness)",
        "Bronfenbrenner's ecological systems theory",
        "Prenatal development and teratogens",
        "Infancy physical and perceptual development",
        "Piaget's stages of cognitive development",
        "Language acquisition and communication",
        "Attachment theory and strange situation",
        "Temperament and emotional regulation",
        "Early childhood cognitive development",
        "Parenting styles and family dynamics",
        "Peer relationships and social development"
    ],
    "PSYC 3590": [
        "Four principles of psychoactive drugs",
        "Pharmacokinetics and ADME processes",
        "Routes of drug administration",
        "Dose-response relationships and therapeutic index",
        "Synaptic transmission and neurotransmitters",
        "Presynaptic and postsynaptic drug mechanisms",
        "Dopaminergic pathways and reward circuitry",
        "Autonomic nervous system divisions",
        "Tolerance, physical dependence, and withdrawal",
        "Neurobiological models of addiction",
        "Stimulants: cocaine and amphetamines",
        "Depressants, sedatives, and alcohol",
        "Opioids and pain modulation",
        "Cannabis and the endocannabinoid system",
        "Psychedelics and hallucinogens",
        "Psychotherapeutic drugs and mental health"
    ]
}

# Linguistic defect patterns
_DANGLING_PREPOSITION = re.compile(
    r'\b(?:of|in|on|at|by|for|with|to|from|and|or|the|a|an)\s*[?.!]?$',
    re.IGNORECASE
)
_LEADING_PUNCTUATION = re.compile(r'^[,\.;:\-]\s*')
_BANNED_GENERIC_PATTERNS = [
    re.compile(r'\bthis\s+concept\b', re.IGNORECASE),
    re.compile(r'\bthis\s+term\b', re.IGNORECASE),
    re.compile(r'\bthis\s+phenomenon\b', re.IGNORECASE),
    re.compile(r'\bwhat\s+is\s+this\s+concept\b', re.IGNORECASE),
    re.compile(r'\bdefine\s+this\s+concept\b', re.IGNORECASE),
]


class CurricularChallenger:
    """
    Automated Challenger Agent auditing deck coverage and syntax against
    course syllabi, textbook summaries, and SuperMemo 20 Rules.
    """

    def __init__(self, course_code: str = "PSYC 2110"):
        self.course_code = course_code.upper().strip()

    def audit_syntax_and_linguistics(self, cards: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Audits cards for grammatical, syntactic, and structural defects.
        Returns defect tally, defect rate, and granular list of defective cards.
        """
        total = len(cards)
        if total == 0:
            return {
                "total_cards": 0,
                "passed_cards": 0,
                "failed_cards": 0,
                "defect_rate": 0.0,
                "is_clean": True,
                "defects": []
            }

        defects: List[Dict[str, Any]] = []

        for idx, card in enumerate(cards):
            q = str(card.get("question") or card.get("front") or "").strip()
            a = str(card.get("answer") or card.get("back") or "").strip()
            kw = str(card.get("keyword") or "").strip()

            # 1. Empty field checks
            if len(q) < 2:
                defects.append({
                    "card_index": idx,
                    "keyword": kw,
                    "rule": "NON_EMPTY_QUESTION",
                    "detail": "Question is missing or too short."
                })
                continue
            if len(a) < 2:
                defects.append({
                    "card_index": idx,
                    "keyword": kw,
                    "rule": "NON_EMPTY_ANSWER",
                    "detail": "Answer is missing or too short."
                })
                continue

            # Strip HTML for plain text linguistic checks
            q_plain = re.sub(r'<[^>]+>', '', q).strip()
            a_plain = re.sub(r'<[^>]+>', '', a).strip()

            # 2. Dangling prepositions or articles at end of question or answer
            if _DANGLING_PREPOSITION.search(q_plain):
                defects.append({
                    "card_index": idx,
                    "keyword": kw,
                    "rule": "DANGLING_PREPOSITION_QUESTION",
                    "detail": f"Question ends with a dangling preposition/article: '{q_plain[-20:]}'"
                })
            if _DANGLING_PREPOSITION.search(a_plain):
                defects.append({
                    "card_index": idx,
                    "keyword": kw,
                    "rule": "DANGLING_PREPOSITION_ANSWER",
                    "detail": f"Answer ends with a dangling preposition/article: '{a_plain[-20:]}'"
                })

            # 3. Leading punctuation in answer
            if _LEADING_PUNCTUATION.search(a_plain):
                defects.append({
                    "card_index": idx,
                    "keyword": kw,
                    "rule": "LEADING_PUNCTUATION_ANSWER",
                    "detail": f"Answer starts with bare punctuation: '{a_plain[:15]}'"
                })

            # 4. Tautology check (Q == A or trivial identity)
            norm_q = re.sub(r'[^a-zA-Z0-9]', '', q_plain.lower())
            norm_a = re.sub(r'[^a-zA-Z0-9]', '', a_plain.lower())
            if norm_q and norm_a and norm_q == norm_a:
                defects.append({
                    "card_index": idx,
                    "keyword": kw,
                    "rule": "TAUTOLOGY",
                    "detail": "Question and answer are identical."
                })

            # 5. Banned generic phrasing ("this concept", etc.)
            for pattern in _BANNED_GENERIC_PATTERNS:
                if pattern.search(q):
                    defects.append({
                        "card_index": idx,
                        "keyword": kw,
                        "rule": "BANNED_GENERIC_PHRASE",
                        "detail": f"Question contains banned generic phrase matching: {pattern.pattern}"
                    })
                    break

            # 6. Unclosed HTML tags (b, i, code)
            for tag in ["b", "i", "code"]:
                open_count = len(re.findall(rf'<{tag}\b[^>]*>', q, re.I))
                close_count = len(re.findall(rf'</{tag}>', q, re.I))
                if open_count != close_count:
                    defects.append({
                        "card_index": idx,
                        "keyword": kw,
                        "rule": "UNCLOSED_HTML_TAG",
                        "detail": f"Mismatched <{tag}> tags in question ({open_count} open, {close_count} close)."
                    })
                    break

        failed_count = len({d["card_index"] for d in defects})
        passed_count = total - failed_count
        defect_rate = failed_count / total if total > 0 else 0.0

        return {
            "total_cards": total,
            "passed_cards": passed_count,
            "failed_cards": failed_count,
            "defect_rate": round(defect_rate, 4),
            "is_clean": (failed_count == 0),
            "defects": defects
        }

    def audit_coverage(
        self,
        cards: List[Dict[str, Any]],
        syllabus_topics: Optional[List[str]] = None,
        textbook_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Performs curricular gap analysis comparing cards against syllabus benchmarks
        and textbook chapter summaries.
        """
        # Assemble target topic benchmarks
        target_topics: List[str] = list(CURRICULAR_BENCHMARKS.get(self.course_code, []))
        if syllabus_topics:
            for s_top in syllabus_topics:
                if s_top not in target_topics:
                    target_topics.append(s_top)

        if textbook_data and "chapters" in textbook_data:
            for ch_num, ch_info in textbook_data["chapters"].items():
                ch_title = ch_info.get("chapter_title") or ch_info.get("title", "")
                if ch_title and ch_title not in target_topics:
                    target_topics.append(ch_title)
                terms = ch_info.get("key_terms", [])
                if isinstance(terms, list):
                    for term in terms:
                        if term and term not in target_topics and len(term) >= 4:
                            target_topics.append(term)
                g_terms = ch_info.get("glossary_terms", {})
                if isinstance(g_terms, dict):
                    for term in g_terms.keys():
                        if term and term not in target_topics and len(term) >= 4:
                            target_topics.append(term)
                elif isinstance(g_terms, list):
                    for term in g_terms:
                        if term and term not in target_topics and len(term) >= 4:
                            target_topics.append(term)

        if not target_topics:
            target_topics = ["General Course Concepts"]

        # Build card searchable text corpus
        card_corpuses = []
        for c in cards:
            kw = str(c.get("keyword") or c.get("front") or "")
            q = str(c.get("question") or "")
            a = str(c.get("answer") or c.get("back") or "")
            tags = " ".join(c.get("tags", []))
            card_corpuses.append(f"{kw} {q} {a} {tags}".lower())

        full_deck_text = " ".join(card_corpuses)

        covered_topics = []
        missing_topics = []

        for topic in target_topics:
            topic_clean = topic.strip().lower()
            topic_core = re.sub(r'\(.*?\)', '', topic_clean).strip()
            # Tokenize into key content words (ignore stop words)
            stop_words = {"and", "or", "the", "of", "in", "vs", "to", "for", "a", "an", "theory", "theories", "stages"}
            tokens = [t for t in re.findall(r'[a-zA-Z0-9]+', topic_core or topic_clean) if t not in stop_words and len(t) >= 3]

            # Topic is covered if full phrase matches, core title matches, or key tokens match
            phrase_match = (topic_clean in full_deck_text) or (bool(topic_core) and topic_core in full_deck_text)
            token_matches = sum(1 for t in tokens if t in full_deck_text)
            matched = phrase_match or (len(tokens) > 0 and token_matches >= max(1, (len(tokens) + 1) // 2))

            if matched:
                covered_topics.append(topic)
            else:
                missing_topics.append(topic)

        coverage_score = len(covered_topics) / len(target_topics) if target_topics else 1.0

        return {
            "course_code": self.course_code,
            "total_curricular_topics": len(target_topics),
            "covered_topics_count": len(covered_topics),
            "missing_topics_count": len(missing_topics),
            "coverage_score": round(coverage_score, 4),
            "covered_topics": covered_topics,
            "missing_topics": missing_topics,
            "status": "PASS" if coverage_score >= 0.85 else "WARN"
        }

    def run_full_audit(
        self,
        cards: List[Dict[str, Any]],
        syllabus_topics: Optional[List[str]] = None,
        textbook_data: Optional[Dict[str, Any]] = None,
        output_report_path: Optional[Union[str, Path]] = None
    ) -> Dict[str, Any]:
        """Runs both syntax and coverage audits and optionally writes a markdown report."""
        syntax_res = self.audit_syntax_and_linguistics(cards)
        coverage_res = self.audit_coverage(cards, syllabus_topics=syllabus_topics, textbook_data=textbook_data)

        overall_status = "PASS"
        if not syntax_res["is_clean"] or coverage_res["coverage_score"] < 0.85:
            overall_status = "WARN" if coverage_res["coverage_score"] >= 0.70 else "FAIL"

        report = {
            "course_code": self.course_code,
            "overall_status": overall_status,
            "total_cards": len(cards),
            "syntax": syntax_res,
            "coverage": coverage_res,
        }

        if output_report_path:
            p = Path(output_report_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            md_content = self._format_markdown_report(report)
            p.write_text(md_content, encoding="utf-8")
            logger.info("Challenger audit report written to %s", p)

        return report

    def _format_markdown_report(self, report: Dict[str, Any]) -> str:
        s = report["syntax"]
        c = report["coverage"]
        status_badge = "🟢 PASS" if report["overall_status"] == "PASS" else ("🟡 WARN" if report["overall_status"] == "WARN" else "🔴 FAIL")

        lines = [
            f"# Curricular Challenger Audit Report — {report['course_code']}",
            "",
            f"**Overall Status**: {status_badge}",
            f"**Total Flashcards Audited**: {report['total_cards']}",
            "",
            "## 1. Syntax & Linguistic Verification",
            f"- **Passed Cards**: {s['passed_cards']} / {s['total_cards']}",
            f"- **Defect Rate**: {s['defect_rate'] * 100:.1f}%",
            f"- **Clean Syntax Status**: {'100% Clean' if s['is_clean'] else 'Defects Detected'}",
            "",
        ]

        if s["defects"]:
            lines.append("### Detected Syntax Defects:")
            for d in s["defects"][:10]:
                lines.append(f"- **Card #{d['card_index']}** (`{d['keyword']}`): [{d['rule']}] {d['detail']}")
            if len(s["defects"]) > 10:
                lines.append(f"- *...and {len(s['defects']) - 10} more defects.*")
            lines.append("")

        lines.extend([
            "## 2. Curricular Coverage & Syllabus Alignment",
            f"- **Curricular Benchmark Topics**: {c['total_curricular_topics']}",
            f"- **Covered Topics**: {c['covered_topics_count']}",
            f"- **Missing Topics**: {c['missing_topics_count']}",
            f"- **Coverage Score**: {c['coverage_score'] * 100:.1f}%",
            "",
        ])

        if c["missing_topics"]:
            lines.append("### Curricular Gaps (Missing Topics):")
            for m in c["missing_topics"]:
                lines.append(f"- {m}")
            lines.append("")

        lines.extend([
            "---",
            "*Report generated by Curricular Challenger Agent (Antigravity Pipeline)*"
        ])

        return "\n".join(lines)

    @staticmethod
    def extract_cards_from_apkg(apkg_path: Union[str, Path]) -> List[Dict[str, Any]]:
        """
        Extracts notes and fields from a compiled Anki .apkg package.
        Returns a list of structured card dicts for syntax and coverage auditing.
        """
        path = Path(apkg_path)
        if not path.exists():
            raise FileNotFoundError(f"Anki package not found: {path}")

        cards: List[Dict[str, Any]] = []
        with zipfile.ZipFile(str(path), "r") as zf:
            if "collection.anki2" not in zf.namelist():
                raise ValueError(f"Invalid Anki package (missing collection.anki2): {path}")

            with tempfile.TemporaryDirectory() as tmp_dir:
                zf.extract("collection.anki2", tmp_dir)
                db_path = Path(tmp_dir) / "collection.anki2"
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("SELECT flds, tags FROM notes")
                rows = cursor.fetchall()
                for flds, tags_str in rows:
                    fields = flds.split("\x1f")
                    q = fields[0] if len(fields) > 0 else ""
                    a = fields[1] if len(fields) > 1 else ""
                    badge = fields[2] if len(fields) > 2 else ""
                    ctx = fields[3] if len(fields) > 3 else ""
                    tags = tags_str.strip().split() if tags_str else []

                    # Extract keyword from <b> tag or question stem
                    kw = ""
                    m = re.search(r'<b>(.*?)</b>', q)
                    if m:
                        kw = m.group(1).strip()
                    elif tags:
                        kw = tags[0].replace("_", " ")

                    cards.append({
                        "question": q,
                        "answer": a,
                        "keyword": kw,
                        "category_badge": badge,
                        "context": ctx,
                        "tags": tags,
                        "front": q,
                        "back": a,
                    })
                conn.close()

        return cards

    def audit_apkg(
        self,
        apkg_path: Union[str, Path],
        syllabus_topics: Optional[List[str]] = None,
        textbook_data: Optional[Dict[str, Any]] = None,
        output_report_path: Optional[Union[str, Path]] = None
    ) -> Dict[str, Any]:
        """Loads cards directly from .apkg file and runs a full audit."""
        cards = self.extract_cards_from_apkg(apkg_path)
        report = self.run_full_audit(
            cards=cards,
            syllabus_topics=syllabus_topics,
            textbook_data=textbook_data,
            output_report_path=output_report_path
        )
        report["deck_path"] = str(apkg_path)
        return report

# Standalone helper
extract_cards_from_apkg = CurricularChallenger.extract_cards_from_apkg


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Audit Anki decks for curricular coverage and syntax integrity"
    )
    parser.add_argument("--deck", "-d", help="Path to compiled .apkg deck to audit")
    parser.add_argument("--course", "-c", default="PSYC 2110", help="Course code (e.g. 'PSYC 2110', 'PSYC 3590')")
    parser.add_argument("--all", action="store_true", help="Audit all compiled decks in Decks/ directory")
    parser.add_argument("--report", "-r", help="Path to write markdown audit report")
    parser.add_argument("--json", action="store_true", help="Output audit report as JSON")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    decks_dir = project_root / "Decks"

    if args.all:
        results = []
        for apkg in sorted(decks_dir.glob("*.apkg")):
            c_code = "PSYC 2110" if "2110" in apkg.name else ("PSYC 3590" if "3590" in apkg.name else args.course)
            challenger = CurricularChallenger(c_code)
            try:
                cards = challenger.extract_cards_from_apkg(apkg)
                if not cards:
                    continue
                rep = challenger.run_full_audit(cards)
                rep["deck_name"] = apkg.name
                results.append(rep)
                print(f"[{rep['overall_status']}] {apkg.name} ({rep['total_cards']} cards) - Coverage: {rep['coverage']['coverage_score']*100:.1f}%, Syntax Clean: {rep['syntax']['is_clean']}")
            except Exception as e:
                print(f"[ERROR] {apkg.name}: {e}")
        if args.json:
            print(json.dumps(results, indent=2))
        return

    if not args.deck:
        parser.error("Must specify --deck <path> or --all")

    challenger = CurricularChallenger(args.course)
    report = challenger.audit_apkg(args.deck, output_report_path=args.report)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(challenger._format_markdown_report(report))


if __name__ == "__main__":
    main()
