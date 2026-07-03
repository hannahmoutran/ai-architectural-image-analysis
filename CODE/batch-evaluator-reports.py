#!/usr/bin/env python3
"""
Batch Evaluator Reports
=======================

Processes all decisions JSONs for a given evaluator, automatically finding the
correct pipeline output folder for each one and running integrate-archivist-edits.py
in analysis-only mode.

Usage:
    python batch-evaluator-reports.py
    python batch-evaluator-reports.py --dry-run

    When prompted, enter the path to the evaluator's folder of decisions JSON files
    (e.g. .../Testing_Spring_2026_FINAL/evaluations/Alice/).

Folder structure expected:
    <testing-folder>/
        claude/     ArchImagesAI_* (pipeline output folders)
        openai/     ArchImagesAI_*
        gemini/     ArchImagesAI_*
        evaluations/
            <EvaluatorName>/
                <collection>_<model>_<Evaluator>_<date>.json   ← decisions files
                <EvaluatorName>_changes/                        ← reports written here
"""

import os
import sys
import json
import shutil
import argparse
import subprocess

script_dir = os.path.dirname(os.path.abspath(__file__))

PROVIDER_SUBFOLDERS = ["claude", "openai", "gemini"]


def find_results_folder(testing_folder, workflow_folder_name):
    """Search claude/, openai/, gemini/ for a folder matching workflow_folder_name."""
    for provider in PROVIDER_SUBFOLDERS:
        candidate = os.path.join(testing_folder, provider, workflow_folder_name)
        if os.path.isdir(candidate):
            return candidate
    return None


def prompt_for_decisions_folders():
    """Prompt the user to enter one or more evaluator folder paths (blank line to finish)."""
    print("\nEnter the path(s) to evaluator folders containing decisions JSON files.")
    print("(e.g. evaluations/Alice/)  Press Enter with no input when done.\n")
    folders = []
    while True:
        raw = input(f"Decisions folder path {len(folders) + 1} (or Enter to finish): ").strip().strip("'\"")
        if not raw:
            if not folders:
                print("Please enter at least one path.")
                continue
            break
        path = os.path.abspath(os.path.expanduser(raw))
        if not os.path.isdir(path):
            print(f"  Not found: {path}")
            continue
        folders.append(path)
        print(f"  Added: {path}")
    return folders


def collect_decisions_files(evaluator_folder):
    """Return all .json decisions files directly in the evaluator folder (not subfolders)."""
    files = []
    for entry in sorted(os.listdir(evaluator_folder)):
        if entry.endswith(".json") and os.path.isfile(os.path.join(evaluator_folder, entry)):
            files.append(os.path.join(evaluator_folder, entry))
    return files


def run_one(decisions_path, results_folder, evaluator_name, output_folder):
    """Call integrate-archivist-edits.py for one decisions file."""
    integrate_script = os.path.join(script_dir, "integrate-archivist-edits.py")

    cmd = [
        sys.executable, integrate_script,
        "--decisions", decisions_path,
        "--folder", results_folder,
        "--evaluator", evaluator_name,
        "--output", output_folder,
        "--yes",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def main():
    parser = argparse.ArgumentParser(
        description="Batch-process all decisions JSONs for an evaluator.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be run without actually running it"
    )
    args = parser.parse_args()

    print("Batch Evaluator Reports")
    print("=" * 60)

    evaluator_folders = prompt_for_decisions_folders()

    total_success = 0
    total_fail = 0

    for evaluator_folder in evaluator_folders:
        evaluator_name = os.path.basename(evaluator_folder)
        testing_folder = os.path.dirname(os.path.dirname(evaluator_folder))

        print(f"\n{'='*60}")
        print(f"Evaluator: {evaluator_name}")
        print(f"Folder:    {evaluator_folder}")

        output_folder = os.path.join(evaluator_folder, f"{evaluator_name}_changes")
        if os.path.isdir(output_folder):
            shutil.rmtree(output_folder)
        os.makedirs(output_folder)
        print(f"Output:    {output_folder}")

        decisions_files = collect_decisions_files(evaluator_folder)
        if not decisions_files:
            print("  No decisions JSON files found — skipping.")
            continue

        print(f"\nFound {len(decisions_files)} decisions file(s):\n")

        plan = []
        errors = []
        for df in decisions_files:
            fname = os.path.basename(df)
            try:
                with open(df, encoding="utf-8") as f:
                    data = json.load(f)
                workflow_folder_name = data.get("workflow_folder", "")
            except Exception as e:
                errors.append(f"  Could not read {fname}: {e}")
                continue

            if not workflow_folder_name:
                errors.append(f"  {fname}: missing 'workflow_folder' field")
                continue

            results_folder = find_results_folder(testing_folder, workflow_folder_name)
            if not results_folder:
                errors.append(
                    f"  {fname}: results folder '{workflow_folder_name}' not found "
                    f"in claude/, openai/, or gemini/"
                )
                continue

            plan.append((df, results_folder, fname, workflow_folder_name))
            print(f"  {fname}")
            print(f"    → {os.path.relpath(results_folder, testing_folder)}")

        if errors:
            print("\nWarnings / errors:")
            for e in errors:
                print(e)

        if not plan:
            print("  Nothing to process — skipping.")
            continue

        if args.dry_run:
            print(f"\nDry run — {len(plan)} job(s) would be run.")
            continue

        print(f"\nProcessing {len(plan)} file(s) for {evaluator_name}...\n")

        for decisions_path, results_folder, fname, workflow_folder_name in plan:
            print(f"Processing: {fname}")
            print(f"  Folder:   {workflow_folder_name}")

            returncode, _, stderr = run_one(
                decisions_path, results_folder, evaluator_name, output_folder
            )

            if returncode == 0:
                print(f"  Status:   OK\n")
                total_success += 1
            else:
                print(f"  Status:   FAILED (exit code {returncode})")
                if stderr:
                    lines = stderr.strip().splitlines()
                    for line in lines[-5:]:
                        print(f"    {line}")
                print()
                total_fail += 1

        print(f"Reports written to: {output_folder}")

    print(f"\n{'='*60}")
    if args.dry_run:
        print("Dry run complete — no files were processed.")
    else:
        print(f"All done. {total_success} succeeded, {total_fail} failed.")

    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
