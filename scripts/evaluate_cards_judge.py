"""
evaluate_cards_judge.py — Agent-as-Judge Evaluation Tool
Evaluates Anki cards against SuperMemo's 20 Rules of Knowledge Formulation and ANKI_SOP.md.
Implements a 30-point evaluation rubric across 6 cognitive dimensions with 4 hard veto checks.
Supports evaluating card collections from JSON files or compiled Anki .apkg packages.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class CardJudgeRubric:
    """
    Agent-as-Judge rubric evaluator enforcing SuperMemo's 20 Rules of Knowledge Formulation
    and ANKI_SOP.md standards on generated Anki cards.
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

    def __init__(self):
        pass

    def evaluate_card(self, card: Dict[str, Any], source_text: str = "") -> Dict[str, Any]:
        """
        Evaluates a single Anki card on a 30-point rubric with 4 hard vetoes.

        Dimensions (0-5 points each):
          D1_Atomicity: Minimum Information Principle (concise answers <= 25 words).
          D2_Wording: Absence of vague prompts, presence of active recall question stems.
          D3_Keyword_Descriptor: ANKI_SOP Keyword-Descriptor bolding or Cloze structure.
          D4_Avoid_Sets: Avoidance of enumerations and set recitations.
          D5_Recall_Recognition: Active Recall vs Recognition directional integrity.
          D6_Context_Anchoring: Context box, category badge, and tagging presence.

        Hard Vetoes (Total score set to 0 immediately):
          1. CRITICAL_FAIL_EMPTY_FIELD: Empty question or answer.
          2. CRITICAL_FAIL_THIS_CONCEPT: Contains banned vague phrases ('this concept').
          3. CRITICAL_FAIL_HEADING_ONLY: Prompt is a raw heading dump.
          4. CRITICAL_FAIL_TAUTOLOGY: Question and answer are identical.
        """
        q = card.get("question", "").strip()
        a = card.get("answer", "").strip()
        badge = card.get("category_badge", "").strip()
        ctx = card.get("context", "").strip()
        tags = card.get("tags", [])

        vetoes: List[str] = []

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
            if len(trailing.split()) <= 8 and not re.search(r'^(What|Which|Why|How|Define|Explain|Identify)\b', trailing, re.IGNORECASE):
                vetoes.append("CRITICAL_FAIL_HEADING_ONLY: Prompt is a raw heading dump without an active recall question.")

        if q.lower() == a.lower() and q != "":
            vetoes.append("CRITICAL_FAIL_TAUTOLOGY: Question and Answer are identical.")

        # 2. Dimension Scoring (0 to 5 each, max 30)
        d_scores: Dict[str, int] = {}

        # D1: Atomicity (SuperMemo Rule 4: Minimum Information Principle)
        word_count = len(a.split())
        if word_count <= 25:
            d_scores["D1_Atomicity"] = 5
        elif word_count <= 40:
            d_scores["D1_Atomicity"] = 3
        else:
            d_scores["D1_Atomicity"] = 1

        # D2: Specificity / Wording (SuperMemo Rule 12: Optimize wording)
        if any(re.search(pat, q, re.IGNORECASE) for pat in self.BANNED_VAGUE_PATTERNS):
            d_scores["D2_Wording"] = 0
        elif re.search(r'^(What|Which|Why|How|Define|Identify|Explain the mechanism|Explain)\b', q, re.IGNORECASE):
            d_scores["D2_Wording"] = 5
        elif "{{c1::" in q:
            d_scores["D2_Wording"] = 5
        elif "<br>" in q:
            d_scores["D2_Wording"] = 4
        else:
            d_scores["D2_Wording"] = 3

        # D3: Keyword-Descriptor Structure (ANKI_SOP.md Section 1.5)
        has_bold_kw = bool(re.search(r'<b>([^<]+)</b>', q))
        if has_bold_kw:
            kw_match = re.search(r'<b>([^<]+)</b>', q).group(1).strip()
            kw_words = len(kw_match.split())
            d_scores["D3_Keyword_Descriptor"] = 5 if 1 <= kw_words <= 5 else 3
        elif "{{c1::" in q or "cloze" in tags:
            d_scores["D3_Keyword_Descriptor"] = 5
        else:
            d_scores["D3_Keyword_Descriptor"] = 2

        # D4: Avoidance of Sets / Enumerations (SuperMemo Rules 9 & 10)
        if any(re.search(pat, q, re.IGNORECASE) for pat in self.SET_ENUMERATION_PATTERNS):
            d_scores["D4_Avoid_Sets"] = 0
        else:
            d_scores["D4_Avoid_Sets"] = 5

        # D5: Active Recall vs Recognition (ANKI_SOP.md Section 1.5 & SuperMemo Rule 17)
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
        """
        Evaluates an entire collection of flashcards and aggregates metrics.
        """
        if not cards:
            return {
                "total_cards": 0,
                "passed_cards": 0,
                "average_score": 0.0,
                "deck_passed": False,
                "veto_count": 0,
                "card_evaluations": [],
            }

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

    def evaluate_apkg(self, apkg_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Extracts notes from an Anki .apkg package and evaluates the deck.
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
                    cards.append({
                        "question": q,
                        "answer": a,
                        "category_badge": badge,
                        "context": ctx,
                        "tags": tags,
                    })
                conn.close()

        return self.evaluate_deck(cards)


# Alias for backward compatibility
SuperMemoCardJudge = CardJudgeRubric


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate Anki flashcards against SuperMemo 20 Rules and ANKI_SOP.md rubric"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", "-i", help="Path to JSON file containing cards array")
    group.add_argument("--deck", "-d", help="Path to compiled Anki .apkg file")
    parser.add_argument("--json", action="store_true", help="Output evaluation report as raw JSON")
    args = parser.parse_args()

    judge = CardJudgeRubric()

    if args.deck:
        report = judge.evaluate_apkg(args.deck)
    else:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
        cards = data if isinstance(data, list) else data.get("cards", [])
        report = judge.evaluate_deck(cards)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("=" * 60)
        print("AGENT-AS-JUDGE EVALUATION REPORT (SuperMemo 20 Rules & ANKI_SOP)")
        print("=" * 60)
        print(f"Total Cards Evaluated: {report['total_cards']}")
        print(f"Cards Passed (>=25/30): {report['passed_cards']}/{report['total_cards']}")
        print(f"Average Card Score:    {report['average_score']:.2f} / 30.0")
        print(f"Hard Veto Violations:  {report['veto_count']}")
        print(f"Deck Verdict:          {'PASSED' if report['deck_passed'] else 'FAILED'}")
        print("=" * 60)

        for i, ev in enumerate(report["card_evaluations"], 1):
            status = "PASS" if ev["passed"] else "FAIL"
            print(f"Card {i:02d}: [{status}] Score: {ev['total_score']}/30")
            if ev["vetoes"]:
                for v in ev["vetoes"]:
                    print(f"       VETO: {v}")
            dim_str = ", ".join(f"{k}: {v}" for k, v in ev["dimension_scores"].items())
            print(f"       Dims: {dim_str}")

    sys.exit(0 if report["deck_passed"] else 1)


if __name__ == "__main__":
    main()
