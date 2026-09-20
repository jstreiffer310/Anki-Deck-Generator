# Anki Deck Generation: Standard Operating Procedures (SOP)

## 1. Core Principles (Based on SuperMemo's 20 Rules)
1. **Minimum Information Principle**: Keep cards as atomic as possible. One card = one specific concept, mechanism, or definition.
2. **Do Not Learn if You Do Not Understand**: Notes must be digested and simplified *before* they become cards. Avoid raw copy-pasting of dense paragraphs.
3. **Active Recall**: The question must force the brain to actively retrieve the answer, rather than just passively recognizing it.
4. **Bidirectionality**: For fundamental vocabulary and definitions, cards should be tested in both directions (Term -> Definition AND Definition -> Term).
5. **The Cognitive Justification**: This principle is the core justification for why our pipeline strictly enforces the keyword-descriptor format and utilizes bidirectional generation:
   - When the **Keyword** is the hint (Question) and the target is the Descriptor (Answer), the user engages in **Recall** (stronger memory, generating the definition from scratch).
   - When the **Descriptor (Definition)** is the hint (Question) and the target is the Keyword (Answer), the user engages only in **Recognition** (weaker memory, as the context heavily hints at the term).
6. **Contextual Anchoring**: Provide a "Context" field to prevent orphan knowledge (e.g., specifying which brain region or chemical pathway a concept belongs to).

## 2. Color-Coding Semantics & Card Types

The extraction pipeline translates specific highlight colors into structural Anki card types.

### Green Highlights (Definitions, Explanations, Mechanisms)
- **Primary Use**: Establishing foundational knowledge and vocabulary.
- **Card Generation Logic**:
  - *Pattern A (Adjacent Yellow+Green)*: Yellow (Term) + Green (Definition) -> Creates a **Bidirectional Definition Card**.
    - Card 1: `What is the definition of [Yellow Term]?` -> `[Green Definition]`
    - Card 2: `What term is defined by: [Green Definition]?` -> `[Yellow Term]`
  - *Pattern B (Standalone Green)*: An isolated green highlight (e.g., "Positive Mutations"). 
    - Card: **Concept Identification / Direct Recall** -> `Explain or Define: [Green Highlight]`

### Yellow Highlights (Important Concepts, Key Terms, High-Yield Facts)
- **Primary Use**: High-priority relationships, thresholds, or critical takeaways.
- **Card Generation Logic**:
  - *Pattern A (Standalone Yellow)*: Creates an **Active Recall Card**. 
    - If it's a short phrase: `Identify / Explain the significance of: [Yellow Highlight]`
    - If it's a factual statement: Consider generating a Cloze deletion if applicable, or a direct Question/Answer.

### Other Colors (Context, Nuance, Examples)
- **Primary Use**: Secondary information that supports the primary card but shouldn't be the focal point of recall.
- **Card Generation Logic**: Routed directly to the **Context / Notes** field on the back of the card. It provides background info when reviewing the card, but is not graded.

## 3. Handling Edge Cases & Highlight Breaks
- **Whitespace / Punctuation Gaps**: If a single highlight is interrupted by an unhighlighted space, comma, or colon, the script should merge them into a single logical block to prevent fragmented cards (e.g., treating "Positive Mutations" and its definition as one unified concept if they were intended as Pattern A).
- **Overly Long Highlights**: If a highlight exceeds 500 characters, it violates the Minimum Information Principle. The pipeline should issue a warning or attempt to segment it.
- **The "this concept" Fallback Problem & Solution**: Highlighting an entire sentence in green (e.g., "Basic developmental science focuses on description...") causes the script to fail to find a preceding subject, which previously caused a fallback to asking "Define / What is this concept?". The pipeline's solution is to use regex to parse internal linking verbs (`is`, `focuses on`, `refers to`) within the green highlight, splitting the sentence into a distinct Keyword and Descriptor.

## 4. Cognitive Taxonomies & Rich Card Patterns
Beyond standard vocabulary definitions, the pipeline supports domain-specific cognitive formulations:
- **Function → Structure**: Testing anatomical or physiological substrate (e.g., `What brain structure is responsible for [Function]?` -> `[Structure]`).
- **Concept → Mechanism**: Highlighting the underlying process or biological cascade.
- **Example → Category / Principle**: Testing inductive reasoning from a clinical case study or experimental observation to the overarching principle.

## 5. Input Ingestion & Quality Validation Guardrails
- **Polymorphic Ingestion**: The CLI seamlessly accepts local `.docx` files, Google Docs URLs (`https://docs.google.com/document/d/...`), or bare Document IDs. When using Google Docs, text runs and their background highlight colors (`textRun.textStyle.backgroundColor`) are extracted directly via the Google Docs API.
- **Automated Validation & Sanitization (`card_validator.py`)**:
  - *Length Thresholds*: Rejects cards with front fields shorter than 5 characters or back fields shorter than 3 characters, and flags cards exceeding atomic length limits.
  - *Placeholder Veto*: Automatically filters out cards with vague/unhelpful content (e.g., "Review this concept", "content needs verification", or empty definitions).
  - *Deduplication*: Strips exact and near-duplicate question/answer pairs before `.apkg` compilation.
  - *Sanitization*: Strips stray CSS blocks, embedded priority badges, parenthetical figure citations (e.g., `(Figure 2.1)`), and normalizes smart quotes/whitespace.
- **AnkiConnect Auto-Injection & Google Drive Sync**: Compiled `.apkg` packages are placed in `Decks/`, synchronized directly to `H:\My Drive\Admin\Anki Decks\`, and injected automatically into the user's running Anki instance via `localhost:8765`.
