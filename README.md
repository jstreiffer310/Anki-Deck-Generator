# Academic Anki Deck Generator

A comprehensive, scalable flashcard generation system that transforms course materials into optimized Anki decks. Built for academic courses with standardized workflows, SuperMemo 20 Rules compliance, and quality-assured card generation.

---

## 🚀 Unified Lecture Notes Pipeline (New)

The automated extraction and generation pipeline (`scripts/extract_and_generate.py`) extracts highlights from university lecture notes and converts them into atomic active recall cards.

### Core Features:
- **Polymorphic Ingestion**: Directly ingests either Google Docs (via Google Docs REST API URL or Document ID) or local Word `.docx` files.
- **The Keyword-Descriptor Framework (`docs/ANKI_SOP.md`)**:
  - *Keyword as hint* = Active **Recall** (stronger memory).
  - *Descriptor as hint* = **Recognition** (weaker memory).
  - Bidirectional pairing strictly enforced for vocabulary and definitions.
- **Internal Linking-Verb Parsing**: Parses `is`, `are`, `focuses on`, `refers to`, `means`, etc. within full-sentence highlights to prevent vague prompt traps.
- **Defensive Quality Guardrails (`scripts/card_validator.py`)**: Automatic character length checks, placeholder filtering, figure citation stripping, and deduplication.
- **Cognitive Taxonomies**: Beyond basic definitions, synthesizes *Function → Structure* (e.g. brain regions), *Concept → Mechanism*, and *Example → Category* formulations.
- **Automated Delivery**: Compiles native `.apkg` packages with WCAG AAA accessible high-contrast styles, dual-syncs to Google Drive (`Admin/Anki Decks/`), and auto-injects into Anki via AnkiConnect (port 8765).
- **Test Suite**: 360 automated unit, integration, and E2E tests (`pytest scripts/tests`).

### Quick Start:
```bash
# Ingest directly from Google Docs
python scripts/extract_and_generate.py "https://docs.google.com/document/d/YOUR_DOC_ID/edit"

# Ingest from a local Word document
python scripts/extract_and_generate.py "path/to/lecture_notes.docx"
```

---

## 🔧 Technical Requirements

### Dependencies
- **Python 3.10+** (see `requirements.txt`)
- **Anki Desktop** with AnkiConnect addon (optional for auto-injection)

### Installation
```bash
# Clone repository
git clone https://github.com/jstreiffer310/Anki-Deck-Generator.git
cd Anki-Deck-Generator

# Install Python dependencies
pip install -r requirements.txt
```


## 🤝 Contributing

1. **Add Course Templates**: Create new templates in `config/templates.json`
2. **Improve Extraction**: Enhance content extraction patterns in `shared/core/`
3. **Quality Improvements**: Add validation rules and quality metrics
4. **Documentation**: Update guides and examples

## 📝 Migration from Old Structure

Existing courses can be migrated to the new flexible structure:

```bash
# Migrate PSYC2240 to new structure (if needed)
python tools/course_manager.py migrate courses/PSYC2240 PSYC2240 --template psychology

# Validate migrated course
python tools/course_manager.py validate PSYC2240
```

## 🎓 Success Stories

- **PSYC2120**: 149 optimized cards generated from learning objectives in 1 session
- **PSYC2240**: 585+ cards with 95%+ quality retention and exam success
- **Template System**: Supports unlimited courses across all academic disciplines

---

**Ready to master any academic subject with optimized flashcards! 🧠📚**

*Repository last updated: September 2024 - Fully reorganized for unlimited course flexibility*nd quality-assured card generation.

## 🏗️ Repository Structure

```
Academic-Anki-Deck-Generator/
├── 📁 courses/                    # ALL COURSE CONTENT
│   ├── PSYC2120/                 # Social Psychology (149 cards)
│   ├── PSYC2240/                 # Biological Psychology (585+ cards)
│   └── [ANY_COURSE]/             # Unlimited courses supported
│
├── 📁 shared/                     # SHARED UTILITIES
│   ├── core/                     # Core generation tools
│   │   ├── content_extractor.py  # Universal content extraction
│   │   └── deck_builder.py       # Universal deck generation
│   ├── utils/                    # Utility functions
│   └── scripts/                  # PowerShell automation
│
├── 📁 config/                     # GLOBAL CONFIGURATION
│   ├── default_settings.json     # Default generation settings
│   └── templates.json            # Course template definitions
│
├── 📁 tools/                      # MANAGEMENT TOOLS
│   └── course_manager.py         # Create/manage courses
│
├── 📁 templates/                  # COURSE TEMPLATES
│   ├── basic/                    # Standard academic course
│   ├── psychology/               # Psychology-specific template
│   ├── science/                  # STEM course template
│   └── humanities/               # Text-heavy course template
│
├── 📁 docs/                       # DOCUMENTATION
└── 📁 examples/                   # EXAMPLE IMPLEMENTATIONS
```

## ✨ Key Features

- **🎯 Unlimited Courses** - Standardized structure for any academic subject
- **🧠 Memory Optimization** - Cards designed using proven retention principles
- **🤖 Automated Generation** - Transform textbooks and lectures into quality cards
- **🛡️ Quality Assurance** - Built-in validation and duplicate detection
- **📋 Template System** - Pre-configured templates for different course types
- **🔄 Cross-Platform** - Windows, macOS, Linux support with PowerShell Core
- **📊 Analytics** - Detailed statistics and quality metrics

## 🚀 Quick Start

### Creating a New Course

```bash
# Install dependencies
pip install -r requirements.txt

# Create a new course (Interactive)
python tools/course_manager.py create COURSE_CODE "Course Name" "Fall 2024"

# Example: Create a psychology course
python tools/course_manager.py create PSYC3100 "Cognitive Psychology" "Fall 2024" --template psychology
```

### Using Existing Courses
- **PSYC2120**: 149 cards ready for import (`courses/PSYC2120/decks/final/`)
- **PSYC2240**: 585+ cards ready for import (`courses/PSYC2240/decks/`)

### Course Templates Available
- **`basic`** - Standard academic course template
- **`psychology`** - Psychology courses with clinical focus
- **`science`** - STEM courses with formulas and equations
- **`humanities`** - Text-heavy courses with quotations and themes

## 📋 Standardized Course Structure

Each course follows this exact structure for consistency and scalability:

```
courses/COURSE_CODE/
├── config/
│   ├── course_config.json        # Course-specific settings
│   └── extraction_rules.json    # Content extraction rules
├── content/
│   ├── textbooks/               # PDF textbooks
│   ├── lectures/                # Transcripts, recordings
│   ├── materials/               # Additional course materials
│   └── raw/                     # Unprocessed source files
├── processing/
│   ├── extracted/               # Processed content
│   ├── analysis/                # Content analysis results
│   └── logs/                    # Processing logs
├── decks/
│   ├── drafts/                  # Work-in-progress decks
│   ├── final/                   # Ready-for-use decks
│   └── archives/                # Previous versions
├── tools/
│   ├── course_extractor.py      # Course-specific extraction
│   └── custom_processors.py    # Custom processing scripts
└── README.md                    # Course-specific documentation
```

## � Workflow for Any Course

### 1. Create Course Structure
```bash
# List available templates
python tools/course_manager.py list templates

# Create new course
python tools/course_manager.py create COURSE_CODE "Course Name" "Semester" --template [basic|psychology|science|humanities]
```

### 2. Add Course Materials
```bash
# Navigate to your course
cd courses/COURSE_CODE/

# Add materials to appropriate directories:
# - Textbooks → content/textbooks/
# - Lectures → content/lectures/
# - Additional materials → content/materials/
```

### 3. Extract Content
```python
from shared.core.content_extractor import CourseExtractor

extractor = CourseExtractor('courses/COURSE_CODE')
content = extractor.extract_all_content()
```

### 4. Build Deck
```python
from shared.core.deck_builder import CourseDeckBuilder

builder = CourseDeckBuilder('courses/COURSE_CODE')
csv_path, apkg_path = builder.build_complete_deck()
```

### 5. Import to Anki
- **Quick Import**: Use the generated `.apkg` file
- **CSV Import**: Use the CSV file with Field mapping (Front→Question, Back→Answer, Tags→Tags)

## 📊 Current Courses

| Course | Cards | Status | Description |
|--------|-------|---------|-------------|
| **PSYC2120** | **149** | ✅ **Ready** | Social Psychology - LOQ-based generation |
| **PSYC2240** | **585+** | ✅ **Ready** | Biological Psychology - Comprehensive coverage |
| **[Your Course]** | **TBD** | 🚀 **Create** | Use templates to generate any course |

### PSYC2120 - Social Psychology
- **Location**: `courses/PSYC2120/decks/final/`
- **Files**: `PSYC2120_Complete_AnkiDeck.csv`, `PSYC2120_Complete_Deck.apkg`
- **Features**: Learning Objective Question (LOQ) methodology, Test 1 focused

### PSYC2240 - Biological Basis of Behaviour  
- **Location**: `courses/PSYC2240/decks/`
- **Files**: `PSYC2240_Complete_AnkiDeck.csv`, `PSYC2240_Complete_Cloze_Cards.csv`
- **Features**: Neuroanatomy, brain disorders, clinical cases, comprehensive coverage

## 🧠 Card Quality Philosophy

Our cards follow proven memory retention principles:
- **Question Format** over term-definition: `"What does the cerebellum do?"` vs `"Cerebellum"`
- **Functional Focus**: Emphasize what structures/concepts DO, not just definitions
- **Concise Answers**: 1-2 sentences max for better memorization
- **Context Preservation**: Cloze cards maintain textbook context while testing recall
- **Learning Objectives**: Questions derived from official course learning objectives (LOQ)

## �️ Management Commands

### Course Management
```bash
# List all courses
python tools/course_manager.py list courses

# Create new course
python tools/course_manager.py create BIOL2100 "Human Anatomy" "Fall 2024" --template science

# Migrate existing course
python tools/course_manager.py migrate old_course_path NEW_CODE --template psychology

# Validate course structure
python tools/course_manager.py validate COURSE_CODE
```

### PowerShell Automation (Windows)
```powershell
# Setup new course environment
pwsh shared/scripts/setup_course.ps1 -CourseCode "MATH2100" -Template "science"

# Build deck with validation
pwsh shared/scripts/build_deck.ps1 -CourseCode "PSYC2120"

# Maintenance and cleanup
pwsh shared/scripts/maintenance.ps1 -Action "validate_all"
```

## 📈 Quality Metrics & Validation

Every generated deck includes:
- **Duplicate Detection**: Automatic removal of redundant cards
- **Length Validation**: Questions 10-200 chars, Answers 5-500 chars
- **Format Consistency**: Standardized CSV format for reliable import
- **Content Verification**: Cross-reference between textbook and lecture materials
- **Priority Classification**: High/Medium/Low priority based on learning objectives

## � Study Recommendations

1. **Import Strategy**: Use `.apkg` files for immediate import with proper formatting
2. **Study Schedule**: 20-30 new cards/day, 200-300 reviews/day maximum
3. **FSRS Algorithm**: Enable for optimal spaced repetition scheduling
4. **Tag Usage**: Study by chapter, priority, or content source using filters
5. **Integration**: Combine with active lecture attendance and textbook reading