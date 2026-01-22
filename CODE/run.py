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

from config import get_step1_config, get_step3_config, print_current_config


def run_step(step_num, env_overrides=None):
    """Run a specific step."""
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)

    # Map step numbers to scripts and their provider-specific variants
    if step_num == 1:
        config = get_step1_config()
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

    try:
        result = subprocess.run(
            [sys.executable, script_path],
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

    # Run the steps
    start_time = datetime.now()
    results = {}

    for step in steps_to_run:
        success = run_step(step)
        results[step] = success
        if not success and step != steps_to_run[-1]:
            # Ask whether to continue after a failure
            cont = input(f"\nStep {step} failed. Continue with remaining steps? [y/n]: ").strip().lower()
            if cont not in ('y', 'yes'):
                break

    # Summary
    end_time = datetime.now()
    duration = end_time - start_time

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Duration: {duration}")
    print()
    for step, success in results.items():
        status = "SUCCESS" if success else "FAILED"
        print(f"  Step {step}: {status}")
    print("=" * 60)

    # Run HTML review interface if requested
    if include_html and all(results.values()):
        run_step('html')

    # Return non-zero if any step failed
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
