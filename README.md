# AI Architectural Image Analysis

Developed by Hannah Moutran, UT Austin Libraries

Multi-provider AI pipeline for automated metadata generation from architectural drawings, developed for the **University of Texas at Austin Libraries - Alexander Architectural Archives**.

## Overview

This system uses LLMs (Claude, OpenAI, Gemini) to:
- Extract archival metadata from architectural drawing images
- Map extracted content to controlled vocabularies (LCSH, FAST, Getty AAT)
- Enable archivist review through an interactive HTML interface
- Generate professional deliverables for archival systems

## Project Status

**This is an experimental research project, not production software.** These scripts are being developed and used to analyze how well LLMs—both in general and specific models—handle architectural drawing materials from the Alexander Architectural Archives. The codebase is actively evolving as we test different approaches and evaluate results.


## Features

- **Calibration step**: Run a small sample first so the archivist can correct it, creating style-guide examples that guide the full run
- **Multi-provider support**: Choose between OpenAI, Anthropic Claude, or Google Gemini for AI processing
- **Controlled vocabulary integration**: Automatically searches and selects terms from LCSH, FAST, and Getty AAT
- **Format/media vocabulary**: Curated Getty AAT medium and support checklists presented in the HTML review for archivist selection (not AI-extracted)
- **OpenAI Batch API support**: 50% cost savings with OpenAI's Batch API for large collections
- **Multi-collection processing**: Process multiple collections sequentially in a single run
- **HTML review interface**: Web-based archivist review of AI-generated metadata
- **Entity extraction**: Identifies architects, firms, buildings, and geographic locations with fuzzy matching deduplication

## Workflow

```
Step 0: CALIBRATION (optional) → Step 1: IMAGE ANALYSIS → Step 1.5: CLEANUP → Step 2: VOCAB LOOKUP → Step 3: VOCAB SELECTION → Step 4: ENTITY REPORT → Step 5: HTML REVIEW → Step 6: INTEGRATE EDITS
```

| Step | Script | Purpose |
|------|--------|---------|
| **0** | `step-0-calibration.py` | Process a small sample, generate HTML review; archivist corrects it to create few-shot style examples for the full run |
| **1** | `step-1-architectural-drawings.py` | Extract metadata from images (title, contributors, genre, description, topics, dates, entities) |
| **1.5** | `step-1.5-batch-cleanup.py` | Reprocess failed items from Step 1 |
| **2** | `step-2-terms.py` | Query controlled vocabulary APIs (LCSH, FAST, Getty AAT) |
| **3** | `step-3-vocab-selection.py` | AI selects best vocabulary terms from search results |
| **4** | `step-4-entity-report-creation.py` | Compile named entity authority file with fuzzy matching |
| **5** | `step-5-html-review.py` | Generate interactive HTML review interface for archivist curation |
| **6** | `step-6-integrate-archivist-edits.py` | Apply archivist edits back to metadata files; generates `edit_report.json` (stats + edit history) and `final_deliverable.xlsx`. Supports **analysis-only mode** (`--evaluator` flag) to generate named reports without modifying any workflow files — useful for comparing multiple evaluators on the same output. |
| — | `batch-evaluator-reports.py` | Batch-process all decisions JSONs for one evaluator across multiple collections/models, automatically locating each pipeline output folder and running `step-6-integrate-archivist-edits.py` in analysis-only mode. Reports are written to `{EvaluatorName}_changes/` inside the evaluator's folder. |

## LLM Providers

**Anthropic** (default: `claude-sonnet-4-5-20250929`)
- claude-sonnet-5, claude-sonnet-4-6, claude-sonnet-4-5-20250929, claude-haiku-4-5-20251001

**OpenAI** (default: `gpt-5.6-luna`)
- GPT-5 series (gpt-5.6-terra, gpt-5.6-luna, gpt-5.2, gpt-5.1, gpt-5, gpt-5-mini, gpt-5-nano), GPT-4.1, GPT-4o, o3/o4 reasoning models

**Google** (default: `gemini-3-flash-preview`)
- gemini-3.5-flash, gemini-3.1-flash-lite, gemini-3-pro-preview, gemini-3-flash-preview, gemini-3-pro-image-preview

## Installation

### Prerequisites
- Python 3.8+
- API key(s) for your chosen provider(s)

### Setup
```bash
# Clone repository
git clone https://github.com/hannahmoutran/ai-architectural-image-analysis
cd ai-architectural-image-analysis

# Install dependencies
pip install -r requirements.txt

# Set API keys (use the ones you need)
export OPENAI_API_KEY="your-key"
export CLAUDE_API_KEY="your-key"
export GEMINI_API_KEY="your-key"

# Portkey gateway (optional — only needed if OPENAI_USE_PORTKEY = True in config.py)
export PORTKEY_API_KEY="your-portkey-api-key"
export PORTKEY_VIRTUAL_KEY="your-portkey-virtual-key"
```

### Key Dependencies
`openai`, `anthropic`, `google-genai`, `portkey-ai`, `pandas`, `openpyxl`, `rapidfuzz`, `tenacity`, `pillow`, `spacy`, `tiktoken`

## Usage

### Quick Start
```bash
cd CODE
python run.py          # Interactive pipeline runner
python run.py --config # Show current configuration
```

The interactive runner will prompt you to:
1. Confirm running Steps 1-4 (and Step 5 HTML review if `CREATE_HTML_REVIEW = True` in `config.py`)
2. Enable OpenAI Batch API processing (if using OpenAI) for 50% cost savings

### Step 0: Calibration (Optional but Recommended)

Before running the full pipeline on a new collection, run Step 0 to process a small sample and create archivist-corrected style examples. These examples are fed to the AI during Step 1 so it adopts the archivist's preferred style for the collection.

```bash
# 1. Run a small sample (CALIBRATION_COUNT images set in config.py, default: 1)
python step-0-calibration.py
# Or specify count/folder on the command line:
python step-0-calibration.py --count 5
python step-0-calibration.py --folder my-collection --count 5

# An HTML review interface is generated automatically.
# Open it in a browser, edit the metadata to match your preferred style,
# then click Export Decisions and save the file in the exports/ subfolder.

# 2. Regenerate the review interface if needed
python step-5-html-review.py --folder output_folders/my-calibration-run

# 3. Export corrected examples as few-shot style guide
python step-0-calibration.py --export
python step-0-calibration.py --export --folder output_folders/my-calibration-run
# This writes collection-examples.txt to the image folder.
# You can optionally edit the style guide section at the bottom of that file.
```

When you run the full pipeline (Steps 1–4), Step 1 automatically picks up `collection-examples.txt` from the image folder if it exists, using your corrections as few-shot examples alongside the prompt.

> **Note:** Step 0 calibration output folders are named with `_calibration_` in the folder name. Use `--folder` to point to them explicitly if needed.

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
STEP1_MODEL = "claude-sonnet-4-6"  # or None for provider default
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

When enabled, `run.py` will route OpenAI calls through the Portkey gateway for Steps 1 and 3. If you are calling OpenAI directly, leave `OPENAI_USE_PORTKEY = False` and set `OPENAI_API_KEY` as usual.

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

### Integrating Archivist Edits (Step 6)

After archivist review, run Step 6 to apply decisions back to the metadata:

```bash
python step-6-integrate-archivist-edits.py                          # Use latest export
python step-6-integrate-archivist-edits.py --decisions path/to.json # Use specific export
```

This updates `drawings_workflow.json`, generates `final_metadata.json`, produces `edit_report.json`, and creates `final_deliverable.xlsx` (two sheets: Final Metadata and Edit Statistics).

#### Analysis-Only Mode (comparing multiple evaluators)

Pass `--evaluator` to generate a named report **without modifying any workflow files**:

```bash
python step-6-integrate-archivist-edits.py --evaluator "Alice" --decisions alice_edits.json --folder /path/to/pipeline/output --output /path/to/reports
python step-6-integrate-archivist-edits.py --evaluator "Bob"   --decisions bob_edits.json   --folder /path/to/pipeline/output --output /path/to/reports
```

This generates `edit_report_Alice_<folder>_<date>.json` and `edit_report_Bob_<folder>_<date>.json` for side-by-side comparison.

#### Batch Evaluator Reports

To process all of one evaluator's decisions files at once across multiple collections/models:

```bash
python batch-evaluator-reports.py          # Interactive — prompts for evaluator folder
python batch-evaluator-reports.py --dry-run  # Preview what would run
```

Expected folder structure:
```
<testing-folder>/
├── claude/     ArchImagesAI_* (pipeline output folders)
├── openai/     ArchImagesAI_*
├── gemini/     ArchImagesAI_*
└── evaluations/
    └── <EvaluatorName>/
        ├── <collection>_<model>_<Evaluator>_<date>.json  ← decisions files
        └── <EvaluatorName>_changes/                       ← reports written here
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
│   │   └── your-collection/      # Images from one collection here
│   │       ├── drawing1.jpg
│   │       ├── drawing2.png
│   │       └── collection-name.txt  # Optional context file
        └── your-second-collection/ # Images from another collection here, etc.
│   └── output_folders/           # Auto-generated outputs
└── requirements.txt, etc. 
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
│   │   └── edit_report.json          # Edit statistics + full edit history
│   └── final_deliverable.xlsx        # Excel: Final Metadata + Edit Statistics sheets
├── logs/
│   ├── *_token_usage_log.txt
│   └── *_api_usage_log.txt
├── review/
│   ├── images/                       # Copied images for portability
│   ├── exports/                      # Archivist decision exports
│   └── *.html                        # Interactive HTML review pages
```

> **Note:** To view the HTML review pages correctly, the entire output folder must be downloaded to your local computer. Images are served from the local `review/images/` directory, so opening the HTML file from a remote location or without the accompanying folder structure will result in missing images.

```
└── original-outputs/                 # Backup automatically created before edits are integrated
```

## Controlled Vocabularies

Terms are sourced from authoritative vocabularies via API:
- **LCSH** - Library of Congress Subject Headings
- **FAST** - Faceted Application of Subject Terminology
- **Getty AAT** - Art & Architecture Thesaurus

The AI selects from verified terms rather than generating subject headings, ensuring all terms include proper URIs.

## Team

University of Texas at Austin Libraries

- Hannah Moutran - Library Specialist, AI Implementation
- Aaron Choate - Director of Research & Strategy
- Devon Murphy - Metadata Analyst
- Karina Sanchez - Scholars Lab Librarian
- Katie Pierce Meyer - Head of Architectural Collections
- Josh Conrad - Digital Initiatives Archival Fellow
- Caitlin Young - Graduate Research Assistant

## Development

This repository was built with the assistance of [Claude Code](https://code.claude.com/docs/en/overview), Anthropic's AI coding assistant in VS Code.

For questions about this repository, please contact [Hannah Moutran](hlm2454@my.utexas.edu)

## License

See [LICENSE](LICENSE) for details.