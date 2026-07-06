# Step 3: Vocabulary term selection using the provider configured in config.py.
import os
import json
import logging
import time
from datetime import datetime
from typing import List, Dict, Any, Tuple
import tenacity
from prompts import ArchitecturalDrawingPrompts
from shared_utilities import APIStats, find_newest_folder
from model_pricing import calculate_cost, get_model_info
from token_logging import create_token_usage_log, log_individual_response
from batch_processor import BatchProcessor
from config import get_step3_config, OPENAI_USE_PORTKEY

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger("anthropic").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

api_stats = APIStats()

# Initialized in main() via _init_provider()
_provider = None
_client = None


class NormalizedUsage:
    """Unified usage object with prompt_tokens / completion_tokens for all providers."""
    def __init__(self, prompt_tokens, completion_tokens):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


def _init_provider(provider):
    """Lazy-import and initialize the API client for the given provider."""
    global _provider, _client
    _provider = provider
    if provider == "claude":
        import anthropic
        _client = anthropic.Anthropic(api_key=os.getenv('CLAUDE_API_KEY'))
    elif provider == "openai":
        if OPENAI_USE_PORTKEY:
            from portkey_ai import Portkey
            _client = Portkey(
                api_key=os.getenv('PORTKEY_API_KEY'),
                virtual_key=os.getenv('PORTKEY_VIRTUAL_KEY')
            )
        else:
            from openai import OpenAI
            _client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    elif provider == "gemini":
        from google import genai
        _client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
    else:
        raise ValueError(f"Unknown provider: {provider}. Choose from: claude, openai, gemini")


def load_collection_context(image_folder_path: str) -> str:
    """Load collection context from text files in the image folder."""
    if not image_folder_path or not os.path.exists(image_folder_path):
        return ""

    context_data = {}
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


def get_max_tokens_param(model_name: str, max_tokens: int) -> dict:
    """Return the correct max tokens parameter for OpenAI model variants."""
    if model_name.startswith('gpt-5') or model_name.startswith('o1') or model_name.startswith('o3'):
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max_tokens}


def prepare_batch_requests(entries_with_vocab, vocabulary_selector, model_name):
    """Prepare batch requests for OpenAI batch processing."""
    batch_requests = []
    custom_id_mapping = {}

    for i, (entry_index, entry_data) in enumerate(entries_with_vocab):
        user_prompt = vocabulary_selector.create_user_prompt(entry_data)
        if not user_prompt:
            continue

        request_data = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": vocabulary_selector.system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            **get_max_tokens_param(model_name, 4000)
        }

        batch_requests.append(request_data)
        custom_id_mapping[f"vocab_selection_{i}"] = {
            "entry_index": entry_index,
            "entry_data": entry_data,
            "row_number": entry_index + 2
        }

    return batch_requests, custom_id_mapping


class VocabularySelector:
    """Selects the best vocabulary terms for each drawing using the configured provider."""

    def __init__(self, model_name: str, collection_context: str = ""):
        self.model_name = model_name
        self.collection_context = collection_context
        self.system_prompt = ArchitecturalDrawingPrompts.get_vocabulary_selection_system_prompt(collection_context)

    def create_system_prompt(self) -> str:
        return ArchitecturalDrawingPrompts.get_vocabulary_selection_system_prompt(self.collection_context)

    def create_user_prompt(self, entry_data: Dict[str, Any]) -> str:
        """Build the user prompt for a specific entry."""
        analysis = entry_data.get('analysis', {})
        content_parts = []

        if analysis.get('title'):
            content_parts.append(f"TITLE:\n{analysis['title']}")
        if analysis.get('genre'):
            content_parts.append(f"DRAWING TYPE:\n{analysis['genre']}")
        if analysis.get('description'):
            content_parts.append(f"DESCRIPTION:\n{analysis['description']}")
        if analysis.get('topics'):
            topics = analysis['topics']
            content_parts.append(f"TOPICS:\n{', '.join(topics) if isinstance(topics, list) else topics}")
        if analysis.get('named_entities'):
            named_entities = analysis['named_entities']
            content_parts.append(f"NAMED ENTITIES:\n{', '.join(named_entities) if isinstance(named_entities, list) else named_entities}")
        if analysis.get('date_on_drawing'):
            content_parts.append(f"DATE:\n{analysis['date_on_drawing']}")
        if analysis.get('format_media'):
            content_parts.append(f"FORMAT MEDIA:\n{analysis['format_media']}")
        if analysis.get('medium'):
            content_parts.append(f"MEDIUM:\n{analysis['medium']}")
        if analysis.get('support'):
            content_parts.append(f"SUPPORT:\n{analysis['support']}")

        content_description = "\n\n".join(content_parts)

        topic_to_terms = analysis.get('vocabulary_search_results', {})
        medium_to_terms = analysis.get('medium_vocabulary_search_results', {})

        if not topic_to_terms and not medium_to_terms:
            return None

        topics_section = self._build_topic_organized_terms(topic_to_terms) if topic_to_terms else ""
        medium_section = self._build_topic_organized_terms(medium_to_terms) if medium_to_terms else ""

        medium_prompt_section = ""
        if medium_section:
            medium_prompt_section = f"""
FORMAT/MEDIA VOCABULARY TERMS (Getty AAT only):
{medium_section}
Select the most accurate Getty AAT terms for the medium and support materials. Only select terms that precisely match the materials described in the Format Media field. Use exact labels.
"""

        user_prompt = f"""Analyze this architectural drawing metadata and select appropriate vocabulary terms:

{content_description}

AVAILABLE VOCABULARY TERMS BY TOPIC:
{topics_section}
{medium_prompt_section}
Select the most relevant terms following your instructions. Use exact labels without [source] brackets. Skip topics with no genuinely relevant terms.
"""
        return user_prompt

    def _build_topic_organized_terms(self, topic_to_terms: Dict[str, List[Dict]]) -> str:
        sections = []
        for topic, terms in topic_to_terms.items():
            if terms:
                sections.append(f"  Topic: {topic}")
                term_strings = []
                for term in terms:
                    if isinstance(term, dict):
                        label = term.get('label', '').strip()
                        source = term.get('source', 'Unknown')
                        uri = term.get('uri', '')
                        term_strings.append(f"{label} ({uri}) [{source}]" if uri else f"{label} [{source}]")
                sections.append(f"  Terms: {'; '.join(term_strings)}")
                sections.append("")
        return "\n".join(sections)

    @tenacity.retry(
        wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
        stop=tenacity.stop_after_attempt(5),
        retry=tenacity.retry_if_exception_type(Exception)
    )
    def select_vocabulary_terms(self, entry_data: Dict[str, Any]) -> Tuple[Dict[str, Any], str, NormalizedUsage, float]:
        """Select vocabulary terms for a single entry using the configured provider."""
        user_prompt = self.create_user_prompt(entry_data)

        if not user_prompt:
            return {"selected_terms": []}, "No vocabulary terms available for selection", None, 0

        api_stats.total_requests += 1
        start_time = time.time()

        raw_response, usage = self._call_api(user_prompt)

        processing_time = time.time() - start_time
        api_stats.processing_times.append(processing_time)
        api_stats.total_input_tokens += usage.prompt_tokens
        api_stats.total_output_tokens += usage.completion_tokens

        try:
            parsed_response = self.parse_json_response(raw_response)
            return parsed_response, raw_response, usage, processing_time
        except Exception as e:
            logging.error(f"Error parsing vocabulary selection response: {e}")
            return {"selected_terms": []}, raw_response, usage, processing_time

    def _call_api(self, user_prompt: str) -> Tuple[str, NormalizedUsage]:
        """Make the provider-specific API call. Returns (text, NormalizedUsage)."""
        if _provider == "claude":
            response = _client.messages.create(
                model=self.model_name,
                max_tokens=4000,
                system=self.system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )
            return response.content[0].text.strip(), NormalizedUsage(
                response.usage.input_tokens, response.usage.output_tokens
            )

        elif _provider == "openai":
            if OPENAI_USE_PORTKEY:
                response = _client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=4000,
                    temperature=0.1
                )
                return response.choices[0].message.content.strip(), NormalizedUsage(
                    response.usage.prompt_tokens, response.usage.completion_tokens
                )
            else:
                full_prompt = f"{self.system_prompt}\n\n{user_prompt}"
                response = _client.responses.create(
                    model=self.model_name,
                    input=[{"role": "user", "content": [{"type": "input_text", "text": full_prompt}]}],
                    max_output_tokens=4000,
                    temperature=0.1
                )
                return response.output_text.strip(), NormalizedUsage(
                    response.usage.input_tokens, response.usage.output_tokens
                )

        elif _provider == "gemini":
            from google.genai import types
            full_prompt = f"{self.system_prompt}\n\n{user_prompt}"
            response = _client.models.generate_content(
                model=self.model_name,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=8000,
                    thinking_config=types.ThinkingConfig(thinking_level="low")
                )
            )
            input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            return response.text.strip(), NormalizedUsage(input_tokens, output_tokens)

    def parse_json_response(self, raw_response: str) -> Dict[str, Any]:
        from shared_utilities import parse_json_response_enhanced
        parsed_json, error = parse_json_response_enhanced(raw_response)
        if parsed_json is None:
            raise ValueError(f"Could not parse JSON response: {error}")
        if 'selected_terms' not in parsed_json:
            parsed_json['selected_terms'] = []
        return parsed_json


class ArchitecturalDrawingsVocabularyProcessor:
    """Main class for vocabulary selection and output generation."""

    def __init__(self, folder_path: str, model_name: str):
        self.folder_path = folder_path
        self.model_name = model_name
        self.workflow_type = None
        self.json_data = None
        self.json_folder = None
        self.collection_context = ""
        self.vocabulary_selector = None
        self.was_batch_processed = False

    def detect_workflow_type(self) -> bool:
        json_folder = os.path.join(self.folder_path, "metadata", "json")
        json_path = os.path.join(json_folder, "drawings_workflow.json")

        if os.path.exists(json_path):
            self.workflow_type = 'drawings'
            self.json_folder = json_folder
        else:
            logging.error("Could not find drawings_workflow.json in metadata/json.")
            return False

        vocab_report_path = os.path.join(self.folder_path, "metadata", 'vocabulary_mapping_report.txt')
        if not os.path.exists(vocab_report_path):
            logging.error("Vocabulary enhancement (step 2) must be run before step 3.")
            return False

        return True

    def load_json_data(self) -> bool:
        json_filename = f"{self.workflow_type}_workflow.json"
        json_path = os.path.join(self.json_folder, json_filename)

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                self.json_data = json.load(f)

            data_items = self.json_data[:-1] if self.json_data and 'api_stats' in self.json_data[-1] else self.json_data

            has_vocab_terms = any(
                item['analysis'].get('vocabulary_search_results', {}) or
                item['analysis'].get('medium_vocabulary_search_results', {})
                for item in data_items if 'analysis' in item
            )

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
        entries_with_vocab = []
        data_items = self.json_data[:-1] if self.json_data and 'api_stats' in self.json_data[-1] else self.json_data

        for i, item in enumerate(data_items):
            if 'analysis' in item:
                vocab_terms = item['analysis'].get('vocabulary_search_results', {})
                medium_vocab_terms = item['analysis'].get('medium_vocabulary_search_results', {})
                if vocab_terms or medium_vocab_terms:
                    entries_with_vocab.append((i, item))

        return entries_with_vocab

    def process_vocabulary_selection(self, entries_with_vocab: List[Tuple[int, Dict[str, Any]]]) -> Dict[int, Dict[str, Any]]:
        """Process vocabulary selection. OpenAI uses batch when count >= threshold; others always individual."""
        selection_results = {}

        logs_folder_path = os.path.join(self.folder_path, "logs")
        if not os.path.exists(logs_folder_path):
            os.makedirs(logs_folder_path)

        total_entries = len(entries_with_vocab)

        if _provider == "openai":
            processor = BatchProcessor()
            use_batch = processor.should_use_batch(total_entries)
            print(f"Processing mode: {'BATCH' if use_batch else 'INDIVIDUAL'}")

            if use_batch:
                print(f"Preparing {total_entries} requests for batch processing...")
                batch_requests, custom_id_mapping = prepare_batch_requests(
                    entries_with_vocab, self.vocabulary_selector, self.model_name
                )

                if not batch_requests:
                    print("No valid requests to process")
                    return selection_results

                cost_estimate = processor.estimate_batch_cost(batch_requests, self.model_name)
                print(f"Cost estimate: ${cost_estimate['batch_cost']:.4f} (${cost_estimate['savings']:.4f} savings)")

                formatted_requests = processor.create_batch_requests(batch_requests, "vocab_selection")
                batch_id = processor.submit_batch(
                    formatted_requests,
                    f"Architectural Drawings Vocabulary Selection - {len(batch_requests)} entries - {datetime.now().strftime('%Y-%m-%d')}"
                )
                batch_results = processor.wait_for_completion(batch_id, max_wait_hours=24, check_interval_minutes=5)

                if batch_results:
                    processed_results = processor.process_batch_results(batch_results, custom_id_mapping)
                    print(f"Processing batch results...")

                    api_stats.total_input_tokens = processed_results["summary"]["total_prompt_tokens"]
                    api_stats.total_output_tokens = processed_results["summary"]["total_completion_tokens"]
                    self.was_batch_processed = True

                    for custom_id, result_data in processed_results["results"].items():
                        if custom_id.startswith("vocab_selection_"):
                            parts = custom_id.split("_")
                            if len(parts) >= 3:
                                try:
                                    index = int(parts[2])
                                    mapping_key = f"vocab_selection_{index}"

                                    if mapping_key in custom_id_mapping:
                                        entry_index = custom_id_mapping[mapping_key]["entry_index"]
                                        entry_data = custom_id_mapping[mapping_key]["entry_data"]
                                        row_number = custom_id_mapping[mapping_key]["row_number"]

                                        if result_data["success"]:
                                            raw_response = result_data["content"]
                                            usage = result_data["usage"]

                                            try:
                                                selection_result = self.vocabulary_selector.parse_json_response(raw_response)
                                            except Exception as e:
                                                logging.error(f"Error parsing vocabulary selection response: {e}")
                                                selection_result = {"selected_terms": []}

                                            log_individual_response(
                                                logs_folder_path=logs_folder_path,
                                                script_name="architectural_drawings_vocabulary_selection",
                                                row_number=row_number,
                                                barcode=f"{entry_data.get('folder', 'unknown')}_page{entry_data.get('page_number', 'unknown')}",
                                                response_text=raw_response,
                                                model_name=self.model_name,
                                                prompt_tokens=usage.get("prompt_tokens", 0),
                                                completion_tokens=usage.get("completion_tokens", 0),
                                                processing_time=0
                                            )

                                            selection_results[entry_index] = {
                                                'selection_result': selection_result,
                                                'raw_response': raw_response,
                                                'processing_time': 0
                                            }
                                            print(f"   Entry {entry_index}: Selected {len(selection_result.get('selected_terms', []))} vocabulary terms")

                                        else:
                                            error_msg = result_data['error']
                                            raw_response = f"Error: {error_msg}"

                                            log_individual_response(
                                                logs_folder_path=logs_folder_path,
                                                script_name="architectural_drawings_vocabulary_selection",
                                                row_number=row_number,
                                                barcode=f"{entry_data.get('folder', 'unknown')}_page{entry_data.get('page_number', 'unknown')}",
                                                response_text=raw_response,
                                                model_name=self.model_name,
                                                prompt_tokens=0,
                                                completion_tokens=0,
                                                processing_time=0
                                            )
                                            selection_results[entry_index] = {
                                                'selection_result': {'selected_terms': []},
                                                'raw_response': raw_response,
                                                'processing_time': 0
                                            }
                                            print(f"   Entry {entry_index}: Processing failed: {error_msg}")

                                except (ValueError, IndexError) as e:
                                    logging.error(f"Error processing custom_id {custom_id}: {e}")
                                    continue

                    print(f"\nBatch processing completed: {len(selection_results)}/{total_entries} entries processed")
                    return selection_results

        print(f"Processing {total_entries} entries individually...")
        self.was_batch_processed = False
        return self._process_individual(entries_with_vocab, logs_folder_path)

    def _process_individual(self, entries_with_vocab: List[Tuple[int, Dict[str, Any]]], logs_folder_path: str) -> Dict[int, Dict[str, Any]]:
        """Process vocabulary selection using individual API calls."""
        selection_results = {}
        total_entries = len(entries_with_vocab)
        processed_entries = 0

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

                print(f"   Selected {len(selection_result.get('selected_terms', []))} vocabulary terms")
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

    def match_selected_labels_to_original_terms(self, selected_labels: List[str], vocab_search_results: Dict[str, List[Dict]], medium_vocab_results: Dict[str, List[Dict]] = None) -> List[Dict]:
        """Match selected labels to original terms with source priority.

        Tracks which subject each term was derived from (for cascade rejection).
        Returns terms with 'is_medium_term' flag set appropriately.
        """
        import re

        all_available_terms = []
        for topic, terms in vocab_search_results.items():
            for term in terms:
                if isinstance(term, dict):
                    t = term.copy()
                    t['derived_from_topic'] = topic
                    t['is_medium_term'] = False
                    all_available_terms.append(t)

        if medium_vocab_results:
            for topic, terms in medium_vocab_results.items():
                for term in terms:
                    if isinstance(term, dict):
                        t = term.copy()
                        t['derived_from_topic'] = topic
                        t['is_medium_term'] = True
                        all_available_terms.append(t)

        def normalize_for_comparison(label: str) -> str:
            normalized = re.sub(r'[^a-z\s]', '', label.lower())
            return re.sub(r'\s+', ' ', normalized).strip()

        source_priority = {'Getty AAT': 1, 'LCSH': 2, 'FAST': 3, 'Getty TGN': 4}
        matched_terms = []

        for selected_label in selected_labels:
            candidate_matches = []
            selected_words = set(normalize_for_comparison(selected_label).split())

            for term in all_available_terms:
                term_words = set(normalize_for_comparison(term.get('label', '')).split())
                if selected_words == term_words and len(selected_words) > 0:
                    candidate_matches.append(term)

            if not candidate_matches:
                selected_normalized = selected_label.lower().strip()
                for term in all_available_terms:
                    if term.get('label', '').lower().strip() == selected_normalized:
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
        try:
            data_items = self.json_data[:-1] if self.json_data and 'api_stats' in self.json_data[-1] else self.json_data
            api_stats_data = self.json_data[-1] if self.json_data and 'api_stats' in self.json_data[-1] else None

            updated_items = []
            for i, item in enumerate(data_items):
                if i in selection_results:
                    selected_term_responses = selection_results[i]['selection_result'].get('selected_terms', [])
                    selected_labels = [t.get('label', '').strip() for t in selected_term_responses if isinstance(t, dict)]

                    vocab_search_results = item['analysis'].get('vocabulary_search_results', {})
                    medium_vocab_results = item['analysis'].get('medium_vocabulary_search_results', {})
                    matched_terms = self.match_selected_labels_to_original_terms(selected_labels, vocab_search_results, medium_vocab_results)

                    subject_terms = [t for t in matched_terms if not t.get('is_medium_term', False)]
                    medium_terms = [t for t in matched_terms if t.get('is_medium_term', False)]

                    for t in subject_terms:
                        t.pop('is_medium_term', None)
                    for t in medium_terms:
                        t.pop('is_medium_term', None)

                    item['analysis']['final_selected_terms'] = subject_terms
                    item['analysis']['final_selected_medium_terms'] = medium_terms
                else:
                    item['analysis']['final_selected_terms'] = []
                    item['analysis']['final_selected_medium_terms'] = []

                updated_items.append(item)

            if api_stats_data:
                updated_items.append(api_stats_data)

            json_path = os.path.join(self.json_folder, f"{self.workflow_type}_workflow.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(updated_items, f, indent=2, ensure_ascii=False)

            print("Updated JSON file with selected vocabulary terms")
            return True

        except Exception as e:
            logging.error(f"Error updating JSON data: {e}")
            return False

    def create_vocabulary_mapping_json(self, selection_results: Dict[int, Dict[str, Any]]) -> bool:
        try:
            data_items = self.json_data[:-1] if self.json_data and 'api_stats' in self.json_data[-1] else self.json_data

            vocabulary_mapping = {
                "generated_timestamp": datetime.now().isoformat(),
                "model": self.model_name,
                "drawings": []
            }

            for i, item in enumerate(data_items):
                vocab_search_results = item['analysis'].get('vocabulary_search_results', {})
                medium_vocab_results = item['analysis'].get('medium_vocabulary_search_results', {})
                selected_terms = item['analysis'].get('final_selected_terms', [])
                selected_medium_terms = item['analysis'].get('final_selected_medium_terms', [])

                selected_uris = {t['uri'] for t in selected_terms if isinstance(t, dict) and t.get('uri')}
                selected_medium_uris = {t['uri'] for t in selected_medium_terms if isinstance(t, dict) and t.get('uri')}

                drawing_data = {
                    "folder": item.get('folder', 'Unknown'),
                    "page_number": item.get('page_number', 'Unknown'),
                    "vocabulary_search_results": {
                        topic: [{**t, 'selected': t.get('uri', '') in selected_uris} for t in terms if isinstance(t, dict)]
                        for topic, terms in vocab_search_results.items()
                    },
                    "medium_vocabulary_search_results": {
                        topic: [{**t, 'selected': t.get('uri', '') in selected_medium_uris} for t in terms if isinstance(t, dict)]
                        for topic, terms in medium_vocab_results.items()
                    },
                    "final_selected_terms": selected_terms,
                    "final_selected_medium_terms": selected_medium_terms
                }
                vocabulary_mapping['drawings'].append(drawing_data)

            vocab_mapping_path = os.path.join(self.json_folder, "vocabulary_mapping.json")
            with open(vocab_mapping_path, 'w', encoding='utf-8') as f:
                json.dump(vocabulary_mapping, f, indent=2, ensure_ascii=False)

            print(f"Created vocabulary mapping JSON: {vocab_mapping_path}")
            return True

        except Exception as e:
            logging.error(f"Error creating vocabulary mapping JSON: {e}")
            return False

    def create_vocabulary_mapping_report(self, selection_results: Dict[int, Dict[str, Any]]) -> bool:
        try:
            metadata_dir = os.path.join(self.folder_path, "metadata")
            report_path = os.path.join(metadata_dir, "vocabulary_mapping_report.txt")
            data_items = self.json_data[:-1] if self.json_data and 'api_stats' in self.json_data[-1] else self.json_data

            with open(report_path, 'w', encoding='utf-8') as f:
                f.write("ARCHITECTURAL DRAWINGS VOCABULARY MAPPING REPORT\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Model: {self.model_name}\n\n")

                for item in data_items:
                    folder = item.get('folder', 'Unknown')
                    page_number = item.get('page_number', 'Unknown')

                    f.write(f"DRAWING {page_number} (Collection: {folder}):\n")
                    f.write("=" * 50 + "\n")

                    vocab_search_results = item['analysis'].get('vocabulary_search_results', {})
                    medium_vocab_results = item['analysis'].get('medium_vocabulary_search_results', {})
                    selected_terms = item['analysis'].get('final_selected_terms', [])
                    selected_medium_terms = item['analysis'].get('final_selected_medium_terms', [])

                    selected_uris = {t.get('uri', '') for t in selected_terms if isinstance(t, dict)}
                    selected_medium_uris = {t.get('uri', '') for t in selected_medium_terms if isinstance(t, dict)}

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

                    if medium_vocab_results:
                        f.write(f"\nFORMAT/MEDIA VOCABULARY SEARCH RESULTS (Getty AAT):\n")
                        for topic, terms in medium_vocab_results.items():
                            f.write(f"  Material: {topic}\n")
                            if terms:
                                topic_terms = []
                                for term in terms:
                                    if isinstance(term, dict):
                                        label = term.get('label', '')
                                        source = term.get('source', '')
                                        uri = term.get('uri', '')
                                        is_selected = uri in selected_medium_uris
                                        topic_terms.append(f"{label} ({uri}) [{source}] {'✓' if is_selected else ''}")
                                f.write(f"    Terms: {'; '.join(topic_terms)}\n")
                            else:
                                f.write(f"    Terms: No terms available\n")
                            f.write("\n")

                    if selected_terms:
                        f.write("FINAL SELECTED TERMS:\n")
                        for term in selected_terms:
                            if isinstance(term, dict):
                                f.write(f"  - {term.get('label', '')} ({term.get('uri', '')}) [{term.get('source', '')}]\n")
                        f.write("\n")

                    if selected_medium_terms:
                        f.write("FINAL SELECTED FORMAT/MEDIA TERMS (Getty AAT):\n")
                        for term in selected_medium_terms:
                            if isinstance(term, dict):
                                f.write(f"  - {term.get('label', '')} ({term.get('uri', '')}) [{term.get('source', '')}]\n")
                        f.write("\n")

                    if not vocab_search_results and not medium_vocab_results:
                        f.write("\nNo vocabulary terms available for this drawing.\n\n")

                    f.write("=" * 50 + "\n\n")

            print(f"Created vocabulary mapping report: {report_path}")
            return True

        except Exception as e:
            logging.error(f"Error creating vocabulary mapping report: {e}")
            return False

    def run(self) -> bool:
        provider_label = f"{_provider.upper()}" + (" (Portkey)" if _provider == "openai" and OPENAI_USE_PORTKEY else "")
        print(f"\nARCHITECTURAL DRAWINGS STEP 3 - VOCABULARY SELECTION ({provider_label})")
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

        total_processing_time = sum(r.get('processing_time', 0) for r in selection_results.values())
        estimated_cost = calculate_cost(
            model_name=self.model_name,
            prompt_tokens=api_stats.total_input_tokens,
            completion_tokens=api_stats.total_output_tokens,
            is_batch=self.was_batch_processed
        )

        logs_folder_path = os.path.join(self.folder_path, "logs")
        if not os.path.exists(logs_folder_path):
            os.makedirs(logs_folder_path)

        create_token_usage_log(
            logs_folder_path=logs_folder_path,
            script_name=f"architectural_drawings_vocabulary_selection_{_provider}",
            model_name=self.model_name,
            total_items=len(selection_results),
            items_with_issues=0,
            total_time=total_processing_time,
            total_prompt_tokens=api_stats.total_input_tokens,
            total_completion_tokens=api_stats.total_output_tokens,
            additional_metrics={
                "Processing mode": "BATCH" if self.was_batch_processed else "INDIVIDUAL",
                "Actual cost": f"${estimated_cost:.4f}",
                "Average tokens per entry": f"{(api_stats.total_input_tokens + api_stats.total_output_tokens)/len(selection_results):.0f}" if selection_results else "0",
            }
        )

        total_selected = sum(len(r['selection_result'].get('selected_terms', [])) for r in selection_results.values())
        entries_with_selections = sum(1 for r in selection_results.values() if r['selection_result'].get('selected_terms'))

        print("\n" + "=" * 50)
        print(f"STEP 3 COMPLETE ({provider_label})")
        print(f"Entries processed: {len(selection_results)}")
        print(f"Total vocabulary terms selected: {total_selected}")
        print(f"Entries with selections: {entries_with_selections}/{len(selection_results)}")
        print(f"Total tokens: {api_stats.total_input_tokens + api_stats.total_output_tokens:,}")
        print(f"Estimated cost: ${estimated_cost:.4f}")

        return True


def main():
    config = get_step3_config()
    provider = config["provider"]
    model_name = os.getenv('MODEL_NAME', config["model"])

    _init_provider(provider)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_output_dir = os.path.join(script_dir, "output_folders")

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
