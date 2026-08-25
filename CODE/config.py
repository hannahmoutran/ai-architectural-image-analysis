# config.py
"""
Configuration file for AI Architectural Image Analysis pipeline.
Edit this file to set your preferences for image processing.
Please note that output folder name will be based on the model used in step 1 
"""

# =============================================================================
# IMAGE FOLDER CONFIGURATION
# =============================================================================
# Option 1: Process a SINGLE folder
# Set IMAGE_FOLDER to process just one collection
IMAGE_FOLDER = "charles-steven-dilbeck"

# Option 2: Process MULTIPLE folders
# Set IMAGE_FOLDERS to a list of folder names to process them all sequentially
# When IMAGE_FOLDERS is set (not None/empty), it takes precedence over IMAGE_FOLDER
IMAGE_FOLDERS = None  # e.g., ["collection-1", "collection-2", "collection-3"]
# IMAGE_FOLDERS = ["alfred-zucker", "charles-steven-dilbeck", "james-riely-gordon", "ut-buildings"]

# =============================================================================
# CALIBRATION CONFIGURATION
# =============================================================================
# Number of sample images to process in Step 0 (calibration run).
# These images will be reviewed by the archivist to create a style guide.
CALIBRATION_COUNT = 1

# =============================================================================
# HTML REVIEW CONFIGURATION
# =============================================================================
# When True, run.py automatically generates the HTML review interface (Step 5)
# after Steps 1-4 complete for each folder.
CREATE_HTML_REVIEW = True

# =============================================================================
# MODEL CONFIGURATION
# =============================================================================
# Provider options: "claude", "openai", "gemini"
# The provider determines which API and script will be used

# --- Step 1: Image Analysis ---
# Extracts metadata from architectural drawings
STEP1_PROVIDER = "gemini"

# --- Step 3: Vocabulary Selection ---
# Selects best vocabulary terms for each drawing
STEP3_PROVIDER = "gemini"

# =============================================================================
# AVAILABLE MODELS BY PROVIDER
# =============================================================================
# These are the available models for each provider.
# Uncomment the model you want to use, or set a custom model name.

AVAILABLE_MODELS = {
    # -------------------------------------------------------------------------
    # ANTHROPIC CLAUDE MODELS
    # -------------------------------------------------------------------------
    "claude": {
        "default": "claude-sonnet-4-5-20250929",
        "models": [
            # Sonnet - Balanced performance/cost
            "claude-sonnet-5",
            "claude-sonnet-4-6",
            "claude-sonnet-4-5-20250929",
            # Haiku - Fast and affordable
            "claude-haiku-4-5-20251001",
        ]
    },

    # -------------------------------------------------------------------------
    # OPENAI MODELS
    # -------------------------------------------------------------------------
    "openai": {
        "default": "gpt-5.6-luna",
        "models": [
            # GPT-5 Series
            "gpt-5.6-terra",
            "gpt-5.6-luna",
            "gpt-5.2",
            "gpt-5.1",
            "gpt-5",
            "gpt-5-mini",
            "gpt-5-nano",
            # GPT-4.1 Series
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            # GPT-4o Series
            "gpt-4o",
            "gpt-4o-mini",
            # O-Series (reasoning)
            "o3",
            "o3-mini",
            "o4-mini",
        ]
    },

    # -------------------------------------------------------------------------
    # GOOGLE GEMINI MODELS
    # -------------------------------------------------------------------------
    "gemini": {
        "default": "gemini-3-flash-preview",
        "models": [
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-3-pro-preview",
            "gemini-3-flash-preview",
            "gemini-3-pro-image-preview",
        ]
    }
}

# =============================================================================
# CUSTOM MODEL OVERRIDE (Optional)
# =============================================================================
# If you want to use a specific model instead of the provider default,
# set it here. Leave as None to use the provider's default model.

STEP1_MODEL = None  # e.g., "claude-sonnet-4-6" or None for default
STEP3_MODEL = None  # e.g., "gpt-4.1-mini" or None for default


# =============================================================================
# OPENAI GATEWAY CONFIGURATION
# =============================================================================
# Set to True to route OpenAI calls through the Portkey gateway (requires
# PORTKEY_API_KEY and PORTKEY_VIRTUAL_KEY environment variables).
# Set to False (default) to call the OpenAI API directly.
OPENAI_USE_PORTKEY = True


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_image_folders():
    """
    Get the list of image folders to process.

    Returns a list of folder names. If IMAGE_FOLDERS is set, returns that list.
    Otherwise, returns a single-item list with IMAGE_FOLDER.
    """
    if IMAGE_FOLDERS:
        return IMAGE_FOLDERS
    return [IMAGE_FOLDER]


def get_step1_config(image_folder=None):
    """Get the configuration for Step 1 (Image Analysis).

    Args:
        image_folder: Optional folder name override. If not provided,
                      uses IMAGE_FOLDER from config.
    """
    provider = STEP1_PROVIDER.lower()
    if provider not in AVAILABLE_MODELS:
        raise ValueError(f"Unknown provider: {provider}. Choose from: {list(AVAILABLE_MODELS.keys())}")

    model = STEP1_MODEL if STEP1_MODEL else AVAILABLE_MODELS[provider]["default"]
    folder = image_folder if image_folder else IMAGE_FOLDER

    return {
        "provider": provider,
        "model": model,
        "image_folder": folder
    }


def get_step3_config():
    """Get the configuration for Step 3 (Vocabulary Selection)."""
    provider = STEP3_PROVIDER.lower()
    if provider not in AVAILABLE_MODELS:
        raise ValueError(f"Unknown provider: {provider}. Choose from: {list(AVAILABLE_MODELS.keys())}")

    model = STEP3_MODEL if STEP3_MODEL else AVAILABLE_MODELS[provider]["default"]

    return {
        "provider": provider,
        "model": model
    }


def list_available_models(provider=None):
    """List available models, optionally filtered by provider."""
    if provider:
        provider = provider.lower()
        if provider not in AVAILABLE_MODELS:
            print(f"Unknown provider: {provider}")
            return
        print(f"\n{provider.upper()} Models:")
        print(f"  Default: {AVAILABLE_MODELS[provider]['default']}")
        print("  Available:")
        for model in AVAILABLE_MODELS[provider]["models"]:
            print(f"    - {model}")
    else:
        for prov, config in AVAILABLE_MODELS.items():
            print(f"\n{prov.upper()} Models:")
            print(f"  Default: {config['default']}")
            print("  Available:")
            for model in config["models"]:
                print(f"    - {model}")


def print_current_config():
    """Print the current configuration."""
    print("\n" + "=" * 60)
    print("CURRENT CONFIGURATION")
    print("=" * 60)

    folders = get_image_folders()
    if len(folders) == 1:
        print(f"\nImage Folder: {folders[0]}")
    else:
        print(f"\nImage Folders ({len(folders)} total):")
        for folder in folders:
            print(f"  - {folder}")

    step1 = get_step1_config()
    print(f"\nStep 1 (Image Analysis):")
    print(f"  Provider: {step1['provider']}")
    print(f"  Model: {step1['model']}")

    step3 = get_step3_config()
    print(f"\nStep 3 (Vocabulary Selection):")
    print(f"  Provider: {step3['provider']}")
    print(f"  Model: {step3['model']}")
    print("=" * 60 + "\n")


# =============================================================================
# CURATED MEDIUM & SUPPORT TERMS (Getty AAT)
# =============================================================================
# These are displayed as a checklist in the HTML review interface.
# Archivists select whichever terms apply to each drawing.
# URIs verified against Getty AAT — edit labels/URIs here to customize.
# Run lookup-getty-aat.py to find URIs for additional terms.

MEDIUM_TERMS = [
    # Drawing / inscribing materials
    {'label': 'graphite (mineral)',        'uri': 'http://vocab.getty.edu/aat/300011098', 'source': 'Getty AAT'},
    {'label': 'graphite pencils',          'uri': 'http://vocab.getty.edu/aat/300022443', 'source': 'Getty AAT'},
    {'label': 'ink',                       'uri': 'http://vocab.getty.edu/aat/300015012', 'source': 'Getty AAT'},
    {'label': 'India ink (ink)',           'uri': 'http://vocab.getty.edu/aat/300015018', 'source': 'Getty AAT'},
    {'label': 'pen and ink drawings',      'uri': 'http://vocab.getty.edu/aat/300404676', 'source': 'Getty AAT'},
    {'label': 'pencil (marking material)', 'uri': 'http://vocab.getty.edu/aat/300410335', 'source': 'Getty AAT'},
    {'label': 'colored pencils',           'uri': 'http://vocab.getty.edu/aat/300022441', 'source': 'Getty AAT'},
    {'label': 'charcoal (material)',       'uri': 'http://vocab.getty.edu/aat/300012862', 'source': 'Getty AAT'},
    {'label': 'crayon',                    'uri': 'http://vocab.getty.edu/aat/300022415', 'source': 'Getty AAT'},
    {'label': 'watercolor (paint)',        'uri': 'http://vocab.getty.edu/aat/300015045', 'source': 'Getty AAT'},
    {'label': 'gouache (paint)',           'uri': 'http://vocab.getty.edu/aat/300070114', 'source': 'Getty AAT'},
    {'label': 'wash (material)',           'uri': 'http://vocab.getty.edu/aat/300011051', 'source': 'Getty AAT'},
    {'label': 'tempera',                   'uri': 'http://vocab.getty.edu/aat/300015062', 'source': 'Getty AAT'},
    {'label': 'pastel (material)',         'uri': 'http://vocab.getty.edu/aat/300404632', 'source': 'Getty AAT'},
]

SUPPORT_TERMS = [
    # Base / carrier materials
    {'label': 'paper (fiber product)',       'uri': 'http://vocab.getty.edu/aat/300014109', 'source': 'Getty AAT'},
    {'label': 'wove paper',                  'uri': 'http://vocab.getty.edu/aat/300014187', 'source': 'Getty AAT'},
    {'label': 'laid paper',                  'uri': 'http://vocab.getty.edu/aat/300014184', 'source': 'Getty AAT'},
    {'label': 'tracing paper',               'uri': 'http://vocab.getty.edu/aat/300014161', 'source': 'Getty AAT'},
    {'label': 'tracing vellum',              'uri': 'http://vocab.getty.edu/aat/300014164', 'source': 'Getty AAT'},
    {'label': 'vellum (parchment)',          'uri': 'http://vocab.getty.edu/aat/300011852', 'source': 'Getty AAT'},
    {'label': 'parchment (animal material)', 'uri': 'http://vocab.getty.edu/aat/300011851', 'source': 'Getty AAT'},
    {'label': 'plastic drafting film',       'uri': 'http://vocab.getty.edu/aat/300419267', 'source': 'Getty AAT'},
    {'label': 'linen (material)',            'uri': 'http://vocab.getty.edu/aat/300014069', 'source': 'Getty AAT'},
    {'label': 'cloth',                       'uri': 'http://vocab.getty.edu/aat/300162391', 'source': 'Getty AAT'},
    {'label': 'illustration board',          'uri': 'http://vocab.getty.edu/aat/300014229', 'source': 'Getty AAT'},
    {'label': 'cardboard',                   'uri': 'http://vocab.getty.edu/aat/300014224', 'source': 'Getty AAT'},
]


if __name__ == "__main__":
    # When run directly, show current config and available models
    print_current_config()
    print("\nAVAILABLE MODELS:")
    list_available_models()
