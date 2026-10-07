"""
Semantic Card Parser Engine & SuperMemo 20 Rules Knowledge Formulation
Implements LLM-assisted parsing via Ollama and a deterministic 64+ pattern
rule-based fallback parser with multi-tier subject resolution and zero "this concept" emissions.
"""

import os
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
    r"\bresults\s+in\b",
    r"\bresult\s+in\b",
    r"\bleads\s+to\b",
    r"\blead\s+to\b",
    r"\bcauses\b",
    r"\bcause\b",
    r"\bmanifests\s+as\b",
    r"\bmanifest\s+as\b",
    r"\boccurs\s+when\b",
    r"\boccur\s+when\b",
    r"\boccurs\s+after\b",
    r"\boccur\s+after\b",
    r"\boccurs\s+via\b",
    r"\boccur\s+via\b",
    r"\boccurs\s+during\b",
    r"\boccur\s+during\b",
    r"\boccurs\s+with\b",
    r"\boccur\s+with\b",
    r"\boccurs\s+in\b",
    r"\boccur\s+in\b",
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
    r"\bstabilizes\b",
    r"\bstabilize\b",
    r"\bbinds\s+to\b",
    r"\bbind\s+to\b",
    r"\bbinds\s+without\b",
    r"\bbind\s+without\b",
    r"\bbinds\b",
    r"\bbind\b",
    r"\bactivates\b",
    r"\bactivate\b",
    r"\binhibits\b",
    r"\binhibit\b",
    r"\bblocks\b",
    r"\bblock\b",
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

8. GLOBAL DIRECTIVE - APPLICATION OVER ROTE MEMORIZATION:
   - For content-based courses (biology, psychology, pharmacology, etc.), actively transform rote factual highlights into APPLICATION-BASED, SCENARIO-DRIVEN questions.
   - Instead of asking purely for a definition, require the user to apply the concept to a concrete clinical case, real-world example, or physiological mechanic.
   - Automatically embed or request concrete examples for mechanisms, phases, stages, and types.
   - CRITICAL REQUIREMENT: Every generated question MUST explicitly prompt for a concrete example, clinical application, or scenario, and the answer MUST provide one.
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
1. APPLIED PHARMACOKINETICS (ADME): Generate applied, scenario-based cards for Absorption, Distribution, Metabolism, and Elimination. Include the two distinct types of elimination (Zero-order vs First-order kinetics) and provide real-world drug examples for each phase.
2. ADME INTERACTIONS: Generate scenarios testing drug-drug or drug-body interactions at specific stages of ADME (with concrete examples).
3. TYPES OF TOLERANCE: Generate applied cards differentiating types of tolerance (Metabolic/Dispositional, Pharmacodynamic/Cellular, Behavioral/Conditioned, Cross-tolerance, Reverse-tolerance/Sensitization) with concrete examples.
4. DRUG ACTION MECHANISMS: Differentiate at least 3 distinct mechanisms of drug action, explicitly forcing concrete examples for each.
5. RECEPTOR MECHANISMS & AFFINITY: Test agonist, antagonist, and allosteric modulator kinetics, explicitly focusing on binding affinity and receptor interactions.
6. PHARMACODYNAMICS: Focus on efficacy, half-life ($t_{1/2}$), $ED_{50}$, therapeutic index.
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
                    "concrete_example": {
                        "type": "string",
                        "description": "A concrete real-world example, clinical application, or scenario illustrating the concept."
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
                "required": ["card_type", "question", "answer", "category_badge", "context", "tags", "concrete_example"]
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
    """Strips leading English articles (The, A, An), wrapping quotes, and trailing punctuation from a term."""
    clean = re.sub(r'^["\'`“”’‘]+|["\'`“”’‘]+$', '', term.strip()).strip()
    clean = re.sub(r'^(the|a|an)\s+', '', clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r'[\.\s\…:;\-]+$', '', clean).strip()
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
# Failure Mode Elimination & Concept Keyword Validation (Milestone M9)
# ============================================================================

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

INTERROGATIVE_REGEX = re.compile(
    r'^(?:what|why|how|when|where|who|which|can|does|do|is|are|should|could|would)\b',
    re.IGNORECASE
)

RELATIVE_CLAUSE_REGEX = re.compile(
    r'\b(?:in\s+which|by\s+which|where\s+by|whereby|characterized\s+by|'
    r'(?:theorists?|people|individuals?|children|patients?)\s+(?:who|that))\b',
    re.IGNORECASE
)


def is_interrogative_note(text: str) -> bool:
    """
    Determines if a highlighted note is a genuine question/interrogative note (Card 11).
    Excludes definitions that contain colons/copulas with trailing question marks (e.g. 'Term ::: Def ???').
    Excludes declarative conditional statements starting with 'When ...' that lack question marks.
    """
    if not text:
        return False
    clean = clean_phrase(text).strip()
    # If text contains definition separator (:::, :=, : [), it is a definition, not an interrogative
    if ":::" in clean or ":=" in clean or re.search(r':\s*\[', clean):
        return False
    has_question_mark = "?" in clean
    lower = clean.lower()
    # Declarative starting with 'when ' without a question mark is NOT an interrogative
    if lower.startswith("when ") and not has_question_mark:
        return False
    direct_q_starters = (
        "what ", "why ", "how ", "where ", "who ", "which ",
        "can ", "does ", "do ", "is it ", "are there ", "should ",
        "could ", "would ", "is there ", "what are ", "what is "
    )
    if any(lower.startswith(q) for q in direct_q_starters):
        return True
    if lower.startswith("when ") and has_question_mark:
        return True
    if clean.rstrip().endswith("?"):
        if any(c in lower for c in (" is defined as ", " refers to ", " is characterized by ", " represents ")):
            return False
        return True
    return False


def is_valid_concept_keyword(term: str) -> bool:
    """
    Validates whether a string represents a clean, nominal concept keyword
    rather than an action verb phrase, critique, full sentence, or interrogative.
    """
    if not term:
        return False
    clean = clean_phrase(term).strip()
    # Strip wrapping quotes
    clean = re.sub(r'^["\'`“”’‘]+|["\'`“”’‘]+$', '', clean).strip()
    # Strip trailing ellipsis, periods, colons, hyphens
    clean = re.sub(r'[\.\s\…:;\-]+$', '', clean).strip()
    if not clean:
        return False

    words = clean.split()
    if not (1 <= len(words) <= 8 and 2 <= len(clean) <= 65):
        return False
    if any(p in clean for p in ['?', '!', ';']):
        return False

    # Check parens/brackets: reject pure parentheticals "(...)"
    if clean.startswith('(') and clean.endswith(')'):
        return False
    if clean.startswith(('(', '[')):
        # Allow stereoisomer / chemical notation like (R)-, (S)-, (+)-, (-)-, (±)-, [3H]-
        if not re.match(r'^[(\[][0-9A-Za-z\+\-\,\s±]+[)\]]-', clean):
            return False
    elif clean.startswith(('—', '–', '-', '...', ':', '/')):
        return False

    # Disqualify interrogatives
    if '?' in clean or INTERROGATIVE_REGEX.search(clean):
        return False

    # Disqualify action verbs and critique phrases
    if clean.upper() in CRITIQUE_STANDALONE_WORDS or CRITIQUE_ACTION_REGEX.search(clean):
        return False

    # Disqualify relative-clause and definitional framing phrases
    if DEFINITIONAL_FRAMING_REGEX.search(clean) or RELATIVE_CLAUSE_REGEX.search(clean):
        return False

    # Disqualify participle modifier clauses (e.g. 'Neurotransmitter found in the raphe nuclei')
    if re.search(r'\b(?:found|located|produced|synthesized|acting|derived|associated|involved|stored|released)\s+(?:in|by|at|from|with|on)\b', clean, re.I):
        return False

    lower = clean.lower()
    disqualified_leads = (
        'and', 'or', 'while', 'whereas', 'because', 'although', 'since', 'if',
        'in r', 'how do you', 'accomplish', 'begins in', 'begins during',
        'numbers with', 'values with'
    )
    for lead in disqualified_leads:
        if lower == lead or lower.startswith(lead + ' '):
            return False
    return True


def resolve_keyword_descriptor_pair(
    term_candidate: str,
    def_candidate: str,
    term_color: str = "yellow",
    def_color: str = "green"
) -> Tuple[Optional[str], Optional[str]]:
    """
    Dynamically evaluates which highlight is the Concept Keyword and which is the Descriptor
    using is_valid_concept_keyword() and cognitive heuristics.
    Eliminates inverted cards where definitions become questions and terms become answers.
    Returns (keyword, descriptor) or (None, None) if neither is a valid concept keyword or if critique.
    """
    clean_1 = clean_phrase(term_candidate).strip() if term_candidate else ""
    clean_2 = clean_phrase(def_candidate).strip() if def_candidate else ""

    if not clean_1 or not clean_2:
        return None, None

    # Critiques / action verbs cannot be standard definition descriptors or keywords
    if (CRITIQUE_ACTION_REGEX.search(clean_1) or clean_1.upper() in CRITIQUE_STANDALONE_WORDS or
        CRITIQUE_ACTION_REGEX.search(clean_2) or clean_2.upper() in CRITIQUE_STANDALONE_WORDS):
        return None, None

    # Definitional framing or relative clause check: the framed candidate MUST be the descriptor
    is_framing_1 = bool(DEFINITIONAL_FRAMING_REGEX.search(clean_1) or RELATIVE_CLAUSE_REGEX.search(clean_1) or
                        re.match(r'^(?:the|a|an)\s+.*?\b(?:that|which|where|whereby|who|of|in)\b', clean_1, re.I))
    is_framing_2 = bool(DEFINITIONAL_FRAMING_REGEX.search(clean_2) or RELATIVE_CLAUSE_REGEX.search(clean_2) or
                        re.match(r'^(?:the|a|an)\s+.*?\b(?:that|which|where|whereby|who|of|in)\b', clean_2, re.I))

    if is_framing_1 and not is_framing_2:
        return clean_2, clean_1
    if is_framing_2 and not is_framing_1:
        return clean_1, clean_2

    v1 = is_valid_concept_keyword(clean_1)
    v2 = is_valid_concept_keyword(clean_2)

    # Case 1: Exactly one is a valid concept keyword
    if v1 and not v2:
        return clean_1, clean_2
    if v2 and not v1:
        return clean_2, clean_1  # SWAP: eliminates card inversion!

    # Case 2: Both satisfy validity rules -> apply cognitive heuristics
    if v1 and v2:
        w1, w2 = len(clean_1.split()), len(clean_2.split())
        # Heuristic 0: Candidate starts with article (a, an, the) + longer word count -> definition
        art_1 = bool(re.match(r'^(?:the|a|an)\s+', clean_1, re.I))
        art_2 = bool(re.match(r'^(?:the|a|an)\s+', clean_2, re.I))
        if art_1 and not art_2 and w1 > w2:
            return clean_2, clean_1
        if art_2 and not art_1 and w2 > w1:
            return clean_1, clean_2

        # Heuristic A: Significant word count discrepancy (shorter is term, longer is definition)
        if w1 <= 3 and w2 > 3:
            return clean_1, clean_2
        if w2 <= 3 and w1 > 3:
            return clean_2, clean_1
        if w1 >= 5 and w2 <= 4:
            return clean_2, clean_1
        if w2 >= 5 and w1 <= 4:
            return clean_1, clean_2
        if abs(w1 - w2) >= 2:
            if w1 < w2:
                return clean_1, clean_2
            else:
                return clean_2, clean_1

        # Heuristic B: Acronyms or Title Case presence (e.g. "LTP", "GABA")
        has_caps_1 = bool(re.search(r'\b[A-Z]{2,}\b', clean_1))
        has_caps_2 = bool(re.search(r'\b[A-Z]{2,}\b', clean_2))
        if has_caps_1 and not has_caps_2:
            return clean_1, clean_2
        if has_caps_2 and not has_caps_1:
            return clean_2, clean_1

        # Heuristic C: Tie-breaker defaults to Yellow = Term, Green = Descriptor
        if term_color.lower() == "yellow" and def_color.lower() == "green":
            return clean_1, clean_2
        elif def_color.lower() == "yellow" and term_color.lower() == "green":
            return clean_2, clean_1
        return clean_1, clean_2

    # Case 3: Neither is a valid concept keyword
    return None, None


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
    guaranteeing ZERO occurrence of 'this concept' and preventing broken clause/action-verb keywords.

    Resolution Order:
      Framing Bypass: Definitional Framing Early Interception (Card 138 fix)
      Tier 1: Internal Linking Verb Split within highlight text
      Tier 2: Paragraph Prefix Search
      Tier 3: Structural Anchor (Heading / First Clause)
    """
    text = clean_phrase(highlight_text)
    if not text:
        fallback_anchor = heading_context if heading_context and heading_context != "General" else "Key Concept"
        return fallback_anchor, fallback_anchor, "tier3_empty_fallback"

    # --- Framing Bypass: Definitional Framing Early Interception (Card 138 fix) ---
    if DEFINITIONAL_FRAMING_REGEX.search(text):
        clean_def = text[0].upper() + text[1:] if text else ""
        if not clean_def.endswith((".", "!", "?")) and clean_def:
            clean_def += "."

        # Check paragraph prefix for preceding subject (e.g. "Neurogenesis: ")
        if paragraph_prefix:
            pref = clean_phrase(paragraph_prefix)
            if pref.endswith(":"):
                candidate = strip_leading_articles(pref[:-1].strip())
                if is_valid_concept_keyword(candidate):
                    return candidate, clean_def, "framing_prefix_colon"
            pref_match = LINKING_VERBS_REGEX.search(pref)
            if pref_match:
                candidate = strip_leading_articles(pref[:pref_match.start()].strip())
                if is_valid_concept_keyword(candidate):
                    return candidate, clean_def, "framing_prefix_copula"
            pref_sentences = [s.strip() for s in re.split(r'[\.\?!;]\s*', pref) if s.strip()]
            if pref_sentences:
                trailing = pref_sentences[-1]
                trailing = re.sub(r'[:\-\—\s]+$', '', trailing).strip()
                clean_trailing = strip_leading_articles(trailing)
                if is_valid_concept_keyword(clean_trailing):
                    return clean_trailing, clean_def, "framing_prefix_trailing"

        # Structural heading anchor
        anchor = heading_context if heading_context and heading_context != "General" else "Key Principle"
        return anchor, clean_def, "framing_heading_anchor"

    # --- Tier 1: Internal Linking Verb Split ---
    match = LINKING_VERBS_REGEX.search(text)
    if match:
        term_part = text[:match.start()].strip()
        verb_part = match.group(1).strip()
        def_part = text[match.end():].strip()

        # Clean term_part of quotes and trailing dots before checking validity
        clean_cand = re.sub(r'^["\'`“”’‘]+|["\'`“”’‘]+$', '', term_part).strip()
        clean_cand = re.sub(r'[\.\s\…:;\-]+$', '', clean_cand).strip()

        # Check that clean_cand is a valid concept keyword
        if is_valid_concept_keyword(clean_cand) and 2 <= len(clean_cand) <= 65:
            clean_term = strip_leading_articles(clean_cand)
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
            if is_valid_concept_keyword(clean_cand) and 2 <= len(clean_cand) <= 65:
                clean_def = text[0].upper() + text[1:] if text else ""
                if not clean_def.endswith((".", "!", "?")) and clean_def:
                    clean_def += "."
                return clean_cand, clean_def, "tier2_prefix_copula"

        # Check if prefix ends with a colon (e.g. "Action Potential:")
        if pref.endswith(":"):
            candidate = pref[:-1].strip()
            clean_cand = strip_leading_articles(candidate)
            if is_valid_concept_keyword(clean_cand) and 2 <= len(clean_cand) <= 65:
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
            if is_valid_concept_keyword(clean_trailing) and 3 <= len(clean_trailing) <= 65:
                clean_def = text[0].upper() + text[1:] if text else ""
                if not clean_def.endswith((".", "!", "?")) and clean_def:
                    clean_def += "."
                return clean_trailing, clean_def, "tier2_prefix_trailing"

    # --- Tier 3: Structural Anchor (Zero 'this concept' Guarantee) ---
    # Check if the entire text is a short term (1-5 words, <= 55 chars)
    words = text.split()
    if 1 <= len(words) <= 5 and len(text) <= 55 and not text.endswith(".") and is_valid_concept_keyword(text):
        clean_term = strip_leading_articles(text)
        def_str = f"{clean_term} — core concept under {heading_context}."
        return clean_term, def_str, "tier3_short_term"

    # First clause before punctuation if valid keyword
    first_clause = re.split(r'[,;:\(\)]', text)[0].strip()
    clause_words = first_clause.split()
    if 1 <= len(clause_words) <= 6 and 3 <= len(first_clause) <= 55 and is_valid_concept_keyword(first_clause):
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
# 5b. Umbrella Framework & Recursive Sub-Component Decomposition Engine (Rule 6)
# ============================================================================

UMBRELLA_MODELS: Dict[str, Dict[str, Any]] = {
    "developmental_niche": {
        "canonical_name": "Developmental Niche",
        "aliases": [
            "developmental niche", "super and harkness", "super & harkness",
            "three subsystems of the developmental niche", "subsystems of developmental niche"
        ],
        "domain": "developmental_psychology",
        "theorist": "Super & Harkness (1986)",
        "framework_descriptor": (
            "A theoretical framework by Super & Harkness conceptualizing how culture structures child development "
            "through three interacting subsystems surrounding the child: physical and social settings, culturally "
            "regulated customs of childcare, and caretaker psychology."
        ),
        "components": [
            {
                "name": "Physical and Social Settings (Developmental Niche)",
                "short_name": "Physical and Social Settings",
                "tag": "developmental_niche_settings",
                "descriptor": (
                    "The subsystem of Super & Harkness's developmental niche comprising the physical living space, "
                    "household composition, peer presence, family size, and social density shaping a child's daily life."
                ),
                "example": "Living arrangements, household size, multi-generational caregiving, urban vs. rural ecology.",
                "fwd_question": "Within Super & Harkness's developmental niche framework, what constitutes the <b>Physical and Social Settings</b> subsystem?",
                "rev_question": "Which subsystem of Super & Harkness's developmental niche encompasses living arrangements, household density, and the child's daily physical ecology?",
            },
            {
                "name": "Culturally Regulated Customs (Developmental Niche)",
                "short_name": "Culturally Regulated Customs",
                "tag": "developmental_niche_customs",
                "descriptor": (
                    "The subsystem of Super & Harkness's developmental niche consisting of culturally established "
                    "practices of childcare, child-rearing routines, sleeping arrangements, and institutional schooling."
                ),
                "example": "Co-sleeping practices, infant carrying schedules, weaning rituals, formal schooling routines.",
                "fwd_question": "Within Super & Harkness's developmental niche framework, what constitutes the <b>Culturally Regulated Customs</b> subsystem?",
                "rev_question": "Which subsystem of Super & Harkness's developmental niche encompasses child-rearing traditions, infant sleeping practices, and culturally normative care routines?",
            },
            {
                "name": "Psychology of Caretakers (Developmental Niche)",
                "short_name": "Psychology of Caretakers (Parental Ethnotheories)",
                "tag": "developmental_niche_caretaker_psychology",
                "descriptor": (
                    "The subsystem of Super & Harkness's developmental niche encompassing parental belief systems, "
                    "ethnotheories, developmental milestones expectations, and cultural values regarding children."
                ),
                "example": "Parental goals regarding infant independence vs. interdependence, maternal responsiveness styles.",
                "fwd_question": "Within Super & Harkness's developmental niche framework, what constitutes the <b>Psychology of Caretakers</b> (Parental Ethnotheories) subsystem?",
                "rev_question": "Which subsystem of Super & Harkness's developmental niche encompasses parental belief systems, child-rearing values, and ethnotheories?",
            }
        ]
    },
    "ecological_systems": {
        "canonical_name": "Bronfenbrenner's Ecological Systems Theory",
        "aliases": [
            "ecological systems theory", "bronfenbrenner", "bioecological model",
            "ecological systems model"
        ],
        "domain": "developmental_psychology",
        "theorist": "Urie Bronfenbrenner",
        "framework_descriptor": (
            "A contextual developmental theory positing that human development is shaped by interactions "
            "across five nested environmental systems, ranging from direct face-to-face settings to overarching cultural macrosystems."
        ),
        "components": [
            {
                "name": "Microsystem (Ecological Systems Theory)",
                "short_name": "Microsystem",
                "tag": "ecological_microsystem",
                "descriptor": "The innermost environmental layer consisting of immediate, direct, face-to-face interactions and relationships experienced by the developing child.",
                "example": "Immediate family, classroom/school setting, peer group, neighborhood play area.",
                "fwd_question": "In Bronfenbrenner's ecological model, what is the definition of the <b>Microsystem</b>?",
                "rev_question": "In Bronfenbrenner's ecological model, which system consists of the child's immediate, direct face-to-face settings (family, classroom, peers)?",
            },
            {
                "name": "Mesosystem (Ecological Systems Theory)",
                "short_name": "Mesosystem",
                "tag": "ecological_mesosystem",
                "descriptor": "The layer comprising interconnections, linkages, and relationships between two or more of the child's immediate microsystems.",
                "example": "Parent-teacher conferences, collaboration between family and church, connections between home and peer group.",
                "fwd_question": "In Bronfenbrenner's ecological model, what is the definition of the <b>Mesosystem</b>?",
                "rev_question": "In Bronfenbrenner's ecological model, which system represents interactions between two or more of the child's microsystems (e.g., parent-teacher relations)?",
            },
            {
                "name": "Exosystem (Ecological Systems Theory)",
                "short_name": "Exosystem",
                "tag": "ecological_exosystem",
                "descriptor": "Environmental settings that the developing child does not actively inhabit, but which indirectly exert significant influence on their immediate environment.",
                "example": "Parental workplace policies, parental maternity/paternity leave, school board administrative decisions, community welfare services.",
                "fwd_question": "In Bronfenbrenner's ecological model, what is the definition of the <b>Exosystem</b>?",
                "rev_question": "In Bronfenbrenner's ecological model, which system consists of external settings the child never enters but that indirectly affect them (e.g., parental workplace)?",
            },
            {
                "name": "Macrosystem (Ecological Systems Theory)",
                "short_name": "Macrosystem",
                "tag": "ecological_macrosystem",
                "descriptor": "The overarching cultural, subcultural, ideological, socioeconomic, and legal blueprints shaping all underlying ecological systems.",
                "example": "Cultural values of individualism vs. collectivism, national laws, healthcare systems, prevailing economic conditions.",
                "fwd_question": "In Bronfenbrenner's ecological model, what is the definition of the <b>Macrosystem</b>?",
                "rev_question": "In Bronfenbrenner's ecological model, which system comprises the overarching cultural values, legal structures, and economic ideologies of a society?",
            },
            {
                "name": "Chronosystem (Ecological Systems Theory)",
                "short_name": "Chronosystem",
                "tag": "ecological_chronosystem",
                "descriptor": "The temporal dimension encompassing historical events, societal changes, and normative/non-normative life transitions across the life course.",
                "example": "The COVID-19 pandemic, family divorce, technological transitions, growing up during the Great Depression.",
                "fwd_question": "In Bronfenbrenner's ecological model, what is the definition of the <b>Chronosystem</b>?",
                "rev_question": "In Bronfenbrenner's ecological model, which dimension encompasses socio-historical changes and cumulative transitions over developmental time?",
            }
        ]
    },
    "piaget_stages": {
        "canonical_name": "Piaget's Stages of Cognitive Development",
        "aliases": [
            "piaget's stages", "piagetian stages", "stages of cognitive development",
            "four stages of cognitive development"
        ],
        "domain": "developmental_psychology",
        "theorist": "Jean Piaget",
        "framework_descriptor": (
            "A four-stage structural developmental theory positing that children construct mental models of the world "
            "through qualitative reorganizations of cognitive schemas."
        ),
        "components": [
            {
                "name": "Sensorimotor Stage (Piaget)",
                "short_name": "Sensorimotor Stage",
                "tag": "piaget_sensorimotor",
                "descriptor": "The cognitive developmental stage (birth to ~2 years) where infants coordinate sensory perceptions with motor behaviors, culminating in object permanence and deferred imitation.",
                "example": "Searching for a hidden toy under a blanket, circular reactions, A-not-B error resolution.",
                "fwd_question": "What are the core cognitive characteristics of Piaget's <b>Sensorimotor Stage</b> (0–2 years)?",
                "rev_question": "Which Piagetian cognitive stage spans birth to 2 years and centers on coordinating sensory inputs with motor actions and acquiring object permanence?",
            },
            {
                "name": "Preoperational Stage (Piaget)",
                "short_name": "Preoperational Stage",
                "tag": "piaget_preoperational",
                "descriptor": "The cognitive developmental stage (~2 to 7 years) characterized by symbolic thought, language explosion, and imaginative play, but limited by egocentrism, centration, and lack of conservation.",
                "example": "Three-mountain task failure, attributing living qualities to inanimate objects (animism), failing liquid conservation tasks.",
                "fwd_question": "What are the core cognitive characteristics of Piaget's <b>Preoperational Stage</b> (2–7 years)?",
                "rev_question": "Which Piagetian cognitive stage spans ages 2 to 7 and features symbolic representation and pretend play alongside egocentrism and absence of conservation?",
            },
            {
                "name": "Concrete Operational Stage (Piaget)",
                "short_name": "Concrete Operational Stage",
                "tag": "piaget_concrete_operational",
                "descriptor": "The cognitive developmental stage (~7 to 11 years) where children master mental operations on physical/tangible objects, demonstrating conservation, reversibility, decentration, and transitive inference.",
                "example": "Successfully understanding that clay volume remains constant despite shape alteration; seriation of sticks by length.",
                "fwd_question": "What are the core cognitive characteristics of Piaget's <b>Concrete Operational Stage</b> (7–11 years)?",
                "rev_question": "Which Piagetian cognitive stage spans ages 7 to 11 and is marked by logical mental operations on tangible objects, reversibility, and mastery of conservation?",
            },
            {
                "name": "Formal Operational Stage (Piaget)",
                "short_name": "Formal Operational Stage",
                "tag": "piaget_formal_operational",
                "descriptor": "The cognitive developmental stage (age 11+ to adulthood) characterized by abstract hypothetical-deductive reasoning, propositional logic, and systematic scientific problem-solving.",
                "example": "Pendulum problem hypothesis testing, reasoning about hypothetical worlds and abstract moral concepts.",
                "fwd_question": "What are the core cognitive characteristics of Piaget's <b>Formal Operational Stage</b> (11+ years)?",
                "rev_question": "Which Piagetian cognitive stage emerges around age 11 and enables systematic hypothetical-deductive reasoning, abstract thinking, and propositional logic?",
            }
        ]
    },
    "attachment_styles": {
        "canonical_name": "Ainsworth's Attachment Classifications",
        "aliases": [
            "attachment styles", "attachment classifications", "strange situation",
            "mary ainsworth", "attachment patterns"
        ],
        "domain": "developmental_psychology",
        "theorist": "Mary Ainsworth",
        "framework_descriptor": (
            "A taxonomical framework assessing infant-caregiver socio-emotional bonds based on behavioral patterns "
            "exhibited during separation and reunion episodes in the Strange Situation paradigm."
        ),
        "components": [
            {
                "name": "Secure Attachment (Strange Situation)",
                "short_name": "Secure Attachment",
                "tag": "attachment_secure",
                "descriptor": "Attachment pattern where the infant uses the primary caregiver as a secure base for exploration, demonstrates visible distress upon separation, and actively seeks comfort, which readily soothes them upon reunion.",
                "example": "Infant explores toys freely when mother is present, cries when she leaves, and calms quickly with physical contact upon her return.",
                "fwd_question": "What behavioral pattern defines <b>Secure Attachment</b> in Ainsworth's Strange Situation paradigm?",
                "rev_question": "Which attachment classification is characterized by using the parent as a secure base, showing separation distress, and being quickly comforted upon reunion?",
            },
            {
                "name": "Insecure-Avoidant Attachment (Strange Situation)",
                "short_name": "Insecure-Avoidant Attachment",
                "tag": "attachment_avoidant",
                "descriptor": "Attachment pattern where the infant appears indifferent to the caregiver's presence or departure and actively avoids, ignores, or turns away from the caregiver upon reunion despite high internal physiological arousal.",
                "example": "Infant shows little outwardly visible emotion when mother departs and looks away or plays with toys without greeting her upon reunion.",
                "fwd_question": "What behavioral pattern defines <b>Insecure-Avoidant Attachment</b> in Ainsworth's Strange Situation paradigm?",
                "rev_question": "Which attachment classification is characterized by minimal overt distress upon separation and active turning away or ignoring of the caregiver upon reunion?",
            },
            {
                "name": "Insecure-Resistant / Ambivalent Attachment (Strange Situation)",
                "short_name": "Insecure-Resistant / Ambivalent Attachment",
                "tag": "attachment_resistant_ambivalent",
                "descriptor": "Attachment pattern where the infant shows intense anxiety, clings rather than explores, exhibits extreme distress upon separation, and displays contradictory seeking and angry resistance (e.g., hitting or squirming away) upon reunion.",
                "example": "Infant clings to mother, cries inconsolably when left alone, and pushes away or kicks when mother attempts to hold them during reunion.",
                "fwd_question": "What behavioral pattern defines <b>Insecure-Resistant / Ambivalent Attachment</b> in Ainsworth's Strange Situation paradigm?",
                "rev_question": "Which attachment classification is characterized by clinging anxiety, extreme separation panic, and mixed proximity-seeking with angry resistance upon reunion?",
            },
            {
                "name": "Disorganized / Disoriented Attachment (Strange Situation)",
                "short_name": "Disorganized / Disoriented Attachment",
                "tag": "attachment_disorganized",
                "descriptor": "Attachment pattern (identified by Main & Solomon) where the infant lacks a coherent behavioral coping strategy, displaying conflicting behaviors such as freezing, wandering aimlessly, or approaching the parent with head averted.",
                "example": "Infant freezes in a trance-like state midway through approaching the parent; associated with frightening or traumatizing caregiving.",
                "fwd_question": "What behavioral pattern defines <b>Disorganized / Disoriented Attachment</b> in Ainsworth's Strange Situation paradigm?",
                "rev_question": "Which attachment classification is characterized by anomalous behaviors such as freezing, fear, or approaching with averted gaze upon caregiver reunion?",
            }
        ]
    },
    "pharmacokinetics_adme": {
        "canonical_name": "Pharmacokinetic Processes (ADME)",
        "aliases": [
            "adme", "pharmacokinetics", "pharmacokinetic processes",
            "four processes of pharmacokinetics", "drug disposition"
        ],
        "domain": "pharmacology",
        "theorist": "Classical Pharmacology",
        "framework_descriptor": (
            "The four fundamental biological processes (Absorption, Distribution, Metabolism, and Excretion) "
            "governing what the biological organism does to a drug over time."
        ),
        "components": [
            {
                "name": "Absorption (Pharmacokinetics)",
                "short_name": "Absorption",
                "tag": "pk_absorption",
                "descriptor": "The pharmacokinetic process by which an administered drug transfers from its site of administration across biological membranes into systemic blood circulation.",
                "example": "Oral gastrointestinal absorption across mucosal epithelial membranes; sublingual venous absorption.",
                "fwd_question": "Within pharmacokinetics (ADME), what is the definition of <b>Absorption</b>?",
                "rev_question": "Which pharmacokinetic process describes the passage of an administered substance from its route of entry into the systemic circulation?",
            },
            {
                "name": "Distribution (Pharmacokinetics)",
                "short_name": "Distribution",
                "tag": "pk_distribution",
                "descriptor": "The pharmacokinetic process by which a drug reversibly disperses and diffuses throughout bodily fluids, tissues, organs, and target sites.",
                "example": "Penetration of lipid-soluble drugs across the blood-brain barrier; binding of acidic drugs to plasma albumin.",
                "fwd_question": "Within pharmacokinetics (ADME), what is the definition of <b>Distribution</b>?",
                "rev_question": "Which pharmacokinetic process describes the reversible movement and dispersion of a drug between the bloodstream and body tissues?",
            },
            {
                "name": "Metabolism / Biotransformation (Pharmacokinetics)",
                "short_name": "Metabolism / Biotransformation",
                "tag": "pk_metabolism",
                "descriptor": "The pharmacokinetic enzymatic transformation of a lipophilic drug molecule into more polar, water-soluble metabolites primarily catalyzed by hepatic enzymes (e.g., CYP450).",
                "example": "Hepatic Phase I oxidation by CYP3A4; Phase II glucuronidation conjugation.",
                "fwd_question": "Within pharmacokinetics (ADME), what is the definition of <b>Metabolism / Biotransformation</b>?",
                "rev_question": "Which pharmacokinetic process describes the enzymatic alteration of parent drug molecules into polar, excretable metabolites, primarily in the liver?",
            },
            {
                "name": "Excretion / Elimination (Pharmacokinetics)",
                "short_name": "Excretion / Elimination",
                "tag": "pk_excretion",
                "descriptor": "The irreversible pharmacokinetic removal of parent drug molecules and metabolites from the body, primarily via renal filtration and urine formation.",
                "example": "Glomerular filtration and active tubular secretion by the kidneys; biliary excretion into feces.",
                "fwd_question": "Within pharmacokinetics (ADME), what is the definition of <b>Excretion / Elimination</b>?",
                "rev_question": "Which pharmacokinetic process describes the physical clearance and irreversible exit of drug molecules from the body, primarily through the kidneys?",
            }
        ]
    },
    "dopamine_pathways": {
        "canonical_name": "Major Dopaminergic Pathways",
        "aliases": [
            "dopamine pathways", "dopaminergic pathways", "four dopamine pathways",
            "ascending dopamine pathways"
        ],
        "domain": "pharmacology",
        "theorist": "Neuroanatomy / Neuropsychopharmacology",
        "framework_descriptor": (
            "The four primary central nervous system axonal projections that synthesize and transmit dopamine to regulate motor control, incentive motivation, cognitive processing, and neuroendocrine function."
        ),
        "components": [
            {
                "name": "Mesolimbic Pathway (Dopamine)",
                "short_name": "Mesolimbic Pathway",
                "tag": "pathway_mesolimbic",
                "descriptor": "Dopaminergic pathway projecting from the ventral tegmental area (VTA) to the nucleus accumbens and limbic structures, mediating incentive salience, reward reinforcement, and addictive drug craving.",
                "example": "Phasic dopamine surges in the nucleus accumbens triggered by cocaine, amphetamine, or nicotine.",
                "fwd_question": "What anatomical trajectory and functional role defines the <b>Mesolimbic Dopamine Pathway</b>?",
                "rev_question": "Which dopamine pathway projects from the VTA to the nucleus accumbens and serves as the central neural substrate for reward, motivation, and addiction?",
            },
            {
                "name": "Mesocortical Pathway (Dopamine)",
                "short_name": "Mesocortical Pathway",
                "tag": "pathway_mesocortical",
                "descriptor": "Dopaminergic pathway projecting from the ventral tegmental area (VTA) to the dorsolateral and ventromedial prefrontal cortex, subserving executive cognitive functions, working memory, and affective modulation.",
                "example": "Hypofunction of this pathway in schizophrenia produces negative symptoms and executive cognitive deficits.",
                "fwd_question": "What anatomical trajectory and functional role defines the <b>Mesocortical Dopamine Pathway</b>?",
                "rev_question": "Which dopamine pathway projects from the VTA to the prefrontal cortex, regulating executive functioning, working memory, and cognitive control?",
            },
            {
                "name": "Nigrostriatal Pathway (Dopamine)",
                "short_name": "Nigrostriatal Pathway",
                "tag": "pathway_nigrostriatal",
                "descriptor": "Dopaminergic pathway projecting from the substantia nigra pars compacta (SNc) to the dorsal striatum (caudate and putamen), orchestrating motor initiation, extrapyramidal movement, and procedural habit formation.",
                "example": "Degeneration of nigrostriatal dopaminergic neurons results in the cardinal motor signs of Parkinson's disease (resting tremor, rigidity, bradykinesia).",
                "fwd_question": "What anatomical trajectory and functional role defines the <b>Nigrostriatal Dopamine Pathway</b>?",
                "rev_question": "Which dopamine pathway projects from the substantia nigra to the dorsal striatum and regulates voluntary motor movement (degenerating in Parkinson's disease)?",
            },
            {
                "name": "Tuberoinfundibular Pathway (Dopamine)",
                "short_name": "Tuberoinfundibular Pathway",
                "tag": "pathway_tuberoinfundibular",
                "descriptor": "Dopaminergic pathway projecting from the arcuate nucleus of the hypothalamus to the median eminence / pituitary stalk, where dopamine acts tonic-inhibitorily as prolactin-inhibiting factor.",
                "example": "D2 receptor blockade by first-generation antipsychotics disinhibits prolactin release, causing hyperprolactinemia.",
                "fwd_question": "What anatomical trajectory and functional role defines the <b>Tuberoinfundibular Dopamine Pathway</b>?",
                "rev_question": "Which dopamine pathway projects from the hypothalamus to the pituitary gland to inhibit prolactin secretion?",
            }
        ]
    },
    "autonomic_divisions": {
        "canonical_name": "Autonomic Nervous System Divisions",
        "aliases": [
            "autonomic nervous system", "divisions of the autonomic nervous system",
            "ans divisions", "sympathetic and parasympathetic"
        ],
        "domain": "pharmacology",
        "theorist": "Autonomic Physiology",
        "framework_descriptor": (
            "The two reciprocal motor subdivisions of the peripheral nervous system (Sympathetic and Parasympathetic) "
            "that involuntarily regulate homeostatic internal visceral functions and glandular secretion."
        ),
        "components": [
            {
                "name": "Sympathetic Nervous System (ANS)",
                "short_name": "Sympathetic Nervous System",
                "tag": "ans_sympathetic",
                "descriptor": "The thoracolumbar autonomic division that orchestrates the catabolic 'fight-or-flight' stress response via adrenergic neurotransmission (norepinephrine/epinephrine).",
                "example": "Pupillary dilation (mydriasis), bronchodilation, tachycardia, inhibition of digestive peristalsis.",
                "fwd_question": "What physiological functions characterize the <b>Sympathetic Division</b> of the Autonomic Nervous System?",
                "rev_question": "Which autonomic nervous system division coordinates the 'fight-or-flight' stress reaction via norepinephrine and epinephrine?",
            },
            {
                "name": "Parasympathetic Nervous System (ANS)",
                "short_name": "Parasympathetic Nervous System",
                "tag": "ans_parasympathetic",
                "descriptor": "The craniosacral autonomic division that directs anabolic 'rest-and-digest' vegetative conservation via cholinergic neurotransmission (acetylcholine on muscarinic receptors).",
                "example": "Pupillary constriction (miosis), bronchoconstriction, bradycardia, stimulation of salivation and gastrointestinal motility.",
                "fwd_question": "What physiological functions characterize the <b>Parasympathetic Division</b> of the Autonomic Nervous System?",
                "rev_question": "Which autonomic nervous system division directs 'rest-and-digest' vegetative maintenance via acetylcholine acting on muscarinic receptors?",
            }
        ]
    }
}


def decompose_umbrella_model(
    text: str,
    heading: str = "General",
    context: str = "",
    domain: str = "general"
) -> Optional[Dict[str, Any]]:
    """
    Identifies high-level umbrella frameworks, models, and taxonomies (SuperMemo Rule 6: Avoid Sets).
    Unpacks them into:
      1. Overarching framework definition card.
      2. Atomic, separate cards for each constituent sub-component.
    
    Returns structured dictionary or None if text does not represent a known or structured umbrella model.
    """
    if not text:
        return None

    clean_t = clean_phrase(text).lower()
    clean_h = clean_phrase(heading).lower()
    combined_probe = f"{clean_h} {clean_t} {context.lower()}"

    # 1. Match against curated UMBRELLA_MODELS registry
    matched_model_key = None
    for model_key, model_data in UMBRELLA_MODELS.items():
        # Check aliases
        for alias in model_data["aliases"]:
            if alias in combined_probe:
                matched_model_key = model_key
                break
        if matched_model_key:
            break

        # Check domain-specific heuristic indicators
        if model_key == "developmental_niche":
            if "developmental niche" in combined_probe or ("settings" in clean_t and "customs" in clean_t and ("beliefs" in clean_t or "caretaker" in clean_t or "ethnotheor" in clean_t)):
                matched_model_key = model_key
                break

    if matched_model_key:
        model = UMBRELLA_MODELS[matched_model_key]
        m_domain = model.get("domain", domain)
        heading_tag = re.sub(r'[^a-zA-Z0-9_]', '', heading.replace(" ", "_"))[:30]
        base_tags = [heading_tag] if heading_tag and heading_tag != "General" else []
        if m_domain and m_domain not in base_tags:
            base_tags.append(m_domain)

        # Framework card
        c_name = model["canonical_name"]
        f_desc = model["framework_descriptor"]
        fwd_q = f"What is the theoretical definition and framework of the <b>{c_name}</b>?"
        rev_q = f"What theoretical framework is defined as:<br><i>{f_desc}</i>"

        fwd_card = {
            "card_type": "bidirectional_definition",
            "taxonomy": "term_definition",
            "keyword": c_name,
            "descriptor": f_desc,
            "question": fwd_q,
            "answer": f_desc,
            "category_badge": "badge-definition",
            "context": context or heading,
            "tags": list(dict.fromkeys(base_tags + ["umbrella_model", "framework", "forward"]))
        }
        rev_card = {
            "card_type": "bidirectional_definition",
            "taxonomy": "term_definition",
            "keyword": c_name,
            "descriptor": f_desc,
            "question": rev_q,
            "answer": c_name,
            "category_badge": "badge-definition",
            "context": context or heading,
            "tags": list(dict.fromkeys(base_tags + ["umbrella_model", "framework", "reverse"]))
        }

        component_card_pairs = []
        for comp in model["components"]:
            comp_kw = comp["name"]
            comp_short = comp.get("short_name", comp_kw)
            comp_desc = comp["descriptor"]
            comp_ex = comp.get("example", "")
            comp_tag = comp.get("tag", "subcomponent")

            comp_ans = comp_desc
            if comp_ex:
                comp_ans += f"<br><br><b>Concrete Examples:</b> {comp_ex}"

            c_fwd = {
                "card_type": "bidirectional_definition",
                "taxonomy": "term_definition",
                "keyword": comp_short,
                "descriptor": comp_desc,
                "question": comp.get("fwd_question") or f"What constitutes the <b>{comp_kw}</b>?",
                "answer": comp_ans,
                "category_badge": "badge-important",
                "context": f"{c_name} | {heading}",
                "tags": list(dict.fromkeys(base_tags + ["umbrella_model", "decomposed_subcomponent", comp_tag, "forward"]))
            }
            c_rev = {
                "card_type": "bidirectional_definition",
                "taxonomy": "term_definition",
                "keyword": comp_short,
                "descriptor": comp_desc,
                "question": comp.get("rev_question") or f"What component is defined by:<br><i>{comp_desc}</i>",
                "answer": comp_short,
                "category_badge": "badge-important",
                "context": f"{c_name} | {heading}",
                "tags": list(dict.fromkeys(base_tags + ["umbrella_model", "decomposed_subcomponent", comp_tag, "reverse"]))
            }
            component_card_pairs.extend([c_fwd, c_rev])

        all_cards = [fwd_card, rev_card] + component_card_pairs
        return {
            "model_key": matched_model_key,
            "canonical_name": c_name,
            "framework_cards": [fwd_card, rev_card],
            "component_cards": component_card_pairs,
            "all_cards": all_cards
        }

    # 2. Dynamic pattern matching for unlisted multi-part lists in text
    list_intro = re.search(
        r'([A-Z][a-zA-Z0-9\s\(\)-]{2,40})\s+(?:consists of|comprises|is composed of|has|is divided into)\s+'
        r'(?:three|four|five|six|\d+)\s+(?:main\s+)?(?:components|subsystems|parts|stages|phases|elements|pillars|dimensions)\b(?::|—|-)?\s*(.*)',
        text,
        re.IGNORECASE | re.DOTALL
    )
    if list_intro:
        framework_title = list_intro.group(1).strip()
        body = list_intro.group(2).strip()
        # Parse numbered or bulleted items
        raw_items = re.split(r'(?:\(\d+\)|\b\d+[\.\)]\s+|[•\*\—\–]\s*)', body)
        parsed_items = [it.strip() for it in raw_items if len(it.strip()) > 8]
        if len(parsed_items) >= 2:
            heading_tag = re.sub(r'[^a-zA-Z0-9_]', '', heading.replace(" ", "_"))[:30]
            base_tags = [heading_tag] if heading_tag and heading_tag != "General" else []
            if domain and domain != "general":
                base_tags.append(domain)

            f_desc = f"Multifaceted framework comprising {len(parsed_items)} core components: {clean_phrase(text)}."
            fwd_card = {
                "card_type": "bidirectional_definition",
                "taxonomy": "term_definition",
                "keyword": framework_title,
                "descriptor": f_desc,
                "question": f"What is the overall framework and structure of <b>{framework_title}</b>?",
                "answer": f_desc,
                "category_badge": "badge-definition",
                "context": context or heading,
                "tags": list(dict.fromkeys(base_tags + ["umbrella_model", "framework", "forward"]))
            }
            rev_card = {
                "card_type": "bidirectional_definition",
                "taxonomy": "term_definition",
                "keyword": framework_title,
                "descriptor": f_desc,
                "question": f"What framework is defined by:<br><i>{f_desc}</i>",
                "answer": framework_title,
                "category_badge": "badge-definition",
                "context": context or heading,
                "tags": list(dict.fromkeys(base_tags + ["umbrella_model", "framework", "reverse"]))
            }

            component_card_pairs = []
            for idx, item_str in enumerate(parsed_items, 1):
                clean_item = clean_phrase(item_str)
                # Check for "Item Name: Description"
                colon_split = re.match(r'^([^:—–]{2,35})(?::|—|–)\s*(.*)', clean_item)
                if colon_split:
                    comp_name = colon_split.group(1).strip()
                    comp_desc = colon_split.group(2).strip()
                else:
                    words = clean_item.split()
                    comp_name = " ".join(words[:3]) if len(words) > 3 else clean_item
                    comp_desc = clean_item

                if not comp_desc.endswith(('.', '!', '?')):
                    comp_desc += '.'

                c_fwd = {
                    "card_type": "bidirectional_definition",
                    "taxonomy": "term_definition",
                    "keyword": f"{framework_title}: {comp_name}",
                    "descriptor": comp_desc,
                    "question": f"Within the <b>{framework_title}</b> framework, what is the role and definition of <b>{comp_name}</b>?",
                    "answer": comp_desc,
                    "category_badge": "badge-important",
                    "context": f"{framework_title} | {heading}",
                    "tags": list(dict.fromkeys(base_tags + ["umbrella_model", "decomposed_subcomponent", "forward"]))
                }
                c_rev = {
                    "card_type": "bidirectional_definition",
                    "taxonomy": "term_definition",
                    "keyword": comp_name,
                    "descriptor": comp_desc,
                    "question": f"Within the <b>{framework_title}</b> framework, which component is defined by:<br><i>{comp_desc}</i>",
                    "answer": comp_name,
                    "category_badge": "badge-important",
                    "context": f"{framework_title} | {heading}",
                    "tags": list(dict.fromkeys(base_tags + ["umbrella_model", "decomposed_subcomponent", "reverse"]))
                }
                component_card_pairs.extend([c_fwd, c_rev])

            all_cards = [fwd_card, rev_card] + component_card_pairs
            return {
                "model_key": re.sub(r'[^a-zA-Z0-9_]', '_', framework_title.lower()),
                "canonical_name": framework_title,
                "framework_cards": [fwd_card, rev_card],
                "component_cards": component_card_pairs,
                "all_cards": all_cards
            }

    return None


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

        # Auto-infer domain from heading when no explicit domain is provided.
        # Ensures callers/tests passing heading= without domain= get correct
        # domain-aware phrasing (e.g. "applied definition" for pharmacology).
        if domain == "general" and heading:
            heading_lower = heading.lower()
            if any(k in heading_lower for k in ("pharmacology", "pharmacokinetic", "pharmacodynamic", "drugs", "drug")):
                domain = "pharmacology"
            elif any(k in heading_lower for k in ("developmental", "development", "lifespan", "piaget", "erikson")):
                domain = "developmental_psychology"
            elif any(k in heading_lower for k in ("statistic", "quantitative", "psyc 3031", "r syntax")):
                domain = "statistics"
            elif any(k in heading_lower for k in ("professionalism", "ethics", "professional", "psyc 3000")):
                domain = "professionalism"

        # 0. Check for Umbrella Model Decomposition (Rule 6: Avoid Sets)
        umbrella_res = self.decompose_umbrella_model(clean_input, heading=heading, context=context, domain=domain)
        if umbrella_res and umbrella_res.get("all_cards"):
            return umbrella_res["all_cards"]

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

    def decompose_umbrella_model(
        self,
        text: str,
        heading: str = "General",
        context: str = "",
        domain: str = "general"
    ) -> Optional[Dict[str, Any]]:
        """Decomposes an umbrella model or multi-part framework into atomic sub-components."""
        return decompose_umbrella_model(text, heading=heading, context=context, domain=domain)

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
            f"CRITICAL CONSTRAINTS (ZERO-TAUTOLOGY):\n"
            f"1. For Green highlights (Definitions): Use card_type 'bidirectional_definition' with 'keyword' (the term, 1-4 words) and 'descriptor' (the clean definition). Question and answer MUST NOT be identical.\n"
            f"2. For Yellow highlights (Concepts): 'question' must be an active recall question testing the concept, and 'answer' must be the explanation. NEVER repeat the text as the question with a question mark.\n"
            f"3. Any card where Question == Answer will be rejected immediately.\n\n"
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
                
                if "concrete_example" in item and item["concrete_example"]:
                    fwd_a += f"<br><br><b>Example/Application:</b> {item['concrete_example']}"
                    if "example" not in fwd_q.lower() and "application" not in fwd_q.lower():
                        fwd_q += " (Include a concrete example/application)"
                fwd_card = {
                    "card_type": "bidirectional_definition",
                    "keyword": kw,
                    "descriptor": desc,
                    "question": fwd_q,
                    "answer": fwd_a,
                    "category_badge": badge,
                    "context": ctx,
                    "tags": list(set(merged_tags + ["definition", "forward", "applied"]))
                }
                # Generate Reverse Card (Recognition)
                rev_q = item.get("reverse_question") or f"What term or concept is applied/defined by:<br><i>{desc}</i>"
                rev_a = kw
                rev_card = {
                    "card_type": "bidirectional_definition",
                    "keyword": kw,
                    "descriptor": desc,
                    "question": rev_q,
                    "answer": rev_a,
                    "category_badge": badge,
                    "context": ctx,
                    "tags": list(set(merged_tags + ["definition", "reverse", "applied"]))
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
                
                if "concrete_example" in item and item["concrete_example"]:
                    a += f"<br><br><b>Example/Application:</b> {item['concrete_example']}"
                    if "example" not in q.lower() and "application" not in q.lower():
                        q += " (Include a concrete example/application)"
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
            if re.search(r'\b(e\.g\.|for example|such as|for instance|like)\b', definition, re.IGNORECASE):
                fwd_q = f"What is the definition and a concrete example of <b>{term}</b>?"
            elif domain in ("pharmacology", "developmental_psychology"):
                fwd_q = f"What is the applied definition of <b>{term}</b>?"
            else:
                fwd_q = f"What is the definition of <b>{term}</b>?"

            cards.append({
                "card_type": "bidirectional_definition",
                "taxonomy": "term_definition",
                "keyword": term,
                "descriptor": definition,
                "question": fwd_q,
                "answer": definition,
                "category_badge": "badge-definition",
                "context": ctx_field,
                "tags": base_tags + ["definition", "forward", "applied"]
            })

            rev_q = f"What term or concept is applied/defined by:<br><i>{definition}</i>" if domain in ("pharmacology", "developmental_psychology") else f"What term is defined by:<br><i>{definition}</i>"
            cards.append({
                "card_type": "bidirectional_definition",
                "taxonomy": "term_definition",
                "keyword": term,
                "descriptor": definition,
                "question": rev_q,
                "answer": term,
                "category_badge": "badge-definition",
                "context": ctx_field,
                "tags": base_tags + ["definition", "reverse", "applied"]
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

                # Check for interrogative / rhetorical question in clause (e.g. "What constitutes Abuse????? (not so simple)")
                if is_interrogative_note(clause):
                    paren_match = re.search(r'[\(\[](.*?)[\)\]]', clause)
                    raw_q = re.sub(r'[\(\[].*?[\)\]]', '', clause).strip()
                    raw_q = re.sub(r'\s*\?+', '', raw_q).strip()
                    if raw_q:
                        raw_q += '?'
                    anchor_ctx = heading if heading and heading != "General" else "Core Principle"
                    ans_text = ""
                    if paren_match:
                        ans_text = paren_match.group(1).strip()
                    elif paragraph_prefix and not any(paragraph_prefix.lower().startswith(w) for w in ('what', 'why', 'how', 'when', 'where', 'who', 'which')):
                        ans_text = paragraph_prefix.strip(" :-")
                    elif context and context != heading:
                        ans_text = context.strip()

                    norm_q = re.sub(r'[^a-z0-9]', '', raw_q.lower())
                    norm_a = re.sub(r'[^a-z0-9]', '', ans_text.lower()) if ans_text else ""
                    if not ans_text or norm_q == norm_a or (norm_a in norm_q and len(norm_a) >= 8):
                        ans_text = f"Key criteria, definition, and standards governing {anchor_ctx}."

                    if not ans_text.endswith(('.', '!', '?')):
                        ans_text += '.'
                    cards.append({
                        "card_type": "active_recall_qa",
                        "keyword": anchor_ctx,
                        "descriptor": ans_text,
                        "question": f"Regarding <b>{anchor_ctx}</b>: {raw_q}",
                        "answer": ans_text,
                        "category_badge": "badge-important",
                        "context": ctx_field,
                        "tags": base_tags + ["high_yield"]
                    })
                    continue

                # Otherwise, extract subject via multi-tier fallback
                term, descriptor, tier = split_highlight_fallback(clause, paragraph_prefix, heading)
                
                if domain == "statistics":
                    sig_label = "applied statistical role"
                    mech_label = "applied statistical principle"
                elif domain == "developmental_psychology":
                    sig_label = "applied developmental significance"
                    mech_label = "applied developmental process"
                elif domain == "professionalism":
                    sig_label = "applied ethical significance"
                    mech_label = "applied ethical rule or principle"
                elif domain == "pharmacology":
                    sig_label = "pharmacokinetic/pharmacodynamic application"
                    mech_label = "applied physiological mechanism"
                else:
                    sig_label = "concrete clinical application or significance"
                    mech_label = "applied mechanism or real-world example"

                # If term is short and clean, create active recall question
                if term and term != heading and term != "Key Principle" and is_valid_concept_keyword(term):
                    cards.append({
                        "card_type": "active_recall_qa",
                        "keyword": term,
                        "descriptor": descriptor,
                        "question": f"What is the {sig_label} and a concrete example of <b>{term}</b>?" if re.search(r'\\b(e\\.g\\.|for example|such as|for instance|like)\\b', descriptor, re.IGNORECASE) else f"What is the {sig_label} of <b>{term}</b>?",
                        "answer": descriptor,
                        "category_badge": "badge-important",
                        "context": ctx_field,
                        "tags": base_tags + ["high_yield", "applied"]
                    })
                else:
                    # Heading-anchored active recall question (never raw heading dump)
                    cards.append({
                        "card_type": "active_recall_qa",
                        "keyword": term,
                        "descriptor": descriptor,
                        "question": f"What is the {mech_label} and a concrete example regarding <b>{term}</b>?" if re.search(r'\\b(e\\.g\\.|for example|such as|for instance|like)\\b', descriptor, re.IGNORECASE) else f"What is the {mech_label} regarding <b>{term}</b>?",
                        "answer": descriptor,
                        "category_badge": "badge-important",
                        "context": ctx_field,
                        "tags": base_tags + ["high_yield", "applied"]
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
            "question": f"What is the applied role and a concrete example of <b>{term}</b>?" if re.search(r'\\b(e\\.g\\.|for example|such as|for instance|like)\\b', descriptor, re.IGNORECASE) else f"What is the applied role of <b>{term}</b>?",
            "answer": descriptor,
            "category_badge": "badge-important",
            "context": ctx_field,
            "tags": base_tags + ["secondary", "applied"]
        })
        return cards
