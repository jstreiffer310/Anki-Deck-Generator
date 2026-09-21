# Anki Deck Generation: Standard Operating Procedures (SOP)
> **Version 2.0** — Updated after multi-class empirical audit across Statistics, Pharmacology, Developmental Psychology, and Professionalism domains.

---

## 1. Core Principles (SuperMemo's 20 Rules)

1. **Minimum Information Principle** (Rule 4): One card = one atomic concept, mechanism, or definition. Never bundle more than one retrievable fact per card.
2. **Do Not Learn if You Do Not Understand** (Rule 1): Notes must be digested before becoming cards. Raw copy-pasted dense paragraphs are rejected.
3. **Active Recall** (Rule 5): Questions must force active retrieval, never passive recognition. The answer must not be recoverable from the question alone.
4. **Bidirectionality** (Rule 14): For fundamental vocabulary and definitions, always generate both directions: Term → Definition AND Definition → Term. This is mandatory for all Pattern A (Yellow+Green) pairs.
5. **Contextual Anchoring** (Rule 16): Every card carries a `Context` field showing its heading/chapter lineage to prevent orphan knowledge.
6. **Avoid Sets** (Rules 9 & 10): Multi-item enumerations must be decomposed into individual atomic cards. Never ask "List the 5 types of X" — ask about each type separately.
7. **Anti-Interference** (Rule 11): Cards on similar symbols or closely related concepts must include distinguishing context cues (e.g., `s` vs `σ`, `df_between` vs `df_within`, Type I vs Type II errors).

---

## 2. Color-Coding Semantics & Card Types

### Green Highlights — Definitions, Explanations, Mechanisms
- **Semantic role**: The foundational clause. Establishes what something *is*, how it *works*, or what it *means*.
- **Pattern A (Yellow+Green pair)**: Yellow = Concept Keyword, Green = Descriptor/Definition → **Bidirectional Definition Card** (2 cards).
  - Card 1: `What is the definition of [Yellow Term]?` → `[Green Definition]`
  - Card 2: `What term is defined by: [Green Definition]?` → `[Yellow Term]`
- **Pattern B (Standalone Green)**: Single isolated green highlight → **Concept Identification Card**.
  - Internal verb splitting: parse linking verbs (`is`, `focuses on`, `refers to`, `consists of`, `occurs when`) to auto-split into Keyword and Descriptor.
  - Card: `What is the definition of [parsed Keyword]?` → `[remainder as Descriptor]`

### Yellow Highlights — Important Concepts, Key Terms, High-Yield Facts
- **Semantic role**: The focal concept, threshold, or critical takeaway. Becomes the *keyword* in a pair, or a standalone active-recall target.
- **Pattern A (Yellow+Green pair)**: As above — Yellow anchors the question.
- **Pattern C (Standalone Yellow)**: Creates an active recall card anchored to the section heading.
  - Short phrase: `What is the significance of [Yellow]?` anchored to `[Heading]`
  - Interrogative note (ends in `?` or starts with question word): Rephrase as direct active recall query (see §4, Rule C-3).
  - Full factual statement: Attempt Cloze deletion on the most retrievable token.

### Other Colors — Context, Nuance, Examples
- Routed to the **Context / Notes field** on card back. Not graded. Provides background when reviewing.

---

## 3. Keyword Validity Rules (Empirically Derived)

A string qualifies as a **Concept Keyword** (question anchor) only if it passes ALL of the following:

### Rule K-1: Nominal Phrase Requirement
The keyword must be a **noun or nominal phrase** (1–6 words). Verb phrases, clause fragments, and sentences are disqualified.

> ✅ `Neurogenesis`, `Working Memory`, `Dopamine Receptor`
> ❌ `The process in which new neurons are formed`, `Leads to cell division`

### Rule K-2: Critique / Action Verb Disqualification
Disqualify any phrase that starts with or is dominated by a **critique or action verb** — these describe what a theorist *does*, not what a concept *is*:

Disqualified verbs: `REJECTS`, `CRITICIZES`, `CONTRASTS`, `ARGUES`, `CLAIMS`, `POSITS`, `DEMONSTRATES`, `SHOWS`, `SUGGESTS`, `SUPPORTS`, `LEADS TO`, `RESULTS IN`, `CAUSES`

> ❌ `REJECTS/criticizes the nativist approach` — anchor instead to heading, formulate as active recall query.
> ✅ Heading `Developmental Systems Theory` becomes the keyword; the critique becomes the answer.

### Rule K-3: Relative-Clause & Definitional Framing Disqualification
Disqualify phrases that start with **definitional relative-clause leads** — these are the *definition itself*, not the term being defined:

Disqualified leads: `process in which`, `mechanism that`, `condition where`, `state of`, `movement of`, `formation of`, `process by which`, `system that`, `tendency to`, `ability to`, `capacity for`, `act of`, `instance of`

> ❌ `The process in which new neurons are formed` → fall back to structural heading `Neurogenesis` as keyword.

### Rule K-4: Interrogative Disqualification
Disqualify question words as keyword leads — these are notes, not terms:

Disqualified leads: `what`, `why`, `how`, `when`, `where`, `who`, `which`

When a yellow highlight is interrogative (starts with question word or ends in `?`), **rephrase as a direct active recall query** anchored to the heading — do not wrap in `"What is the significance of [the question itself]?"`.

> ❌ `What is the clinical significance of What constitutes Abuse?????`
> ✅ `What constitutes abuse according to [Heading]?`

### Rule K-5: Smart Pair Resolution
When both highlights in a Yellow+Green pair fail `is_valid_concept_keyword()`, apply fallback:
1. Use the section **heading** as the concept keyword.
2. Treat the green highlight as the descriptor.
3. Formulate the yellow highlight as a targeted active-recall question about the heading.

---

## 4. Domain-Specific Card Archetypes

### 4A. Statistics / Quantitative Methods (PSYC 3031)
Standard definition cards are **insufficient** for statistics. Deploy these 6 archetypes:

| Archetype | Question Format | Answer Format |
|---|---|---|
| **1. Test Selection** | "What statistical test is appropriate when [design constraints]?" | `[Test name]` + brief rationale |
| **2. Assumption Triad** | "What is the diagnostic test for the [assumption] assumption?" | `[Test]` + "If violated: [remedy]" |
| **3. Formula Decomposition** | "In the formula `[formula]`, what does `[symbol]` represent?" | Atomic definition of that symbol only |
| **4. Decision Rule** | "At α = [value], with [df], what is the critical value of [statistic]?" | `[Critical value]` + reject/retain rule |
| **5. Output Reading** | "Given `[R output snippet]`, what conclusion do you draw about [hypothesis]?" | Plain-English interpretation |
| **6. R Syntax** | "In R ([topic]), how do you [task in plain English]?" | `<code>[R code]</code>` |

**R Script Ingestion rules**:
- Parse `# TOPIC N - ...` blocks as heading hierarchy.
- Parse `#' Term: description` as keyword–descriptor pairs → bidirectional definition cards.
- Parse `#' **TASK: ...**` + following code lines as Archetype 6 cards.
- HTML-escape all code snippets (`<`, `>`, `&`) before inserting into card HTML.
- Code answers use `<code>escaped_code</code>` with `<br>` for newlines.

### 4B. Developmental Psychology (PSYC 2110)
- **Stage Theory cards**: `[Theorist]'s [Stage Name]: what are the key cognitive milestones?` → `[Age range] + [milestones]`
- **Experimental Paradigm cards**: `What does the [Paradigm name] paradigm measure?` → `[Operationalized construct]`
- **Chronological Marker cards**: `At what age does [developmental milestone] typically emerge?` → `[Age range]`

### 4C. Pharmacology (PSYC 3590)
- **Receptor Mechanism**: `What is the mechanism of action of [drug/class]?` → `[Receptor type + effect]`
- **Pharmacokinetics**: `What is the [ED₅₀ / t₁/₂ / TI] of [drug]?` → `[Value + clinical meaning]`
- **Pathway**: `Which neurotransmitter pathway does [drug] primarily modulate?` → `[Pathway + direction]`

### 4D. Professionalism & Ethics (PSYC 3000)
- **CPA Hierarchy**: `When Principles [X] and [Y] conflict, which takes precedence?` → `[Higher principle] + rationale`
- **Mandatory Reporting**: `What are the conditions that trigger a mandatory reporting obligation?` → `[Threshold criteria]`
- **Communication Standard**: `What is the [APA/CPA] standard for [communication context]?` → `[Rule + rationale]`

---

## 5. Tagging Taxonomy

Every card is tagged with its **full heading hierarchy** — one tag per level — so decks can be filtered by chapter, topic, or subtopic in Anki's browser or custom study sessions.

**Tag format rules**:
- Alphanumeric + underscores only (`[^a-zA-Z0-9_]` → `_`)
- Collapse consecutive underscores; strip leading/trailing underscores
- Max 50 characters per tag
- Deduplicated within each card

**Mandatory system tags** (always present):
- `lecture_notes` — applied to all cards by default
- `[domain]` — e.g. `statistics`, `pharmacology`, `developmental_psychology`, `professionalism`
- `[heading_level_1]`, `[heading_level_2]`, ... — one per level of heading hierarchy

**Usage in Anki**:
- Filter a chapter: `deck:"PSYC 2110*" tag:Brain_Development`
- Study by domain: `tag:statistics`
- Create a filtered deck for a test: combine `tag:TOPIC_3` + `deck:"PSYC 3031*"`

---

## 6. Ingestion Sources & Pipeline Routing

| Source type | Extension / Pattern | Extractor |
|---|---|---|
| Word document | `.docx` | `extract_document_highlights()` — OpenXML highlight color parsing |
| Google Doc | URL or bare Doc ID | `extract_google_doc_structured()` — Google Docs API `textStyle.backgroundColor` |
| R script | `.R`, `.Rmd` | `extract_r_script_highlights()` — TOPIC/comment/TASK block parser |
| Virtual `.gdoc` pointer | `.gdoc` (Drive FS) | Must be opened via Google Docs API — cannot be read with `open()` |

**Google Docs API 403 fix**: The service account / OAuth credential must be shared on the document. Share the Google Doc with the configured OAuth email (e.g. `jstreiffer310@gmail.com`) as Viewer before running the pipeline.

---

## 7. Validation & Sanitization Guardrails

- **Length thresholds**: Front < 5 chars or back < 3 chars → rejected. Front > 500 chars → flagged.
- **Placeholder veto**: Cards containing `Review this concept`, `content needs verification`, or empty definitions are filtered out.
- **Deduplication**: Exact and near-duplicate Q/A pairs are stripped before `.apkg` compilation.
- **ContentShield**: LaTeX math (`$...$`, `$$...$$`) and code spans/fences (`` `...` ``, ```` ```...``` ````) are tokenized and protected from `CardSanitizer` quote normalization and punctuation mutation.
- **HTML escaping**: All code content inserted into card HTML must be `html.escape()`d to prevent `<-` and `<=` operators from being parsed as HTML tags by genanki/Anki.
- **Sanitization**: Strips stray CSS, priority badges, figure citations (e.g. `(Figure 2.1)`), and normalizes smart quotes/whitespace.

---

## 8. Delivery & Accessibility

- **Output path**: `C:\Users\jstre\Projects\AnkiDeckCreator\Decks\[DeckName].apkg`
- **Google Drive sync**: Auto-mirrored to `H:\My Drive\Admin\Anki Decks\`
- **AnkiConnect auto-injection**: Compiled `.apkg` is sent to `http://localhost:8765` via `importPackage` action (requires Anki to be running with AnkiConnect add-on). Default: `auto_inject=True`.
- **Re-injection**: Re-running the pipeline overwrites the existing deck and re-injects — existing scheduling data for unchanged cards is preserved by Anki.
