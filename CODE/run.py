#!/usr/bin/env python3
"""
AI Architectural Image Analysis - Unified Runner
=================================================

Run the processing pipeline using settings from config.py.

Usage:
    python run.py              # Run the pipeline
    python run.py --config     # Show current configuration

Note: integrate-archivist-edits.py must be run standalone after archivist review.

Configure settings in config.py before running.
"""

import os
import sys
import subprocess
from datetime import datetime

# Add CODE directory to path for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from config import get_step1_config, get_step3_config, get_image_folders, print_current_config


def find_output_folder_for_image_folder(image_folder_name):
    """Find the newest output folder matching the given image folder name.

    Args:
        image_folder_name: The name of the source image folder (e.g., 'ut-buildings')

    Returns:
        Full path to the output folder, or None if not found
    """
    base_output_dir = os.path.join(script_dir, "output_folders")
    if not os.path.exists(base_output_dir):
        return None

    # Look for folders matching pattern: ArchImagesAI_{image_folder_name}_*
    prefix = f"ArchImagesAI_{image_folder_name}_"
    matching_folders = []

    for item in os.listdir(base_output_dir):
        if item.startswith(prefix):
            folder_path = os.path.join(base_output_dir, item)
            if os.path.isdir(folder_path):
                matching_folders.append(folder_path)

    if not matching_folders:
        return None

    # Return the newest by modification time
    matching_folders.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return matching_folders[0]


def run_step(step_num, env_overrides=None, image_folder=None, output_folder=None):
    """Run a specific step.

    Args:
        step_num: Step number to run (1, 2, 3, 4, or 'html')
        env_overrides: Optional dict of environment variable overrides
        image_folder: Optional folder name override for multi-folder processing
        output_folder: Optional output folder path for steps 2, 3, 4, and html
    """
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)

    # Map step numbers to scripts and their provider-specific variants
    if step_num == 1:
        config = get_step1_config(image_folder)
        provider = config["provider"]
        script_map = {
            "claude": "step-1-architectural-drawings-claude.py",
            "openai": "step-1-architectural-drawings-openai.py",
            "gemini": "step-1-architectural-drawings-gemini.py"
        }
        script_name = script_map.get(provider)
        env["CONFIG_MODEL"] = config["model"]
        env["CONFIG_IMAGE_FOLDER"] = config["image_folder"]
        step_desc = f"Image Analysis ({provider.upper()} - {config['model']})"

    elif step_num == 2:
        script_name = "step-2-terms.py"
        step_desc = "Vocabulary Term Lookup (LCSH, FAST, Getty)"

    elif step_num == 3:
        config = get_step3_config()
        provider = config["provider"]
        script_map = {
            "claude": "step-3-vocab-selection-claude.py",
            "openai": "step-3-vocab-selection-openai.py",
            "gemini": "step-3-vocab-selection-gemini.py"
        }
        script_name = script_map.get(provider)
        env["MODEL_NAME"] = config["model"]
        step_desc = f"Vocabulary Selection ({provider.upper()} - {config['model']})"

    elif step_num == 4:
        script_name = "step-4-entity-report-creation.py"
        step_desc = "Entity Report Creation"

    elif step_num == 'html':
        script_name = "html-review.py"
        step_desc = "HTML Review Interface (Optional)"

    else:
        print(f"Unknown step: {step_num}")
        return False

    if not script_name:
        print(f"Error: No script found for step {step_num}")
        return False

    script_path = os.path.join(script_dir, script_name)

    if not os.path.exists(script_path):
        print(f"Error: Script not found: {script_path}")
        return False

    print("\n" + "=" * 60)
    print(f"STEP {step_num}: {step_desc}")
    print("=" * 60)
    print(f"Running: {script_name}")
    print("-" * 60 + "\n")

    # Build command with optional --folder argument for steps 2, 3, 4, and html
    cmd = [sys.executable, script_path]
    if output_folder and step_num in (2, 3, 4, 'html'):
        cmd.extend(['--folder', output_folder])
        print(f"Using output folder: {os.path.basename(output_folder)}")

    try:
        result = subprocess.run(
            cmd,
            env=env,
            cwd=script_dir
        )
        if result.returncode == 0:
            print(f"\n Step {step_desc} completed successfully")
        else:
            print(f"\n Step {step_desc} failed (exit code: {result.returncode})")
        return result.returncode == 0
    except KeyboardInterrupt:
        print(f"\n Step {step_num} interrupted by user")
        return False
    except Exception as e:
        print(f"\n Error running step {step_num}: {e}")
        return False


def interactive_menu():
    """Show interactive menu for selecting steps to run."""
    print("\n" + "=" * 60)
    print("AI ARCHITECTURAL IMAGE ANALYSIS")
    print("=" * 60)

    print_current_config()

    folders = get_image_folders()
    if len(folders) > 1:
        print(f"Will process {len(folders)} folders sequentially.")
        print()

    print("This will run:")
    print("  Step 1: Image Analysis (extract metadata from drawings)")
    print("  Step 2: Vocabulary Lookup (LCSH, FAST, Getty terms)")
    print("  Step 3: Vocabulary Selection (AI-powered term selection)")
    print("  Step 4: Entity Report Creation")
    print()

    response = input("Proceed? [y/n]: ").strip().lower()
    if response not in ('y', 'yes'):
        print("Cancelled.")
        return [], False

    print()
    html_response = input("Do you want to create the HTML review interface? [y/n]: ").strip().lower()
    include_html = html_response in ('y', 'yes')

    return [1, 2, 3, 4], include_html


def main():
    # Check for --config flag
    if len(sys.argv) > 1 and sys.argv[1] in ('--config', '-c'):
        print_current_config()
        return 0

    # Get confirmation to run
    steps_to_run, include_html = interactive_menu()

    if not steps_to_run:
        return 0

    # Get folders to process
    folders = get_image_folders()
    start_time = datetime.now()

    # Track results per folder
    all_results = {}

    for folder_idx, folder in enumerate(folders):
        if len(folders) > 1:
            print("\n" + "#" * 60)
            print(f"PROCESSING FOLDER {folder_idx + 1}/{len(folders)}: {folder}")
            print("#" * 60)

        folder_results = {}
        output_folder = None  # Will be set after Step 1 completes

        for step in steps_to_run:
            success = run_step(step, image_folder=folder, output_folder=output_folder)
            folder_results[step] = success

            # After Step 1 completes successfully, find the output folder for subsequent steps
            if step == 1 and success:
                output_folder = find_output_folder_for_image_folder(folder)
                if output_folder:
                    print(f"\nOutput folder: {os.path.basename(output_folder)}")
                else:
                    print(f"\nWarning: Could not find output folder for {folder}")

            if not success and step != steps_to_run[-1]:
                # Ask whether to continue after a failure
                cont = input(f"\nStep {step} failed. Continue with remaining steps? [y/n]: ").strip().lower()
                if cont not in ('y', 'yes'):
                    break

        all_results[folder] = folder_results

        # Run HTML review for this folder if requested and all steps succeeded
        if include_html and all(folder_results.values()):
            run_step('html', image_folder=folder, output_folder=output_folder)

    # Summary
    end_time = datetime.now()
    duration = end_time - start_time

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Duration: {duration}")
    print()

    if len(folders) == 1:
        # Single folder - show simple results
        folder_results = all_results[folders[0]]
        for step, success in folder_results.items():
            status = "SUCCESS" if success else "FAILED"
            print(f"  Step {step}: {status}")
    else:
        # Multiple folders - show per-folder results
        for folder, folder_results in all_results.items():
            all_success = all(folder_results.values())
            folder_status = "SUCCESS" if all_success else "PARTIAL"
            print(f"  {folder}: {folder_status}")
            for step, success in folder_results.items():
                status = "OK" if success else "FAILED"
                print(f"    Step {step}: {status}")

    print("=" * 60)

    # Return non-zero if any step in any folder failed
    any_failed = any(
        not success
        for folder_results in all_results.values()
        for success in folder_results.values()
    )
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
