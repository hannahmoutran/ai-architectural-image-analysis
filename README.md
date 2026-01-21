# AI Architectural Image Analysis

A multi-provider AI pipeline for generating archival metadata from architectural drawings using controlled vocabularies.

## Overview

This tool automates first-pass metadata creation for architectural drawing collections using Large Language Models (OpenAI, Claude, or Gemini). It extracts metadata from images and maps content to authoritative controlled vocabularies (LCSH, FAST, Getty AAT, Getty TGN).

Developed at the University of Texas at Austin Libraries for the Alexander Architectural Archives.

## Features

- **Multi-provider support**: Choose between OpenAI, Anthropic Claude, or Google Gemini for AI processing
- **Controlled vocabulary integration**: Automatically searches and selects terms from LCSH, FAST, Getty AAT, and Getty TGN
- **Batch processing**: Handles large collections with automatic cost optimization
- **HTML review interface**: Web-based cataloger review of AI-generated metadata
- **Entity extraction**: Identifies architects, firms, buildings, and geographic locations

## Workflow

The pipeline consists of 5 steps:

| Step | Description | Provider |
|------|-------------|----------|
| 1 | **Image Analysis** - Extract metadata from architectural drawings | OpenAI/Claude/Gemini |
| 1.5 | **Batch Cleanup** - Reprocess any failed items | Automatic |
| 2 | **Vocabulary Lookup** - Search LCSH, FAST, Getty AAT/TGN for matching terms | APIs only |
| 3 | **Vocabulary Selection** - AI selects best terms from search results | OpenAI/Claude/Gemini |
| 4 | **Entity Report** - Compile named entity authority file | Local processing |
| 5 | **HTML Review** - Generate cataloger review interface | Local processing |

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

## Usage

### Quick Start
```bash
cd CODE
python run.py          # Interactive menu
python run.py 1        # Run Step 1 only
python run.py all      # Run all steps
python run.py --config # Show current configuration
```

### Configuration

Edit `CODE/config.py` to set:
- **IMAGE_FOLDER**: Name of your image folder (in `CODE/image_folders/`)
- **STEP1_PROVIDER**: AI provider for image analysis (`openai`, `claude`, or `gemini`)
- **STEP3_PROVIDER**: AI provider for vocabulary selection

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
│   │       └── ...
│   └── output_folders/           # Auto-generated outputs
└── requirements.txt
```

## Output

The pipeline generates:
- **Excel workbooks** with extracted metadata and thumbnails
- **JSON files** with structured data for programmatic access
- **Text reports** including vocabulary mappings and entity lists
- **HTML review interface** for cataloger verification

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

## License

See [LICENSE](LICENSE) for details.