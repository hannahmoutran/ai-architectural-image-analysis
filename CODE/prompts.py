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
    def get_architectural_drawing_prompt(cls, collection_context: str = "", collection_examples: str = ""):
        """Get the prompt for architectural drawing analysis."""
        context_section = ""
        if collection_context:
            context_section = f"""
COLLECTION CONTEXT:
{collection_context}

"""

        if collection_examples:
            examples_section = f"\n\n{collection_examples}"
        else:
            examples_section = """
EXAMPLE OUTPUT:
Title: First Floor Plan - Smith Residence
Contributors: John Smith (Architect); ABC Engineering (Structural Engineer)
Genre: floor plan
Description: Floor plan showing a four-bedroom residence with central hallway, formal living and dining rooms at front, kitchen and service areas at rear.
Topics: residential architecture; single-family homes; floor plans; hallways; living rooms; dining rooms; kitchens; residential floor plans
Date On Drawing: March 1925
Sheet Info: Sheet 3 of 12
Named Entities: Smith Residence (Building)
Geographic Entities: Austin--Texas (City); Texas (State)
Content Warning: None"""

        return f"""You are an archivist at the Alexander Architectural Archives at the University of Texas at Austin, cataloging architectural drawings for researchers and students.
{context_section}
Analyze this image from our architectural archives, in light of the context, and extract the following metadata:

FIELDS TO EXTRACT:
- Title: From title block or drawing text. Use [untitled] if none found.
- Contributors: People/firms with roles, format as "Name (Role)" separated by semicolons. Roles: Architect, Draftsman, Engineer, Contractor, Owner, Firm, Client, etc. Only record names and initials that are clearly legible. Do NOT attempt to decipher scribbled signatures or fuzzy, unclear initials — omit them entirely rather than guessing at the letters.
- Genre: Drawing type (floor plan, elevation, section, detail, site plan, perspective, etc.). Be specific (e.g., "first floor plan"). List multiple types with semicolons.
- Description: Include a short description of this drawing. Do not include information that is inferred, only what is clearly shown. Make sure that every sentence is specific to this drawing. Do not describe the physical medium in the description.
- Topics: Extract 5–10 specific topic keywords covering: building type, building use, architectural features visible in the drawing, structural or material elements shown, and any relevant thematic context. Be specific (e.g., "single-family homes" not just "architecture"). Separate with semicolons. These keywords are used to search controlled vocabularies, so specificity matters.
- Date On Drawing: Dates from title block, stamps, annotations. Use [no date] if none visible.
- Sheet Info: Sheet number.
- Named Entities: Entities that the drawing depicts or references — NOT the people or firms who created it (those belong in Contributors). Include: named buildings or structures shown or referenced; organizations such as clients, contractors, or manufacturers named in the drawing content; individuals named in the content who are not creators of the drawing (e.g., a client, a building's namesake, someone credited in an inscription). Format as "Name (Type)". Types: Building, Organization, Person. Do NOT repeat Contributors here.
- Geographic Entities: Locations as "City--State (City)", "State (State)", or "Country (Country)". Use full names.
- Content Warning: Make a note of biased language/terminology, culturally sensitive material, or offensive or harmful language or imagery. Write 'None' if there is nothing of note.  Another archivist will assess how to handle the issue, your job is only to flag for review.
{cls.UNCERTAINTY_INSTRUCTIONS}{examples_section}"""

    @classmethod
    def get_style_analysis_prompt(cls, examples_text: str) -> str:
        """Prompt for analyzing calibration examples to derive a collection-specific style guide."""
        return f"""You are an expert archivist at the Alexander Architectural Archives at the University of Texas at Austin. You are analyzing a set of architectural drawing metadata records that have been reviewed and approved by the collection's archivist.

Your task: study these archivist-approved examples and write a concise STYLE GUIDE capturing the archivist's preferences — how they phrase descriptions, which topics they choose, how they format contributors, and any other distinctive patterns you observe.

ARCHIVIST-APPROVED EXAMPLES:
{examples_text}

Write a STYLE GUIDE (under 350 words) covering:
1. Description style — sentence structure, length, level of detail, what to include or omit
2. Topics — preferred specificity and terminology, typical count per drawing, what categories to include
3. Contributors — formatting conventions, how roles are specified, any consistent patterns
4. Named and geographic entities — what qualifies, level of specificity, any consistent patterns
5. Any other notable preferences you observe across the examples

Be specific and actionable. This guide will be used by an AI to analyze additional drawings from this same collection in the same archivist's style."""

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

AUTHORITY LOOKUP SANITY CHECK:
You may also be shown authority lookup matches produced by automatic keyword search: contributor names matched to FAST name authority records, geographic entities matched to FAST geographic records, chronological terms generated from the drawing date, and genre terms matched to Getty AAT. These automatic matches can be badly wrong (e.g., a draftsman's initials matched to a completely unrelated organization). Apply a common-sense check to each one:
- REJECT a match only when it clearly refers to a different person, firm, place, time period, or drawing type than the metadata value it was matched to
- If a match is plausible, leave it alone — do NOT reject a match just because you cannot fully verify it
- List rejected matches in "rejected_lookups" using the exact key and label shown; if nothing is clearly wrong, return an empty list

You will be provided with drawing metadata and available vocabulary terms organized by topic. For each relevant topic, select the most appropriate term that accurately represents the drawing content.

Return JSON format:
{{
"selected_terms": [
    {{
    "label": "Exact label",
    "source": "LCSH/FAST/Getty AAT/Getty TGN",
    "reasoning": "Brief explanation of relevance to the drawing"
    }}
],
"rejected_lookups": [
    {{
    "category": "contributor OR geographic OR chronological OR genre",
    "key": "Exact key shown for the lookup",
    "label": "Exact label of the rejected match",
    "reasoning": "Why this match is clearly wrong"
    }}
]
}}
"""