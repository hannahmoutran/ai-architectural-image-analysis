# Extracts metadata from architectural drawings using the provider configured in config.py.
import os
import json
import base64
import logging
from datetime import datetime
import tenacity
import re
from PIL import Image as PILImage
from io import BytesIO
import time
from prompts import ArchitecturalDrawingPrompts
from shared_utilities import APIStats, postprocess_api_response, parse_json_response_enhanced
from model_pricing import calculate_cost
from token_logging import create_token_usage_log, log_individual_response
from batch_processor import BatchProcessor
from config import get_step1_config, OPENAI_USE_PORTKEY

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

CALIBRATION_EXAMPLES_FILENAME = "collection-examples.txt"


def read_calibration_examples(input_folder: str):
    """Return the contents of collection-examples.txt if it exists in input_folder."""
    path = os.path.join(input_folder, CALIBRATION_EXAMPLES_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        logging.warning(f"Could not read calibration examples: {e}")
        return None


def format_collection_examples(examples_text: str, style_analysis: str = "") -> str:
    """Format calibration examples and optional style guide for prompt injection."""
    parts = [
        "COLLECTION-SPECIFIC STYLE GUIDE AND EXAMPLES:",
        "The following are actual drawings from this collection that an archivist has reviewed and approved.",
        "Use them as a reference for writing style, level of detail, terminology, and formatting.\n",
    ]
    if style_analysis:
        parts.append(f"STYLE GUIDE (derived from archivist edits):\n{style_analysis}\n")
    parts.append(f"ARCHIVIST-APPROVED EXAMPLES:\n{examples_text}")
    return "\n".join(parts)


_STYLE_GUIDE_MARKER = "\n# STYLE GUIDE\n"


def _split_calibration_file(text: str) -> tuple[str, str]:
    """Split collection-examples.txt into (examples_text, style_guide_text).

    Returns the raw examples section and the editable style guide section separately.
    If no embedded style guide is found, style_guide_text is "".
    """
    if _STYLE_GUIDE_MARKER not in text:
        return text, ""

    examples_part, rest = text.split(_STYLE_GUIDE_MARKER, 1)

    # Strip the header comment lines ("# Generated...", "# ===...") from the style guide block
    rest_lines = rest.split('\n')
    content_start = 0
    for i, line in enumerate(rest_lines):
        if not line.startswith('#') and line.strip() != '':
            content_start = i
            break

    style_guide = '\n'.join(rest_lines[content_start:]).strip()
    return examples_part.rstrip(), style_guide


class SimpleUsage:
    """Normalized token usage object, always uses input_tokens/output_tokens."""
    def __init__(self, input_tokens, output_tokens):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


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
            _client = OpenAI(api_key=os.getenv('OPENAI_API_KEY_DIRECT'))
    elif provider == "gemini":
        from google import genai
        _client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
    else:
        raise ValueError(f"Unknown provider: {provider}. Choose from: claude, openai, gemini")


def _get_media_type(img_path):
    ext = os.path.splitext(img_path)[1].lower()
    return {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp'
    }.get(ext, 'image/jpeg')


def _prepare_image(image_path):
    """Prepare image data for the current provider.

    Returns:
        (base64_str, media_type) for claude/openai, or (bytes, media_type) for gemini.
    """
    ext = os.path.splitext(image_path)[1].lower()
    is_tiff = ext in ('.tif', '.tiff')

    if _provider == "gemini":
        if is_tiff:
            img = PILImage.open(image_path)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            buf = BytesIO()
            img.save(buf, format='JPEG', quality=95)
            buf.seek(0)
            return buf.read(), 'image/jpeg'
        with open(image_path, "rb") as f:
            return f.read(), _get_media_type(image_path)

    # claude and openai: return base64 string
    if _provider == "claude" and is_tiff:
        img = PILImage.open(image_path)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        buf = BytesIO()
        img.save(buf, format='JPEG', quality=95)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode('utf-8'), 'image/jpeg'

    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8'), _get_media_type(image_path)


def _call_api(image_path, model_name, prompt):
    """Make the provider-specific API call. Returns (text, SimpleUsage)."""
    image_data, media_type = _prepare_image(image_path)

    if _provider == "claude":
        response = _client.messages.create(
            model=model_name,
            max_tokens=3000,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                {"type": "text", "text": prompt}
            ]}]
        )
        return response.content[0].text.strip(), SimpleUsage(response.usage.input_tokens, response.usage.output_tokens)

    elif _provider == "openai":
        if OPENAI_USE_PORTKEY:
            max_tokens_key = "max_completion_tokens" if any(model_name.startswith(p) for p in ("gpt-5", "o1", "o3")) else "max_tokens"
            response = _client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}", "detail": "high"}}
                ]}],
                **{max_tokens_key: 3000},
                temperature=0.3
            )
            return response.choices[0].message.content.strip(), SimpleUsage(response.usage.prompt_tokens, response.usage.completion_tokens)
        else:
            response = _client.responses.create(
                model=model_name,
                input=[{"role": "user", "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": f"data:image/jpeg;base64,{image_data}", "detail": "high"}
                ]}],
                max_output_tokens=3000,
                temperature=0.3
            )
            return response.output_text.strip(), SimpleUsage(response.usage.input_tokens, response.usage.output_tokens)

    elif _provider == "gemini":
        from google.genai import types
        response = _client.models.generate_content(
            model=model_name,
            contents=[types.Content(parts=[
                types.Part(inline_data=types.Blob(mime_type=media_type, data=image_data)),
                types.Part(text=prompt)
            ])],
            config=types.GenerateContentConfig(
                max_output_tokens=3000,
                thinking_config=types.ThinkingConfig(thinking_level="low")
            )
        )
        input_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
        output_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
        return response.text.strip(), SimpleUsage(input_tokens, output_tokens)


def _call_text_api(prompt: str, model_name: str):
    """Make a text-only API call using the initialized provider. Returns (text, SimpleUsage)."""
    if _provider == "claude":
        response = _client.messages.create(
            model=model_name,
            max_tokens=4000,
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        )
        return response.content[0].text.strip(), SimpleUsage(response.usage.input_tokens, response.usage.output_tokens)

    elif _provider == "openai":
        if OPENAI_USE_PORTKEY:
            response = _client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4000,
                temperature=0.3
            )
            return response.choices[0].message.content.strip(), SimpleUsage(response.usage.prompt_tokens, response.usage.completion_tokens)
        else:
            response = _client.responses.create(
                model=model_name,
                input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
                max_output_tokens=4000,
                temperature=0.3
            )
            return response.output_text.strip(), SimpleUsage(response.usage.input_tokens, response.usage.output_tokens)

    elif _provider == "gemini":
        from google.genai import types
        response = _client.models.generate_content(
            model=model_name,
            contents=[types.Content(parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(max_output_tokens=4000)
        )
        input_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
        output_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
        return response.text.strip(), SimpleUsage(input_tokens, output_tokens)


def generate_style_analysis(examples_text: str, model_name: str) -> str:
    """Call AI to derive a collection style guide from calibration examples. Returns empty string on failure."""
    prompt = ArchitecturalDrawingPrompts.get_style_analysis_prompt(examples_text)
    try:
        text, _ = _call_text_api(prompt, model_name)
        return text
    except Exception as e:
        logging.warning(f"Style analysis failed: {e}")
        return ""


def parse_json_response(raw_response):
    """JSON parsing with trailing comma handling."""
    return parse_json_response_enhanced(raw_response)


def parse_key_value_response(raw_response: str) -> tuple[dict, str]:
    """Parse key-value format response from LLM into a dictionary.

    Handles both plain and markdown-formatted output:
      Title: First Floor Plan - Smith Residence
      **Title:** First Floor Plan - Smith Residence
    """
    if not raw_response or not raw_response.strip():
        return None, "Empty response"

    result = {}

    field_mapping = {
        'title': 'title',
        'contributors': 'contributors',
        'genre': 'genre',
        'description': 'description',
        'topics': 'topics',
        'date on drawing': 'dateOnDrawing',
        'dateondrawing': 'dateOnDrawing',
        'sheet info': 'sheetInfo',
        'sheetinfo': 'sheetInfo',
        'named entities': 'namedEntities',
        'namedentities': 'namedEntities',
        'geographic entities': 'geographicEntities',
        'geographicentities': 'geographicEntities',
        'content warning': 'contentWarning',
        'contentwarning': 'contentWarning'
    }

    current_key = None
    current_value_lines = []

    for line in raw_response.split('\n'):
        found_field = False

        # Strip markdown formatting (headers, bullets/list markers, bold) for field detection
        cleaned_line = line.strip()
        cleaned_line = re.sub(r'^#+\s*', '', cleaned_line)
        cleaned_line = re.sub(r'^[-*+•]+\s*', '', cleaned_line)
        cleaned_line = re.sub(r'\*+', '', cleaned_line)
        cleaned_line_lower = cleaned_line.lower()

        for display_name, dict_key in field_mapping.items():
            if cleaned_line_lower.startswith(display_name + ':'):
                if current_key:
                    value = ' '.join(current_value_lines).strip()
                    result[current_key] = _parse_field_value(current_key, value)

                current_key = dict_key
                colon_pos = cleaned_line.lower().find(display_name + ':')
                if colon_pos != -1:
                    value_start = colon_pos + len(display_name) + 1
                    current_value_lines = [cleaned_line[value_start:].strip()]
                found_field = True
                break

        if not found_field and current_key and line.strip():
            stripped = line.strip()
            if not stripped.startswith('#'):
                current_value_lines.append(stripped)

    if current_key:
        value = ' '.join(current_value_lines).strip()
        result[current_key] = _parse_field_value(current_key, value)

    if not result:
        return None, "No valid fields found in response"

    return result, None


def _parse_field_value(field_key: str, value: str):
    """Parse a field value, converting list fields from semicolon-separated strings."""
    list_fields = ['contributors', 'topics', 'namedEntities', 'geographicEntities']

    if field_key in list_fields:
        items = [item.strip() for item in value.split(';') if item.strip()]
        if field_key == 'contributors':
            parsed_contributors = []
            for item in items:
                match = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', item)
                if match:
                    parsed_contributors.append({
                        'name': match.group(1).strip(),
                        'role': match.group(2).strip()
                    })
                else:
                    parsed_contributors.append({'name': item, 'role': ''})
            return parsed_contributors
        return items

    return value


def parse_key_value_text(text: str) -> dict:
    """Parse collection context text (key: value format)."""
    result = {}
    current_key = None
    current_value_lines = []

    known_fields = ['creator', 'title', 'dates', 'abstract', 'extent', 'repository',
                    'identification', 'language']

    for line in text.split('\n'):
        found_field = False
        for field in known_fields:
            if line.lower().startswith(field + ':'):
                if current_key:
                    result[current_key] = ' '.join(current_value_lines).strip()
                current_key = field.lower()
                value_start = len(field) + 1
                current_value_lines = [line[value_start:].strip()]
                found_field = True
                break

        if not found_field and current_key and line.strip():
            current_value_lines.append(line.strip())

    if current_key:
        result[current_key] = ' '.join(current_value_lines).strip()

    return result


def load_collection_context(input_folder: str = None) -> str:
    """Load collection context from .txt files in the input folder."""
    context_data = {}

    if not input_folder or not os.path.isdir(input_folder):
        return ""

    txt_files = [f for f in os.listdir(input_folder)
                 if f.lower().endswith('.txt') and os.path.isfile(os.path.join(input_folder, f))
                 and f != CALIBRATION_EXAMPLES_FILENAME]

    for txt_file in sorted(txt_files):
        txt_path = os.path.join(input_folder, txt_file)
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
            file_data = parse_key_value_text(file_content)
            context_data.update(file_data)
            logging.info(f"Loaded collection context from: {txt_path}")
        except Exception as e:
            logging.warning(f"Could not load text from {txt_path}: {e}")

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


def collect_all_images(input_folder):
    """Collect all images to process from folder (or its subfolders)."""
    all_images = []

    def safe_page_num(fname: str) -> int:
        m = re.search(r'page(\d+)', fname, re.IGNORECASE)
        return int(m.group(1)) if m else 0

    direct_images = [f for f in os.listdir(input_folder)
                     if os.path.isfile(os.path.join(input_folder, f))
                     and f.lower().endswith(('.jpg', '.jpeg', '.png', '.tif', '.tiff'))]
    if direct_images:
        direct_images_sorted = sorted(direct_images, key=lambda x: (safe_page_num(x), x.lower()))
        folder_label = os.path.basename(os.path.normpath(input_folder)) or "root"
        for idx, img_file in enumerate(direct_images_sorted, start=1):
            page_number = safe_page_num(img_file) or idx
            img_path = os.path.join(input_folder, img_file)
            all_images.append((folder_label, page_number, img_path))

    for folder_name in sorted(os.listdir(input_folder), key=lambda x: x.lower()):
        folder_path = os.path.join(input_folder, folder_name)
        if os.path.isdir(folder_path):
            image_files = [f for f in os.listdir(folder_path)
                           if f.lower().endswith(('.jpg', '.jpeg', '.png', '.tif', '.tiff'))]
            image_files_sorted = sorted(image_files, key=lambda x: (safe_page_num(x), x.lower()))
            for idx, img_file in enumerate(image_files_sorted, start=1):
                page_number = safe_page_num(img_file) or idx
                img_path = os.path.join(folder_path, img_file)
                all_images.append((folder_name, page_number, img_path))

    return all_images


def prepare_batch_requests(all_images, model_name, collection_context="", collection_examples=""):
    """Prepare batch requests (OpenAI only). Uses Responses API format."""
    batch_requests = []
    custom_id_mapping = {}

    prompt = ArchitecturalDrawingPrompts.get_architectural_drawing_prompt(collection_context, collection_examples)

    for i, (folder_name, page_number, img_path) in enumerate(all_images):
        with open(img_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        request_data = {
            "model": model_name,
            "input": [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": f"data:image/jpeg;base64,{base64_image}", "detail": "low"}
                ]
            }],
            "max_output_tokens": 3000
        }

        batch_requests.append(request_data)
        custom_id_mapping[f"arch_drawing_{i}"] = {
            "folder_name": folder_name,
            "page_number": page_number,
            "img_path": img_path,
            "row_number": i + 2
        }

    return batch_requests, custom_id_mapping


@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
    stop=tenacity.stop_after_attempt(3),
    retry=tenacity.retry_if_exception_type(Exception),
    reraise=True
)
def process_image(image_path, model_name, collection_context="", collection_examples=""):
    """Process a single architectural drawing image and return the parsed response."""
    prompt = ArchitecturalDrawingPrompts.get_architectural_drawing_prompt(collection_context, collection_examples)

    api_stats.total_requests += 1
    start_time = time.time()

    raw_response, usage = _call_api(image_path, model_name, prompt)

    processing_time = time.time() - start_time
    api_stats.processing_times.append(processing_time)
    api_stats.total_input_tokens += usage.input_tokens
    api_stats.total_output_tokens += usage.output_tokens

    parsed_data, error = parse_key_value_response(raw_response)

    if parsed_data:
        required_fields = ['title', 'contributors', 'genre', 'description',
                           'topics', 'dateOnDrawing', 'sheetInfo', 'namedEntities',
                           'geographicEntities', 'contentWarning']
        for field in required_fields:
            if field not in parsed_data:
                parsed_data[field] = [] if field in ['contributors', 'topics', 'namedEntities', 'geographicEntities'] else ""

        parsed_data = postprocess_api_response(parsed_data)
        return parsed_data, raw_response, usage, processing_time
    else:
        logging.error(f"Key-value parsing failed for {image_path}: {error}\nRaw response: {raw_response}")
        raise Exception(f"Key-value parsing failed: {error}")


def create_error_response(raw_response, error):
    """Create a standard error response dictionary."""
    return {
        "title": f"Error: {error}",
        "contributors": [],
        "genre": "",
        "description": raw_response,
        "topics": [],
        "dateOnDrawing": "",
        "sheetInfo": "",
        "namedEntities": [],
        "geographicEntities": [],
        "contentWarning": "None"
    }


def create_result_entry(folder_name, page_number, img_path, response_data, raw_response):
    """Create a result entry dictionary for JSON output."""
    return {
        'folder': folder_name,
        'page_number': page_number,
        'image_path': img_path,
        'analysis': {
            'title': response_data.get('title', ''),
            'contributors': response_data.get('contributors', []),
            'genre': response_data.get('genre', ''),
            'description': response_data.get('description', ''),
            'topics': response_data.get('topics', []),
            'date_on_drawing': response_data.get('dateOnDrawing', ''),
            'sheet_info': response_data.get('sheetInfo', ''),
            'named_entities': response_data.get('namedEntities', []),
            'geographic_entities': response_data.get('geographicEntities', []),
            'content_warning': response_data.get('contentWarning', 'None'),
            'raw_response': raw_response
        }
    }


def process_folder_individual(all_images, logs_folder_path, model_name, all_results,
                               issues, collection_context="", collection_examples=""):
    """Process images using individual API calls."""
    items_with_issues = 0
    total_processing_time = 0

    for i, (folder_name, page_number, img_path) in enumerate(all_images):
        row_number = i + 2
        filename = os.path.basename(img_path)

        print(f"\nProcessing drawing {i+1}/{len(all_images)}")
        print(f"   File: {filename}")

        try:
            response_data, raw_response, usage, processing_time = process_image(
                img_path, model_name, collection_context, collection_examples
            )
            total_processing_time += processing_time

            log_individual_response(
                logs_folder_path=logs_folder_path,
                script_name="architectural_drawings_metadata",
                row_number=row_number,
                barcode=f"{folder_name}_drawing{page_number}",
                response_text=raw_response,
                model_name=model_name,
                prompt_tokens=usage.input_tokens if usage else 0,
                completion_tokens=usage.output_tokens if usage else 0,
                processing_time=processing_time
            )

            print(f"   Processed successfully - Tokens: {(usage.input_tokens + usage.output_tokens) if usage else 0:,}")

        except Exception as e:
            logging.error(f"Error processing {img_path}: {str(e)}")
            items_with_issues += 1
            raw_response = f"Processing error: {str(e)}"
            response_data = create_error_response(raw_response, str(e))
            usage = None

            issues.append({"image_path": img_path, "error": str(e)})

            log_individual_response(
                logs_folder_path=logs_folder_path,
                script_name="architectural_drawings_metadata",
                row_number=row_number,
                barcode=f"{folder_name}_drawing{page_number}",
                response_text=raw_response,
                model_name=model_name,
                prompt_tokens=0,
                completion_tokens=0,
                processing_time=0
            )

            print(f"   Processing failed: {str(e)}")

        all_results.append(create_result_entry(folder_name, page_number,
                                               img_path, response_data, raw_response))
        time.sleep(1)

    return (all_results, api_stats, len(all_images), items_with_issues, total_processing_time,
            api_stats.total_input_tokens, api_stats.total_output_tokens, issues, False)


def process_folder_with_batch(input_folder, output_dir, model_name, collection_context="", collection_examples=""):
    """Process folder. OpenAI uses batch when count >= threshold; others always individual."""
    logs_folder_path = os.path.join(output_dir, "logs")
    if not os.path.exists(logs_folder_path):
        os.makedirs(logs_folder_path)

    all_images = collect_all_images(input_folder)
    total_items = len(all_images)
    all_results = []
    issues = []
    items_with_issues = 0

    if _provider == "openai":
        processor = BatchProcessor()
        use_batch = processor.should_use_batch(total_items)

        print(f"\nFound {total_items} images to process")
        print(f"Processing mode: {'BATCH' if use_batch else 'INDIVIDUAL'}")
        print(f"Model: {model_name}")

        if use_batch:
            print(f" Preparing {total_items} requests for batch processing...")

            batch_requests, custom_id_mapping = prepare_batch_requests(all_images, model_name, collection_context, collection_examples)
            cost_estimate = processor.estimate_batch_cost(batch_requests, model_name)
            print(f" Estimated cost: ${cost_estimate['batch_cost']:.4f} (${cost_estimate['savings']:.4f} savings)")

            formatted_requests = processor.create_batch_requests(batch_requests, "arch_drawing")
            batch_id = processor.submit_batch(
                formatted_requests,
                f"Architectural Drawings Metadata - {total_items} images - {datetime.now().strftime('%Y-%m-%d')}"
            )
            batch_results = processor.wait_for_completion(batch_id, max_wait_hours=24, check_interval_minutes=5)

            if batch_results:
                processed_results = processor.process_batch_results(batch_results, custom_id_mapping)
                print(f"Processing batch results...")

                api_stats.total_input_tokens = processed_results["summary"]["total_prompt_tokens"]
                api_stats.total_output_tokens = processed_results["summary"]["total_completion_tokens"]

                for custom_id, result_data in processed_results["results"].items():
                    if custom_id.startswith("arch_drawing_"):
                        parts = custom_id.split("_")
                        if len(parts) >= 3:
                            try:
                                index = int(parts[2])
                                mapping_key = f"arch_drawing_{index}"

                                if mapping_key in custom_id_mapping:
                                    folder_name = custom_id_mapping[mapping_key]["folder_name"]
                                    page_number = custom_id_mapping[mapping_key]["page_number"]
                                    img_path = custom_id_mapping[mapping_key]["img_path"]
                                    row_number = custom_id_mapping[mapping_key]["row_number"]

                                    if result_data["success"]:
                                        raw_response = result_data["content"]
                                        usage = result_data["usage"]

                                        parsed_data, error = parse_key_value_response(raw_response)
                                        if parsed_data:
                                            response_data = postprocess_api_response(parsed_data)
                                        else:
                                            response_data = create_error_response(raw_response, error)

                                        log_individual_response(
                                            logs_folder_path=logs_folder_path,
                                            script_name="architectural_drawings_metadata",
                                            row_number=row_number,
                                            barcode=f"{folder_name}_drawing{page_number}",
                                            response_text=raw_response,
                                            model_name=model_name,
                                            prompt_tokens=usage.get("prompt_tokens", 0),
                                            completion_tokens=usage.get("completion_tokens", 0),
                                            processing_time=0
                                        )
                                    else:
                                        raw_response = f"Error: {result_data['error']}"
                                        items_with_issues += 1
                                        response_data = create_error_response(raw_response, result_data['error'])
                                        issues.append({"image_path": img_path, "error": result_data['error']})

                                        log_individual_response(
                                            logs_folder_path=logs_folder_path,
                                            script_name="architectural_drawings_metadata",
                                            row_number=row_number,
                                            barcode=f"{folder_name}_drawing{page_number}",
                                            response_text=raw_response,
                                            model_name=model_name,
                                            prompt_tokens=0,
                                            completion_tokens=0,
                                            processing_time=0
                                        )

                                    all_results.append(create_result_entry(folder_name, page_number,
                                                                           img_path, response_data, raw_response))

                            except (ValueError, IndexError) as e:
                                logging.error(f"Error processing custom_id {custom_id}: {e}")
                                continue

                summary = processed_results["summary"]
                return (all_results, api_stats, total_items, items_with_issues, 0,
                        summary["total_prompt_tokens"], summary["total_completion_tokens"], issues, True)

    else:
        print(f"\nFound {total_items} images to process")
        print(f"Processing mode: INDIVIDUAL")
        print(f"Model: {model_name}")

    return process_folder_individual(all_images, logs_folder_path, model_name, all_results,
                                     issues, collection_context, collection_examples)


def main():
    config = get_step1_config()
    provider = config["provider"]
    model_name = os.getenv('CONFIG_MODEL', config["model"])
    input_folder_name = os.getenv('CONFIG_IMAGE_FOLDER', config["image_folder"])

    _init_provider(provider)

    script_start_time = time.time()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_folder = os.path.join(script_dir, "image_folders", input_folder_name)

    collection_context = load_collection_context(input_folder=input_folder)

    if not os.path.exists(input_folder):
        print(f"Input folder not found: {os.path.abspath(input_folder)}")
        return 1

    provider_label = f"{provider.upper()}" + (" (Portkey)" if provider == "openai" and OPENAI_USE_PORTKEY else "")
    print(f"\nARCHITECTURAL DRAWINGS METADATA EXTRACTION ({provider_label})\n")
    if collection_context:
        print(f"Collection context: {input_folder_name}")
    print(f"Using input folder: image_folders/{input_folder_name}")

    # Load calibration examples and style guide if available
    raw_file = read_calibration_examples(input_folder)
    collection_examples = ""
    if raw_file:
        examples_text, embedded_style = _split_calibration_file(raw_file)
        if embedded_style:
            print(f"\nCalibration examples with embedded style guide found.")
            collection_examples = format_collection_examples(examples_text, embedded_style)
        else:
            print(f"\nCalibration examples found — generating style analysis...")
            style_analysis = generate_style_analysis(raw_file, model_name)
            if style_analysis:
                print(f"Style analysis complete.")
            else:
                print(f"Style analysis unavailable — using examples only.")
                style_analysis = ""
            collection_examples = format_collection_examples(raw_file, style_analysis)
        print(f"Archivist style guide will be applied to all images in this run.\n")

    current_date = datetime.now().strftime("%Y-%m-%d")
    current_time = datetime.now().strftime("%H-%M-%S")
    folder_name = f"ArchImagesAI_{input_folder_name}_{model_name}_{current_date}_Time_{current_time}"

    base_output_dir = os.path.join(script_dir, "output_folders")
    output_dir = os.path.join(base_output_dir, folder_name)
    os.makedirs(output_dir, exist_ok=True)

    metadata_folder = os.path.join(output_dir, "metadata")
    json_folder = os.path.join(metadata_folder, "json")
    os.makedirs(json_folder, exist_ok=True)

    print(f"Output directory: output_folders/{folder_name}")

    (all_results, api_stats, total_items, items_with_issues, total_processing_time,
     total_prompt_tokens, total_completion_tokens, issues, was_batch_processed) = process_folder_with_batch(
        input_folder, output_dir, model_name, collection_context, collection_examples
    )

    api_summary = {
        "total_requests": api_stats.total_requests,
        "total_input_tokens": total_prompt_tokens,
        "total_output_tokens": total_completion_tokens,
        "total_tokens": total_prompt_tokens + total_completion_tokens,
        "processing_mode": "BATCH" if was_batch_processed else "INDIVIDUAL"
    }
    all_results.append({"api_stats": api_summary})

    if issues:
        all_results.append({"issues": issues})

    json_path = os.path.join(json_folder, "drawings_workflow.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    script_duration = time.time() - script_start_time

    estimated_cost = calculate_cost(
        model_name=model_name,
        prompt_tokens=total_prompt_tokens,
        completion_tokens=total_completion_tokens,
        is_batch=was_batch_processed
    )

    logs_folder_path = os.path.join(output_dir, "logs")
    if not os.path.exists(logs_folder_path):
        os.makedirs(logs_folder_path)

    create_token_usage_log(
        logs_folder_path=logs_folder_path,
        script_name="architectural_drawings_metadata",
        model_name=model_name,
        total_items=total_items,
        items_with_issues=items_with_issues,
        total_time=total_processing_time,
        total_prompt_tokens=total_prompt_tokens,
        total_completion_tokens=total_completion_tokens,
        additional_metrics={
            "Total script execution time": f"{script_duration:.2f}s",
            "Processing time percentage": f"{(total_processing_time/script_duration)*100:.1f}%" if script_duration > 0 else "0%",
            "Items successfully processed": total_items - items_with_issues,
            "Processing mode": "BATCH" if was_batch_processed else "INDIVIDUAL",
            "Cost": f"${estimated_cost:.4f}",
            "Average tokens per item": f"{(total_prompt_tokens + total_completion_tokens)/total_items:.0f}" if total_items > 0 else "0"
        }
    )

    print(f"\nSTEP 1 COMPLETE ({provider_label})")
    print(f"Successfully processed: {total_items - items_with_issues}/{total_items} drawings")
    print(f"Items with issues: {items_with_issues}")
    print(f"Total script time: {script_duration:.1f}s ({script_duration/60:.1f} minutes)")
    print(f"Tokens: {total_prompt_tokens + total_completion_tokens:,} (Input: {total_prompt_tokens:,}, Output: {total_completion_tokens:,})")
    print(f"Cost estimate: ${estimated_cost:.4f}")


if __name__ == "__main__":
    exit(main())
