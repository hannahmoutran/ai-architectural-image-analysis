# Step 3: Vocabulary term selection using Google's Gemini models

import os
import json
import logging
import time
from datetime import datetime
from typing import List, Dict, Any, Tuple
from google import genai
from google.genai import types
import tenacity
from prompts import ArchitecturalDrawingPrompts
from shared_utilities import APIStats, find_newest_folder

# Import our custom modules
from model_pricing import calculate_cost, get_model_info
from token_logging import create_token_usage_log, log_individual_response

def load_collection_context(image_folder_path: str) -> str:
    """
    Load collection context from text files in the image folder.
    Returns formatted context string for use in prompts.
    """
    if not image_folder_path or not os.path.exists(image_folder_path):
        return ""

    context_data = {}

    # Find all .txt files in the folder
    txt_files = [f for f in os.listdir(image_folder_path) if f.endswith('.txt')]

    for txt_file in txt_files:
        txt_path = os.path.join(image_folder_path, txt_file)
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip().lower()
                        value = value.strip()
                        if value:
                            context_data[key] = value
            logging.info(f"Loaded collection context from: {txt_path}")
        except Exception as e:
            logging.warning(f"Could not read context file {txt_path}: {e}")

    if not context_data:
        return ""

    return ArchitecturalDrawingPrompts.create_collection_context(
        creator=context_data.get('creator', ''),
        title=context_data.get('title', ''),
        dates=context_data.get('dates', ''),
        abstract=context_data.get('abstract', ''),
        extent=context_data.get('extent', ''),
        repository=context_data.get('repository', '')
    )

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Suppress verbose HTTP logging
logging.getLogger("google").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Initialize Gemini client
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
DEFAULT_MODEL = "gemini-3-flash-preview"

api_stats = APIStats()


class VocabularySelector:
    """Class to select the best vocabulary terms for each drawing using Gemini."""

    def __init__(self, model_name: str = DEFAULT_MODEL, collection_context: str = ""):
        self.model_name = model_name
        self.collection_context = collection_context
        self.system_prompt = ArchitecturalDrawingPrompts.get_vocabulary_selection_system_prompt(collection_context)

    def create_system_prompt(self) -> str:
        """Create the system prompt for vocabulary selection."""
        return ArchitecturalDrawingPrompts.get_vocabulary_selection_system_prompt(self.collection_context)

    def create_user_prompt(self, entry_data: Dict[str, Any]) -> str:
        """Create the user prompt for a specific entry with topics organized format."""
        analysis = entry_data.get('analysis', {})

        # Build content description from architectural drawing metadata
        content_parts = []

        # Add drawing title
        if analysis.get('title'):
            content_parts.append(f"TITLE:\n{analysis['title']}")

        # Add genre/drawing type
        if analysis.get('genre'):
            content_parts.append(f"DRAWING TYPE:\n{analysis['genre']}")

        # Add description
        if analysis.get('description'):
            content_parts.append(f"DESCRIPTION:\n{analysis['description']}")

        # Add subjects (these are the keywords from step 1)
        if analysis.get('subjects'):
            subjects = analysis['subjects']
            if isinstance(subjects, list):
                content_parts.append(f"SUBJECTS:\n{', '.join(subjects)}")
            else:
                content_parts.append(f"SUBJECTS:\n{subjects}")

        # Add named entities
        if analysis.get('named_entities'):
            named_entities = analysis['named_entities']
            if isinstance(named_entities, list):
                content_parts.append(f"NAMED ENTITIES:\n{', '.join(named_entities)}")
            else:
                content_parts.append(f"NAMED ENTITIES:\n{named_entities}")

        # Add date if available
        if analysis.get('date_on_drawing'):
            content_parts.append(f"DATE:\n{analysis['date_on_drawing']}")

        content_description = "\n\n".join(content_parts)

        # Build topic-organized vocabulary terms
        topic_to_terms = analysis.get('vocabulary_search_results', {})

        if not topic_to_terms:
            return None  # No topic-organized vocabulary terms available

        topics_section = self._build_topic_organized_terms(topic_to_terms)

        # Combine everything
        user_prompt = f"""Analyze this architectural drawing metadata and select appropriate vocabulary terms:

{content_description}

AVAILABLE VOCABULARY TERMS BY TOPIC:
{topics_section}

Select the most relevant terms following your instructions. Use exact labels without [source] brackets. Skip topics with no genuinely relevant terms.
"""

        return user_prompt

    def _build_topic_organized_terms(self, topic_to_terms: Dict[str, List[Dict]]) -> str:
        """Build the topic-organized terms section from topic_to_terms mapping."""
        sections = []

        for topic, terms in topic_to_terms.items():
            if terms:  # Only show topics that have terms
                sections.append(f"  Topic: {topic}")

                term_strings = []
                for term in terms:
                    if isinstance(term, dict):
                        label = term.get('label', '').strip()
                        source = term.get('source', 'Unknown')
                        uri = term.get('uri', '')
                        if uri:
                            term_strings.append(f"{label} ({uri}) [{source}]")
                        else:
                            term_strings.append(f"{label} [{source}]")

                sections.append(f"  Terms: {'; '.join(term_strings)}")
                sections.append("")  # Empty line between topics

        return "\n".join(sections)

    @tenacity.retry(
        wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
        stop=tenacity.stop_after_attempt(5),
        retry=tenacity.retry_if_exception_type(Exception)
    )
    def select_vocabulary_terms(self, entry_data: Dict[str, Any]) -> Tuple[Dict[str, Any], str, Any, float]:
        """Select vocabulary terms for a single entry using Gemini."""
        user_prompt = self.create_user_prompt(entry_data)

        if not user_prompt:
            return {
                "selected_terms": []
            }, "No vocabulary terms available for selection", None, 0

        api_stats.total_requests += 1
        start_time = time.time()

        # Build full prompt with system instructions
        full_prompt = f"{self.system_prompt}\n\n{user_prompt}"

        response = client.models.generate_content(
            model=self.model_name,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=1500,
                thinking_config=types.ThinkingConfig(thinking_level="low")
            )
        )

        processing_time = time.time() - start_time
        api_stats.processing_times.append(processing_time)

        # Extract token usage from Gemini response
        input_tokens = 0
        output_tokens = 0
        if hasattr(response, 'usage_metadata'):
            input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0)
            output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0)

        api_stats.total_input_tokens += input_tokens
        api_stats.total_output_tokens += output_tokens

        raw_response = response.text.strip()

        # Create a usage-like object for compatibility
        usage = type('Usage', (), {
            'prompt_tokens': input_tokens,
            'completion_tokens': output_tokens
        })()

        try:
            parsed_response = self.parse_json_response(raw_response)
            return parsed_response, raw_response, usage, processing_time
        except Exception as e:
            logging.error(f"Error parsing vocabulary selection response: {e}")
            return {
                "selected_terms": []
            }, raw_response, usage, processing_time

    def parse_json_response(self, raw_response: str) -> Dict[str, Any]:
        """Parse JSON response from the API."""
        from shared_utilities import parse_json_response_enhanced

        parsed_json, error = parse_json_response_enhanced(raw_response)

        if parsed_json is None:
            raise ValueError(f"Could not parse JSON response: {error}")

        if 'selected_terms' not in parsed_json:
            parsed_json['selected_terms'] = []

        return parsed_json

class ArchitecturalDrawingsVocabularyProcessor:
    """Main class for vocabulary selection and clean output generation."""

    def __init__(self, folder_path: str, model_name: str = DEFAULT_MODEL):
        self.folder_path = folder_path
        self.model_name = model_name
        self.workflow_type = None
        self.json_data = None
        self.json_folder = None
        self.collection_context = ""
        self.vocabulary_selector = None
        self.was_batch_processed = False

    def detect_workflow_type(self) -> bool:
        """Detect workflow type and check for vocabulary enhancement."""
        json_folder = os.path.join(self.folder_path, "metadata", "json")
        json_path = os.path.join(json_folder, "drawings_workflow.json")

        if os.path.exists(json_path):
            self.workflow_type = 'drawings'
            self.json_folder = json_folder
        else:
            logging.error("Could not find drawings_workflow.json in metadata/json.")
            return False

        metadata_dir = os.path.join(self.folder_path, "metadata")
        vocab_report_path = os.path.join(metadata_dir, 'vocabulary_mapping_report.txt')
        if not os.path.exists(vocab_report_path):
            logging.error("Vocabulary enhancement (step 2) must be run before step 3.")
            return False

        return True

    def load_json_data(self) -> bool:
        """Load JSON data and verify vocabulary terms exist."""
        json_filename = f"{self.workflow_type}_workflow.json"
        json_path = os.path.join(self.json_folder, json_filename)

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                self.json_data = json.load(f)

            data_items = self.json_data[:-1] if self.json_data and 'api_stats' in self.json_data[-1] else self.json_data

            has_vocab_terms = False
            for item in data_items:
                if 'analysis' in item and 'vocabulary_search_results' in item['analysis']:
                    vocab_terms = item['analysis']['vocabulary_search_results']
                    if vocab_terms:
                        has_vocab_terms = True
                        break

            if not has_vocab_terms:
                logging.error("No vocabulary terms found. Please run step 2 first.")
                return False

            print(f"Loaded JSON data from {json_filename}")

            self._load_collection_context()
            self.vocabulary_selector = VocabularySelector(self.model_name, self.collection_context)

            return True

        except Exception as e:
            logging.error(f"Error loading JSON data: {e}")
            return False

    def _load_collection_context(self) -> None:
        """Load collection context from the original image folder."""
        data_items = self.json_data[:-1] if self.json_data and 'api_stats' in self.json_data[-1] else self.json_data

        if not data_items:
            return

        folder_name = data_items[0].get('folder', '')
        if not folder_name:
            return

        script_dir = os.path.dirname(os.path.abspath(__file__))
        image_folder_path = os.path.join(script_dir, "image_folders", folder_name)

        if os.path.exists(image_folder_path):
            self.collection_context = load_collection_context(image_folder_path)
            if self.collection_context:
                print(f"Loaded collection context from: {folder_name}")
        else:
            logging.warning(f"Image folder not found: {image_folder_path}")

    def find_entries_with_vocabulary(self) -> List[Tuple[int, Dict[str, Any]]]:
        """Find entries that have vocabulary terms available for selection."""
        entries_with_vocab = []
        data_items = self.json_data[:-1] if self.json_data and 'api_stats' in self.json_data[-1] else self.json_data

        for i, item in enumerate(data_items):
            if 'analysis' in item and 'vocabulary_search_results' in item['analysis']:
                vocab_terms = item['analysis']['vocabulary_search_results']
                if vocab_terms:
                    entries_with_vocab.append((i, item))

        return entries_with_vocab

    def process_vocabulary_selection(self, entries_with_vocab: List[Tuple[int, Dict[str, Any]]]) -> Dict[int, Dict[str, Any]]:
        """Process vocabulary selection using individual API calls."""
        selection_results = {}

        logs_folder_path = os.path.join(self.folder_path, "logs")
        if not os.path.exists(logs_folder_path):
            os.makedirs(logs_folder_path)

        total_entries = len(entries_with_vocab)
        processed_entries = 0

        print(f"Processing {total_entries} entries individually...")

        for i, (entry_index, entry_data) in enumerate(entries_with_vocab):
            print(f"\nProcessing entry {i+1}/{total_entries}")
            print(f"   Entry index: {entry_index}")
            print(f"   Progress: {((i+1)/total_entries)*100:.1f}%")

            try:
                selection_result, raw_response, usage, processing_time = self.vocabulary_selector.select_vocabulary_terms(entry_data)

                log_individual_response(
                    logs_folder_path=logs_folder_path,
                    script_name="architectural_drawings_vocabulary_selection",
                    row_number=entry_index + 2,
                    barcode=f"{entry_data.get('folder', 'unknown')}_page{entry_data.get('page_number', 'unknown')}",
                    response_text=raw_response,
                    model_name=self.model_name,
                    prompt_tokens=usage.prompt_tokens if usage else 0,
                    completion_tokens=usage.completion_tokens if usage else 0,
                    processing_time=processing_time
                )

                selection_results[entry_index] = {
                    'selection_result': selection_result,
                    'raw_response': raw_response,
                    'processing_time': processing_time
                }

                selected_count = len(selection_result.get('selected_terms', []))
                print(f"   Selected {selected_count} vocabulary terms")
                processed_entries += 1

            except Exception as e:
                logging.error(f"Error processing entry {entry_index}: {e}")
                selection_results[entry_index] = {
                    'selection_result': {'selected_terms': []},
                    'raw_response': f"Error: {str(e)}",
                    'processing_time': 0
                }
                print(f"   Processing failed: {str(e)}")

            time.sleep(0.5)

        print(f"\nProcessing completed: {processed_entries}/{total_entries} entries processed")
        return selection_results

    def match_selected_labels_to_original_terms(self, selected_labels: List[str], vocab_search_results: Dict[str, List[Dict]]) -> List[Dict]:
        """Match selected labels to original terms with source priority.

        Also tracks which subject (topic) each term was derived from for cascade rejection support.
        """
        import re

        # Build a list of all terms with their source topic (subject) for provenance tracking
        all_available_terms = []
        for topic, terms in vocab_search_results.items():
            for term in terms:
                if isinstance(term, dict):
                    # Create a copy with provenance tracking
                    term_with_provenance = term.copy()
                    term_with_provenance['derived_from_subject'] = topic
                    all_available_terms.append(term_with_provenance)

        def normalize_for_comparison(label: str) -> str:
            normalized = re.sub(r'[^a-z\s]', '', label.lower())
            normalized = re.sub(r'\s+', ' ', normalized).strip()
            return normalized

        source_priority = {
            'Getty AAT': 1,
            'LCSH': 2,
            'FAST': 3,
            'Getty TGN': 4
        }

        matched_terms = []

        for selected_label in selected_labels:
            candidate_matches = []
            selected_words = set(normalize_for_comparison(selected_label).split())

            for term in all_available_terms:
                term_label = term.get('label', '').strip()
                term_words = set(normalize_for_comparison(term_label).split())

                if selected_words == term_words and len(selected_words) > 0:
                    candidate_matches.append(term)

            if candidate_matches:
                best_match = min(candidate_matches, key=lambda t: source_priority.get(t.get('source', ''), 999))
                matched_terms.append(best_match)
            else:
                selected_normalized = selected_label.lower().strip()

                for term in all_available_terms:
                    term_label = term.get('label', '').strip()
                    term_normalized = term_label.lower().strip()

                    if selected_normalized == term_normalized:
                        candidate_matches.append(term)

                if candidate_matches:
                    best_match = min(candidate_matches, key=lambda t: source_priority.get(t.get('source', ''), 999))
                    matched_terms.append(best_match)

        seen_uris = set()
        deduplicated_terms = []
        for term in matched_terms:
            uri = term.get('uri', '')
            if uri and uri not in seen_uris:
                deduplicated_terms.append(term)
                seen_uris.add(uri)
            elif not uri:
                deduplicated_terms.append(term)

        return deduplicated_terms

    def update_json_data(self, selection_results: Dict[int, Dict[str, Any]]) -> bool:
        """Update JSON data with selected vocabulary terms only."""
        try:
            data_items = self.json_data[:-1] if self.json_data and 'api_stats' in self.json_data[-1] else self.json_data
            api_stats_data = self.json_data[-1] if self.json_data and 'api_stats' in self.json_data[-1] else None

            updated_items = []

            for i, item in enumerate(data_items):
                if i in selection_results:
                    selected_term_responses = selection_results[i]['selection_result'].get('selected_terms', [])

                    selected_labels = []
                    for term in selected_term_responses:
                        if isinstance(term, dict):
                            label = term.get('label', '').strip()
                            selected_labels.append(label)

                    vocab_search_results = item['analysis'].get('vocabulary_search_results', {})
                    matched_terms = self.match_selected_labels_to_original_terms(selected_labels, vocab_search_results)

                    item['analysis']['final_selected_terms'] = matched_terms
                else:
                    item['analysis']['final_selected_terms'] = []

                # Keep vocabulary_search_results in JSON - valuable for showing all candidate terms
                # The vocabulary mapping report provides a human-readable summary

                updated_items.append(item)

            if api_stats_data:
                updated_items.append(api_stats_data)

            json_filename = f"{self.workflow_type}_workflow.json"
            json_path = os.path.join(self.json_folder, json_filename)

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(updated_items, f, indent=2, ensure_ascii=False)

            print("Updated JSON file with selected vocabulary terms")
            return True

        except Exception as e:
            logging.error(f"Error updating JSON data: {e}")
            return False

    def create_vocabulary_mapping_json(self, selection_results: Dict[int, Dict[str, Any]]) -> bool:
        """Create vocabulary_mapping.json with structured vocabulary data."""
        try:
            data_items = self.json_data[:-1] if self.json_data and 'api_stats' in self.json_data[-1] else self.json_data

            vocabulary_mapping = {
                "generated_timestamp": datetime.now().isoformat(),
                "model": self.model_name,
                "drawings": []
            }

            for i, item in enumerate(data_items):
                drawing_data = {
                    "folder": item.get('folder', 'Unknown'),
                    "page_number": item.get('page_number', 'Unknown'),
                    "vocabulary_search_results": {},
                    "final_selected_terms": []
                }

                # Get vocabulary search results and mark which are selected
                vocab_search_results = item['analysis'].get('vocabulary_search_results', {})
                selected_terms = item['analysis'].get('final_selected_terms', [])

                # Get selected URIs for marking
                selected_uris = set()
                for term in selected_terms:
                    if isinstance(term, dict) and term.get('uri'):
                        selected_uris.add(term['uri'])

                # Process vocabulary search results and add 'selected' flag
                for topic, terms in vocab_search_results.items():
                    marked_terms = []
                    for term in terms:
                        if isinstance(term, dict):
                            term_copy = term.copy()
                            term_copy['selected'] = term.get('uri', '') in selected_uris
                            marked_terms.append(term_copy)
                    drawing_data['vocabulary_search_results'][topic] = marked_terms

                drawing_data['final_selected_terms'] = selected_terms
                vocabulary_mapping['drawings'].append(drawing_data)

            # Save to metadata/json folder
            vocab_mapping_path = os.path.join(self.json_folder, "vocabulary_mapping.json")

            with open(vocab_mapping_path, 'w', encoding='utf-8') as f:
                json.dump(vocabulary_mapping, f, indent=2, ensure_ascii=False)

            print(f"Created vocabulary mapping JSON: {vocab_mapping_path}")
            return True

        except Exception as e:
            logging.error(f"Error creating vocabulary mapping JSON: {e}")
            return False

    def create_vocabulary_mapping_report(self, selection_results: Dict[int, Dict[str, Any]]) -> bool:
        """Create vocabulary mapping report."""
        try:
            metadata_dir = os.path.join(self.folder_path, "metadata")
            report_path = os.path.join(metadata_dir, "vocabulary_mapping_report.txt")

            data_items = self.json_data[:-1] if self.json_data and 'api_stats' in self.json_data[-1] else self.json_data

            with open(report_path, 'w', encoding='utf-8') as f:
                f.write("ARCHITECTURAL DRAWINGS VOCABULARY MAPPING REPORT\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Model: {self.model_name}\n\n")

                for i, item in enumerate(data_items):
                    folder = item.get('folder', 'Unknown')
                    page_number = item.get('page_number', 'Unknown')

                    f.write(f"DRAWING {page_number} (Collection: {folder}):\n")
                    f.write("=" * 50 + "\n")

                    vocab_search_results = item['analysis'].get('vocabulary_search_results', {})
                    selected_terms = item['analysis'].get('final_selected_terms', [])

                    selected_uris = set()
                    if selected_terms:
                        for term in selected_terms:
                            if isinstance(term, dict):
                                uri = term.get('uri', '')
                                if uri:
                                    selected_uris.add(uri)

                    if vocab_search_results:
                        f.write(f"\nVOCABULARY SEARCH RESULTS:\n")
                        selected_count = 0

                        for topic, terms in vocab_search_results.items():
                            f.write(f"  Topic: {topic}\n")

                            if terms:
                                topic_terms = []
                                for term in terms:
                                    if isinstance(term, dict):
                                        label = term.get('label', '')
                                        source = term.get('source', '')
                                        uri = term.get('uri', '')

                                        is_selected = uri in selected_uris

                                        if is_selected:
                                            selected_count += 1
                                            topic_terms.append(f"{label} ({uri}) [{source}] ✓")
                                        else:
                                            topic_terms.append(f"{label} ({uri}) [{source}]")

                                f.write(f"    Terms: {'; '.join(topic_terms)}\n")
                            else:
                                f.write(f"    Terms: No terms available\n")

                            f.write("\n")

                    # Always show selected terms if they exist
                    if selected_terms:
                        f.write("FINAL SELECTED TERMS:\n")
                        for term in selected_terms:
                            if isinstance(term, dict):
                                label = term.get('label', '')
                                uri = term.get('uri', '')
                                source = term.get('source', '')
                                f.write(f"  - {label} ({uri}) [{source}]\n")
                        f.write("\n")
                    elif not vocab_search_results:
                        f.write("\nNo vocabulary terms available for this drawing.\n\n")

                    f.write("=" * 50 + "\n\n")

            print(f"Created vocabulary mapping report: {report_path}")
            return True

        except Exception as e:
            logging.error(f"Error creating vocabulary mapping report: {e}")
            return False

    def run(self) -> bool:
        """Main execution method."""
        print(f"\nARCHITECTURAL DRAWINGS STEP 3 - VOCABULARY SELECTION (Gemini)")
        print(f"Processing folder: {self.folder_path}")
        print(f"Model: {self.model_name}")
        print("-" * 50)

        if not self.detect_workflow_type():
            return False

        if not self.load_json_data():
            return False

        entries_with_vocab = self.find_entries_with_vocabulary()
        if not entries_with_vocab:
            print("No entries with vocabulary terms found")
            return False

        print(f"Found {len(entries_with_vocab)} entries with vocabulary terms")

        model_info = get_model_info(self.model_name)
        if model_info:
            print(f"Pricing: ${model_info['input_per_1k']:.5f}/1K input, ${model_info['output_per_1k']:.5f}/1K output")

        print(f"\nSelecting best vocabulary terms for each drawing...")
        selection_results = self.process_vocabulary_selection(entries_with_vocab)

        if not selection_results:
            print("Vocabulary selection failed")
            return False

        if not self.update_json_data(selection_results):
            return False

        if not self.create_vocabulary_mapping_json(selection_results):
            return False

        if not self.create_vocabulary_mapping_report(selection_results):
            return False

        total_processing_time = sum(result.get('processing_time', 0) for result in selection_results.values())

        estimated_cost = calculate_cost(
            model_name=self.model_name,
            prompt_tokens=api_stats.total_input_tokens,
            completion_tokens=api_stats.total_output_tokens,
            is_batch=False
        )

        logs_folder_path = os.path.join(self.folder_path, "logs")
        if not os.path.exists(logs_folder_path):
            os.makedirs(logs_folder_path)

        create_token_usage_log(
            logs_folder_path=logs_folder_path,
            script_name="architectural_drawings_vocabulary_selection_gemini",
            model_name=self.model_name,
            total_items=len(selection_results),
            items_with_issues=0,
            total_time=total_processing_time,
            total_prompt_tokens=api_stats.total_input_tokens,
            total_completion_tokens=api_stats.total_output_tokens,
            additional_metrics={
                "Actual cost": f"${estimated_cost:.4f}",
                "Average tokens per entry": f"{(api_stats.total_input_tokens + api_stats.total_output_tokens)/len(selection_results):.0f}" if selection_results else "0",
            }
        )

        total_selected = sum(len(result['selection_result'].get('selected_terms', [])) for result in selection_results.values())
        entries_with_selections = sum(1 for result in selection_results.values() if result['selection_result'].get('selected_terms'))

        print("\n" + "=" * 50)
        print(f"STEP 3 COMPLETE (Gemini)")
        print(f"Entries processed: {len(selection_results)}")
        print(f"Total vocabulary terms selected: {total_selected}")
        print(f"Entries with selections: {entries_with_selections}/{len(selection_results)}")
        print(f"Total tokens: {api_stats.total_input_tokens + api_stats.total_output_tokens:,}")
        print(f"Estimated cost: ${estimated_cost:.4f}")

        return True

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_output_dir = os.path.join(script_dir, "output_folders")

    model_name = os.getenv('MODEL_NAME', DEFAULT_MODEL)

    folder_path = find_newest_folder(base_output_dir)
    if not folder_path:
        print(f"No folders found in: {base_output_dir}")
        return 1
    print(f"Auto-selected newest folder: {os.path.basename(folder_path)}")

    processor = ArchitecturalDrawingsVocabularyProcessor(folder_path, model_name)
    success = processor.run()

    if not success:
        print("Vocabulary selection failed")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
