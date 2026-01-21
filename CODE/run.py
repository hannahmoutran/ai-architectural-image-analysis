#!/usr/bin/env python3
"""
AI Architectural Image Analysis - Unified Runner
=================================================

Run the processing pipeline using settings from config.py.

Usage:
    python run.py              # Interactive menu
    python run.py 1            # Run Step 1 only
    python run.py 3            # Run Step 3 only
    python run.py 1 2 3        # Run Steps 1, 2, and 3
    python run.py all          # Run all steps (1, 2, 3, 4)
    python run.py --config     # Show current configuration

Configure settings in config.py before running.
"""

import os
import sys
import subprocess
import argparse
from datetime import datetime

# Add CODE directory to path for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from config import get_step1_config, get_step3_config, print_current_config, IMAGE_FOLDER


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

    elif step_num == 5:
        script_name = "step-5-html-review.py"
        step_desc = "HTML Review Interface"

    elif step_num == 6:
        script_name = "step-6-integrate-archivist-edits.py"
        step_desc = "Integrate Archivist Edits"

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
            print(f"\n Step {step_num} completed successfully")
        else:
            print(f"\n Step {step_num} failed (exit code: {result.returncode})")
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

    print("SELECT STEPS TO RUN:")
    print("  1. Step 1: Image Analysis (extract metadata from drawings)")
    print("  2. Step 2: Vocabulary Lookup (LCSH, FAST, Getty terms)")
    print("  3. Step 3: Vocabulary Selection (AI-powered term selection)")
    print("  4. Step 4: Entity Report Creation")
    print("  5. Step 5: HTML Review Interface (archivist review)")
    print("  6. Step 6: Integrate Archivist Edits")
    print()
    print("  A. Run ALL steps (1-6)")
    print("  C. Show/edit configuration")
    print("  Q. Quit")
    print()

    while True:
        choice = input("Enter choice (1-6, A, C, or Q): ").strip().lower()

        if choice == 'q':
            print("Goodbye!")
            return []
        elif choice == 'c':
            print_current_config()
            print("\nEdit config.py to change settings, then restart.\n")
            continue
        elif choice == 'a':
            return [1, 2, 3, 4, 5, 6]
        elif choice in ['1', '2', '3', '4', '5', '6']:
            return [int(choice)]
        elif ',' in choice or ' ' in choice:
            # Allow multiple steps like "1,2,3" or "1 2 3"
            try:
                steps = [int(s.strip()) for s in choice.replace(',', ' ').split()]
                if all(1 <= s <= 6 for s in steps):
                    return steps
            except ValueError:
                pass
            print("Invalid input. Enter step numbers 1-6.")
        else:
            print("Invalid choice. Try again.")


def main():
    parser = argparse.ArgumentParser(
        description='AI Architectural Image Analysis - Unified Runner',
        epilog="""
Examples:
  python run.py              # Interactive menu
  python run.py 1            # Run Step 1 only
  python run.py 1 2 3        # Run Steps 1, 2, and 3
  python run.py all          # Run all steps
  python run.py --config     # Show current configuration
        """
    )

    parser.add_argument('steps', nargs='*',
                        help='Steps to run (1-6 or "all")')
    parser.add_argument('--config', '-c', action='store_true',
                        help='Show current configuration and exit')

    args = parser.parse_args()

    # Show config only
    if args.config:
        print_current_config()
        return 0

    # Determine which steps to run
    if args.steps:
        if 'all' in [s.lower() for s in args.steps]:
            steps_to_run = [1, 2, 3, 4, 5, 6]
        else:
            try:
                steps_to_run = [int(s) for s in args.steps]
                if not all(1 <= s <= 6 for s in steps_to_run):
                    print("Error: Steps must be 1, 2, 3, 4, 5, or 6")
                    return 1
            except ValueError:
                print("Error: Invalid step number")
                return 1
    else:
        # Interactive mode
        steps_to_run = interactive_menu()

    if not steps_to_run:
        return 0

    # Confirm before running
    print("\n" + "-" * 60)
    print(f"Will run: Step(s) {', '.join(str(s) for s in steps_to_run)}")
    print(f"Image folder: {IMAGE_FOLDER}")
    print("-" * 60)

    response = input("Proceed? [y/n]: ").strip().lower()
    if response in ('n', 'no'):
        print("Cancelled.")
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

    # Return non-zero if any step failed
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
