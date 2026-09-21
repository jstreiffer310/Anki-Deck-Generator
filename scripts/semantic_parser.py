"""
Semantic Card Parser Engine & SuperMemo 20 Rules Knowledge Formulation
Implements LLM-assisted parsing via Ollama and a deterministic 64+ pattern
rule-based fallback parser with multi-tier subject resolution and zero "this concept" emissions.
"""

import re
import json
import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Attempt import of OllamaRuntimeManager
try:
    from scripts.ollama_runtime import OllamaRuntimeManager
except ImportError:
    try:
        from ollama_runtime import OllamaRuntimeManager
    except ImportError:
        OllamaRuntimeManager = None

try:
    from scripts.card_validator import (
        validate_card as validator_validate_card,
        remove_duplicate_cards,
        classify_cognitive_taxonomy,
        formulate_cognitive_cards,
        has_inadequate_content,
        has_inadequate_question,
        COGNITIVE_TAXONOMIES,
    )
except ImportError:
    try:
        from card_validator import (
            validate_card as validator_validate_card,
            remove_duplicate_cards,
            classify_cognitive_taxonomy,
            formulate_cognitive_cards,
            has_inadequate_content,
            has_inadequate_question,
            COGNITIVE_TAXONOMIES,
        )
    except ImportError:
        validator_validate_card = None
        remove_duplicate_cards = None
        classify_cognitive_taxonomy = None
        formulate_cognitive_cards = None
        has_inadequate_content = None
        has_inadequate_question = None
        COGNITIVE_TAXONOMIES = {}

# ============================================================================
# 1. 64+ Pattern Linking Verb Lexicon across 4 Functional Classes
# ============================================================================

# Class 1: Explicit Definitional Copulas (24 patterns)
DEFINITIONAL_COPULAS = [
    r"\bis\s+defined\s+as\b",
    r"\bcan\s+be\s+defined\s+as\b",
    r"\bis\s+described\s+as\b",
    r"\bcan\s+be\s+described\s+as\b",
    r"\bis\s+characterized\s+by\b",
    r"\bcan\s+be\s+characterized\s+by\b",
    r"\bis\s+distinguished\s+by\b",
    r"\bcan\s+be\s+distinguished\s+by\b",
    r"\brefers\s+to\s+the\s+process\s+of\b",
    r"\brefers\s+to\s+the\s+concept\s+of\b",
    r"\brefers\s+to\s+the\s+state\s+of\b",
    r"\brefers\s+to\s+the\s+phenomenon\s+of\b",
    r"\brefers\s+to\b",
    r"\brepresents\b",
    r"\bdenotes\b",
    r"\bsignifies\b",
    r"\bmeans\b",
    r"\binvolves\b",
    r"\bdesignates\b",
    r"\bis\s+known\s+as\b",
    r"\bis\s+recognized\s+as\b",
    r"\bis\s+understood\s+as\b",
    r"\bstands\s+for\b",
    r"\bis\s+termed\b",
]

# Class 2: Simple Copulas & Equatives (17 patterns)
EQUATIVE_COPULAS = [
    r"\bis\s+the\s+process\s+of\b",
    r"\bis\s+the\s+study\s+of\b",
    r"\bis\s+the\s+state\s+of\b",
    r"\bis\s+the\s+science\s+of\b",
    r"\bis\s+the\s+branch\s+of\b",
    r"\bis\s+a\s+type\s+of\b",
    r"\bis\s+a\s+form\s+of\b",
    r"\bis\s+an\s+example\s+of\b",
    r"\bis\s+the\b",
    r"\bis\s+an\b",
    r"\bis\s+a\b",
    r"\bare\s+defined\s+as\b",
    r"\bare\s+described\s+as\b",
    r"\bare\s+characterized\s+by\b",
    r"\bare\s+the\b",
    r"\bare\b",
    r"\bis\b",
]

# Class 3: Functional & Action Verbs (32 patterns)
FUNCTIONAL_COPULAS = [
    r"\bfocuses\s+on\b",
    r"\bfocus\s+on\b",
    r"\baims\s+to\b",
    r"\baim\s+to\b",
    r"\bdeals\s+with\b",
    r"\bdeal\s+with\b",
    r"\bexamines\b",
    r"\bexamine\b",
    r"\binvestigates\b",
    r"\binvestigate\b",
    r"\bmeasures\b",
    r"\bmeasure\b",
    r"\bfunctions\s+as\b",
    r"\bfunction\s+as\b",
    r"\bserves\s+as\b",
    r"\bserve\s+as\b",
    r"\bacts\s+as\b",
    r"\bact\s+as\b",
    r"\bconsists\s+of\b",
    r"\bconsist\s+of\b",
    r"\bcomprises\b",
    r"\bcomprise\b",
    r"\bresults\s+from\b",
    r"\bresult\s+from\b",
    r"\bleads\s+to\b",
    r"\blead\s+to\b",
    r"\bcauses\b",
    r"\bcause\b",
    r"\boccurs\s+when\b",
    r"\boccur\s+when\b",
    r"\bdescribes\b",
    r"\bdescribe\b",
    r"\bmediates\b",
    r"\bmediate\b",
    r"\bproduces\b",
    r"\bproduce\b",
    r"\binduces\b",
    r"\binduce\b",
    r"\btriggers\b",
    r"\btrigger\b",
    r"\bregulates\b",
    r"\bregulate\b",
    r"\bmodulates\b",
    r"\bmodulate\b",
]

# Class 4: Statistical, Methodological & Computational Copulas (24 patterns)
STATISTICAL_COPULAS = [
    r"\bis\s+calculated\s+as\b",
    r"\bis\s+calculated\s+by\b",
    r"\bis\s+computed\s+as\b",
    r"\bis\s+computed\s+by\b",
    r"\bis\s+given\s+by\s+the\s+formula\b",
    r"\bis\s+given\s+by\b",
    r"\bequals\b",
    r"\bassumes\s+that\b",
    r"\brequires\s+the\s+assumption\s+of\b",
    r"\bis\s+diagnosed\s+by\b",
    r"\bis\s+diagnosed\s+using\b",
    r"\bis\s+evaluated\s+using\b",
    r"\bis\s+remedied\s+by\b",
    r"\bis\s+remedied\s+using\b",
    r"\bis\s+used\s+to\s+test\b",
    r"\bis\s+used\s+when\s+comparing\b",
    r"\bis\s+appropriate\s+when\b",
    r"\bis\s+selected\s+when\b",
    r"\breject\s+h0\s+when\b",
    r"\breject\s+the\s+null\s+hypothesis\s+if\b",
    r"\bfail\s+to\s+reject\s+h0\s+when\b",
    r"\bretain\s+the\s+null\s+hypothesis\s+if\b",
    r"\bin\s+r,\s+the\s+function\b",
    r"\bis\s+executed\s+in\s+r\s+using\b",
]

# Class 5: Punctuation & Typographic Copulas (4 patterns)
TYPOGRAPHIC_COPULAS = [
    r"\s*:\s*",
    r"\s+—\s+",
    r"\s+–\s+",
    r"\s+-\s+",
]

# Combined Lexicon (total >= 101 patterns, exceeding 64 required)
ALL_LINKING_PATTERNS = (
    DEFINITIONAL_COPULAS + EQUATIVE_COPULAS + FUNCTIONAL_COPULAS + STATISTICAL_COPULAS + TYPOGRAPHIC_COPULAS
)
COPULA_LEXICON_COUNT = len(ALL_LINKING_PATTERNS)

# Compile regex sorted by descending length to ensure longest match precedence
# (e.g. "is defined as" matches before "is")
_SORTED_COPULA_PATTERNS = sorted(ALL_LINKING_PATTERNS, key=len, reverse=True)
LINKING_VERBS_REGEX = re.compile(
    r"(" + "|".join(_SORTED_COPULA_PATTERNS) + r")\s*",
    re.IGNORECASE
)

# Contrastive clause splitting regex for compound statements
COMPOUND_SPLIT_REGEX = re.compile(
    r'(?:,\s*whereas\s+|,\s*while\s+|;\s*however,\s*|;\s*|\s*—\s*)',
    re.IGNORECASE
)

# Banned phrases triggering critical veto
BANNED_PHRASES = [
    r"\bthis\s+concept\b",
    r"\bthis\s+term\b",
    r"\bthis\s+phenomenon\b",
    r"\bwhat\s+is\s+this\s+concept\b",
    r"\bdefine\s+this\s+concept\b",
]

# ============================================================================
# 2. SuperMemo 20 Rules System Prompt & JSON Schema
# ============================================================================

SUPERMEMO_SYSTEM_PROMPT = """You are an expert cognitive science flashcard creator specializing in SuperMemo's 20 Rules of Knowledge Formulation and university lecture spaced-repetition design.

Your objective is to convert raw student lecture highlights into atomic, high-retrieval flashcards conforming strictly to the provided JSON schema.

STRICT OPERATIONAL RULES:
1. MINIMUM INFORMATION PRINCIPLE (ATOMICITY - Rule 4):
   - Every card must test exactly ONE proposition, concept, or relationship.
   - If an input sentence contains multiple facts, thresholds, or mechanisms, you MUST decompose it into multiple separate cards.
   - An answer must be concise (ideally under 15 words; never exceed 35 words).
   - Target retrieval latency must be under 5 seconds.

2. CLOZE DELETION (Rule 5):
   - When yellow highlights state numerical thresholds, biochemical targets, percentages, or precise physiological rules, create a "cloze" card targeting the critical value using {{c1::target}} syntax.

3. KEYWORD-DESCRIPTOR FORMAT (ANKI_SOP.md & SuperMemo):
   - For definitions (Green highlights), extract a clean, nominal "keyword" (1 to 5 words, e.g. "Therapeutic Index (TI)").
   - Extract a clean "descriptor" that defines the keyword WITHOUT repeating the keyword itself and WITHOUT leading copula verbs (strip "is defined as", "refers to").
   - Generate bidirectional cards:
     * Forward (Recall): "What is the definition of <b>[keyword]</b>?" -> [descriptor]
     * Reverse (Recognition): "What term is defined by:<br><i>[descriptor]</i>" -> [keyword]

4. ABSOLUTELY FORBIDDEN PATTERNS (HARD VETO):
   - NEVER generate questions containing "this concept", "this term", or "this phenomenon".
   - NEVER generate generic prompts like "Define / What is this concept?" or "Key Concept / Mechanism: [Heading]".
   - NEVER create cards that ask the user to recite an entire multi-clause paragraph.

5. AVOID SETS AND ENUMERATIONS (Rules 9 & 10):
   - NEVER ask "List the 3 types of...", "What are the criteria for...".
   - Break sets into individual attribute queries (e.g., "Which type of glial cell produces myelin in the CNS?").

6. CONTEXT ANCHORING (Rules 11 & 16):
   - Always populate the "context" field with the lecture topic, heading, or clinical examples to eliminate ambiguity and prevent interference.

7. COGNITIVE FORMULATION TAXONOMIES ACROSS ACADEMIC DISCIPLINES:
   - Term -> Definition: For foundational vocabulary, vocabulary acquisition, and core definitions.
   - Concept -> Mechanism: For biochemical processes, pathways, cascades, and physiological mechanisms.
   - Function -> Structure: For anatomical brain regions and structures linked to specific physiological/behavioral functions.
   - Example -> Category: For clinical cases, disorders, or specific case studies exemplifying a general phenomenon.
   - Diagnostic Test Selection: For mapping study design parameters and variance conditions to the appropriate statistical test.
   - Assumption Triad: For statistical assumptions linked to diagnostic checks and violation remediations.
   - Formula Decomposition: For atomic components, ratio meaning, and degrees of freedom in mathematical models.
   - Statistical Decision Rule: For alpha levels, p-value criteria, and null hypothesis rejection boundaries.
   - Computational / R Syntax: For R functions, argument flags, coercion rules, and data structures.
   - Developmental Stage & Milestone: For psychological stages (Piaget, Erikson) and chronological age milestones.
   - Experimental Paradigm: For experimental designs (e.g. Strange Situation, Visual Cliff) testing specific constructs.
   - Ethical Dilemma & Rule: For professional codes of conduct (e.g. CPA principles) and precedence rules.
"""

def get_domain_system_prompt(domain: str = "general") -> str:
    """Returns the base SuperMemo prompt enhanced with subject-specific guidelines."""
    extensions = {
        "statistics": """
DOMAIN INSTRUCTIONS — STATISTICS & QUANTITATIVE METHODS (PSYC 3031):
1. MATHEMATICAL NOTATION & EQUATIONS:
   - Format inline math using LaTeX $...$ (e.g., $p < .05$, $df = N - k$, $\\alpha = .05$, $t(28) = 2.45$, $\\eta^2 = .14$).
   - Format display math using LaTeX $$...$$ (e.g., $$s^2 = \\frac{\\sum (X - \\bar{X})^2}{N - 1}$$).
   - Deconstruct complex formulas into atomic ratio meaning (Signal vs Noise) and degrees of freedom.
2. R COMPUTATIONAL SYNTAX:
   - Format all R code, package functions, and command calls using markdown backticks (e.g. `t.test(..., paired = TRUE)`).
   - Use 'r_syntax' taxonomy when notes highlight coding workflows or data manipulation (dplyr, psych).
3. THE 6 QUANTITATIVE ARCHETYPES:
   - 'test_selection': Test mapping from experimental design constraints to test names.
   - 'assumption_triad': Test assumptions paired with diagnostic tests and violation remediations.
   - 'formula_decomposition': Component meaning of mathematical terms.
   - 'decision_rule': Hypotheses rejection conditions.
   - 'cloze': Cloze deletions targeting operators, thresholds, or code arguments.
""",
        "pharmacology": """
DOMAIN INSTRUCTIONS — PHARMACOLOGY (PSYC 3590):
1. RECEPTOR MECHANISMS: Test agonist, antagonist, allosteric modulator kinetics.
2. PHARMACOKINETICS / DYNAMICS: Focus on affinity, efficacy, half-life ($t_{1/2}$), $ED_{50}$, therapeutic index.
3. STRUCTURE & FUNCTION: Correlate anatomical brain regions and neurotransmitter pathways.
""",
        "developmental_psychology": """
DOMAIN INSTRUCTIONS — DEVELOPMENTAL PSYCHOLOGY (PSYC 2110):
1. STAGE THEORIES: Test Piaget, Erikson, Vygotsky stages and chronological age brackets.
2. EXPERIMENTAL PARADIGMS: Test paradigms (Strange Situation, Visual Cliff, Habituation) paired with operationalized constructs.
""",
        "professionalism": """
DOMAIN INSTRUCTIONS — PROFESSIONALISM & ETHICS (PSYC 3000):
1. CPA ETHICAL PRINCIPLES: Respect for Dignity > Responsible Caring > Integrity > Responsibility to Society.
2. MANDATORY BOUNDARIES: Limits of confidentiality, mandatory reporting, duty to protect.
"""
    }
    ext = extensions.get(domain, "")
    return (SUPERMEMO_SYSTEM_PROMPT + "\n" + ext).strip()


CARD_DECOMPOSITION_JSON_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "AnkiCardDecompositionBatch",
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "card_type": {
                        "type": "string",
                        "enum": [
                            "bidirectional_definition",
                            "active_recall_qa",
                            "cloze",
                            "function_structure",
                            "concept_mechanism",
                            "example_category",
                            "test_selection",
                            "assumption_triad",
                            "formula_decomposition",
                            "decision_rule",
                            "r_syntax",
                            "developmental_stage",
                            "experimental_paradigm",
                            "ethical_dilemma_rule"
                        ]
                    },
                    "taxonomy": {
                        "type": "string",
                        "enum": [
                            "term_definition",
                            "concept_mechanism",
                            "function_structure",
                            "example_category",
                            "test_selection",
                            "assumption_triad",
                            "formula_decomposition",
                            "decision_rule",
                            "r_syntax",
                            "developmental_stage",
                            "experimental_paradigm",
                            "ethical_dilemma_rule"
                        ]
                    },
                    "keyword": {
                        "type": "string",
                        "description": "Concise scientific term or entity (1-5 words)."
                    },
                    "descriptor": {
                        "type": "string",
                        "description": "Clean definition or mechanism omitting the keyword and copulas."
                    },
                    "question": {
                        "type": "string",
                        "description": "Specific active recall question."
                    },
                    "answer": {
                        "type": "string",
                        "description": "Atomic answer target."
                    },
                    "reverse_question": {
                        "type": "string",
                        "description": "Required if card_type is bidirectional_definition: 'What term is defined by: ...'"
                    },
                    "cloze_text": {
                        "type": "string",
                        "description": "Required if card_type is cloze: sentence with {{c1::target}}."
                    },
                    "category_badge": {
                        "type": "string",
                        "enum": ["badge-definition", "badge-important"]
                    },
                    "context": {
                        "type": "string",
                        "description": "Topic, brain region, drug class, or clinical example context."
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["card_type", "question", "answer", "category_badge", "context", "tags"]
            }
        }
    },
    "required": ["cards"]
}


# ============================================================================
# 3. Text Processing & Normalization Utilities
# ============================================================================

def clean_phrase(text: str) -> str:
    """Removes leading bullets, excess whitespace, and normalizes capitalization."""
    if not text:
        return ""
    # Strip bullet symbols (•, -, *, —, –) or numbered list prefix like '1. ' or '1) '
    # Must NOT strip leading alphanumeric drug names or numbers with hyphens (e.g. '5-HT2A')
    t = re.sub(r'^(?:[•\*\—\–]|\s*-\s+|\d+[\.\)]\s+)+', '', text.strip())
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def strip_leading_articles(term: str) -> str:
    """Strips leading English articles (The, A, An) from a term and capitalizes."""
    clean = re.sub(r'^(the|a|an)\s+', '', term.strip(), flags=re.IGNORECASE).strip()
    if clean:
        return clean[0].upper() + clean[1:]
    return clean

def split_compound_yellow(yellow_text: str) -> List[str]:
    """
    Splits compound yellow statements into atomic propositions (SuperMemo Rule 4).
    Uses contrastive markers ('whereas', 'while', '; however', ';', '—').
    """
    text = yellow_text.strip()
    parts = COMPOUND_SPLIT_REGEX.split(text)
    if len(parts) > 1:
        atomic_propositions = [p.strip() for p in parts if len(p.strip()) > 10]
        if len(atomic_propositions) >= 2:
            return atomic_propositions
    return [text]

def check_veto_violations(text: str) -> bool:
    """Returns True if text contains any banned phrases violating zero 'this concept' mandate."""
    if not text:
        return False
    for pat in BANNED_PHRASES:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False

def is_valid_card(card: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validates that a card has non-empty Q/A, zero banned phrases,
    non-tautological content, passes length bounds and lacks placeholder text.
    """
    q = card.get("question", "").strip()
    a = card.get("answer", "").strip()
    if not q or not a:
        return False, "Empty question or answer"
    if check_veto_violations(q) or check_veto_violations(a):
        return False, "Contains banned phrase ('this concept')"
    if q.lower() == a.lower():
        return False, "Question and answer are identical (tautology)"
    if validator_validate_card is not None:
        return validator_validate_card(card)
    return True, None


# ============================================================================
# 4. Cloze Generation Engine (Rule 5)
# ============================================================================

def create_cloze_card(
    text: str,
    heading: str = "General",
    context: str = "",
    tags: Optional[List[str]] = None
) -> Optional[Dict[str, Any]]:
    """
    Creates an atomic Cloze deletion card targeting numerical ranges,
    percentages, or physiological thresholds.
    """
    if not text:
        return None

    clean_text = clean_phrase(text)
    tags_list = list(tags) if tags else []

    # Target 1: Percentage ranges or thresholds (e.g., 'between 65% and 80%', 'exceeding 80%', '65% to 80%')
    pct_match = re.search(
        r'(?:\b(?:between|exceeding|greater than|over|less than|under)\s+)?\d+(?:\.\d+)?%\s*(?:to|and|-)\s*\d+(?:\.\d+)?%|(?:\b(?:between|exceeding|greater than|over|less than|under)\s+)?\d+(?:\.\d+)?%',
        clean_text,
        re.IGNORECASE
    )
    if pct_match:
        target = pct_match.group(0).strip()
        start, end = pct_match.span()
        cloze_text = clean_text[:start] + f"{{{{c1::{target}}}}}" + clean_text[end:]

        # Extract subject from preceding text or heading
        text_before = clean_text[:start].strip()
        if text_before:
            words_before = text_before.split()
            subject = " ".join(words_before[:4]) if len(words_before) <= 5 else " ".join(words_before[-4:])
            subject = re.sub(r'[:;,].*', '', subject).strip()
            subject = strip_leading_articles(subject)
        else:
            subject = heading if heading != "General" else "Clinical Threshold"

        if not subject or len(subject) < 2:
            subject = heading if heading != "General" else "Clinical Threshold"

        return {
            "card_type": "cloze",
            "keyword": subject,
            "descriptor": clean_text,
            "question": f"Identify the missing value regarding <b>{subject}</b>:<br>{cloze_text}",
            "answer": target,
            "cloze_text": cloze_text,
            "category_badge": "badge-important",
            "context": context or heading,
            "tags": list(set(tags_list + ["cloze", "high_yield"]))
        }

    # Target 2: Numerical range with units (e.g., '10 to 20 mg', 'between 50 to 200 mg', '50-100 ms')
    num_unit_match = re.search(
        r'(?:\b(?:between)\s+)?\d+(?:\.\d+)?\s*(?:to|-)\s*\d+(?:\.\d+)?\s*(?:mg|ml|g|kg|hz|ms|s|min|hours|nm|um|mm|cm|m)\b|\b\d+(?:\.\d+)?\s*(?:mg|ml|g|kg|hz|ms|s|min|hours|nm|um|mm|cm|m)\b',
        clean_text,
        re.IGNORECASE
    )
    if num_unit_match:
        target = num_unit_match.group(0).strip()
        start, end = num_unit_match.span()
        cloze_text = clean_text[:start] + f"{{{{c1::{target}}}}}" + clean_text[end:]

        text_before = clean_text[:start].strip()
        if text_before:
            words_before = text_before.split()
            subject = " ".join(words_before[:4]) if len(words_before) <= 5 else " ".join(words_before[-4:])
            subject = re.sub(r'[:;,].*', '', subject).strip()
            subject = strip_leading_articles(subject)
        else:
            subject = heading if heading != "General" else "Measurement"

        if not subject or len(subject) < 2:
            subject = heading if heading != "General" else "Measurement"

        return {
            "card_type": "cloze",
            "keyword": subject,
            "descriptor": clean_text,
            "question": f"Identify the missing parameter regarding <b>{subject}</b>:<br>{cloze_text}",
            "answer": target,
            "cloze_text": cloze_text,
            "category_badge": "badge-important",
            "context": context or heading,
            "tags": list(set(tags_list + ["cloze", "high_yield"]))
        }

    # Target 3: Statistical metrics (p-values, alpha, degrees of freedom, confidence intervals, effect sizes)
    stat_match = re.search(
        r'(?:\b(?:p|alpha|F|t|z|r)\s*[<>=≤≥]\s*\.?\d+(?:\.\d+)?|\bdf\s*=\s*[\w\s\-\+\(\)]+|\b\d{2}%\s*CI\s*\[\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\]|\b(?:d|eta\^2|R\^2)\s*=\s*\.?\d+(?:\.\d+)?)',
        clean_text,
        re.IGNORECASE
    )
    if stat_match:
        target = stat_match.group(0).strip()
        start, end = stat_match.span()
        cloze_text = clean_text[:start] + f"{{{{c1::{target}}}}}" + clean_text[end:]
        subject = heading if heading != "General" else "Statistical Rule"
        return {
            "card_type": "cloze",
            "keyword": subject,
            "descriptor": clean_text,
            "question": f"Identify the statistical threshold/value regarding <b>{subject}</b>:<br>{cloze_text}",
            "answer": target,
            "cloze_text": cloze_text,
            "category_badge": "badge-important",
            "context": context or heading,
            "tags": list(set(tags_list + ["cloze", "statistics", "high_yield"]))
        }

    return None


# ============================================================================
# 5. Deterministic Multi-Tier Subject Resolution Algorithm
# ============================================================================

def split_highlight_fallback(
    highlight_text: str,
    paragraph_prefix: str = "",
    heading_context: str = "General"
) -> Tuple[str, str, str]:
    """
    Robust deterministic parser that splits text into (Keyword, Descriptor, Tier)
    guaranteeing ZERO occurrence of 'this concept'.

    Resolution Order:
      Tier 1: Internal Linking Verb Split within highlight text
      Tier 2: Paragraph Prefix Search
      Tier 3: Structural Anchor (Heading / First Clause)
    """
    text = clean_phrase(highlight_text)
    if not text:
        fallback_anchor = heading_context if heading_context and heading_context != "General" else "Key Concept"
        return fallback_anchor, fallback_anchor, "tier3_empty_fallback"

    # --- Tier 1: Internal Linking Verb Split ---
    match = LINKING_VERBS_REGEX.search(text)
    if match:
        term_part = text[:match.start()].strip()
        verb_part = match.group(1).strip()
        def_part = text[match.end():].strip()

        # Check for subordinate leading words that indicate term_part is not a clean concept
        subordinate_leads = ("when", "if", "because", "although", "since", "while", "whereas")
        if 2 <= len(term_part) <= 60 and not term_part.lower().startswith(subordinate_leads):
            clean_term = strip_leading_articles(term_part)
            clean_def = def_part[0].upper() + def_part[1:] if def_part else ""
            if not clean_def.endswith((".", "!", "?")) and clean_def:
                clean_def += "."
            return clean_term, clean_def, "tier1_internal"

    # --- Tier 2: Paragraph Prefix Search ---
    if paragraph_prefix:
        pref = clean_phrase(paragraph_prefix)
        # Look for "Term: " or "Term is defined as" in prefix
        pref_match = LINKING_VERBS_REGEX.search(pref)
        if pref_match:
            candidate = pref[:pref_match.start()].strip()
            clean_cand = strip_leading_articles(candidate)
            if 2 <= len(clean_cand) <= 60:
                clean_def = text[0].upper() + text[1:] if text else ""
                if not clean_def.endswith((".", "!", "?")) and clean_def:
                    clean_def += "."
                return clean_cand, clean_def, "tier2_prefix_copula"

        # Check if prefix ends with a colon (e.g. "Action Potential:")
        if pref.endswith(":"):
            candidate = pref[:-1].strip()
            clean_cand = strip_leading_articles(candidate)
            if 2 <= len(clean_cand) <= 60:
                clean_def = text[0].upper() + text[1:] if text else ""
                if not clean_def.endswith((".", "!", "?")) and clean_def:
                    clean_def += "."
                return clean_cand, clean_def, "tier2_prefix_colon"

        # Check trailing noun phrase in prefix
        pref_sentences = [s.strip() for s in re.split(r'[\.\?!;]\s*', pref) if s.strip()]
        if pref_sentences:
            trailing = pref_sentences[-1]
            trailing = re.sub(r'[:\-\—\s]+$', '', trailing).strip()
            clean_trailing = strip_leading_articles(trailing)
            if 3 <= len(clean_trailing) <= 45:
                clean_def = text[0].upper() + text[1:] if text else ""
                if not clean_def.endswith((".", "!", "?")) and clean_def:
                    clean_def += "."
                return clean_trailing, clean_def, "tier2_prefix_trailing"

    # --- Tier 3: Structural Anchor (Zero 'this concept' Guarantee) ---
    # Check if the entire text is a short term (1-5 words, <= 45 chars)
    words = text.split()
    if 1 <= len(words) <= 5 and len(text) <= 45 and not text.endswith("."):
        clean_term = strip_leading_articles(text)
        def_str = f"{clean_term} — core concept under {heading_context}."
        return clean_term, def_str, "tier3_short_term"

    # First clause before punctuation
    first_clause = re.split(r'[,;:\(\)]', text)[0].strip()
    clause_words = first_clause.split()
    if 1 <= len(clause_words) <= 5 and 3 <= len(first_clause) <= 45:
        clean_term = strip_leading_articles(first_clause)
        clean_def = text[0].upper() + text[1:] if text else ""
        if not clean_def.endswith((".", "!", "?")) and clean_def:
            clean_def += "."
        return clean_term, clean_def, "tier3_clause_subject"

    # Final fallback: Structural Heading Anchor
    fallback_term = heading_context if heading_context and heading_context != "General" else "Key Principle"
    clean_def = text[0].upper() + text[1:] if text else ""
    if not clean_def.endswith((".", "!", "?")) and clean_def:
        clean_def += "."
    return fallback_term, clean_def, "tier3_heading_anchor"


# ============================================================================
# 6. SemanticCardParser Implementation
# ============================================================================

class SemanticCardParser:
    """
    Unified card formulation parser enforcing SuperMemo's 20 Rules
    and ANKI_SOP Keyword-Descriptor standards.
    Supports local AI (Ollama) generation with structured JSON schema
    and deterministic 64-pattern fallback parsing.
    """

    def __init__(self, runtime_manager: Optional[Any] = None):
        """
        Initializes parser with an optional OllamaRuntimeManager instance.
        If runtime_manager is None, deterministic fallback parsing is used by default.
        """
        self.runtime_manager = runtime_manager
        self._last_service_check: Optional[float] = None
        self._is_service_ready: bool = False

    def parse_highlight(
        self,
        text: str,
        highlight_color: str,
        heading: str = "General",
        context: str = "",
        paragraph_prefix: str = "",
        domain: str = "general"
    ) -> List[Dict[str, Any]]:
        """
        Main entry point for parsing a highlighted text segment.
        Attempts Ollama semantic parsing first; on failure or veto violation,
        seamlessly executes deterministic fallback parsing.
        """
        clean_input = text.strip() if text else ""
        if not clean_input:
            return []

        # 1. Attempt LLM Parsing via Ollama
        cards = self.parse_with_ollama(clean_input, highlight_color, heading, context, paragraph_prefix, domain=domain)
        if cards:
            # Validate all returned cards against veto conditions
            valid_cards = []
            for c in cards:
                is_valid, _ = is_valid_card(c)
                if is_valid:
                    valid_cards.append(c)
            if valid_cards:
                return valid_cards

        # 2. Fallback to Deterministic Parser
        return self.parse_with_fallback(clean_input, highlight_color, heading, context, paragraph_prefix, domain=domain)

    def parse_with_ollama(
        self,
        text: str,
        highlight_color: str,
        heading: str = "General",
        context: str = "",
        paragraph_prefix: str = "",
        domain: str = "general"
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Parses highlight using Ollama local AI runtime with structured JSON output.
        Returns None if Ollama is unavailable, times out, or returns malformed/vetoed cards.
        """
        if self.runtime_manager is None:
            return None

        # Cached readiness check if runtime_manager provides is_service_ready
        if hasattr(self.runtime_manager, "is_service_ready"):
            import time
            now = time.time()
            if self._last_service_check is None or (now - self._last_service_check) > 5.0:
                self._last_service_check = now
                try:
                    self._is_service_ready = self.runtime_manager.is_service_ready(timeout=0.5)
                except Exception:
                    self._is_service_ready = False
            if not self._is_service_ready:
                return None

        # Prepare user prompt with context and exemplar alignment
        user_prompt = (
            f"Please decompose the following lecture highlight into atomic Anki cards according to SuperMemo 20 Rules:\n\n"
            f"Topic/Heading: {heading}\n"
            f"Domain: {domain}\n"
            f"Highlight Color: {highlight_color} (Green=Definition/Mechanism, Yellow=Important/Threshold)\n"
            f"Preceding Context: {paragraph_prefix or 'None'}\n"
            f"Additional Context: {context or 'None'}\n"
            f"Highlighted Text:\n\"{text}\"\n\n"
            f"Output must strictly follow the JSON schema: {{\"cards\": [...]}}"
        )

        try:
            result = self.runtime_manager.generate_json(
                prompt=user_prompt,
                system_prompt=get_domain_system_prompt(domain),
                temperature=0.1
            )
        except Exception as e:
            logger.warning("Ollama generate_json encountered error: %s", e)
            return None

        if not result or not isinstance(result, dict) or "cards" not in result:
            return None

        raw_cards = result.get("cards", [])
        if not isinstance(raw_cards, list) or len(raw_cards) == 0:
            return None

        expanded_cards: List[Dict[str, Any]] = []
        heading_tag = re.sub(r'[^a-zA-Z0-9_]', '', heading.replace(" ", "_"))[:30]
        base_tags = [heading_tag] if heading_tag else []

        for item in raw_cards:
            if not isinstance(item, dict):
                continue

            card_type = item.get("card_type", "active_recall_qa")
            kw = clean_phrase(item.get("keyword", ""))
            desc = clean_phrase(item.get("descriptor", ""))
            badge = item.get("category_badge", "badge-definition" if highlight_color == "green" else "badge-important")
            ctx = item.get("context", context or heading)
            card_tags = item.get("tags", [])
            merged_tags = list(set(base_tags + card_tags))

            if card_type == "bidirectional_definition":
                # Generate Forward Card (Recall)
                fwd_q = item.get("question") or f"What is the definition of <b>{kw}</b>?"
                fwd_a = item.get("answer") or desc
                fwd_card = {
                    "card_type": "bidirectional_definition",
                    "keyword": kw,
                    "descriptor": desc,
                    "question": fwd_q,
                    "answer": fwd_a,
                    "category_badge": badge,
                    "context": ctx,
                    "tags": list(set(merged_tags + ["definition", "forward"]))
                }
                # Generate Reverse Card (Recognition)
                rev_q = item.get("reverse_question") or f"What term is defined by:<br><i>{desc}</i>"
                rev_a = kw
                rev_card = {
                    "card_type": "bidirectional_definition",
                    "keyword": kw,
                    "descriptor": desc,
                    "question": rev_q,
                    "answer": rev_a,
                    "category_badge": badge,
                    "context": ctx,
                    "tags": list(set(merged_tags + ["definition", "reverse"]))
                }
                expanded_cards.extend([fwd_card, rev_card])

            elif card_type == "cloze":
                cloze_text = item.get("cloze_text") or item.get("question") or ""
                cloze_q = item.get("question") or f"Identify the missing element regarding <b>{kw or heading}</b>:<br>{cloze_text}"
                cloze_a = item.get("answer") or kw
                expanded_cards.append({
                    "card_type": "cloze",
                    "keyword": kw,
                    "descriptor": desc,
                    "question": cloze_q,
                    "answer": cloze_a,
                    "cloze_text": cloze_text,
                    "category_badge": badge,
                    "context": ctx,
                    "tags": list(set(merged_tags + ["cloze", "high_yield"]))
                })

            else:  # active_recall_qa or specialized taxonomies
                q = item.get("question", "")
                a = item.get("answer", "")
                expanded_cards.append({
                    "card_type": "active_recall_qa",
                    "taxonomy": item.get("taxonomy", "active_recall_qa"),
                    "keyword": kw,
                    "descriptor": desc,
                    "question": q,
                    "answer": a,
                    "category_badge": badge,
                    "context": ctx,
                    "tags": list(set(merged_tags + ["high_yield"]))
                })

        # Veto filter: check that no card in expanded_cards has veto violations
        filtered_cards = []
        for c in expanded_cards:
            valid, reason = is_valid_card(c)
            if valid:
                filtered_cards.append(c)
            else:
                logger.warning("Rejecting LLM-generated card due to veto check (%s): %s", reason, c)

        return filtered_cards if filtered_cards else None

    def parse_with_fallback(
        self,
        text: str,
        highlight_color: str,
        heading: str = "General",
        context: str = "",
        paragraph_prefix: str = "",
        domain: str = "general"
    ) -> List[Dict[str, Any]]:
        """
        Deterministic 101-pattern fallback parser.
        Enforces SuperMemo Rule 4 (Atomicity), Rule 5 (Cloze),
        and ANKI_SOP Keyword-Descriptor separation with 0% 'this concept' emissions.
        """
        clean_text = clean_phrase(text)
        if not clean_text:
            return []

        heading_tag = re.sub(r'[^a-zA-Z0-9_]', '', heading.replace(" ", "_"))[:30]
        base_tags = [heading_tag] if heading_tag else []
        ctx_field = context if context else heading
        color_lower = highlight_color.lower().strip() if highlight_color else "green"

        cards: List[Dict[str, Any]] = []

        # --------------------------------------------------------------------
        # Pattern A: Green Highlight (Definitions & Foundational Mechanisms)
        # --------------------------------------------------------------------
        if color_lower == "green":
            term, definition, tier = split_highlight_fallback(clean_text, paragraph_prefix, heading)

            # In quantitative/statistics domains, route to specialized cognitive archetypes
            QUANT_TAXONOMIES = {"test_selection", "assumption_triad", "formula_decomposition", "decision_rule", "r_syntax"}
            if classify_cognitive_taxonomy is not None and formulate_cognitive_cards is not None:
                tax = classify_cognitive_taxonomy(term, definition, context=ctx_field, domain=domain)
                if tax in QUANT_TAXONOMIES or (domain == "statistics" and tax != "term_definition"):
                    cog_cards = formulate_cognitive_cards(
                        term, definition, taxonomy=tax, heading=heading, context=ctx_field, domain=domain, tags=base_tags
                    )
                    if cog_cards:
                        return cog_cards

            # Card 1: Forward (Active Recall: Term -> Definition)
            cards.append({
                "card_type": "bidirectional_definition",
                "taxonomy": "term_definition",
                "keyword": term,
                "descriptor": definition,
                "question": f"What is the definition of <b>{term}</b>?",
                "answer": definition,
                "category_badge": "badge-definition",
                "context": ctx_field,
                "tags": base_tags + ["definition", "forward"]
            })

            # Card 2: Reverse (Active Recognition: Definition -> Term)
            cards.append({
                "card_type": "bidirectional_definition",
                "taxonomy": "term_definition",
                "keyword": term,
                "descriptor": definition,
                "question": f"What term is defined by:<br><i>{definition}</i>",
                "answer": term,
                "category_badge": "badge-definition",
                "context": ctx_field,
                "tags": base_tags + ["definition", "reverse"]
            })
            return cards

        # --------------------------------------------------------------------
        # Pattern B: Yellow Highlight (Important Facts, Thresholds, Findings)
        # --------------------------------------------------------------------
        if color_lower == "yellow":
            # Rule 4: Split compound clauses (e.g. 'whereas', 'while', ';')
            atomic_clauses = split_compound_yellow(clean_text)

            for clause in atomic_clauses:
                # Rule 5: Check if clause contains numerical threshold or percentage
                cloze_candidate = create_cloze_card(clause, heading=heading, context=ctx_field, tags=base_tags)
                if cloze_candidate:
                    cards.append(cloze_candidate)
                    continue

                # Otherwise, extract subject via multi-tier fallback
                term, descriptor, tier = split_highlight_fallback(clause, paragraph_prefix, heading)
                
                if domain == "statistics":
                    sig_label = "statistical role or rule"
                    mech_label = "key statistical principle"
                elif domain == "developmental_psychology":
                    sig_label = "developmental significance"
                    mech_label = "key developmental process"
                elif domain == "professionalism":
                    sig_label = "ethical significance"
                    mech_label = "key ethical rule or principle"
                else:
                    sig_label = "clinical significance"
                    mech_label = "key mechanism"

                # If term is short and clean, create active recall question
                if term and term != heading and term != "Key Principle":
                    cards.append({
                        "card_type": "active_recall_qa",
                        "keyword": term,
                        "descriptor": descriptor,
                        "question": f"What is the {sig_label} of <b>{term}</b>?",
                        "answer": descriptor,
                        "category_badge": "badge-important",
                        "context": ctx_field,
                        "tags": base_tags + ["high_yield"]
                    })
                else:
                    # Heading-anchored active recall question (never raw heading dump)
                    cards.append({
                        "card_type": "active_recall_qa",
                        "keyword": term,
                        "descriptor": descriptor,
                        "question": f"What is the {mech_label} regarding <b>{term}</b>?",
                        "answer": descriptor,
                        "category_badge": "badge-important",
                        "context": ctx_field,
                        "tags": base_tags + ["high_yield"]
                    })

            if cards:
                return cards

        # --------------------------------------------------------------------
        # Pattern C: Other Highlight Colors (Contextual / Secondary)
        # --------------------------------------------------------------------
        term, descriptor, _ = split_highlight_fallback(clean_text, paragraph_prefix, heading)
        cards.append({
            "card_type": "active_recall_qa",
            "keyword": term,
            "descriptor": descriptor,
            "question": f"What is the primary role of <b>{term}</b>?",
            "answer": descriptor,
            "category_badge": "badge-important",
            "context": ctx_field,
            "tags": base_tags + ["secondary"]
        })
        return cards
