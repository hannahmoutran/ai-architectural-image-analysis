"""
Shared utilities for Architectural Drawing Analysis pipeline.
Contains common functions and classes used across multiple steps.
"""

import os
import json
import re
from typing import Dict, Any, Optional

class APIStats:
    """Shared API statistics tracking class."""
    
    def __init__(self):
        self.total_requests = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.processing_times = []

def find_newest_folder(base_directory: str) -> Optional[str]:
    """Find the newest folder containing the expected metadata structure.

    Searches for folders that contain either:
    - metadata/json/drawings_workflow.json (created by Step 1), OR
    - metadata/drawings_workflow.xlsx (created by later steps)
    Looking both at the top level and one level deep (for nested folder structures).
    """
    if not os.path.exists(base_directory):
        return None

    def has_expected_structure(folder_path: str) -> bool:
        """Check if folder has the expected metadata structure."""
        # Check for JSON file (created by Step 1)
        json_file = os.path.join(folder_path, "metadata", "json", "drawings_workflow.json")
        # Check for XLSX file (created by later steps)
        xlsx_file = os.path.join(folder_path, "metadata", "drawings_workflow.xlsx")
        return os.path.exists(json_file) or os.path.exists(xlsx_file)

    valid_folders = []

    # Check top-level folders
    for item in os.listdir(base_directory):
        item_path = os.path.join(base_directory, item)
        if os.path.isdir(item_path):
            # Check if this folder directly has the structure
            if has_expected_structure(item_path):
                valid_folders.append(item_path)
            else:
                # Check subfolders (one level deep)
                for subitem in os.listdir(item_path):
                    subitem_path = os.path.join(item_path, subitem)
                    if os.path.isdir(subitem_path) and has_expected_structure(subitem_path):
                        valid_folders.append(subitem_path)

    if not valid_folders:
        return None

    # Sort by modification time (newest first)
    valid_folders.sort(key=lambda x: os.path.getmtime(x), reverse=True)

    return valid_folders[0]

def normalize_quotes(text):
    """Normalize smart/curly quotes to straight ASCII quotes."""
    if not isinstance(text, str):
        return text
    # Smart single quotes to straight apostrophe
    text = text.replace('\u2018', "'")  # Left single quote
    text = text.replace('\u2019', "'")  # Right single quote (apostrophe)
    text = text.replace('\u201A', "'")  # Single low-9 quote
    # Smart double quotes to straight double quote
    text = text.replace('\u201C', '"')  # Left double quote
    text = text.replace('\u201D', '"')  # Right double quote
    text = text.replace('\u201E', '"')  # Double low-9 quote
    return text


def postprocess_api_response(response_data):
    """Post-process the API response for consistency - updated for geographic entities."""

    # Normalize smart quotes in all string fields
    for key, value in response_data.items():
        if isinstance(value, str):
            response_data[key] = normalize_quotes(value)
        elif isinstance(value, list):
            response_data[key] = [normalize_quotes(item) if isinstance(item, str) else item for item in value]

    # Helper function to convert string to list if needed
    def ensure_list(field_value):
        if isinstance(field_value, str):
            # Split by semicolon first (primary delimiter), then comma as fallback
            if ';' in field_value:
                items = [item.strip() for item in field_value.split(';') if item.strip()]
            else:
                items = [item.strip() for item in field_value.split(',') if item.strip()]
            return items
        elif isinstance(field_value, list):
            return field_value
        else:
            return []
    
    # Handle named entities
    if 'namedEntities' in response_data:
        response_data['namedEntities'] = ensure_list(response_data['namedEntities'])
        # Remove duplicates while preserving order
        response_data['namedEntities'] = list(dict.fromkeys(response_data['namedEntities']))
        # Remove any entities that are just single letters or numbers
        response_data['namedEntities'] = [entity for entity in response_data['namedEntities'] 
                                        if len(entity) > 1 or not entity.isalnum()]
    
    # Handle geographic entities
    if 'geographicEntities' in response_data:
        response_data['geographicEntities'] = ensure_list(response_data['geographicEntities'])
        # Remove duplicates while preserving order
        response_data['geographicEntities'] = list(dict.fromkeys(response_data['geographicEntities']))
        # Remove any entities that are just single letters or numbers
        response_data['geographicEntities'] = [entity for entity in response_data['geographicEntities'] 
                                             if len(entity) > 1 or not entity.isalnum()]
    
    # Handle topics field (also ensure it's a list)
    if 'topics' in response_data:
        response_data['topics'] = ensure_list(response_data['topics'])
    
    # Handle subjects field - ensure it's a list but keep as 'subjects'
    if 'subjects' in response_data:
        response_data['subjects'] = ensure_list(response_data['subjects'])

    # Handle topics field variations - for scripts that use 'topics' instead of 'subjects'
    if 'topics' in response_data:
        response_data['topics'] = ensure_list(response_data['topics'])
    elif 'subjectHeadings' in response_data:
        response_data['topics'] = ensure_list(response_data.pop('subjectHeadings'))
    
    # Ensure 'contentWarning' field exists and is properly formatted
    if 'contentWarning' not in response_data:
        response_data['contentWarning'] = 'None'
    elif response_data['contentWarning'].lower() == 'none' or response_data['contentWarning'].strip() == '':
        response_data['contentWarning'] = 'None'
    else:
        # Capitalize the first letter and ensure it ends with a period
        response_data['contentWarning'] = response_data['contentWarning'].capitalize().rstrip('.') + '.'
    
    return response_data

def parse_json_response_enhanced(raw_response: str) -> tuple[Dict[str, Any], Optional[str]]:
    """Enhanced JSON parsing with multiple recovery strategies."""
    if not raw_response or not raw_response.strip():
        return None, "Empty response"
    
    try:
        # Strategy 1: Standard cleaning
        cleaned_response = re.sub(r'```json\s*|\s*```', '', raw_response)
        cleaned_response = re.sub(r'^[^{]*({.*})[^}]*$', r'\1', cleaned_response, flags=re.DOTALL)
        cleaned_response = re.sub(r',(\s*[}\]])', r'\1', cleaned_response)
        
        parsed_json = json.loads(cleaned_response)
        return parsed_json, None
        
    except json.JSONDecodeError:
        pass
    
    try:
        # Strategy 2: Extract JSON object more aggressively
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw_response, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
            parsed_json = json.loads(json_str)
            return parsed_json, None
            
    except json.JSONDecodeError:
        pass
    
    try:
        # Strategy 3: Fix common issues
        fixed_response = raw_response
        
        # Fix unquoted keys
        fixed_response = re.sub(r'(\w+):', r'"\1":', fixed_response)
        
        # Fix unquoted string values
        fixed_response = re.sub(r':\s*([^",\[\{][^,\]\}]*)', r': "\1"', fixed_response)
        
        # Remove trailing commas
        fixed_response = re.sub(r',(\s*[}\]])', r'\1', fixed_response)
        
        # Extract JSON part
        json_match = re.search(r'\{.*\}', fixed_response, re.DOTALL)
        if json_match:
            parsed_json = json.loads(json_match.group(0))
            return parsed_json, None
            
    except json.JSONDecodeError:
        pass
    
    return None, "All parsing strategies failed"

def preprocess_ocr_text(text):
    """Preprocess OCR text to fix common errors."""
    # Add your specific OCR corrections here
    replacements = {
        "Sv'cink i^idam": "Frank Adam",
        # Add more common OCR errors as needed
    }
    
    for error, correction in replacements.items():
        text = text.replace(error, correction)
    
    # Remove unusual characters
    text = re.sub(r'[^\w\s.,;:!?()-]', '', text)
    
    return text