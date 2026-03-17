# AI Architectural Image Analysis

Multi-provider AI pipeline for automated metadata generation from architectural drawings, developed for the **University of Texas at Austin Libraries - Alexander Architectural Archives**.

## Overview

This system uses LLMs (Claude, OpenAI, Gemini) to:
- Extract archival metadata from architectural drawing images
- Map extracted content to controlled vocabularies (LCSH, FAST, Getty AAT, Getty TGN)
- Enable archivist review through an interactive HTML interface
- Generate professional deliverables for archival systems

## Project Status

**This is an experimental research project, not production software.** These scripts are being developed and used to analyze how well LLMs—both in general and specific models—handle architectural drawing materials from the Alexander Architectural Archives. The codebase is actively evolving as we test different approaches and evaluate results.


## Features

- **Multi-provider support**: Choose between OpenAI, Anthropic Claude, or Google Gemini for AI processing
- **Controlled vocabulary integration**: Automatically searches and selects terms from LCSH, FAST, Getty AAT, and Getty TGN
- **OpenAI Batch API support**: 50% cost savings with OpenAI's Batch API for large collections
- **Multi-collection processing**: Process multiple collections sequentially in a single run
- **HTML review interface**: Web-based archivist review of AI-generated metadata
- **Entity extraction**: Identifies architects, firms, buildings, and geographic locations with fuzzy matching deduplication

## Workflow

```
Step 1: IMAGE ANALYSIS → Step 1.5: CLEANUP → Step 2: VOCAB LOOKUP → Step 3: VOCAB SELECTION → Step 4: ENTITY REPORT → Step 5: HTML REVIEW → Step 6: INTEGRATE EDITS
```

| Step | Scripts | Purpose |
|------|---------|---------|
| **1** | `step-1-architectural-drawings-{claude,openai,gemini}.py` | Extract metadata from images (title, contributors, genre, description, subjects, dates, entities) |
| **1.5** | `step-1.5-batch-cleanup.py` | Reprocess failed items from Step 1 |
| **2** | `step-2-terms.py` | Query controlled vocabulary APIs (LCSH, FAST, Getty AAT/TGN) |
| **3** | `step-3-vocab-selection-{claude,openai,gemini}.py` | AI selects best vocabulary terms from search results |
| **4** | `step-4-entity-report-creation.py` | Compile named entity authority file with fuzzy matching |
| **5** | `html-review.py` | Generate interactive HTML review interface for archivist curation |
| **6** | `integrate-archivist-edits.py` | Apply archivist edits back to metadata files, generate edit statistics |

## LLM Providers

**Anthropic** (default: `claude-sonnet-4-5-20250929`)
- claude-opus-4-5, claude-sonnet-4-5, claude-haiku-4-5

**OpenAI** (default: `gpt-5.1`)
- GPT-5 series, GPT-4.1, GPT-4o, o1/o3 reasoning models

**Google** (default: `gemini-3-flash-preview`)
- gemini-3-pro-preview, gemini-3-flash-preview

## Installation

### Prerequisites
- Python 3.8+
- API key(s) for your chosen provider(s)

### Setup
```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/ai-architectural-image-analysis.git
cd ai-architectural-image-analysis

# Install dependencies
pip install -r requirements.txt

# Set API keys (use the ones you need)
export OPENAI_API_KEY="your-key"
export CLAUDE_API_KEY="your-key"
export GEMINI_API_KEY="your-key"
```

### Key Dependencies
`openai`, `anthropic`, `google-genai`, `pandas`, `openpyxl`, `rapidfuzz`, `tenacity`, `pillow`, `spacy`, `tiktoken`

## Usage

### Quick Start
```bash
cd CODE
python run.py          # Interactive pipeline runner
python run.py --config # Show current configuration
```

The interactive runner will prompt you to:
1. Confirm running Steps 1-4
2. Enable OpenAI Batch API processing (if using OpenAI) for 50% cost savings
3. Generate the HTML review interface

### Configuration

Edit `CODE/config.py` to set:
- **IMAGE_FOLDER**: Name of your image folder (in `CODE/image_folders/`)
- **IMAGE_FOLDERS**: List of folders to process sequentially (overrides IMAGE_FOLDER)
- **STEP1_PROVIDER**: AI provider for image analysis (`openai`, `claude`, or `gemini`)
- **STEP3_PROVIDER**: AI provider for vocabulary selection
- **STEP1_MODEL**: Optional model override (or `None` for provider default)

#### Processing a Single Collection
```python
IMAGE_FOLDER = "collection-name"
IMAGE_FOLDERS = None
```

#### Processing Multiple Collections
```python
IMAGE_FOLDER = "ignored-when-IMAGE_FOLDERS-is-set"
IMAGE_FOLDERS = ["collection-1", "collection-2", "collection-3"]
```
Each folder runs through the complete pipeline (Steps 1-4) before moving to the next.

#### Changing Provider/Model
```python
STEP1_PROVIDER = "claude"  # or "openai", "gemini"
STEP3_PROVIDER = "claude"  # can use different provider for vocab selection
STEP1_MODEL = "claude-opus-4-5-20250514"  # or None for provider default
```

#### OpenAI via Portkey Gateway (Optional)

If your organization routes OpenAI calls through [Portkey](https://portkey.ai/), set the following in `config.py`:

```python
OPENAI_USE_PORTKEY = True  # Default is False (direct OpenAI API)
```

Then set your Portkey credentials as environment variables:
```bash
export PORTKEY_API_KEY="your-portkey-api-key"
export PORTKEY_VIRTUAL_KEY="your-portkey-virtual-key"
```

Both values can be found in the Portkey dashboard under Getting Started. The **virtual key** is the slug for your OpenAI provider connection (e.g. `your-org-name-openai`).

When enabled, `run.py` will automatically use the Portkey-based scripts for Steps 1 and 3. If you are calling OpenAI directly, leave `OPENAI_USE_PORTKEY = False` and set `OPENAI_API_KEY` as usual.

### OpenAI Batch Processing

When using OpenAI for Step 1 (image analysis), you can enable **Batch API processing** for 50% cost savings. This is offered as a prompt when running `python run.py`:

```
OpenAI detected for Step 1.
Batch processing offers 50% cost savings but has up to 24h turnaround.
Use batch processing? [y/n]:
```

**How it works:**
- All images are submitted as a single batch job to OpenAI's Batch API
- OpenAI processes the batch asynchronously (typically completes in minutes to hours, max 24h)
- The script waits and polls for completion, showing progress updates every 10 minutes
- Results are retrieved and processed automatically when complete

**When to use batch processing:**
- Large collections where cost savings matter
- When you don't need immediate results
- Processing can run overnight or while you work on other tasks

**When to use individual processing:**
- Small collections (< 6 images)
- When you need results immediately
- When debugging or testing

You can also force batch processing via environment variable:
```bash
USE_BATCH_PROCESSING=true python run.py
```

Or disable it entirely:
```bash
USE_BATCH_PROCESSING=false python run.py
```

### Key Files

- **[config.py](CODE/config.py)** - Central configuration for folders and providers
- **[prompts.py](CODE/prompts.py)** - All LLM prompts for image analysis and vocabulary selection
- **[model_pricing.py](CODE/model_pricing.py)** - Current model pricing with batch discounts
- **[shared_utilities.py](CODE/shared_utilities.py)** - API stats, JSON parsing, entity deduplication
- **[batch_processor.py](CODE/batch_processor.py)** - OpenAI Batch API integration
- **[token_logging.py](CODE/token_logging.py)** - Token usage and cost logging

### Directory Structure
```
ai-architectural-image-analysis/
├── CODE/
│   ├── run.py                    # Main runner script
│   ├── config.py                 # Configuration settings
│   ├── image_folders/
│   │   └── your-collection/      # Your images here
│   │       ├── drawing1.jpg
│   │       ├── drawing2.png
│   │       └── collection-name.txt  # Optional context file
│   └── output_folders/           # Auto-generated outputs
└── requirements.txt
```

## Output

The pipeline generates an output folder with the following structure:

```
ArchImagesAI_{collection}_{model}_{date}_Time_{time}/
├── metadata/
│   ├── json/
│   │   ├── drawings_workflow.json    # Main workflow data
│   │   ├── final_metadata.json       # Approved data only
│   │   ├── vocabulary_mapping.json   # All vocab results
│   │   └── edit_changelog.json       # Archivist changes
│   └── drawings_workflow.xlsx        # Excel deliverable
├── logs/
│   ├── *_token_usage_log.txt
│   └── *_api_usage_log.txt
├── review/
│   ├── images/                       # Copied images for portability
│   └── exports/                      # Archivist decision exports
└── original-outputs/                 # Backup before edits
```

## Controlled Vocabularies

Terms are sourced from authoritative vocabularies via API:
- **LCSH** - Library of Congress Subject Headings
- **FAST** - Faceted Application of Subject Terminology
- **Getty AAT** - Art & Architecture Thesaurus
- **Getty TGN** - Thesaurus of Geographic Names

The AI selects from verified terms rather than generating subject headings, ensuring all terms include proper URIs.

## Team

University of Texas at Austin Libraries

- Hannah Moutran - Library Specialist, AI Implementation
- Devon Murphy - Metadata Analyst
- Karina Sanchez - Scholars Lab Librarian
- Katie Pierce Meyer - Head of Architectural Collections
- Josh Conrad - Digital Initiatives Archival Fellow

## Development

This repository was built with the assistance of [Claude Code](https://code.claude.com/docs/en/overview), Anthropic's AI coding assistant in VS Code.

For questions about this repository, please contact [Hannah Moutran](hlm2454@my.utexas.edu)

## License

See [LICENSE](LICENSE) for details.