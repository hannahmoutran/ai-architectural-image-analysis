#!/usr/bin/env python3
"""
Step 0: Calibration — Create Archivist Style Examples

Analyzes a small sample of images so the archivist can correct the results;
the corrected examples then guide the full Step 1 run.

Workflow:
  1. python step-0-calibration.py     # analyze sample; HTML review is generated automatically
     Edit metadata in the browser, then Export Decisions to the exports subfolder.
  2. python step-0-calibration.py --export   # write collection-examples.txt to the images folder
     Step 1 then includes it in every request. Edit its style guide as you see fit.

Options: --count N, --folder <name>
To regenerate the HTML review: python step-5-html-review.py --folder <output-folder-path>
"""

import os
import sys
import json
import argparse
import importlib.util
import time
from datetime import datetime

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
for lib in ("anthropic", "openai", "google", "urllib3", "httpx"):
    logging.getLogger(lib).setLevel(logging.WARNING)

from config import get_step1_config, CALIBRATION_COUNT, OPENAI_USE_PORTKEY
from token_logging import create_token_usage_log
from model_pricing import calculate_cost


def _load_step1():
    """Import step-1 module (hyphenated name requires importlib)."""
    path = os.path.join(script_dir, "step-1-architectural-drawings.py")
    spec = importlib.util.spec_from_file_location("step1_module", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _load_integrate():
    """Import step-6-integrate-archivist-edits module (hyphenated name requires importlib)."""
    path = os.path.join(script_dir, "step-6-integrate-archivist-edits.py")
    spec = importlib.util.spec_from_file_location("integrate_module", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _load_html_review():
    """Import step-5-html-review module (hyphenated name requires importlib)."""
    path = os.path.join(script_dir, "step-5-html-review.py")
    spec = importlib.util.spec_from_file_location("html_review_module", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _generate_html_review(folder_path):
    """Generate an HTML review interface for a calibration output folder."""
    folder_name = os.path.basename(folder_path)
    print(f"\nGenerating HTML review for: {folder_name}")

    html_review = _load_html_review()
    builder = html_review.HTMLReviewBuilder(folder_path, records_per_page=10)
    success = builder.run()

    if success:
        review_index = os.path.join(folder_path, "review", "review-index.html")
        print(f"\n{'='*60}")
        print(f"NEXT STEPS")
        print(f"{'='*60}")
        print(f"  1. Open the review interface in your browser:")
        print(f"       {review_index}")
        print(f"     Edit each record's metadata to match your style,")
        print(f"     then click 'Export Decisions' and save the JSON file.")
        print(f"")
        print(f"  2. Write the calibration examples file:")
        print(f"       python step-0-calibration.py --export")
        print(f"{'='*60}")
        return 0

    return 1


def _export_calibration(folder_path=None):
    """Export archivist-reviewed calibration decisions as collection-examples.txt.

    Finds the most recent calibration output folder (or uses --folder), loads the
    archivist's decisions export, and writes the examples file to the collection's
    image_folder so Step 1 can use it as a style guide.
    """
    m = _load_integrate()

    base_output_dir = os.path.join(script_dir, "output_folders")

    if folder_path:
        if not os.path.exists(folder_path):
            print(f"Error: Folder not found: {folder_path}")
            return 1
    else:
        if not os.path.exists(base_output_dir):
            print("No output_folders directory found.")
            return 1
        calibration_folders = sorted(
            [
                os.path.join(base_output_dir, d)
                for d in os.listdir(base_output_dir)
                if "_calibration_" in d and os.path.isdir(os.path.join(base_output_dir, d))
            ],
            key=os.path.getmtime,
            reverse=True,
        )
        if not calibration_folders:
            print("No calibration output folders found. Run step-0-calibration.py first.")
            return 1
        folder_path = calibration_folders[0]

    folder_name = os.path.basename(folder_path)
    print(f"\nEXPORT CALIBRATION EXAMPLES")
    print(f"Folder   : {folder_name}")

    integrator = m.ArchivistEditsIntegrator(folder_path)
    export_path = integrator.find_latest_export()
    if not export_path:
        print(f"\nNo archivist decisions found.")
        print(f"Complete the HTML review and export decisions first:")
        print(f"  python step-5-html-review.py --folder output_folders/{folder_name}")
        return 1

    print(f"Decisions: {os.path.basename(export_path)}")

    if not integrator.load_workflow_json():
        return 1
    if not integrator.load_decisions(export_path):
        return 1

    image_folders_base = os.path.join(script_dir, "image_folders")
    examples_path = integrator.export_calibration_examples(image_folders_base)

    if examples_path:
        collection_name = integrator._get_collection_name() or ""
        print(f"\nCalibration examples written to:")
        print(f"  {examples_path}")

        # Generate style guide from the examples using the configured LLM
        cfg = get_step1_config()
        provider = cfg['provider']
        model_name = cfg['model']
        provider_label = f"{provider.upper()}" + (" (Portkey)" if provider == "openai" and OPENAI_USE_PORTKEY else "")
        print(f"\nGenerating style guide ({provider_label} / {model_name})...")

        style_appended = False
        try:
            step1 = _load_step1()
            step1._init_provider(provider)
            with open(examples_path, 'r', encoding='utf-8') as f:
                examples_text = f.read()
            style_guide = step1.generate_style_analysis(examples_text, model_name)
            if style_guide:
                style_section = (
                    "\n\n"
                    "# ============================================================\n"
                    "# STYLE GUIDE\n"
                    "# Generated from calibration examples — edit as needed before running Step 1\n"
                    "# ============================================================\n"
                    "\n"
                    + style_guide + "\n"
                )
                with open(examples_path, 'a', encoding='utf-8') as f:
                    f.write(style_section)
                style_appended = True
                print(f"  Style guide appended to examples file.")
            else:
                print(f"  Style guide generation failed — Step 1 will generate one automatically.")
        except Exception as e:
            print(f"  Style guide generation error: {e}")
            print(f"  Examples saved; Step 1 will generate a style guide automatically.")

        print(f"\n{'='*60}")
        print(f"NEXT STEPS")
        print(f"{'='*60}")
        if style_appended:
            print(f"  1. (Optional) Review and edit the style guide in:")
            print(f"       {examples_path}")
            print(f"     The style guide is at the bottom of the file under")
            print(f"     '# STYLE GUIDE'. Edit it to refine the AI's behavior.")
            print(f"")
            print(f"  2. Run the full image analysis:")
        else:
            print(f"  1. Run the full image analysis:")
        print(f"       python step-1-architectural-drawings.py")
        print(f"     The AI will use your personal style guide for every image")
        print(f"     in image_folders/{collection_name}/.")
        print(f"{'='*60}")
        return 0

    print("Error: Failed to write calibration examples.")
    return 1


def main():
    parser = argparse.ArgumentParser(
        description='Step 0: Create archivist calibration examples for style-guided image analysis.',
        epilog="""
Workflow:
  1. python step-0-calibration.py              # analyze a sample of images (review interface auto-generated)
     Open in browser, edit each record, click Export Decisions.
  2. python step-0-calibration.py --export     # write collection-examples.txt
  3. python step-1-architectural-drawings.py # full run, style-guided
        """
    )
    parser.add_argument('--export', '-e', action='store_true',
                        help='Export archivist decisions as collection-examples.txt. '
                             'Run this after completing the HTML review.')
    parser.add_argument('--count', '-n', type=int, default=None,
                        help=f'Number of sample images to process (default: CALIBRATION_COUNT={CALIBRATION_COUNT} from config.py)')
    parser.add_argument('--folder', '-f', default=None,
                        help='Image folder name (step 1) or output folder path (--export)')
    args = parser.parse_args()

    if args.export:
        return _export_calibration(args.folder)

    cfg = get_step1_config(args.folder)
    provider = cfg['provider']
    model_name = cfg['model']
    input_folder_name = args.folder or cfg['image_folder']
    count = args.count if args.count is not None else CALIBRATION_COUNT

    input_folder = os.path.join(script_dir, "image_folders", input_folder_name)
    if not os.path.exists(input_folder):
        print(f"Input folder not found: {os.path.abspath(input_folder)}")
        return 1

    # Load step-1 module for shared logic
    step1 = _load_step1()
    step1._init_provider(provider)

    collection_context = step1.load_collection_context(input_folder)

    provider_label = f"{provider.upper()}" + (" (Portkey)" if provider == "openai" and OPENAI_USE_PORTKEY else "")
    print(f"\nCALIBRATION — Step 0: Sample Image Analysis ({provider_label})")
    print(f"Model    : {model_name}")
    print(f"Folder   : image_folders/{input_folder_name}")
    print(f"Sample   : first {count} images")
    if collection_context:
        print(f"Context  : collection context loaded")

    all_images = step1.collect_all_images(input_folder)
    total_in_folder = len(all_images)

    if total_in_folder == 0:
        print(f"\nNo images found in {input_folder}")
        return 1

    sample_images = all_images[:count]
    actual_count = len(sample_images)
    print(f"\nFound {total_in_folder} image(s) total — processing first {actual_count}\n")

    # Create output folder (calibration marker in name)
    current_date = datetime.now().strftime("%Y-%m-%d")
    current_time = datetime.now().strftime("%H-%M-%S")
    folder_name = f"ArchImagesAI_{input_folder_name}_calibration_{model_name}_{current_date}_Time_{current_time}"
    output_dir = os.path.join(script_dir, "output_folders", folder_name)
    logs_folder_path = os.path.join(output_dir, "logs")
    json_folder = os.path.join(output_dir, "metadata", "json")
    os.makedirs(json_folder, exist_ok=True)
    os.makedirs(logs_folder_path, exist_ok=True)

    script_start = time.time()

    # Process the sample — no collection_examples (that's the point of calibration)
    all_results = []
    issues = []
    (all_results, _, total_items, items_with_issues, total_processing_time,
     total_prompt_tokens, total_completion_tokens, issues, _) = step1.process_folder_individual(
        sample_images, logs_folder_path, model_name, all_results, issues, collection_context
    )

    total_time = time.time() - script_start

    api_summary = {
        "total_requests": step1.api_stats.total_requests,
        "total_input_tokens": total_prompt_tokens,
        "total_output_tokens": total_completion_tokens,
        "total_tokens": total_prompt_tokens + total_completion_tokens,
        "calibration_run": True,
        "processing_mode": "INDIVIDUAL"
    }
    all_results.append({"api_stats": api_summary})
    if issues:
        all_results.append({"issues": issues})

    json_path = os.path.join(json_folder, "drawings_workflow.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    estimated_cost = calculate_cost(
        model_name=model_name,
        prompt_tokens=total_prompt_tokens,
        completion_tokens=total_completion_tokens,
        is_batch=False
    )

    create_token_usage_log(
        logs_folder_path=logs_folder_path,
        script_name="calibration_sample_analysis",
        model_name=model_name,
        total_items=actual_count,
        items_with_issues=items_with_issues,
        total_time=total_processing_time,
        total_prompt_tokens=total_prompt_tokens,
        total_completion_tokens=total_completion_tokens,
        additional_metrics={
            "Total script time": f"{total_time:.2f}s",
            "Calibration run": "True",
            "Images sampled": actual_count,
            "Cost": f"${estimated_cost:.4f}"
        }
    )

    print(f"\nCALIBRATION COMPLETE")
    print(f"Processed : {actual_count - items_with_issues}/{actual_count} images")
    if issues:
        print(f"Failed    : {items_with_issues}")
    print(f"Tokens    : {total_prompt_tokens + total_completion_tokens:,}  "
          f"(in: {total_prompt_tokens:,}, out: {total_completion_tokens:,})")
    print(f"Cost      : ${estimated_cost:.4f}")
    print(f"Time      : {total_time:.1f}s")
    print(f"Output    : output_folders/{folder_name}/")

    # Automatically generate the HTML review interface for this calibration run
    review_result = _generate_html_review(output_dir)
    if review_result != 0:
        print(f"\nHTML review generation failed — you can retry with:")
        print(f"  python step-5-html-review.py --folder output_folders/{folder_name}")
        return 1

    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
