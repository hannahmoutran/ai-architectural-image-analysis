"""
Architectural Archives Prompts Module

This module contains all prompt components for the architectural drawing analysis workflow.

Workflow Steps:
- Step 1: Initial metadata extraction from architectural drawings (image analysis)
- Step 3: Vocabulary selection from controlled vocabularies
"""

class ArchitecturalDrawingPrompts:
    """Container for all workflow prompts."""

    # ==================== SHARED INSTRUCTIONS ====================

    # Uncertainty handling instructions for visual analysis
    UNCERTAINTY_INSTRUCTIONS = """
HANDLING UNCERTAINTY:
- Do NOT guess or speculate about content that is not clearly visible or legible
- If information cannot be read or determined, mark it as [Not Visible]
- Only include information you can confidently extract or observe from the image
"""

    # ==================== STEP 1: ARCHITECTURAL DRAWINGS PROMPTS ====================

    @classmethod
    def get_architectural_drawing_prompt(cls, collection_context: str = ""):
        """Get the prompt for architectural drawing analysis."""
        context_section = ""
        if collection_context:
            context_section = f"""
COLLECTION CONTEXT:
{collection_context}

"""

        return f"""You are an archivist at the Alexander Architectural Archives at the University of Texas at Austin, cataloging architectural drawings for researchers and students.
{context_section}
Analyze this image from our architectural archives, in light of the context, and extract the following metadata:

FIELDS TO EXTRACT:
- Title: From title block or drawing text. Use [untitled] if none found.
- Contributors: People/firms with roles, format as "Name (Role)" separated by semicolons. Roles: Architect, Draftsman, Engineer, Contractor, Owner, Firm, Client, etc.
- Genre: Drawing type (floor plan, elevation, section, detail, site plan, perspective, etc.). Be specific (e.g., "first floor plan"). List multiple types with semicolons.
- Description: Include a description of physical appearance, architectural content, style, decorative elements, and historical context. Make sure that every sentence is specific to this drawing. 
- Format Media: Full descriptive phrase for the drawing medium and support (e.g., "ink on linen", "blueprint", "pencil on vellum"). Include condition notes if notable.
- Medium: The applied medium or material (e.g., ink, graphite, pencil, watercolor, blueprint). Semicolons for multiple. This will be used for Getty AAT lookup.
- Support: The physical substrate or support material (e.g., linen, vellum, tracing paper, cardboard, paper). Semicolons for multiple. This will be used for Getty AAT lookup.
- Subjects: Building types, materials, architectural features, decorative elements (max 10, separated by semicolons). These will be used as keywords to search for controlled vocabulary terms via API.
- Date On Drawing: Dates from title block, stamps, annotations. Use [no date] if none visible.
- Sheet Info: Sheet number, project number, scale notation.
- Named Entities: Non-geographic entities as "Name (Type)" - types: Architect, Firm, Person, Building, Organization, etc.
- Geographic Entities: Locations as "City--State (City)", "State (State)", or "Country (Country)". Use full names.
- Content Warning: Make a note of biased language/terminology, culturally sensitive material, or offensive or harmful language or imagery. Write 'None' if there is nothing of note.  Another archivist will assess how to handle the issue, your job is only to flag for review.
{cls.UNCERTAINTY_INSTRUCTIONS}
EXAMPLE OUTPUT:
Title: First Floor Plan - Smith Residence
Contributors: John Smith (Architect); ABC Engineering (Structural Engineer)
Genre: floor plan
Description: Floor plan in ink on tracing paper showing a four-bedroom residence with central hallway, formal living and dining rooms at front.
Format Media: ink on tracing paper
Medium: ink
Support: tracing paper
Subjects: residential architecture; floor plans; single-family homes
Date On Drawing: March 1925
Sheet Info: Sheet 3 of 12
Named Entities: John Smith (Architect); ABC Engineering (Firm)
Geographic Entities: Austin--Texas (City); Texas (State)
Content Warning: None"""

    @classmethod
    def create_collection_context(cls, creator: str = "", title: str = "",
                                   dates: str = "", abstract: str = "",
                                   extent: str = "", repository: str = "") -> str:
        """
        Helper method to create collection context string from finding aid fields.

        Args:
            creator: Creator name(s) and dates
            title: Collection title
            dates: Inclusive dates
            abstract: Collection abstract/description
            extent: Collection extent
            repository: Repository name

        Returns:
            Formatted context string for use in prompts
        """
        parts = []

        if creator:
            parts.append(f"Creator: {creator}")
        if title:
            parts.append(f"Collection: {title}")
        if dates:
            parts.append(f"Dates: {dates}")
        if repository:
            parts.append(f"Repository: {repository}")
        if extent:
            parts.append(f"Extent: {extent}")
        if abstract:
            parts.append(f"\nAbstract: {abstract}")

        return "\n".join(parts)


    # ==================== STEP 3 PROMPT (VOCABULARY SELECTION) ====================

    @classmethod
    def get_vocabulary_selection_system_prompt(cls, collection_context: str = ""):
        """Get the system prompt for vocabulary selection (step 3)."""
        context_section = ""
        if collection_context:
            context_section = f"""
COLLECTION CONTEXT:
{collection_context}

"""

        return f"""You are a professional archivist specializing in controlled vocabularies for architectural history. You work for the Alexander Architectural Archives at the University of Texas at Austin. You are selecting subject headings for architectural drawings to help researchers and students discover relevant materials.
{context_section}
Your task is to select the most appropriate controlled vocabulary terms for an architectural drawing based on the metadata extracted in step 1 and the vocabulary terms found in step 2.

SELECTION CRITERIA:
1. CONTENT RELEVANCE: Terms must directly relate to what's actually depicted or described in the drawing
2. PRECISION: Choose specific terms over general ones when available
3. TEMPORAL ACCURACY: Terms should be appropriate for the time period of the drawing
4. QUALITY CONTROL: Select NOTHING rather than forcing poor matches

DECISION PROCESS:
For each topic, evaluate whether ANY available terms genuinely describe the specific drawing content:
- RELEVANCE CHECK: Does the term directly and accurately describe what's in the drawing?
- SPECIFICITY: Is this the most specific accurate term available?
- ARCHITECTURAL CONTEXT: Does the term correctly describe the building type, style, feature, or material shown?

AVOID selecting terms that are:
- Not directly relevant to the drawing content
- Based on partial word matches rather than actual content relevance
- Overly broad when specific terms are available
- Representative of content types not shown in the drawing

DECISION RULES:
- If a topic has NO genuinely relevant terms, SKIP that entire topic
- Do not force selections based on partial word matches
- Better to select fewer accurate terms than many irrelevant ones
- If multiple terms are exactly the same, select the one with the best source (Getty AAT > LCSH > Getty TGN > FAST)
- For Format/Media terms (medium and support materials), Getty AAT is the authoritative source — prefer Getty AAT terms over all others

You will be provided with drawing metadata and available vocabulary terms organized by topic. For each relevant topic, select the most appropriate term that accurately represents the drawing content.

Return JSON format:
{{
"selected_terms": [
    {{
    "label": "Exact label",
    "source": "LCSH/FAST/Getty AAT/Getty TGN",
    "reasoning": "Brief explanation of relevance to the drawing"
    }}
]
}}
"""