"""
scripts/card_validator.py — Standalone Card Validation, Sanitization & Deduplication Module
Enforces SuperMemo 20 Rules, ANKI_SOP Keyword-Descriptor standards, and legacy defensive guardrails.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import re
import copy
import logging

logger = logging.getLogger(__name__)


class ContentShield:
    """Isolates math blocks ($$, $, \\[, \\() and code blocks (```, `) using unique placeholder tokens."""

    SHIELD_PATTERNS = [
        ("CODE_BLOCK", re.compile(r'```[\w]*\n?[\s\S]*?```', re.DOTALL)),
        ("CODE_HTML", re.compile(r'<pre>[\s\S]*?</pre>|<code>[\s\S]*?</code>', re.IGNORECASE)),
        ("MATH_DISPLAY", re.compile(r'(\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\])', re.DOTALL)),
        ("MATH_ANKI_DISPLAY", re.compile(r'\[\$\$\][\s\S]*?\[/\$\$\]', re.IGNORECASE)),
        ("MATH_ANKI_INLINE", re.compile(r'\[\$\][\s\S]*?\[/\$\]', re.IGNORECASE)),
        ("MATH_INLINE", re.compile(r'(?<!\$)\$(?!\$)(?:\\\$|[^\$\n])+(?<!\$)\$(?!\$)|\\\(.*?\\\)')),
        ("CODE_INLINE", re.compile(r'`[^`\n]+`')),
    ]

    def __init__(self):
        self.registry: Dict[str, str] = {}
        self.counter = 0

    def shield(self, text: str) -> str:
        if not text:
            return ""
        output = text
        for token_prefix, regex in self.SHIELD_PATTERNS:
            def _replacer(match: re.Match) -> str:
                self.counter += 1
                token = f"____SHIELD_{token_prefix}_{self.counter}____"
                self.registry[token] = match.group(0)
                return token
            output = regex.sub(_replacer, output)
        return output

    def unshield(self, text: str) -> str:
        if not text:
            return ""
        output = text
        for token, original in sorted(self.registry.items(), key=lambda x: len(x[0]), reverse=True):
            output = output.replace(token, original)
        return output


def strip_html_tags(text: str) -> str:
    """Removes HTML tags from text without stripping mathematical comparison inequalities (< or >)."""
    if not text:
        return ""
    return re.sub(r'</?[a-zA-Z][a-zA-Z0-9]*(?:\s+[^>]*)?>', '', text)


# =============================================================================
# M9 Failure Modes Elimination Constants
# =============================================================================

_CRITIQUE_VERB_ROOTS = (
    r'rejects?|rejected|rejecting|'
    r'criticizes?|criticized|criticizing|'
    r'contrasts?|contrasted|contrasting|contrast\s+(?:with|to|against|between|that)|'
    r'argues?(?:\s+that)?|argued(?:\s+that)?|arguing(?:\s+that)?|'
    r'challenges?|challenged|challenging|'
    r'disproves?|disproved|disproving|'
    r'refutes?|refuted|refuting|'
    r'suggests?(?:\s+that)?|suggested(?:\s+that)?|suggesting(?:\s+that)?|'
    r'posits?(?:\s+that)?|posited(?:\s+that)?|positing(?:\s+that)?|'
    r'claims?(?:\s+that)?|claimed(?:\s+that)?|claiming(?:\s+that)?|'
    r'opposes?|opposed|opposing|'
    r'disputes?|disputed|disputing|'
    r'questions?(?:\s+whether|\s+that)?|questioned|questioning|'
    r'doubts?(?:\s+that)?|doubted|doubting'
)

_CRITIQUE_VERBS_COMPOUND = (
    rf'(?:{_CRITIQUE_VERB_ROOTS})(?:\s+(?:and|or|\&)\s+(?:{_CRITIQUE_VERB_ROOTS}))*'
)

_AUTHOR_CITATION_PREFIX = (
    r'^(?:[A-Z][a-zA-Z0-9\'\.\-]*(?:\s+(?:et\s+al\.?|and|\&|[A-Z][a-zA-Z0-9\'\.\-]*))*(?:\s*\(\d{4}[a-z]?\))?\s+)?'
)

CRITIQUE_ACTION_REGEX = re.compile(
    rf'{_AUTHOR_CITATION_PREFIX}{_CRITIQUE_VERBS_COMPOUND}\b',
    re.IGNORECASE
)

CRITIQUE_STANDALONE_WORDS = {
    'REJECT', 'REJECTS', 'REJECTED', 'REJECTING',
    'CRITICIZE', 'CRITICIZES', 'CRITICIZED', 'CRITICIZING',
    'CONTRAST', 'CONTRASTS', 'CONTRASTED', 'CONTRASTING',
    'CHALLENGE', 'CHALLENGES', 'CHALLENGED', 'CHALLENGING',
    'DISPROVE', 'DISPROVES', 'DISPROVED', 'DISPROVING',
    'REFUTE', 'REFUTES', 'REFUTED', 'REFUTING'
}

DEFINITIONAL_FRAMING_REGEX = re.compile(
    r'^(?:(?:the|a|an)\s+)?'
    r'(?:(?:[a-zA-Z0-9\'-]+|\band\b|\bor\b)\s+){0,4}'
    r'(?:process\s+(?:in\s+which|where|by\s+which|whereby|of)|'
    r'mechanism\s+(?:that|which|by\s+which|whereby|of)|'
    r'condition\s+(?:where|in\s+which|characterized\s+by)|'
    r'state\s+(?:of|in\s+which|where)|'
    r'movement\s+of|'
    r'formation\s+of|'
    r'capacity\s+(?:to|for)|'
    r'ability\s+to|'
    r'tendency\s+(?:to|for)|'
    r'phenomenon\s+(?:in\s+which|where|characterized\s+by)|'
    r'cascade\s+(?:that|which|by\s+which|of)|'
    r'pathway\s+(?:that|which|by\s+which|whereby|of))\b',
    re.IGNORECASE
)

RELATIVE_CLAUSE_REGEX = re.compile(
    r'\b(?:in\s+which|by\s+which|where\s+by|whereby|characterized\s+by|'
    r'(?:theorists?|people|individuals?|children|patients?)\s+(?:who|that))\b',
    re.IGNORECASE
)

NESTED_QUESTION_PATTERN = re.compile(
    r'What is the (?:definition|clinical significance|key mechanism|primary role|statistical role|key statistical principle|developmental significance|key developmental process|ethical significance|key ethical rule or principle)\s+(?:of|regarding)\s+(?:<b>)?\s*(?:What|Why|How|When|Where|Who|Which|Can|Does|Is|Are|Should)\b',
    re.IGNORECASE
)


@dataclass
class ValidationIssue:
    severity: str  # "ERROR" | "WARNING"
    rule_id: str
    message: str

    @property
    def code(self) -> str:
        return self.rule_id

    def __str__(self) -> str:
        return f"{self.severity}: {self.rule_id} - {self.message}"


@dataclass
class CardValidationResult:
    is_valid: bool
    sanitized_card: Dict[str, Any]
    issues: List[ValidationIssue] = field(default_factory=list)

    def __iter__(self):
        # Supports tuple unpacking: is_valid, issues = validator.validate_card(card)
        return iter((self.is_valid, [str(i) for i in self.issues]))

    def __getitem__(self, item):
        if item == 0:
            return self.is_valid
        elif item == 1:
            return [str(i) for i in self.issues]
        elif item == 2:
            return self.sanitized_card
        raise IndexError("CardValidationResult index out of range")


@dataclass
class DeckValidationSummary:
    total_input_cards: int = 0
    valid_cards_count: int = 0
    rejected_cards_count: int = 0
    duplicates_removed_count: int = 0
    warnings_count: int = 0
    rejection_reasons: Dict[str, int] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        telemetry = {
            "total_input": self.total_input_cards,
            "valid": self.valid_cards_count,
            "rejected": self.rejected_cards_count,
            "duplicates_removed": self.duplicates_removed_count,
            "warnings": self.warnings_count,
        }
        for reason, count in self.rejection_reasons.items():
            telemetry[reason] = count
        return telemetry


class CardSanitizer:
    """Sanitizes raw text and card fields without altering core semantic meaning."""

    @staticmethod
    def strip_css(text: str) -> str:
        """Strips embedded stylesheets, CSS blocks (.card { ... }), and inline priority badges."""
        if not text:
            return ""
        t = text
        # Remove <style>...</style> blocks
        t = re.sub(r'<style[^>]*>.*?</style>', '', t, flags=re.DOTALL | re.IGNORECASE)
        # Remove .card { ... } blocks
        t = re.sub(r'\.card\s*\{[^}]*\}', '', t, flags=re.DOTALL)
        # Remove arbitrary .class { ... } CSS blocks
        t = re.sub(r'\.[a-zA-Z_-]+\s*\{[^}]*\}', '', t, flags=re.DOTALL)
        # Remove priority badge text leakage (HIGH/MEDIUM/LOW Priority)
        t = re.sub(r'\b(?:HIGH|MEDIUM|LOW)\s+Priority\b', '', t, flags=re.IGNORECASE)
        # Remove inline font-family declarations
        t = re.sub(r'font-family\s*:[^;]+;?', '', t, flags=re.IGNORECASE)
        return t

    @staticmethod
    def strip_figure_citations(text: str) -> str:
        """Strips parenthetical figure and table references like (Figure 3.2), (Fig. 1.4)."""
        if not text:
            return ""
        t = text
        # Match parenthetical or bracketed figure / table references
        t = re.sub(
            r'[\(\[]\s*(?:Figure|Fig\.|Table)\s*\d+(?:\.\d+)?[^\]\)]*[\)\]]',
            '',
            t,
            flags=re.IGNORECASE
        )
        # Clean up empty parentheses left behind
        t = re.sub(r'\(\s*\)', '', t)
        t = re.sub(r'\[\s*\]', '', t)
        return t

    @staticmethod
    def strip_index_runs(text: str) -> str:
        """
        Strips stray index page number runs (e.g. ', 59, 71, 377') if preceded
        by substantive text. Leaves standalone index sequences intact so CardValidator
        can catch and report textbook index corruption.
        """
        if not text:
            return ""
        # If the whole text starts with an index sequence (e.g. ", 59, 71"), do not strip
        # so validator can flag CORRUPTED_INDEX_TEXT.
        if re.match(r'^\s*,\s*\d+', text):
            return text

        # Strip trailing comma-separated number runs
        t = re.sub(r',\s*\d+(?:\s*,\s*\d+)+(?:\s*[A-Za-z]+)?(?=\s*[\.\?!]|\s*$)', '', text)
        return t

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Normalizes Windows newlines, tabs, and runs of whitespace."""
        if not text:
            return ""
        t = text.replace('\r\n', '\n').replace('\r', '\n')
        # Replace multiple spaces/tabs with single space (preserve intentional newlines)
        lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in t.split('\n')]
        # Collapse excessive blank lines
        cleaned = '\n'.join(line for line in lines)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()

    @staticmethod
    def normalize_quotes(text: str) -> str:
        """Normalizes curly / smart quotes to standard ASCII quotes."""
        if not text:
            return ""
        t = text
        t = t.replace('“', '"').replace('”', '"')
        t = t.replace('‘', "'").replace('’', "'")
        t = t.replace('`', "'")
        return t

    @staticmethod
    def normalize_punctuation(text: str, is_question: bool = False) -> str:
        """
        Repairs missing or duplicated terminal punctuation.
        Ensures questions end with '?' and declarative answers end with '.', '!', or '?'.
        Does not mutate mathematical formulas or code blocks.
        """
        if not text:
            return ""

        t = text.strip()
        # Clean space preceding punctuation
        t = re.sub(r'\s+([,\.\?!;:])', r'\1', t)
        # Normalize duplicate punctuation: ?., .. etc.
        t = re.sub(r'\?+\.?', '?', t)
        t = re.sub(r'\.+\?', '?', t)
        t = re.sub(r'\.{2,}', '.', t)
        t = re.sub(r'!+\.?', '!', t)

        # Check if text ends with a shielded math or code token
        ends_with_shield = bool(re.search(r'____SHIELD_(?:MATH|CODE)_[A-Z0-9_]+____$', t))

        if is_question:
            # Check if text is an interrogative sentence
            interrogatives = (
                'what', 'which', 'how', 'why', 'where', 'when', 'who', 'whom', 'whose',
                'explain', 'define', 'identify', 'describe', 'name', 'distinguish',
                'compare', 'state', 'list'
            )
            raw_stripped = strip_html_tags(t).strip()
            first_word = raw_stripped.split()[0].lower() if raw_stripped.split() else ""
            clean_first = re.sub(r'[^a-z]', '', first_word)

            if clean_first in interrogatives or '?' in t:
                # If question doesn't end with ?, replace trailing . or append ?
                if t.endswith('.'):
                    t = t[:-1] + '?'
                elif not t.endswith('?'):
                    # Check if ending with period inside HTML tag: e.g. <b>dopamine.</b>
                    if re.search(r'\.\s*(</[^>]+>)$', t):
                        t = re.sub(r'\.\s*(</[^>]+>)$', r'\1?', t)
                    else:
                        t = t + '?'
        else:
            # For answers, ensure terminal punctuation exists only if NOT ending in shielded math/code
            if not ends_with_shield:
                raw_stripped = strip_html_tags(t).strip()
                if raw_stripped and not raw_stripped.endswith(('.', '!', '?')) and not raw_stripped.endswith(('$', '$$', r'\)', r'\]')):
                    t = t + '.'

        return t

    def sanitize_text(self, text: str, is_question: bool = False) -> str:
        """Applies all cleaning operations sequentially to a string, shielding math and code syntax."""
        if not text:
            return ""
        shield = ContentShield()
        shielded = shield.shield(text)
        t = self.strip_css(shielded)
        t = self.strip_figure_citations(t)
        t = self.strip_index_runs(t)
        t = self.normalize_whitespace(t)
        t = self.normalize_quotes(t)
        t = self.normalize_punctuation(t, is_question=is_question)
        unshielded = shield.unshield(t)
        return unshielded.strip()

    def sanitize(self, card: Dict[str, Any]) -> Dict[str, Any]:
        """
        Returns a sanitized copy of a card dictionary.
        Cleans question, answer, front, back, cloze_text, and context fields.
        """
        c = copy.deepcopy(card)

        # Standard Q/A fields
        if "question" in c and c["question"]:
            c["question"] = self.sanitize_text(c["question"], is_question=True)
        if "front" in c and c["front"]:
            c["front"] = self.sanitize_text(c["front"], is_question=True)

        if "answer" in c and c["answer"]:
            c["answer"] = self.sanitize_text(c["answer"], is_question=False)
        if "back" in c and c["back"]:
            c["back"] = self.sanitize_text(c["back"], is_question=False)

        # Cloze text
        if "cloze_text" in c and c["cloze_text"]:
            cloze = c["cloze_text"]
            # Cloze may be question or statement; repair punctuation without forcing question mark
            is_q = bool(re.search(r'^(What|Which|How|Why|Where|When)\b', strip_html_tags(cloze).strip(), re.I))
            c["cloze_text"] = self.sanitize_text(cloze, is_question=is_q)

        # Context and notes
        if "context" in c and c["context"]:
            c["context"] = self.sanitize_text(c["context"], is_question=False)

        # Keyword and Descriptor fields if present
        if "keyword" in c and c["keyword"]:
            c["keyword"] = self.normalize_whitespace(self.normalize_quotes(c["keyword"])).strip()
        if "descriptor" in c and c["descriptor"]:
            c["descriptor"] = self.sanitize_text(c["descriptor"], is_question=False)

        return c


class CardValidator:
    """Evaluates cards against SuperMemo 20 Rules, length bounds, and legacy rejection patterns."""

    BANNED_PLACEHOLDER_PATTERNS = [
        r"review\s+this\s+concept",
        r"content\s+needs\s+verification",
        r"check.*textbook",
        r"review\s+this\s+(?:answer|question)",
        r"^this\s+content",
        r"needs\s+review",
        r"complete\s+information",
        r"answer\s+to\s+be\s+extracted",
        r"requires\s+specific\s+course\s+material\s+review",
        r"check\s+the\s+textbook",
        r"\btbd\b",
        r"to\s+be\s+determined",
        r"\bplaceholder\b",
        r"\[insert\b",
    ]

    BANNED_VAGUE_PATTERNS = [
        r"\bthis\s+concept\b",
        r"\bthis\s+term\b",
        r"\bthis\s+phenomenon\b",
        r"\bwhat\s+is\s+this\s+concept\b",
        r"\bdefine\s+this\s+concept\b",
        r"\bwhat\s+brain\s+structure\s+or\s+concept\s+is\s+being\s+tested\b",
    ]

    CORRUPTED_INDEX_PATTERNS = [
        r",\s*\d+,\s*\d+,\s*\d+",          # Page sequences: ", 59, 71, 377"
        r",\s*\d+\s*[A-Z][a-z]+",          # Index entry: ", 378 Tower"
        r"\d+,\s*\d+\s*[A-Z]",             # Mixed numbers/caps: "42, 45 Brain"
        r"test,\s*\d+",                    # Test index: "test, 142"
        r"^(?:page|chapter|table)\s+\d+$", # Stray pagination markers
    ]

    CORRUPTED_FIGURE_PATTERNS = [
        r"\d+f\s+[A-Za-z]+",               # Figure markers: "250f Toxins"
        r"\bf\s+[A-Z][a-z]+",              # Figure marker: "f Toxins"
    ]

    def __init__(
        self,
        min_front: int = 10,
        max_front: int = 250,
        min_back: int = 5,
        max_back: int = 500,
        min_cloze: int = 15,
        max_cloze: int = 500,
        config: Optional[Dict[str, Any]] = None
    ):
        cfg = config or {}
        cq = cfg.get("card_quality", {})
        self.min_front = cq.get("min_front_length", cfg.get("min_front", min_front))
        self.max_front = cq.get("max_front_length", cfg.get("max_front", max_front))
        self.min_back = cq.get("min_back_length", cfg.get("min_back", min_back))
        self.max_back = cq.get("max_back_length", cfg.get("max_back", max_back))
        self.min_cloze = cfg.get("min_cloze", min_cloze)
        self.max_cloze = cfg.get("max_cloze", max_cloze)
        self.sanitizer = CardSanitizer()

    def validate_card(self, card: Dict[str, Any]) -> CardValidationResult:
        """
        Validates a single card. Card is sanitized first.
        Returns CardValidationResult with is_valid, sanitized_card, and list of issues.
        """
        sanitized = self.sanitizer.sanitize(card)
        issues: List[ValidationIssue] = []

        q = (sanitized.get("question") or sanitized.get("front") or "").strip()
        a = (sanitized.get("answer") or sanitized.get("back") or "").strip()
        card_type = sanitized.get("card_type", "")
        cloze_str = (sanitized.get("cloze_text") or (q if card_type == "cloze" or "{{c1::" in q else "")).strip()

        is_cloze = (card_type == "cloze") or ("{{c1::" in q) or bool(cloze_str)

        # 1. Empty field checks
        if is_cloze:
            if not cloze_str:
                issues.append(ValidationIssue("ERROR", "EMPTY_FIELD", "Cloze text field is empty."))
        else:
            if not q:
                issues.append(ValidationIssue("ERROR", "EMPTY_FIELD", "Question (Front) is empty."))
            if not a:
                issues.append(ValidationIssue("ERROR", "EMPTY_FIELD", "Answer (Back) is empty."))

        # 1b. Empty HTML tag wrapper check (veto ghost cards e.g. <i></i>)
        EMPTY_HTML_TAG_PATTERN = r'<(?:i|b|span|em|strong)>\s*</(?:i|b|span|em|strong)>'
        if not is_cloze:
            if q and re.search(EMPTY_HTML_TAG_PATTERN, q, re.IGNORECASE):
                issues.append(ValidationIssue("ERROR", "EMPTY_HTML_WRAPPER", "Question (Front) contains empty HTML tag wrapper."))
            if a and re.search(EMPTY_HTML_TAG_PATTERN, a, re.IGNORECASE):
                issues.append(ValidationIssue("ERROR", "EMPTY_HTML_WRAPPER", "Answer (Back) contains empty HTML tag wrapper."))
        else:
            if cloze_str and re.search(EMPTY_HTML_TAG_PATTERN, cloze_str, re.IGNORECASE):
                issues.append(ValidationIssue("ERROR", "EMPTY_HTML_WRAPPER", "Cloze text contains empty HTML tag wrapper."))
            if a and re.search(EMPTY_HTML_TAG_PATTERN, a, re.IGNORECASE):
                issues.append(ValidationIssue("ERROR", "EMPTY_HTML_WRAPPER", "Answer (Back) contains empty HTML tag wrapper."))

        # 2. Tautology check
        if not is_cloze and q and a:
            clean_q = strip_html_tags(q).strip().lower()
            clean_a = strip_html_tags(a).strip().lower()
            # Normalize trailing punctuation
            norm_q = re.sub(r'[^a-z0-9]', '', clean_q)
            norm_a = re.sub(r'[^a-z0-9]', '', clean_a)
            if norm_q == norm_a and norm_q:
                issues.append(ValidationIssue("ERROR", "TAUTOLOGY", "Question and Answer are identical/tautological."))
            elif norm_a and len(norm_a) >= 8 and norm_a in norm_q:
                stripped_q = norm_q.replace(norm_a, '')
                prompt_boilerplate = {
                    '', 'regarding', 'whatisthedefinitionof', 'whatistheclinicalsignificanceof',
                    'whatistheprimaryroleof', 'whatisthekeymechanismregarding',
                    'whatisthestatisticalroleorruleof', 'whatisthedevelopmentalsignificanceof',
                    'whatistheethicalsignificanceof', 'whatisthekeystatisticalprincipleof',
                    'whatisthekeydevelopmentalprocessof', 'whatisthekeyethicalruleorprincipleof'
                }
                if stripped_q in prompt_boilerplate or stripped_q.startswith('regarding'):
                    issues.append(ValidationIssue("ERROR", "TAUTOLOGY", "Question and Answer are identical/tautological."))

        # 3. Cloze validation
        if is_cloze and cloze_str:
            clean_cloze = re.sub(r'\{\{c\d+::(.*?)\}\}', r'\1', strip_html_tags(cloze_str)).strip()
            if len(clean_cloze) < self.min_cloze:
                issues.append(ValidationIssue(
                    "ERROR", "CLOZE_TOO_SHORT",
                    f"Cloze text length ({len(clean_cloze)}) is below minimum {self.min_cloze} characters."
                ))
            if len(cloze_str) > self.max_cloze:
                issues.append(ValidationIssue(
                    "ERROR", "CLOZE_TOO_LONG",
                    f"Cloze text length ({len(cloze_str)}) exceeds maximum {self.max_cloze} characters."
                ))

            cloze_tokens = re.findall(r'\{\{c\d+::(.*?)\}\}', cloze_str)
            if not cloze_tokens:
                issues.append(ValidationIssue("ERROR", "CLOZE_MISSING_TOKEN", "Cloze card lacks valid {{c1::...}} deletion token."))
            else:
                for tok in cloze_tokens:
                    # Token can have hint, e.g. target::hint
                    target = tok.split("::")[0].strip()
                    if not target:
                        issues.append(ValidationIssue("ERROR", "CLOZE_EMPTY_DELETION", "Cloze deletion token contains empty target."))

        # 4. Standard Q/A Length Bounds
        if not is_cloze:
            if q:
                clean_q = strip_html_tags(q).strip()
                if len(clean_q) < self.min_front:
                    issues.append(ValidationIssue(
                        "ERROR", "QUESTION_TOO_SHORT",
                        f"Question length ({len(clean_q)}) is below minimum {self.min_front} characters."
                    ))
                if len(q) > self.max_front:
                    issues.append(ValidationIssue(
                        "ERROR", "QUESTION_TOO_LONG",
                        f"Question length ({len(q)}) exceeds maximum {self.max_front} characters."
                    ))
            if a:
                clean_a = strip_html_tags(a).strip()
                if len(clean_a) < self.min_back:
                    issues.append(ValidationIssue(
                        "ERROR", "ANSWER_TOO_SHORT",
                        f"Answer length ({len(clean_a)}) is below minimum {self.min_back} characters."
                    ))
                if len(a) > self.max_back:
                    issues.append(ValidationIssue(
                        "ERROR", "ANSWER_TOO_LONG",
                        f"Answer length ({len(a)}) exceeds maximum {self.max_back} characters."
                    ))

        # 5. Placeholder & Inadequate Content Rejection
        test_strings = [q, a] if not is_cloze else [cloze_str, a]
        for s in test_strings:
            if not s:
                continue
            for pat in self.BANNED_PLACEHOLDER_PATTERNS:
                if re.search(pat, s, re.IGNORECASE):
                    issues.append(ValidationIssue(
                        "ERROR", "PLACEHOLDER_ANSWER",
                        f"Card text matches banned placeholder pattern '{pat}'."
                    ))
                    break

        # 6. Banned Vague Formulation Rejection (SuperMemo Rule 12)
        for s in test_strings:
            if not s:
                continue
            for pat in self.BANNED_VAGUE_PATTERNS:
                if re.search(pat, s, re.IGNORECASE):
                    issues.append(ValidationIssue(
                        "ERROR", "BANNED_VAGUE_PROMPT",
                        f"Card text matches banned vague prompt pattern '{pat}'."
                    ))
                    break

        # 7. Heading-only prompt veto
        if q and "Key Concept / Mechanism:" in q:
            prompt_body = re.sub(r'^.*?Key Concept\s*(?:/|and)\s*Mechanism:\s*', '', q, flags=re.I).strip()
            trailing = re.split(r'<br>|\n', prompt_body)[-1].strip()
            # If prompt has key concept heading but trailing line lacks active question verb
            if len(trailing.split()) <= 8 and not re.search(r'^(What|Which|Why|How|Define|Explain|Identify|Describe|Name|Distinguish)\b', trailing, re.I):
                issues.append(ValidationIssue(
                    "ERROR", "HEADING_ONLY_PROMPT",
                    "Question prompt is a raw heading dump without an active recall interrogative."
                ))

        # 8. Textbook Index & Figure Corruption Detection
        for s in test_strings:
            if not s:
                continue
            for pat in self.CORRUPTED_INDEX_PATTERNS:
                if re.search(pat, s):
                    issues.append(ValidationIssue(
                        "ERROR", "CORRUPTED_INDEX_TEXT",
                        f"Card contains textbook index corruption matching pattern '{pat}'."
                    ))
                    break
            for pat in self.CORRUPTED_FIGURE_PATTERNS:
                if re.search(pat, s):
                    issues.append(ValidationIssue(
                        "ERROR", "CORRUPTED_FIGURE_TEXT",
                        f"Card contains textbook figure marker corruption matching pattern '{pat}'."
                    ))
                    break

        # 9. Atomicity warnings (SuperMemo Rule 4)
        if a and len(a.split()) > 35:
            issues.append(ValidationIssue(
                "WARNING", "ANSWER_WORDY",
                f"Answer has {len(a.split())} words; optimal atomic recall is <= 25 words."
            ))

        # 10. Failure Modes Elimination (M9 Guardrails)
        kw = card.get("keyword") or sanitized.get("keyword")
        if kw:
            clean_kw = strip_html_tags(str(kw)).strip()
            # Action verb / critique keyword veto
            if clean_kw.upper() in CRITIQUE_STANDALONE_WORDS or CRITIQUE_ACTION_REGEX.search(clean_kw):
                issues.append(ValidationIssue(
                    "ERROR", "ACTION_VERB_KEYWORD",
                    f"Keyword '{clean_kw}' is an action verb or critique phrase."
                ))

            # Definitional framing phrase as keyword veto
            if DEFINITIONAL_FRAMING_REGEX.search(clean_kw) or RELATIVE_CLAUSE_REGEX.search(clean_kw):
                issues.append(ValidationIssue(
                    "ERROR", "DEFINITIONAL_FRAMING_KEYWORD",
                    f"Keyword '{clean_kw}' begins with relative clause or definitional framing."
                ))

            # Inverted definition card veto
            if card_type == "bidirectional_definition":
                if len(clean_kw.split()) > 6 or len(clean_kw) > 55 or \
                   (len(clean_kw.split()) > 4 and re.match(r'^(?:the|a|an)\s+', clean_kw, re.I)) or \
                   DEFINITIONAL_FRAMING_REGEX.search(clean_kw) or \
                   RELATIVE_CLAUSE_REGEX.search(clean_kw):
                    issues.append(ValidationIssue(
                        "ERROR", "INVERTED_CARD_DEFINITION",
                        f"Keyword '{clean_kw}' appears to be a definition rather than a concise concept term."
                    ))

        # Nested interrogative prompt veto
        if q and NESTED_QUESTION_PATTERN.search(q):
            issues.append(ValidationIssue(
                "ERROR", "NESTED_QUESTION_PROMPT",
                f"Question contains nested interrogative phrase: '{q}'."
            ))

        is_valid = not any(issue.severity == "ERROR" for issue in issues)
        return CardValidationResult(is_valid=is_valid, sanitized_card=sanitized, issues=issues)


class CardDeduplicator:
    """
    Deduplicates cards across a deck using normalized signature matching with metadata merging.
    CRITICAL: Preserves bidirectional pairs (Keyword->Descriptor vs Descriptor->Keyword).
    """

    def __init__(self):
        self.duplicates_removed_count = 0

    @staticmethod
    def normalize_for_signature(text: str) -> str:
        """Strips HTML tags, symbols, whitespace, and lowercases text for signature hashing while preserving mathematical/comparison operators."""
        if not text:
            return ""
        t = strip_html_tags(text).lower()
        t = t.replace('<=', ' _lte_ ').replace('>=', ' _gte_ ')
        t = t.replace('<', ' _lt_ ').replace('>', ' _gt_ ')
        t = t.replace('!=', ' _neq_ ').replace('=', ' _eq_ ')
        t = t.replace('~', ' _by_ ').replace('+', ' _plus_ ')
        return re.sub(r'[^a-z0-9_]', '', t)

    def get_signature(self, card: Dict[str, Any]) -> Tuple[str, ...]:
        """
        Generates a normalized composite signature for a card.
        For cloze: ('cloze', norm(cloze_text or question))
        For Q/A: ('qa', norm(question), norm(answer))
        """
        card_type = card.get("card_type", "")
        q = card.get("question") or card.get("front") or ""
        a = card.get("answer") or card.get("back") or ""
        cloze_str = card.get("cloze_text") or (q if card_type == "cloze" or "{{c1::" in q else "")

        if card_type == "cloze" or "{{c1::" in q or "{{c1::" in cloze_str:
            return ("cloze", self.normalize_for_signature(cloze_str or q))
        return ("qa", self.normalize_for_signature(q), self.normalize_for_signature(a))

    def deduplicate(
        self,
        cards: List[Dict[str, Any]],
        return_count: bool = False
    ) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], int]]:
        """
        Deduplicates cards while merging tags and context.
        If return_count is True, returns (unique_cards, duplicates_removed_count).
        Otherwise returns unique_cards (and sets self.duplicates_removed_count).
        """
        seen: Dict[Tuple[str, ...], Dict[str, Any]] = {}
        unique_cards: List[Dict[str, Any]] = []
        removed_count = 0

        for card in cards:
            sig = self.get_signature(card)

            if sig in seen:
                existing = seen[sig]
                # Merge tags
                existing_tags = existing.get("tags", [])
                card_tags = card.get("tags", [])
                existing["tags"] = list(dict.fromkeys(existing_tags + card_tags))

                # Preserve context notes if missing
                if not existing.get("context") and card.get("context"):
                    existing["context"] = card["context"]

                removed_count += 1
            else:
                card_copy = copy.deepcopy(card)
                seen[sig] = card_copy
                unique_cards.append(card_copy)

        self.duplicates_removed_count = removed_count
        if return_count:
            return unique_cards, removed_count
        return unique_cards


class DeckQualityPipeline:
    """Orchestrates Sanitizer -> Validator -> Deduplicator for a full deck."""

    def __init__(
        self,
        validator: Optional[CardValidator] = None,
        deduplicator: Optional[CardDeduplicator] = None,
        sanitizer: Optional[CardSanitizer] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        self.sanitizer = sanitizer or CardSanitizer()
        self.validator = validator or CardValidator(config=config)
        self.deduplicator = deduplicator or CardDeduplicator()

    def process(
        self,
        cards: List[Dict[str, Any]],
        strict: bool = False
    ) -> Tuple[List[Dict[str, Any]], DeckValidationSummary]:
        """
        Executes the three-stage defensive quality pipeline:
        1. Sanitize raw card fields.
        2. Validate cards, discarding invalid cards (or raising if strict=True).
        3. Deduplicate valid cards while merging metadata.
        """
        summary = DeckValidationSummary(total_input_cards=len(cards))
        valid_cards: List[Dict[str, Any]] = []

        for card in cards:
            result = self.validator.validate_card(card)

            if result.is_valid:
                valid_cards.append(result.sanitized_card)
                for issue in result.issues:
                    if issue.severity == "WARNING":
                        summary.warnings_count += 1
                        summary.warnings.append(f"{issue.rule_id}: {issue.message}")
            else:
                summary.rejected_cards_count += 1
                for issue in result.issues:
                    if issue.severity == "ERROR":
                        summary.rejection_reasons[issue.rule_id] = (
                            summary.rejection_reasons.get(issue.rule_id, 0) + 1
                        )
                if strict:
                    raise ValueError(
                        f"Strict deck quality validation failed on card: "
                        f"{card.get('question', card.get('front', 'Unknown'))}. "
                        f"Issues: {[str(i) for i in result.issues]}"
                    )

        # Stage 3: Deduplication
        deduped_cards, duplicates_count = self.deduplicator.deduplicate(valid_cards, return_count=True)
        summary.duplicates_removed_count = duplicates_count
        summary.valid_cards_count = len(deduped_cards)

        return deduped_cards, summary

    def process_deck(
        self,
        cards: List[Dict[str, Any]],
        strict: bool = False
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Interface contract method compatible with PROJECT.md.
        Returns (sanitized_and_deduplicated_cards, telemetry_dict).
        """
        cards_out, summary = self.process(cards, strict=strict)
        return cards_out, summary.to_dict()


# =============================================================================
# Module-level convenience functions & Cognitive Formulation Taxonomies
# =============================================================================

DEFAULT_CARD_QUALITY = {
    "min_front_length": 10,
    "max_front_length": 250,
    "min_back_length": 5,
    "max_back_length": 500,
    "remove_duplicates": True,
    "validate_format": True
}

# Cognitive Taxonomies definitions across university academic domains
COGNITIVE_TAXONOMIES = {
    # Foundational / Biology / Pharmacology
    "term_definition": "Term -> Definition",
    "concept_mechanism": "Concept -> Mechanism",
    "function_structure": "Function -> Structure",
    "example_category": "Example -> Category",
    # Statistics & Quantitative Methods
    "test_selection": "Diagnostic Test Selection",
    "assumption_triad": "Assumption-Diagnosis-Remediation Triad",
    "formula_decomposition": "Formula Decomposition & Degrees of Freedom",
    "decision_rule": "Hypotheses & Statistical Decision Rule",
    "r_syntax": "Computational / R Syntax & Data Types",
    # Developmental Psychology
    "developmental_stage": "Developmental Stage & Milestone",
    "experimental_paradigm": "Experimental Paradigm & Construct",
    # Professionalism & Ethics
    "ethical_dilemma_rule": "Ethical Dilemma & Rule Precedence",
}

# Statistical & Quantitative Constants (PSYC 3031 / Research Methods)
STATISTICAL_TESTS = {
    "independent samples t-test", "independent-samples t-test", "independent t-test",
    "paired samples t-test", "paired-samples t-test", "paired t-test", "dependent t-test",
    "one-way between-subjects anova", "one-way anova", "between-subjects anova",
    "repeated measures anova", "repeated-measures anova", "within-subjects anova",
    "two-way factorial anova", "factorial anova", "two-way anova",
    "chi-square test of independence", "chi-square goodness of fit", "chi-square",
    "pearson correlation", "spearman rank correlation", "spearman correlation",
    "simple linear regression", "multiple linear regression", "linear regression",
    "ancova", "manova", "welch's t-test", "welch's anova",
    "mann-whitney u test", "wilcoxon signed-rank test", "kruskal-wallis test", "friedman test"
}

STATISTICAL_ASSUMPTIONS = {
    "homogeneity of variance", "homoscedasticity", "normality", "sphericity",
    "independence of observations", "linearity", "multicollinearity", "normality of residuals",
    "equal variance", "equal variances"
}

R_SYNTAX_CUES = [
    r"\bt\.test\(", r"\baov\(", r"\blm\(", r"\banova\(", r"\bleveneTest\(",
    r"\bshapiro\.test\(", r"\bggplot\(", r"\bsummary\(", r"\bdata\.frame\(",
    r"\bpairwise\.t\.test\(", r"\boneway\.test\(", r"\bpsych::describe\(",
    r"\bdplyr::", r"\bmutate\(", r"\bfilter\(", r"\bselect\(",
    r"\bread\.csv\(", r"\bgetwd\(", r"\bstr\(", r"\bview\(",
    r"\bdbl\b", r"\bint\b", r"\blgl\b", r"\bchr\b",
    r"\[row,\s*col\]", r"%\>%", r"\|\>",
    r"\blibrary\([a-zA-Z0-9\._]+\)", r"`[a-zA-Z0-9_\.]+\(.*?\)`",
    r"\bcoercion\b", r"\btibble\b", r"\bdata\.frame\b"
]

DECISION_CUES = [
    r"\breject\s+h0\b", r"\bfail\s+to\s+reject\b", r"\bnull\s+hypothesis\b",
    r"\balternative\s+hypothesis\b", r"\balpha\s*=\s*\.?\d+", r"\bp\s*[<>=≤≥]\s*\.?\d+",
    r"\bdecision\s+rule\b", r"\btype\s+i\s+error\b", r"\btype\s+ii\s+error\b",
    r"\bcritical\s+value\b", r"\bstatistical\s+power\b"
]

FORMULA_CUES = [
    r"\$\$.*?\$\$", r"\$.*?\$", r"\\frac", r"\\sum", r"\\sigma", r"\\mu",
    r"\bdf\s*=", r"\bdegrees\s+of\s+freedom\b", r"\bcalculated\s+as\b",
    r"\bformula\s+for\b", r"\bstandard\s+error\b", r"\bpooled\s+variance\b"
]

ANATOMICAL_STRUCTURES = {
    "frontal lobe", "prefrontal cortex", "parietal lobe", "temporal lobe", "occipital lobe",
    "cerebellum", "brainstem", "thalamus", "hypothalamus", "hippocampus", "amygdala",
    "corpus callosum", "basal ganglia", "substantia nigra", "neocortex", "cerebral cortex",
    "glial cell", "glial cells", "astrocyte", "astrocytes", "oligodendrocyte", "oligodendrocytes",
    "microglia", "schwann cell", "schwann cells", "motor cortex", "somatosensory cortex",
    "visual cortex", "auditory cortex", "broca's area", "wernicke's area", "blood-brain barrier",
    "myelin", "myelin sheath", "ventricle", "ventricles", "striatum", "nucleus accumbens",
    "locus coeruleus", "raphe nuclei", "axon", "dendrite", "synapse", "presynaptic terminal",
    "nodes of ranvier", "soma", "cell body", "central nervous system", "peripheral nervous system",
    "cns", "pns", "cerebrum", "meninges", "dura mater", "pia mater", "arachnoid mater"
}

FUNCTION_CUES = [
    r"\bcontrols?\b",
    r"\bresponsible for\b",
    r"\bprocesses sensory\b",
    r"\bcoordinates?\b",
    r"\bprimary visual\b",
    r"\bprimary auditory\b",
    r"\brelay station\b",
    r"\bessential for memory\b",
    r"\bhomeostatic functions?\b",
    r"\bproduces myelin\b",
    r"\bprotects?\b",
    r"\binsulates?\b",
    r"\bmediates?\b",
    r"\bexecutive functions?\b",
    r"\binterhemispheric communication\b",
    r"\blanguage comprehension\b",
    r"\bspeech production\b",
]

MECHANISM_TERMS = {
    "action potential", "long-term potentiation", "ltp", "long-term depression", "ltd",
    "synaptic transmission", "neurotransmitter release", "reuptake", "depolarization",
    "repolarization", "hyperpolarization", "refractory period", "signal transduction",
    "g-protein", "second messenger", "phosphorylation", "exocytosis", "endocytosis",
    "receptor downregulation", "receptor upregulation", "agonism", "antagonism",
    "enzyme inhibition", "voltage-gated", "ligand-gated", "snare complex", "active transport",
    "passive diffusion", "retrograde transmission", "vesicle fusion"
}

MECHANISM_CUES = [
    r"\bmechanism of\b",
    r"\bprocess (?:by which|of)\b",
    r"\bresults from\b",
    r"\bleads to\b",
    r"\bcauses?\b",
    r"\btriggers?\b",
    r"\binduces?\b",
    r"\bcascade\b",
    r"\bpathway\b",
    r"\bpropagates?\b",
    r"\bfuses with\b",
    r"\binitiates?\b",
]

CLINICAL_EXAMPLES = {
    "locked-in syndrome", "minimally conscious state", "hemispatial neglect",
    "broca's aphasia", "wernicke's aphasia", "aphasia", "concussion",
    "traumatic brain injury", "tbi", "martin pistorius", "phineas gage", "patient h.m.",
    "alzheimer's disease", "alzheimer's", "parkinson's disease", "parkinson's",
    "huntington's disease", "multiple sclerosis", "epilepsy", "agnosia", "apraxia",
    "retrograde amnesia", "anterograde amnesia", "korsakoff's syndrome", "schizophrenia",
    "bipolar disorder", "major depressive disorder", "mdd", "extrapyramidal symptoms", "eps"
}

EXEMPLAR_CUES = [
    r"\bis an example of\b",
    r"\bis a type of\b",
    r"\bis a form of\b",
    r"\bexemplifies\b",
    r"\brepresents a case of\b",
    r"\ba classic case of\b",
    r"\bclinical condition characterized by\b",
    r"\bdisorder caused by\b",
    r"\bcondition where\b",
]


def clean_card_text(text: str) -> str:
    """Convenience function delegating to CardSanitizer().sanitize_text."""
    return CardSanitizer().sanitize_text(text)


def has_inadequate_content(text: str) -> bool:
    """Checks whether an answer has inadequate or placeholder content."""
    if not text or not text.strip():
        return True
    if re.search(r'<(?:i|b|span|em|strong)>\s*</(?:i|b|span|em|strong)>', text, re.IGNORECASE):
        return True
    clean = strip_html_tags(text).strip()
    if len(clean) < 2:
        return True
    for pat in CardValidator.BANNED_PLACEHOLDER_PATTERNS:
        if re.search(pat, clean, re.IGNORECASE):
            return True
    return False


def has_inadequate_question(text: str) -> bool:
    """Checks whether a question is vague, empty, or placeholder."""
    if not text or not text.strip():
        return True
    if re.search(r'<(?:i|b|span|em|strong)>\s*</(?:i|b|span|em|strong)>', text, re.IGNORECASE):
        return True
    clean = strip_html_tags(text).strip()
    if len(clean) < 4:
        return True
    for pat in CardValidator.BANNED_VAGUE_PATTERNS:
        if re.search(pat, clean, re.IGNORECASE):
            return True
    return False


def validate_card(card: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[str]]:
    """
    Convenience function delegating to CardValidator().validate_card.
    Returns (is_valid, error_reason).
    """
    result = CardValidator(config=config).validate_card(card)
    if result.is_valid:
        return True, None
    error_issues = [str(i) for i in result.issues if i.severity == "ERROR"]
    reason = "; ".join(error_issues) if error_issues else "Validation failed"
    return False, reason


def remove_duplicate_cards(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convenience function delegating to CardDeduplicator().deduplicate."""
    return CardDeduplicator().deduplicate(cards)


def filter_and_validate_deck(
    cards: List[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
    strict: bool = False
) -> List[Dict[str, Any]]:
    """Convenience function executing the three-stage DeckQualityPipeline."""
    cards_out, _ = DeckQualityPipeline(config=config).process(cards, strict=strict)
    return cards_out


def classify_cognitive_taxonomy(keyword: str, descriptor: str, context: str = "", domain: str = "general") -> str:
    """
    Classifies content into domain-specific cognitive card formulation taxonomies:
    1. Statistics: test_selection, assumption_triad, formula_decomposition, decision_rule, r_syntax
    2. Developmental Psychology: developmental_stage, experimental_paradigm
    3. Professionalism & Ethics: ethical_dilemma_rule
    4. Biological / Pharmacology: function_structure, concept_mechanism, example_category
    5. Fallback: term_definition
    """
    kw_lower = keyword.strip().lower() if keyword else ""
    desc_lower = descriptor.strip().lower() if descriptor else ""
    ctx_lower = context.strip().lower() if context else ""
    combined = f"{kw_lower} {desc_lower} {ctx_lower}"

    # 1. Statistics & Quantitative Methods
    if domain == "statistics" or any(t in combined for t in ["anova", "t-test", "regression", "p-value", "degrees of freedom", "null hypothesis"]):
        if any(re.search(cue, combined) for cue in R_SYNTAX_CUES) or "r code" in combined or "syntax" in combined:
            return "r_syntax"
        if any(re.search(cue, combined) for cue in DECISION_CUES):
            return "decision_rule"
        if any(a in combined for a in STATISTICAL_ASSUMPTIONS):
            return "assumption_triad"
        if any(t in kw_lower for t in STATISTICAL_TESTS) or "test used" in desc_lower or "test is used" in desc_lower or "appropriate test" in desc_lower:
            return "test_selection"
        if any(re.search(cue, combined) for cue in FORMULA_CUES):
            return "formula_decomposition"

    # 2. Developmental Psychology
    if domain == "developmental_psychology" or any(t in combined for t in ["piaget", "erikson", "vygotsky", "developmental stage"]):
        if any(s in combined for s in ["stage", "sensorimotor", "preoperational", "concrete operational", "formal operational", "crisis", "attachment style"]):
            return "developmental_stage"
        if any(p in combined for p in ["strange situation", "visual cliff", "false belief", "habituation", "conservation task"]):
            return "experimental_paradigm"

    # 3. Professionalism & Ethics
    if domain == "professionalism" or any(t in combined for t in ["cpa code", "ethics", "informed consent", "confidentiality", "tri-council"]):
        return "ethical_dilemma_rule"

    # 4. Biological / Pharmacology
    if kw_lower in CLINICAL_EXAMPLES or any(term in kw_lower for term in ["syndrome", "aphasia", "neglect", "disease", "disorder"]):
        return "example_category"
    for cue in EXEMPLAR_CUES:
        if re.search(cue, combined):
            return "example_category"

    if kw_lower in ANATOMICAL_STRUCTURES or any(struct in kw_lower for struct in ["lobe", "cortex", "ganglia", "nucleus", "tract", "ventricle"]):
        return "function_structure"
    for cue in FUNCTION_CUES:
        if re.search(cue, desc_lower):
            if any(s in combined for s in ["brain", "cortex", "neuron", "axon", "cell", "cns", "lobe", "hemisphere"]):
                return "function_structure"

    if kw_lower in MECHANISM_TERMS or any(m in kw_lower for m in ["potential", "transmission", "cascade", "cycle", "pathway"]):
        return "concept_mechanism"
    for cue in MECHANISM_CUES:
        if re.search(cue, desc_lower):
            return "concept_mechanism"

    return "term_definition"


def formulate_cognitive_cards(
    keyword: str,
    descriptor: str,
    taxonomy: Optional[str] = None,
    heading: str = "General",
    context: str = "",
    badge: Optional[str] = None,
    tags: Optional[List[str]] = None,
    domain: str = "general"
) -> List[Dict[str, Any]]:
    """
    Formulates atomic flashcards according to cognitive formulation taxonomies
    across academic domains while adhering to SuperMemo 20 Rules.
    """
    sanitizer = CardSanitizer()
    clean_kw = sanitizer.sanitize_text(keyword, is_question=False)
    clean_desc = sanitizer.sanitize_text(descriptor, is_question=False)
    ctx_field = context or heading
    base_tags = list(tags) if tags else []

    if not taxonomy:
        taxonomy = classify_cognitive_taxonomy(clean_kw, clean_desc, context=ctx_field, domain=domain)

    cards: List[Dict[str, Any]] = []

    # 1. Function -> Structure
    if taxonomy == "function_structure":
        b = badge or "badge-definition"
        cards.append({
            "card_type": "active_recall_qa",
            "taxonomy": "function_structure",
            "keyword": clean_kw,
            "descriptor": clean_desc,
            "question": f"What brain structure is responsible for: <i>{clean_desc}</i>?",
            "answer": f"<b>{clean_kw}</b>",
            "category_badge": b,
            "context": ctx_field,
            "tags": list(dict.fromkeys(base_tags + ["anatomy", "function_structure", "recall"]))
        })
        cards.append({
            "card_type": "active_recall_qa",
            "taxonomy": "function_structure",
            "keyword": clean_kw,
            "descriptor": clean_desc,
            "question": f"What is the primary function of the <b>{clean_kw}</b>?",
            "answer": clean_desc,
            "category_badge": b,
            "context": ctx_field,
            "tags": list(dict.fromkeys(base_tags + ["anatomy", "function_structure", "recognition"]))
        })
        return cards

    # 2. Concept -> Mechanism
    if taxonomy == "concept_mechanism":
        b = badge or "badge-important"
        cards.append({
            "card_type": "active_recall_qa",
            "taxonomy": "concept_mechanism",
            "keyword": clean_kw,
            "descriptor": clean_desc,
            "question": f"What is the key mechanism regarding <b>{clean_kw}</b>?",
            "answer": clean_desc,
            "category_badge": b,
            "context": ctx_field,
            "tags": list(dict.fromkeys(base_tags + ["mechanism", "concept_mechanism"]))
        })
        return cards

    # 3. Example -> Category
    if taxonomy == "example_category":
        b = badge or "badge-important"
        cards.append({
            "card_type": "active_recall_qa",
            "taxonomy": "example_category",
            "keyword": clean_kw,
            "descriptor": clean_desc,
            "question": f"<b>{clean_kw}</b> is a primary clinical example of what condition or phenomenon?",
            "answer": clean_desc,
            "category_badge": b,
            "context": ctx_field,
            "tags": list(dict.fromkeys(base_tags + ["clinical", "example_category"]))
        })
        cards.append({
            "card_type": "active_recall_qa",
            "taxonomy": "example_category",
            "keyword": clean_kw,
            "descriptor": clean_desc,
            "question": f"What clinical condition or case exemplifies: <i>{clean_desc}</i>?",
            "answer": f"<b>{clean_kw}</b>",
            "category_badge": b,
            "context": ctx_field,
            "tags": list(dict.fromkeys(base_tags + ["clinical", "example_category"]))
        })
        return cards

    # 4. Diagnostic Test Selection (PSYC 3031)
    if taxonomy == "test_selection":
        b = badge or "badge-important"
        cards.append({
            "card_type": "active_recall_qa",
            "taxonomy": "test_selection",
            "keyword": clean_kw,
            "descriptor": clean_desc,
            "question": f"Which statistical test should be selected for: <i>{clean_desc}</i>?",
            "answer": f"<b>{clean_kw}</b>",
            "category_badge": b,
            "context": ctx_field,
            "tags": list(dict.fromkeys(base_tags + ["statistics", "test_selection", "recall"]))
        })
        cards.append({
            "card_type": "active_recall_qa",
            "taxonomy": "test_selection",
            "keyword": clean_kw,
            "descriptor": clean_desc,
            "question": f"Under what study design conditions is <b>{clean_kw}</b> appropriate?",
            "answer": clean_desc,
            "category_badge": b,
            "context": ctx_field,
            "tags": list(dict.fromkeys(base_tags + ["statistics", "test_selection", "recognition"]))
        })
        return cards

    # 5. Assumption-Diagnosis-Remediation Triad (PSYC 3031)
    if taxonomy == "assumption_triad":
        b = badge or "badge-important"
        cards.append({
            "card_type": "active_recall_qa",
            "taxonomy": "assumption_triad",
            "keyword": clean_kw,
            "descriptor": clean_desc,
            "question": f"Regarding the assumption of <b>{clean_kw}</b>, what diagnostic test is used and what is the remediation if violated?",
            "answer": clean_desc,
            "category_badge": b,
            "context": ctx_field,
            "tags": list(dict.fromkeys(base_tags + ["statistics", "assumption_triad"]))
        })
        return cards

    # 6. Formula Decomposition & Degrees of Freedom (PSYC 3031)
    if taxonomy == "formula_decomposition":
        b = badge or "badge-important"
        cards.append({
            "card_type": "active_recall_qa",
            "taxonomy": "formula_decomposition",
            "keyword": clean_kw,
            "descriptor": clean_desc,
            "question": f"In the formula for <b>{clean_kw}</b>, what does the following component represent:<br><i>{clean_desc}</i>?",
            "answer": clean_desc if "represents" in clean_desc.lower() else f"<b>{clean_kw}</b>: {clean_desc}",
            "category_badge": b,
            "context": ctx_field,
            "tags": list(dict.fromkeys(base_tags + ["statistics", "formula_decomposition"]))
        })
        return cards

    # 7. Hypotheses & Statistical Decision Rules (PSYC 3031)
    if taxonomy == "decision_rule":
        b = badge or "badge-important"
        cards.append({
            "card_type": "active_recall_qa",
            "taxonomy": "decision_rule",
            "keyword": clean_kw,
            "descriptor": clean_desc,
            "question": f"State the statistical decision rule regarding <b>{clean_kw}</b>:",
            "answer": clean_desc,
            "category_badge": b,
            "context": ctx_field,
            "tags": list(dict.fromkeys(base_tags + ["statistics", "decision_rule"]))
        })
        return cards

    # 8. Computational / R Syntax & Data Types (PSYC 3031)
    if taxonomy == "r_syntax":
        b = badge or "badge-code"
        # Card 1: Purpose -> Function Syntax
        cards.append({
            "card_type": "active_recall_qa",
            "taxonomy": "r_syntax",
            "keyword": clean_kw,
            "descriptor": clean_desc,
            "question": f"What R syntax or function executes: <i>{clean_desc}</i>?",
            "answer": f"<code>{clean_kw}</code>",
            "category_badge": b,
            "context": ctx_field,
            "tags": list(dict.fromkeys(base_tags + ["r_syntax", "programming", "forward"]))
        })
        # Card 2: Function Syntax -> Purpose / Output
        cards.append({
            "card_type": "active_recall_qa",
            "taxonomy": "r_syntax",
            "keyword": clean_kw,
            "descriptor": clean_desc,
            "question": f"What is the purpose and effect of the R function <code>{clean_kw}</code>?",
            "answer": clean_desc,
            "category_badge": b,
            "context": ctx_field,
            "tags": list(dict.fromkeys(base_tags + ["r_syntax", "programming", "reverse"]))
        })
        return cards

    # 9. Developmental Stage & Milestone (PSYC 2110)
    if taxonomy == "developmental_stage":
        b = badge or "badge-definition"
        cards.append({
            "card_type": "active_recall_qa",
            "taxonomy": "developmental_stage",
            "keyword": clean_kw,
            "descriptor": clean_desc,
            "question": f"In developmental psychology, what age range and milestone characterize <b>{clean_kw}</b>?",
            "answer": clean_desc,
            "category_badge": b,
            "context": ctx_field,
            "tags": list(dict.fromkeys(base_tags + ["developmental", "stage_milestone"]))
        })
        return cards

    # 10. Experimental Paradigm & Construct (PSYC 2110)
    if taxonomy == "experimental_paradigm":
        b = badge or "badge-definition"
        cards.append({
            "card_type": "active_recall_qa",
            "taxonomy": "experimental_paradigm",
            "keyword": clean_kw,
            "descriptor": clean_desc,
            "question": f"What psychological construct is evaluated by the <b>{clean_kw}</b> paradigm?",
            "answer": clean_desc,
            "category_badge": b,
            "context": ctx_field,
            "tags": list(dict.fromkeys(base_tags + ["developmental", "experimental_paradigm"]))
        })
        return cards

    # 11. Ethical Dilemma & Rule Precedence (PSYC 3000)
    if taxonomy == "ethical_dilemma_rule":
        b = badge or "badge-important"
        cards.append({
            "card_type": "active_recall_qa",
            "taxonomy": "ethical_dilemma_rule",
            "keyword": clean_kw,
            "descriptor": clean_desc,
            "question": f"According to professional ethics standards, what rule governs <b>{clean_kw}</b>?",
            "answer": clean_desc,
            "category_badge": b,
            "context": ctx_field,
            "tags": list(dict.fromkeys(base_tags + ["ethics", "professionalism"]))
        })
        return cards

    # 12. Term -> Definition (Default)
    b = badge or "badge-definition"
    cards.append({
        "card_type": "bidirectional_definition",
        "taxonomy": "term_definition",
        "keyword": clean_kw,
        "descriptor": clean_desc,
        "question": f"What is the definition of <b>{clean_kw}</b>?",
        "answer": clean_desc,
        "category_badge": b,
        "context": ctx_field,
        "tags": list(dict.fromkeys(base_tags + ["definition", "forward"]))
    })
    cards.append({
        "card_type": "bidirectional_definition",
        "taxonomy": "term_definition",
        "keyword": clean_kw,
        "descriptor": clean_desc,
        "question": f"What term is defined by:<br><i>{clean_desc}</i>",
        "answer": clean_kw,
        "category_badge": b,
        "context": ctx_field,
        "tags": list(dict.fromkeys(base_tags + ["definition", "reverse"]))
    })
    return cards
