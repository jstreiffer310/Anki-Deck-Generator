"""
test_domain_and_math_pipeline.py — Verification of Domain Routing & Quantitative Archetypes
Tests domain auto-detection, MathJax and code preservation, operator-sensitive deduplication,
and the 6 quantitative card archetypes for statistics and empirical methodology.
"""

import pytest
from pathlib import Path
from scripts.card_validator import (
    CardSanitizer,
    CardDeduplicator,
    ContentShield,
    classify_cognitive_taxonomy,
    formulate_cognitive_cards,
    validate_card,
    strip_html_tags,
)
from scripts.semantic_parser import (
    SemanticCardParser,
    get_domain_system_prompt,
    LINKING_VERBS_REGEX,
)
from scripts.extract_and_generate import (
    detect_course_domain,
    synthesize_cards,
    ANKI_MODEL,
    ANKI_CLOZE_MODEL,
)


class TestDomainAutoDetection:
    """Verifies that course paths, codes, titles, and text samples route to the correct domain."""

    def test_course_code_mapping(self):
        assert detect_course_domain("", explicit_class="PSYC 3031") == "statistics"
        assert detect_course_domain("", explicit_class="PSYC 2030") == "statistics"
        assert detect_course_domain("", explicit_class="PSYC 3590") == "pharmacology"
        assert detect_course_domain("", explicit_class="PSYC 2110") == "developmental_psychology"
        assert detect_course_domain("", explicit_class="PSYC 3000") == "professionalism"

    def test_folder_path_detection(self):
        path_3031 = r"H:\My Drive\Classes\F PSYC 3031  Intermediate Statistics I"
        assert detect_course_domain(path_3031) == "statistics"

        path_3590 = r"H:\My Drive\Classes\F PSYC 3590  Drugs & Behaviour"
        assert detect_course_domain(path_3590) == "pharmacology"

        path_2110 = r"H:\My Drive\Classes\F PSYC 2110  Developmental Psychology"
        assert detect_course_domain(path_2110) == "developmental_psychology"

        path_3000 = r"H:\My Drive\Classes\Y PSYC 3000  Professionalism & Communication"
        assert detect_course_domain(path_3000) == "professionalism"

    def test_text_sample_fallback(self):
        stats_sample = "In this lecture we conduct ANOVA, check homoscedasticity using Levene's test, and write R scripts using dplyr."
        assert detect_course_domain("", text_sample=stats_sample) == "statistics"

        pharma_sample = "Agonists bind to the receptor and trigger an intracellular signaling cascade with high bioavailability."
        assert detect_course_domain("", text_sample=pharma_sample) == "pharmacology"

        dev_sample = "Piaget proposed that children in the sensorimotor stage develop object permanence through scaffolding."
        assert detect_course_domain("", text_sample=dev_sample) == "developmental_psychology"


class TestMathJaxAndCodePreservation:
    """Verifies that mathematical inequalities, LaTeX formulas, and R code are never corrupted."""

    @pytest.fixture
    def sanitizer(self):
        return CardSanitizer()

    def test_content_shield_tokenization(self):
        shield = ContentShield()
        raw = "Reject $H_0$ if $p < .05$ or when using `t.test()`."
        shielded = shield.shield(raw)
        assert "$p < .05$" not in shielded
        assert "`t.test()`" not in shielded
        assert "____SHIELD_" in shielded

        unshielded = shield.unshield(shielded)
        assert unshielded == raw

    def test_strip_html_tags_preserves_math_inequalities(self):
        raw = "When $p < .05$, we reject $H_0$. If $p > .05$, we fail to reject."
        stripped = strip_html_tags(raw)
        assert stripped == raw
        assert "< .05" in stripped
        assert "> .05" in stripped

    def test_sanitizer_preserves_latex_and_code(self, sanitizer):
        card = {
            "question": "What is the decision rule for `aov()` when $p < .05$?",
            "answer": "Reject the null hypothesis: $$\\mu_1 = \\mu_2 = \\dots = \\mu_k$$"
        }
        clean = sanitizer.sanitize(card)
        assert "`aov()`" in clean["question"]
        assert "$p < .05$" in clean["question"]
        assert "$$\\mu_1 = \\mu_2 = \\dots = \\mu_k$$" in clean["answer"]
        # Ensure trailing period was NOT appended directly to the display math
        assert not clean["answer"].endswith("$$ .")

    def test_sanitizer_quote_and_backtick_coexistence(self, sanitizer):
        # normalize_quotes alone handles curly quotes
        raw = "“Estimated mean” is `mean(x, na.rm = TRUE)`."
        clean = sanitizer.sanitize_text(raw)
        assert '"Estimated mean"' in clean
        assert "`mean(x, na.rm = TRUE)`" in clean


class TestOperatorSensitiveDeduplication:
    """Verifies that opposite mathematical claims are not falsely collapsed by signature deduplication."""

    @pytest.fixture
    def deduplicator(self):
        return CardDeduplicator()

    def test_different_inequality_operators_produce_distinct_signatures(self, deduplicator):
        c1 = {"question": "What happens when $p < .05$?", "answer": "Reject H0."}
        c2 = {"question": "What happens when $p > .05$?", "answer": "Fail to reject H0."}

        sig1 = deduplicator.get_signature(c1)
        sig2 = deduplicator.get_signature(c2)

        assert sig1 != sig2
        unique, removed = deduplicator.deduplicate([c1, c2], return_count=True)
        assert len(unique) == 2
        assert removed == 0

    def test_subtraction_vs_addition_distinct_signatures(self, deduplicator):
        c_minus = {"question": "Calculate degrees of freedom: $N - 1$", "answer": "Sample df."}
        c_plus = {"question": "Calculate degrees of freedom: $N + 1$", "answer": "Hypothetical df."}

        sig_minus = deduplicator.get_signature(c_minus)
        sig_plus = deduplicator.get_signature(c_plus)

        assert sig_minus != sig_plus


class TestQuantitativeCardArchetypes:
    """Verifies cognitive taxonomy classification and formulation for university quantitative statistics."""

    def test_classify_test_selection(self):
        tax = classify_cognitive_taxonomy(
            "Repeated Measures ANOVA",
            "Comparing mean reaction times across 3 time points in the same participants",
            domain="statistics"
        )
        assert tax == "test_selection"

    def test_formulate_test_selection_cards(self):
        cards = formulate_cognitive_cards(
            "One-Way ANOVA",
            "Testing mean differences across 3 or more independent treatment groups",
            domain="statistics"
        )
        assert len(cards) == 2
        # Card 1 should ask for test selection
        assert any("Which statistical test should be selected" in c["question"] for c in cards)
        # Card 2 should ask for design conditions
        assert any("Under what study design conditions" in c["question"] for c in cards)

    def test_classify_and_formulate_assumption_triad(self):
        tax = classify_cognitive_taxonomy(
            "Sphericity",
            "Mauchly's test is used; apply Greenhouse-Geisser correction if violated.",
            domain="statistics"
        )
        assert tax == "assumption_triad"
        cards = formulate_cognitive_cards(
            "Sphericity",
            "Assessed via Mauchly's test; apply Greenhouse-Geisser correction if violated.",
            domain="statistics"
        )
        assert len(cards) >= 1
        assert "assumption" in cards[0]["question"].lower()

    def test_classify_and_formulate_r_syntax(self):
        tax = classify_cognitive_taxonomy(
            "dplyr::mutate()",
            "Creates new variables or modifies existing ones in a data frame.",
            domain="statistics"
        )
        assert tax == "r_syntax"
        cards = formulate_cognitive_cards(
            "dplyr::mutate()",
            "Computes and adds new columns to a tibble.",
            domain="statistics"
        )
        assert len(cards) == 2
        assert any("R syntax" in c["question"] or "R function" in c["question"] for c in cards)

    def test_classify_and_formulate_decision_rule(self):
        tax = classify_cognitive_taxonomy(
            "Reject Null Hypothesis",
            "When the calculated p-value is strictly less than alpha (.05).",
            domain="statistics"
        )
        assert tax == "decision_rule"


class TestFullStatsDeckSynthesis:
    """End-to-end verification of synthesizing structured lecture highlights in statistics domain."""

    def test_stats_synthesis_produces_valid_atomic_cards(self):
        structured_data = [
            {
                "heading": "ANOVA Assumptions",
                "full_paragraph": "Homoscedasticity requires equal population variances: tested by Levene's test, remediated by Welch's ANOVA.",
                "highlights": [
                    {
                        "category": "green",
                        "raw_color": "green",
                        "text": "Homoscedasticity requires equal population variances: tested by Levene's test, remediated by Welch's ANOVA."
                    }
                ]
            },
            {
                "heading": "R Data Manipulation",
                "full_paragraph": "The mutate() function from dplyr creates new calculated variables.",
                "highlights": [
                    {
                        "category": "green",
                        "raw_color": "green",
                        "text": "dplyr::mutate() is used to add new variables while preserving existing rows."
                    }
                ]
            },
            {
                "heading": "Alpha Threshold",
                "full_paragraph": "Statistical significance threshold: reject H0 when p < .05.",
                "highlights": [
                    {
                        "category": "yellow",
                        "raw_color": "yellow",
                        "text": "Reject H0 when p < .05"
                    }
                ]
            }
        ]

        cards = synthesize_cards(structured_data, deck_tags=["stats_week1"], domain="statistics")
        assert len(cards) >= 3

        for c in cards:
            is_valid, issues = validate_card(c)
            assert is_valid is True, f"Card failed validation: {c} Issues: {issues}"
            assert "statistics" in c.get("tags", [])

    def test_anki_models_contain_mathjax_script(self):
        # Verify both models have MathJax configuration in question format
        qfmt_model = ANKI_MODEL.templates[0]["qfmt"]
        assert "MathJax" in qfmt_model
        assert "tex2jax" in qfmt_model

        qfmt_cloze = ANKI_CLOZE_MODEL.templates[0]["qfmt"]
        assert "MathJax" in qfmt_cloze
        assert "tex2jax" in qfmt_cloze
