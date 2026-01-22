#!/usr/bin/env python3
"""
Integrate Archivist Edits into Workflow Outputs
================================================

Processes archivist review decisions from exported JSON and updates all deliverable files.

This script:
1. Reads archivist decisions from JSON exports (created by html-review.py)
2. Backs up original files to an 'original-outputs' folder
3. Applies edits to the workflow JSON (drawings_workflow.json)
4. Handles cascade rejection logic (rejected subjects → reject derived headings)
5. Updates the Excel deliverable (drawings_workflow.xlsx)
6. Adds an 'Edit History' sheet tracking all changes with statistics
7. Generates final_metadata.json with only approved/clean data

Usage:
    python integrate-archivist-edits.py                           # Use latest export
    python integrate-archivist-edits.py --decisions path/to.json  # Use specific export
    python run.py 6
"""

import os
import sys
import json
import shutil
import argparse
from datetime import datetime
from difflib import SequenceMatcher
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Alignment, Font, Border, Side

# Add CODE directory to path for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from shared_utilities import find_newest_folder


class ArchivistEditsIntegrator:
    """Integrates archivist edits from the HTML review interface back into workflow files."""

    def __init__(self, folder_path):
        self.folder_path = folder_path
        self.folder_name = os.path.basename(folder_path)
        self.metadata_folder = os.path.join(folder_path, "metadata")
        self.review_folder = os.path.join(folder_path, "review")
        self.exports_folder = os.path.join(self.review_folder, "exports")
        self.original_outputs_folder = os.path.join(folder_path, "original-outputs")

        self.workflow_json_path = os.path.join(self.metadata_folder, "drawings_workflow.json")
        self.workflow_excel_path = os.path.join(self.metadata_folder, "drawings_workflow.xlsx")

        self.workflow_data = None
        self.decisions_data = None
        self.edit_history = []
        self.stats = {
            'total_records_in_export': 0,
            'records_with_edits': 0,
            'records_reviewed_only': 0,
            'total_field_edits': 0,
            'total_term_decisions': 0,
            'terms_approved': 0,
            'terms_rejected': 0,
            'terms_cascade_rejected': 0,
            'subjects_rejected': 0,
            'custom_terms_added': 0,
            'custom_subjects_added': 0,
            'edits_by_field': {},
            'archivist_name': '',
            'export_timestamp': '',
            'integration_timestamp': '',
            # Detailed character-level metrics for text fields
            'text_field_metrics': {},  # {field_name: {chars_added, chars_deleted, chars_total_changed, edits_count}}
            # Subject/heading detailed metrics
            'subjects_original_count': 0,
            'subjects_final_count': 0,
            'subjects_added': 0,
            'subjects_removed': 0,
            'subjects_kept': 0,
            'headings_original_count': 0,
            'headings_final_count': 0,
            'headings_added': 0,
            'headings_removed': 0,
            'headings_kept': 0,
            # Per-record detailed metrics
            'per_record_metrics': []
        }

    def find_latest_export(self):
        """Find the most recent archivist decisions export JSON."""
        if not os.path.exists(self.exports_folder):
            print(f"Error: Exports folder not found at {self.exports_folder}")
            print("Please run Step 5 and export decisions first.")
            return None

        json_files = [f for f in os.listdir(self.exports_folder) if f.endswith('.json')]

        if not json_files:
            print(f"Error: No JSON export files found in {self.exports_folder}")
            print("Please export your review decisions from the HTML interface first.")
            return None

        # Sort by modification time, newest first
        json_files.sort(key=lambda f: os.path.getmtime(os.path.join(self.exports_folder, f)), reverse=True)

        latest_file = json_files[0]
        return os.path.join(self.exports_folder, latest_file)

    def load_decisions(self, decisions_path):
        """Load archivist decisions from JSON export."""
        try:
            with open(decisions_path, 'r', encoding='utf-8') as f:
                self.decisions_data = json.load(f)

            # Support both old 'cataloger_name' and new 'archivist_name' keys
            self.stats['archivist_name'] = self.decisions_data.get('archivist_name',
                                            self.decisions_data.get('cataloger_name', 'Unknown'))
            self.stats['export_timestamp'] = self.decisions_data.get('export_timestamp', '')
            self.stats['total_records_in_export'] = len(self.decisions_data.get('decisions', []))

            print(f"Loaded {self.stats['total_records_in_export']} record decisions")
            print(f"Archivist: {self.stats['archivist_name']}")
            print(f"Export timestamp: {self.stats['export_timestamp']}")

            return True
        except Exception as e:
            print(f"Error loading decisions: {e}")
            return False

    def load_workflow_json(self):
        """Load the workflow JSON data."""
        if not os.path.exists(self.workflow_json_path):
            print(f"Error: Workflow JSON not found at {self.workflow_json_path}")
            return False

        try:
            with open(self.workflow_json_path, 'r', encoding='utf-8') as f:
                self.workflow_data = json.load(f)

            # Handle api_stats entry at the end
            if self.workflow_data and isinstance(self.workflow_data[-1], dict) and 'api_stats' in self.workflow_data[-1]:
                self.api_stats = self.workflow_data[-1]
                self.workflow_data = self.workflow_data[:-1]
            else:
                self.api_stats = None

            print(f"Loaded workflow JSON with {len(self.workflow_data)} records")
            return True
        except Exception as e:
            print(f"Error loading workflow JSON: {e}")
            return False

    def backup_original_files(self):
        """Backup original files to original-outputs folder."""
        os.makedirs(self.original_outputs_folder, exist_ok=True)

        files_to_backup = [
            (self.workflow_json_path, "drawings_workflow.json"),
            (self.workflow_excel_path, "drawings_workflow.xlsx")
        ]

        backed_up = []
        for src_path, filename in files_to_backup:
            if os.path.exists(src_path):
                dest_path = os.path.join(self.original_outputs_folder, filename)

                # Only backup if not already backed up (preserve truly original files)
                if not os.path.exists(dest_path):
                    shutil.copy2(src_path, dest_path)
                    backed_up.append(filename)
                    print(f"   Backed up: {filename}")
                else:
                    print(f"   Backup already exists: {filename} (preserving original)")

        return backed_up

    def apply_field_edit(self, record, field_name, edit_data, record_id):
        """Apply a single field edit to a record."""
        analysis = record.get('analysis', {})
        original_value = edit_data.get('original', '')
        new_value = edit_data.get('value', '')

        # Map field names between export and workflow JSON
        field_mapping = {
            'title': 'title',
            'genre': 'genre',
            'description': 'description',
            'ocr_text': 'ocr_text',
            'format_media': 'format_media',
            'date_on_drawing': 'date_on_drawing',
            'sheet_info': 'sheet_info',
            'content_warning': 'content_warning',
            'contributors': 'contributors',
            'named_entities': 'named_entities',
            'geographic_entities': 'geographic_entities',
            'subjects': 'subjects'
        }

        # Fields that are text (for character-level diff)
        text_fields = {'title', 'genre', 'description', 'ocr_text', 'format_media',
                       'date_on_drawing', 'sheet_info', 'content_warning'}
        # Fields that are lists
        list_fields = {'contributors', 'named_entities', 'geographic_entities', 'subjects'}

        json_field = field_mapping.get(field_name, field_name)

        if json_field in analysis or json_field in field_mapping.values():
            analysis[json_field] = new_value
            record['analysis'] = analysis

            # Calculate detailed metrics based on field type
            if field_name in text_fields:
                diff_metrics = self._calculate_text_diff_metrics(original_value, new_value)
                # Initialize field metrics if needed
                if field_name not in self.stats['text_field_metrics']:
                    self.stats['text_field_metrics'][field_name] = {
                        'edits_count': 0,
                        'chars_added': 0,
                        'chars_deleted': 0,
                        'chars_total_changed': 0,
                        'total_original_length': 0,
                        'total_new_length': 0
                    }
                # Accumulate metrics
                self.stats['text_field_metrics'][field_name]['edits_count'] += 1
                self.stats['text_field_metrics'][field_name]['chars_added'] += diff_metrics['chars_added']
                self.stats['text_field_metrics'][field_name]['chars_deleted'] += diff_metrics['chars_deleted']
                self.stats['text_field_metrics'][field_name]['chars_total_changed'] += diff_metrics['chars_total_changed']
                self.stats['text_field_metrics'][field_name]['total_original_length'] += diff_metrics['original_length']
                self.stats['text_field_metrics'][field_name]['total_new_length'] += diff_metrics['new_length']
            elif field_name in list_fields:
                diff_metrics = self._calculate_list_diff_metrics(original_value, new_value)
            else:
                diff_metrics = {}

            # Track the edit with detailed metrics
            self.edit_history.append({
                'record_id': record_id,
                'field': field_name,
                'original_value': self._truncate_for_display(original_value),
                'new_value': self._truncate_for_display(new_value),
                'edit_type': 'field_edit',
                'diff_metrics': diff_metrics
            })

            # Update stats
            self.stats['total_field_edits'] += 1
            if field_name not in self.stats['edits_by_field']:
                self.stats['edits_by_field'][field_name] = 0
            self.stats['edits_by_field'][field_name] += 1

            return True, diff_metrics
        return False, {}

    def _truncate_for_display(self, value, max_length=100):
        """Truncate a value for display in edit history."""
        if value is None:
            return ""
        if isinstance(value, list):
            value = str(value)
        value = str(value)
        if len(value) > max_length:
            return value[:max_length] + "..."
        return value

    def _calculate_text_diff_metrics(self, original, new_value):
        """Calculate detailed character-level difference metrics between two strings.

        Returns a dict with:
        - chars_added: number of characters added
        - chars_deleted: number of characters deleted
        - chars_unchanged: number of characters that stayed the same
        - chars_total_changed: total characters changed (added + deleted)
        - similarity_ratio: 0.0-1.0 similarity score
        - edit_operations: list of (operation, count) tuples
        """
        # Handle None values
        original = str(original) if original else ""
        new_value = str(new_value) if new_value else ""

        # Use SequenceMatcher for detailed diff
        matcher = SequenceMatcher(None, original, new_value)

        chars_added = 0
        chars_deleted = 0
        chars_unchanged = 0
        edit_operations = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                chars_unchanged += (i2 - i1)
            elif tag == 'delete':
                chars_deleted += (i2 - i1)
                edit_operations.append(('delete', i2 - i1))
            elif tag == 'insert':
                chars_added += (j2 - j1)
                edit_operations.append(('insert', j2 - j1))
            elif tag == 'replace':
                chars_deleted += (i2 - i1)
                chars_added += (j2 - j1)
                edit_operations.append(('replace', max(i2 - i1, j2 - j1)))

        return {
            'chars_added': chars_added,
            'chars_deleted': chars_deleted,
            'chars_unchanged': chars_unchanged,
            'chars_total_changed': chars_added + chars_deleted,
            'original_length': len(original),
            'new_length': len(new_value),
            'similarity_ratio': round(matcher.ratio(), 4),
            'edit_operations': edit_operations
        }

    def _calculate_list_diff_metrics(self, original_list, new_list):
        """Calculate metrics for list-type fields (subjects, entities, etc.).

        Returns a dict with:
        - items_added: number of new items
        - items_removed: number of removed items
        - items_kept: number of unchanged items
        - added_items: list of added item values
        - removed_items: list of removed item values
        """
        # Normalize to lists
        if not isinstance(original_list, list):
            original_list = [original_list] if original_list else []
        if not isinstance(new_list, list):
            new_list = [new_list] if new_list else []

        # Convert to sets for comparison (handle dicts by converting to string)
        def normalize_item(item):
            if isinstance(item, dict):
                return json.dumps(item, sort_keys=True)
            return str(item)

        original_set = set(normalize_item(i) for i in original_list if i)
        new_set = set(normalize_item(i) for i in new_list if i)

        added = new_set - original_set
        removed = original_set - new_set
        kept = original_set & new_set

        return {
            'items_added': len(added),
            'items_removed': len(removed),
            'items_kept': len(kept),
            'original_count': len(original_set),
            'new_count': len(new_set),
            'added_items': list(added),
            'removed_items': list(removed)
        }

    def apply_term_decisions(self, record, term_decisions, record_id):
        """Apply vocabulary term decisions to a record.

        Handles three types of decisions:
        - 'approved': Term is approved
        - 'rejected': Term is explicitly rejected
        - dict with 'status': 'cascade_rejected': Term auto-rejected due to parent subject rejection
        """
        analysis = record.get('analysis', {})

        # Track term decisions
        for term_id, decision in term_decisions.items():
            self.stats['total_term_decisions'] += 1

            # Handle both old format (string) and new format (object with cascade info)
            if isinstance(decision, dict):
                status = decision.get('status', '')
                cascade_from = decision.get('cascadeFrom', '')
                if status == 'cascade_rejected':
                    self.stats['terms_cascade_rejected'] += 1
                    self.edit_history.append({
                        'record_id': record_id,
                        'field': 'vocabulary_term',
                        'original_value': term_id,
                        'new_value': f'cascade_rejected (from: {cascade_from})',
                        'edit_type': 'term_cascade_rejected'
                    })
                else:
                    # Unknown object format, treat as approved
                    self.stats['terms_approved'] += 1
            else:
                status = decision
                if status == 'approved':
                    self.stats['terms_approved'] += 1
                elif status == 'rejected':
                    self.stats['terms_rejected'] += 1
                    # Check if this is a subject rejection
                    if term_id.startswith('subject-'):
                        self.stats['subjects_rejected'] += 1

                self.edit_history.append({
                    'record_id': record_id,
                    'field': 'vocabulary_term',
                    'original_value': term_id,
                    'new_value': status,
                    'edit_type': 'term_decision'
                })

        # Store term decisions in the record for reference
        if 'archivist_term_decisions' not in analysis:
            analysis['archivist_term_decisions'] = {}
        analysis['archivist_term_decisions'] = term_decisions
        record['analysis'] = analysis

        return True

    def apply_custom_terms(self, record, custom_terms, custom_subjects, record_id):
        """Apply custom terms and subjects added by archivist."""
        analysis = record.get('analysis', {})

        # Add custom terms to a dedicated field
        if custom_terms:
            analysis['archivist_custom_terms'] = custom_terms
            self.stats['custom_terms_added'] += len(custom_terms)

            for term in custom_terms:
                self.edit_history.append({
                    'record_id': record_id,
                    'field': 'custom_term',
                    'original_value': '',
                    'new_value': f"{term.get('label', '')} ({term.get('source', '')})",
                    'edit_type': 'custom_term_added'
                })

        # Add custom subjects to the subjects list
        if custom_subjects:
            existing_subjects = analysis.get('subjects', [])
            if not isinstance(existing_subjects, list):
                existing_subjects = [existing_subjects] if existing_subjects else []

            for subj in custom_subjects:
                label = subj.get('label', '')
                if label and label not in existing_subjects:
                    existing_subjects.append(label)
                    self.stats['custom_subjects_added'] += 1

                    self.edit_history.append({
                        'record_id': record_id,
                        'field': 'custom_subject',
                        'original_value': '',
                        'new_value': label,
                        'edit_type': 'custom_subject_added'
                    })

            analysis['subjects'] = existing_subjects

        record['analysis'] = analysis
        return True

    def apply_all_edits(self):
        """Apply all archivist edits to the workflow data."""
        if not self.decisions_data or not self.workflow_data:
            return False

        decisions = self.decisions_data.get('decisions', [])

        for decision in decisions:
            record_id = decision.get('record_id')

            # Find the corresponding record in workflow data (1-indexed to 0-indexed)
            record_idx = record_id - 1
            if record_idx < 0 or record_idx >= len(self.workflow_data):
                print(f"   Warning: Record ID {record_id} not found in workflow data")
                continue

            record = self.workflow_data[record_idx]
            has_edits = False

            # Track per-record metrics
            record_metrics = {
                'record_id': record_id,
                'field_edits': {},
                'term_decisions': {},
                'custom_additions': {}
            }

            # Apply field edits
            edits = decision.get('edits', {})
            if edits:
                for field_name, edit_data in edits.items():
                    if edit_data.get('edited', False):
                        success, diff_metrics = self.apply_field_edit(record, field_name, edit_data, record_id)
                        if success:
                            has_edits = True
                            record_metrics['field_edits'][field_name] = diff_metrics

            # Apply term decisions
            term_decisions = decision.get('term_decisions', {})
            if term_decisions:
                self.apply_term_decisions(record, term_decisions, record_id)
                has_edits = True
                record_metrics['term_decisions'] = {
                    'total': len(term_decisions),
                    'approved': sum(1 for v in term_decisions.values()
                                    if v == 'approved' or (isinstance(v, dict) and v.get('status') == 'approved')),
                    'rejected': sum(1 for v in term_decisions.values()
                                    if v == 'rejected'),
                    'cascade_rejected': sum(1 for v in term_decisions.values()
                                            if isinstance(v, dict) and v.get('status') == 'cascade_rejected')
                }

            # Apply custom terms and subjects
            custom_terms = decision.get('custom_terms', [])
            custom_subjects = decision.get('custom_subjects', [])
            if custom_terms or custom_subjects:
                self.apply_custom_terms(record, custom_terms, custom_subjects, record_id)
                has_edits = True
                record_metrics['custom_additions'] = {
                    'custom_terms': len(custom_terms),
                    'custom_subjects': len(custom_subjects)
                }

            # Add archivist metadata
            analysis = record.get('analysis', {})
            analysis['archivist_reviewed'] = decision.get('reviewed', False)
            # Support both old 'cataloger_notes' and new 'archivist_notes' keys
            analysis['archivist_notes'] = decision.get('archivist_notes',
                                           decision.get('cataloger_notes', ''))
            analysis['archivist_review_date'] = self.stats['export_timestamp']
            analysis['archivist_name'] = self.stats['archivist_name']
            record['analysis'] = analysis

            # Update stats
            if has_edits:
                self.stats['records_with_edits'] += 1
                self.stats['per_record_metrics'].append(record_metrics)
            elif decision.get('reviewed', False):
                self.stats['records_reviewed_only'] += 1

        # Calculate aggregate subject/heading metrics across all records
        self._calculate_aggregate_subject_heading_metrics()

        return True

    def _calculate_aggregate_subject_heading_metrics(self):
        """Calculate aggregate metrics for subjects and headings across all records."""
        for record in self.workflow_data:
            analysis = record.get('analysis', {})
            term_decisions = analysis.get('archivist_term_decisions', {})

            # Count original subjects
            original_subjects = analysis.get('subjects', [])
            if not isinstance(original_subjects, list):
                original_subjects = [original_subjects] if original_subjects else []
            self.stats['subjects_original_count'] += len(original_subjects)

            # Count subject decisions
            for i, _ in enumerate(original_subjects):
                term_id = f"subject-{i}"
                decision = term_decisions.get(term_id)
                if decision is None or decision == 'approved':
                    self.stats['subjects_kept'] += 1
                elif decision == 'rejected':
                    self.stats['subjects_removed'] += 1

            # Count custom subjects added
            custom_subjects = analysis.get('archivist_custom_subjects', [])
            if custom_subjects:
                self.stats['subjects_added'] += len(custom_subjects)

            # Calculate final subject count
            self.stats['subjects_final_count'] = (
                self.stats['subjects_kept'] + self.stats['subjects_added']
            )

            # Count original headings
            final_selected_terms = analysis.get('final_selected_terms', [])
            self.stats['headings_original_count'] += len(final_selected_terms)

            # Count heading decisions
            for i, _ in enumerate(final_selected_terms):
                term_id = f"selected-{i}"
                decision = term_decisions.get(term_id)
                if isinstance(decision, dict) and decision.get('status') == 'cascade_rejected':
                    self.stats['headings_removed'] += 1
                elif decision == 'rejected':
                    self.stats['headings_removed'] += 1
                else:
                    self.stats['headings_kept'] += 1

            # Count custom terms added
            custom_terms = analysis.get('archivist_custom_terms', [])
            if custom_terms:
                self.stats['headings_added'] += len(custom_terms)

        # Calculate final heading count
        self.stats['headings_final_count'] = (
            self.stats['headings_kept'] + self.stats['headings_added']
        )

    def save_workflow_json(self):
        """Save the updated workflow JSON."""
        try:
            # Re-add api_stats if it existed
            output_data = self.workflow_data.copy()
            if self.api_stats:
                output_data.append(self.api_stats)

            with open(self.workflow_json_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)

            print(f"   Saved updated workflow JSON")
            return True
        except Exception as e:
            print(f"Error saving workflow JSON: {e}")
            return False

    def update_excel_deliverable(self):
        """Update the Excel deliverable with archivist edits and add Edit History sheet."""
        if not os.path.exists(self.workflow_excel_path):
            print(f"   Warning: Excel file not found at {self.workflow_excel_path}")
            return False

        try:
            wb = load_workbook(self.workflow_excel_path)

            # Get or create the main analysis sheet
            if 'Analysis' in wb.sheetnames:
                ws = wb['Analysis']
            elif 'Sheet' in wb.sheetnames:
                ws = wb['Sheet']
            else:
                ws = wb.active

            # Update cells based on edits
            # The Excel columns typically are:
            # A: Folder, B: Page, C: Image, D: Title, E: Contributors, F: Genre,
            # G: OCR Text, H: Description, I: Format, J: Subjects, K: Date,
            # L: Sheet Info, M: Named Entities, N: Geographic Entities, O: Content Warning

            column_mapping = {
                'title': 4,  # D
                'contributors': 5,  # E
                'genre': 6,  # F
                'ocr_text': 7,  # G
                'description': 8,  # H
                'format_media': 9,  # I
                'subjects': 10,  # J
                'date_on_drawing': 11,  # K
                'sheet_info': 12,  # L
                'named_entities': 13,  # M
                'geographic_entities': 14,  # N
                'content_warning': 15  # O
            }

            # Apply edits to Excel
            for decision in self.decisions_data.get('decisions', []):
                record_id = decision.get('record_id')
                row_num = record_id + 1  # +1 for header row

                edits = decision.get('edits', {})
                for field_name, edit_data in edits.items():
                    if edit_data.get('edited', False) and field_name in column_mapping:
                        col_num = column_mapping[field_name]
                        new_value = edit_data.get('value', '')

                        # Format list values
                        if isinstance(new_value, list):
                            if field_name == 'contributors':
                                # Format contributors specially
                                contrib_strs = []
                                for c in new_value:
                                    if isinstance(c, dict):
                                        name = c.get('name', '')
                                        role = c.get('role', '')
                                        if role:
                                            contrib_strs.append(f"{name} ({role})")
                                        else:
                                            contrib_strs.append(name)
                                    else:
                                        contrib_strs.append(str(c))
                                new_value = '; '.join(contrib_strs)
                            else:
                                new_value = ', '.join(str(v) for v in new_value)

                        cell = ws.cell(row=row_num, column=col_num)
                        cell.value = new_value
                        # Highlight edited cells
                        cell.fill = PatternFill(start_color="FFFFD700", end_color="FFFFD700", fill_type="solid")

            # Add Edit History sheet
            self._add_edit_history_sheet(wb)

            wb.save(self.workflow_excel_path)
            print(f"   Saved updated Excel deliverable")
            return True

        except Exception as e:
            print(f"Error updating Excel: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _add_edit_history_sheet(self, wb):
        """Add an Edit History sheet to the workbook."""
        # Remove existing Edit History sheet if present
        if 'Edit History' in wb.sheetnames:
            del wb['Edit History']

        ws = wb.create_sheet('Edit History')

        # Styles
        header_fill = PatternFill(start_color="FF2C3E50", end_color="FF2C3E50", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        stats_fill = PatternFill(start_color="FFE8F4F8", end_color="FFE8F4F8", fill_type="solid")
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # Summary Statistics Section
        ws['A1'] = "ARCHIVIST EDIT INTEGRATION SUMMARY"
        ws['A1'].font = Font(size=14, bold=True)
        ws.merge_cells('A1:E1')

        self.stats['integration_timestamp'] = datetime.now().isoformat()

        summary_data = [
            ("Archivist Name:", self.stats['archivist_name']),
            ("Export Timestamp:", self.stats['export_timestamp']),
            ("Integration Timestamp:", self.stats['integration_timestamp']),
            ("", ""),
            ("Total Records in Export:", self.stats['total_records_in_export']),
            ("Records with Edits:", self.stats['records_with_edits']),
            ("Records Reviewed Only (no edits):", self.stats['records_reviewed_only']),
            ("", ""),
            ("Total Field Edits:", self.stats['total_field_edits']),
            ("Total Term Decisions:", self.stats['total_term_decisions']),
            ("Terms Approved:", self.stats['terms_approved']),
            ("Terms Rejected:", self.stats['terms_rejected']),
            ("Custom Terms Added:", self.stats['custom_terms_added']),
            ("Custom Subjects Added:", self.stats['custom_subjects_added']),
        ]

        row = 3
        for label, value in summary_data:
            ws.cell(row=row, column=1, value=label).font = Font(bold=True)
            ws.cell(row=row, column=2, value=value)
            if label:
                ws.cell(row=row, column=1).fill = stats_fill
                ws.cell(row=row, column=2).fill = stats_fill
            row += 1

        # Edits by Field Section
        row += 1
        ws.cell(row=row, column=1, value="Edits by Field:").font = Font(bold=True)
        row += 1
        for field, count in sorted(self.stats['edits_by_field'].items()):
            ws.cell(row=row, column=1, value=f"  {field}:")
            ws.cell(row=row, column=2, value=count)
            row += 1

        # Detailed Edit History Section
        row += 2
        ws.cell(row=row, column=1, value="DETAILED EDIT HISTORY").font = Font(size=12, bold=True)
        ws.merge_cells(f'A{row}:E{row}')
        row += 1

        # Headers
        headers = ["Record ID", "Field", "Edit Type", "Original Value", "New Value"]
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=row, column=col, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.border = border
            cell.alignment = Alignment(horizontal='center', vertical='center')

        row += 1

        # Edit history rows
        for edit in self.edit_history:
            ws.cell(row=row, column=1, value=edit['record_id']).border = border
            ws.cell(row=row, column=2, value=edit['field']).border = border
            ws.cell(row=row, column=3, value=edit['edit_type']).border = border

            orig_cell = ws.cell(row=row, column=4, value=edit['original_value'])
            orig_cell.border = border
            orig_cell.alignment = Alignment(wrap_text=True, vertical='top')

            new_cell = ws.cell(row=row, column=5, value=edit['new_value'])
            new_cell.border = border
            new_cell.alignment = Alignment(wrap_text=True, vertical='top')

            row += 1

        # Adjust column widths
        ws.column_dimensions['A'].width = 12
        ws.column_dimensions['B'].width = 20
        ws.column_dimensions['C'].width = 20
        ws.column_dimensions['D'].width = 40
        ws.column_dimensions['E'].width = 40

    def generate_edit_statistics_report(self):
        """Generate a detailed JSON report quantifying all archivist edits.

        Creates edit_statistics_report.json with:
        - Summary statistics
        - Character-level metrics for each text field
        - Subject/heading change metrics
        - Per-record detailed metrics
        """
        self.stats['integration_timestamp'] = datetime.now().isoformat()

        report = {
            'report_generated': self.stats['integration_timestamp'],
            'archivist_name': self.stats['archivist_name'],
            'export_timestamp': self.stats['export_timestamp'],

            # High-level summary
            'summary': {
                'total_records_in_export': self.stats['total_records_in_export'],
                'records_with_edits': self.stats['records_with_edits'],
                'records_reviewed_only': self.stats['records_reviewed_only'],
                'total_field_edits': self.stats['total_field_edits'],
                'total_term_decisions': self.stats['total_term_decisions']
            },

            # Text field character-level metrics
            'text_field_metrics': {},

            # Subject metrics
            'subject_metrics': {
                'original_count': self.stats['subjects_original_count'],
                'final_count': self.stats['subjects_final_count'],
                'kept': self.stats['subjects_kept'],
                'removed': self.stats['subjects_removed'],
                'added_by_archivist': self.stats['subjects_added'],
                'net_change': self.stats['subjects_final_count'] - self.stats['subjects_original_count']
            },

            # Subject heading metrics
            'subject_heading_metrics': {
                'original_count': self.stats['headings_original_count'],
                'final_count': self.stats['headings_final_count'],
                'kept': self.stats['headings_kept'],
                'removed': self.stats['headings_removed'],
                'added_by_archivist': self.stats['headings_added'],
                'net_change': self.stats['headings_final_count'] - self.stats['headings_original_count']
            },

            # Term decision breakdown
            'term_decisions': {
                'total': self.stats['total_term_decisions'],
                'approved': self.stats['terms_approved'],
                'rejected_explicit': self.stats['terms_rejected'],
                'rejected_cascade': self.stats['terms_cascade_rejected'],
                'subjects_rejected': self.stats['subjects_rejected'],
                'custom_terms_added': self.stats['custom_terms_added'],
                'custom_subjects_added': self.stats['custom_subjects_added']
            },

            # Edits by field count
            'edits_by_field_count': self.stats['edits_by_field'],

            # Per-record detailed metrics
            'per_record_metrics': self.stats['per_record_metrics'],

            # Full edit history (for auditing)
            'edit_history': self.edit_history
        }

        # Build detailed text field metrics
        for field_name, metrics in self.stats['text_field_metrics'].items():
            report['text_field_metrics'][field_name] = {
                'edits_count': metrics['edits_count'],
                'characters_added': metrics['chars_added'],
                'characters_deleted': metrics['chars_deleted'],
                'characters_total_changed': metrics['chars_total_changed'],
                'total_original_length': metrics['total_original_length'],
                'total_new_length': metrics['total_new_length'],
                'net_character_change': metrics['total_new_length'] - metrics['total_original_length'],
                'average_chars_changed_per_edit': round(
                    metrics['chars_total_changed'] / metrics['edits_count'], 2
                ) if metrics['edits_count'] > 0 else 0
            }

        # Calculate totals across all text fields
        total_chars_added = sum(m['chars_added'] for m in self.stats['text_field_metrics'].values())
        total_chars_deleted = sum(m['chars_deleted'] for m in self.stats['text_field_metrics'].values())
        total_chars_changed = sum(m['chars_total_changed'] for m in self.stats['text_field_metrics'].values())

        report['text_field_totals'] = {
            'total_characters_added': total_chars_added,
            'total_characters_deleted': total_chars_deleted,
            'total_characters_changed': total_chars_changed,
            'net_character_change': total_chars_added - total_chars_deleted
        }

        # Save report
        report_path = os.path.join(self.metadata_folder, "edit_statistics_report.json")
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print(f"   Generated edit_statistics_report.json")
            return report_path
        except Exception as e:
            print(f"   Error generating edit statistics report: {e}")
            return None

    def print_summary(self):
        """Print a summary of the integration."""
        print("\n" + "=" * 60)
        print("INTEGRATION SUMMARY")
        print("=" * 60)
        print(f"Archivist: {self.stats['archivist_name']}")
        print(f"Total records processed: {self.stats['total_records_in_export']}")
        print(f"Records with edits: {self.stats['records_with_edits']}")
        print(f"Records reviewed only: {self.stats['records_reviewed_only']}")

        print(f"\n--- Field Edits ---")
        print(f"Total field edits: {self.stats['total_field_edits']}")
        if self.stats['edits_by_field']:
            for field, count in sorted(self.stats['edits_by_field'].items()):
                print(f"   {field}: {count}")

        # Text field character metrics
        if self.stats['text_field_metrics']:
            print(f"\n--- Character-Level Changes ---")
            total_added = 0
            total_deleted = 0
            for field, metrics in sorted(self.stats['text_field_metrics'].items()):
                print(f"   {field}:")
                print(f"      Edits: {metrics['edits_count']}")
                print(f"      Characters added: {metrics['chars_added']}")
                print(f"      Characters deleted: {metrics['chars_deleted']}")
                print(f"      Total changed: {metrics['chars_total_changed']}")
                total_added += metrics['chars_added']
                total_deleted += metrics['chars_deleted']
            print(f"   TOTALS:")
            print(f"      All characters added: {total_added}")
            print(f"      All characters deleted: {total_deleted}")
            print(f"      Net change: {total_added - total_deleted:+d}")

        # Subject metrics
        print(f"\n--- Subject Changes ---")
        print(f"   Original subjects: {self.stats['subjects_original_count']}")
        print(f"   Subjects kept: {self.stats['subjects_kept']}")
        print(f"   Subjects removed: {self.stats['subjects_removed']}")
        print(f"   Subjects added by archivist: {self.stats['subjects_added']}")
        print(f"   Final subject count: {self.stats['subjects_final_count']}")
        net_subj = self.stats['subjects_final_count'] - self.stats['subjects_original_count']
        print(f"   Net change: {net_subj:+d}")

        # Heading metrics
        print(f"\n--- Subject Heading Changes ---")
        print(f"   Original headings: {self.stats['headings_original_count']}")
        print(f"   Headings kept: {self.stats['headings_kept']}")
        print(f"   Headings removed: {self.stats['headings_removed']}")
        print(f"   Headings added by archivist: {self.stats['headings_added']}")
        print(f"   Final heading count: {self.stats['headings_final_count']}")
        net_head = self.stats['headings_final_count'] - self.stats['headings_original_count']
        print(f"   Net change: {net_head:+d}")

        print(f"\n--- Term Decisions ---")
        print(f"Total decisions: {self.stats['total_term_decisions']}")
        print(f"   Approved: {self.stats['terms_approved']}")
        print(f"   Rejected (explicit): {self.stats['terms_rejected']}")
        print(f"   Rejected (cascade): {self.stats['terms_cascade_rejected']}")
        print(f"Custom terms added: {self.stats['custom_terms_added']}")
        print(f"Custom subjects added: {self.stats['custom_subjects_added']}")

    def generate_final_metadata(self):
        """Generate final_metadata.json with only approved/clean data.

        This creates a clean JSON file containing only:
        - Edited/final field values
        - Only approved subjects (not rejected)
        - Only approved subject headings (not rejected or cascade-rejected)
        - Custom terms/subjects added by archivist
        - No intermediate data (raw_response, vocabulary_search_results, etc.)
        """
        if not self.workflow_data:
            print("   Warning: No workflow data loaded")
            return False

        final_records = []

        for record in self.workflow_data:
            analysis = record.get('analysis', {})
            term_decisions = analysis.get('archivist_term_decisions', {})

            # Get the list of original subjects
            original_subjects = analysis.get('subjects', [])
            if not isinstance(original_subjects, list):
                original_subjects = [original_subjects] if original_subjects else []

            # Filter subjects: keep only approved ones
            approved_subjects = []
            for i, subject in enumerate(original_subjects):
                term_id = f"subject-{i}"
                decision = term_decisions.get(term_id)
                # Keep if no decision (default approved) or explicitly approved
                if decision is None or decision == 'approved':
                    approved_subjects.append(subject)

            # Add any custom subjects added by archivist
            custom_subjects = analysis.get('archivist_custom_subjects', [])
            for subj in custom_subjects:
                label = subj.get('label', '') if isinstance(subj, dict) else subj
                if label and label not in approved_subjects:
                    approved_subjects.append(label)

            # Filter subject headings: keep only approved ones
            final_selected_terms = analysis.get('final_selected_terms', [])
            approved_headings = []
            for i, term in enumerate(final_selected_terms):
                term_id = f"selected-{i}"
                decision = term_decisions.get(term_id)

                # Check if decision is cascade_rejected (object format)
                if isinstance(decision, dict) and decision.get('status') == 'cascade_rejected':
                    continue  # Skip cascade-rejected
                elif decision == 'rejected':
                    continue  # Skip explicitly rejected

                # Keep approved or no decision (default approved)
                approved_headings.append({
                    'label': term.get('label', ''),
                    'uri': term.get('uri', ''),
                    'source': term.get('source', ''),
                    'derived_from_subject': term.get('derived_from_subject', '')
                })

            # Add any custom terms added by archivist
            custom_terms = analysis.get('archivist_custom_terms', [])
            for term in custom_terms:
                approved_headings.append({
                    'label': term.get('label', ''),
                    'uri': term.get('uri', ''),
                    'source': term.get('source', 'Manual'),
                    'derived_from_subject': ''
                })

            # Build clean record
            clean_record = {
                'folder': record.get('folder', ''),
                'page_number': record.get('page_number', 0),
                'image_path': record.get('image_path', ''),
                'metadata': {
                    'title': analysis.get('title', ''),
                    'contributors': analysis.get('contributors', []),
                    'genre': analysis.get('genre', ''),
                    'description': analysis.get('description', ''),
                    'ocr_text': analysis.get('ocr_text', ''),
                    'format_media': analysis.get('format_media', ''),
                    'date_on_drawing': analysis.get('date_on_drawing', ''),
                    'sheet_info': analysis.get('sheet_info', ''),
                    'named_entities': analysis.get('named_entities', []),
                    'geographic_entities': analysis.get('geographic_entities', []),
                    'content_warning': analysis.get('content_warning', ''),
                    'subjects': approved_subjects,
                    'subject_headings': approved_headings
                },
                'review_info': {
                    'reviewed': analysis.get('archivist_reviewed', False),
                    'archivist_name': analysis.get('archivist_name', ''),
                    'review_date': analysis.get('archivist_review_date', ''),
                    'archivist_notes': analysis.get('archivist_notes', '')
                }
            }

            final_records.append(clean_record)

        # Write final metadata
        final_metadata_path = os.path.join(self.metadata_folder, "final_metadata.json")
        try:
            with open(final_metadata_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'generated_timestamp': datetime.now().isoformat(),
                    'archivist_name': self.stats['archivist_name'],
                    'total_records': len(final_records),
                    'records': final_records
                }, f, indent=2, ensure_ascii=False)

            print(f"   Generated final_metadata.json with {len(final_records)} records")
            return True
        except Exception as e:
            print(f"   Error generating final_metadata.json: {e}")
            return False

    def run(self, decisions_path=None):
        """Main execution method.

        Args:
            decisions_path: Optional path to a specific decisions JSON file.
                          If not provided, uses the latest export.
        """
        print("\n" + "=" * 60)
        print("Integrate Archivist Edits")
        print("=" * 60)

        print(f"\nUsing folder: {self.folder_name}")

        # Find or use specified export
        print("\n1. Finding archivist decisions export...")
        if decisions_path:
            if not os.path.exists(decisions_path):
                print(f"   Error: Specified decisions file not found: {decisions_path}")
                return False
            export_path = decisions_path
            print(f"   Using specified file: {os.path.basename(export_path)}")
        else:
            export_path = self.find_latest_export()
            if not export_path:
                return False
            print(f"   Found latest: {os.path.basename(export_path)}")

        # Load decisions
        print("\n2. Loading archivist decisions...")
        if not self.load_decisions(export_path):
            return False

        # Load workflow JSON
        print("\n3. Loading workflow data...")
        if not self.load_workflow_json():
            return False

        # Backup original files
        print("\n4. Backing up original files...")
        self.backup_original_files()

        # Apply edits
        print("\n5. Applying archivist edits...")
        if not self.apply_all_edits():
            return False
        print(f"   Applied edits to {self.stats['records_with_edits']} records")

        # Save updated JSON
        print("\n6. Saving updated workflow JSON...")
        if not self.save_workflow_json():
            return False

        # Update Excel
        print("\n7. Updating Excel deliverable...")
        self.update_excel_deliverable()

        # Generate final metadata
        print("\n8. Generating final_metadata.json...")
        self.generate_final_metadata()

        # Generate edit statistics report
        print("\n9. Generating edit statistics report...")
        report_path = self.generate_edit_statistics_report()

        # Print summary
        self.print_summary()

        final_metadata_path = os.path.join(self.metadata_folder, "final_metadata.json")
        edit_stats_path = os.path.join(self.metadata_folder, "edit_statistics_report.json")

        print("\n" + "=" * 60)
        print("INTEGRATION COMPLETE")
        print("=" * 60)
        print(f"\nUpdated files:")
        print(f"   {self.workflow_json_path}")
        print(f"   {self.workflow_excel_path}")
        print(f"   {final_metadata_path}")
        print(f"\nEdit statistics report:")
        print(f"   {edit_stats_path}")
        print(f"\nOriginal files backed up to:")
        print(f"   {self.original_outputs_folder}")
        print("=" * 60)

        return True


def list_available_folders(base_dir):
    """List all available output folders."""
    if not os.path.exists(base_dir):
        return []

    folders = []
    for item in os.listdir(base_dir):
        item_path = os.path.join(base_dir, item)
        if os.path.isdir(item_path) and item.startswith("ArchImagesAI_"):
            folders.append((item, item_path))

    # Sort by modification time, newest first
    folders.sort(key=lambda x: os.path.getmtime(x[1]), reverse=True)
    return folders


def list_available_exports(exports_folder):
    """List all available JSON exports in the exports folder."""
    if not os.path.exists(exports_folder):
        return []

    exports = []
    for item in os.listdir(exports_folder):
        if item.endswith('.json'):
            item_path = os.path.join(exports_folder, item)
            exports.append((item, item_path))

    # Sort by modification time, newest first
    exports.sort(key=lambda x: os.path.getmtime(x[1]), reverse=True)
    return exports


def prompt_for_folder(base_dir):
    """Prompt user to select an output folder."""
    folders = list_available_folders(base_dir)

    if not folders:
        print(f"No output folders found in: {base_dir}")
        print("Please run Steps 1-4 first, then html-review.py.")
        return None

    print("\nAvailable output folders:")
    print("-" * 60)
    for i, (name, path) in enumerate(folders, 1):
        mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
        marker = " (newest)" if i == 1 else ""
        print(f"  {i}. {name}{marker}")
        print(f"      Modified: {mtime}")

    print("-" * 60)
    print(f"  Enter 1-{len(folders)} to select a folder")
    print(f"  Or press Enter to use the newest folder (1)")
    print(f"  Or type a full path to a folder")

    while True:
        choice = input("\nSelect output folder: ").strip()

        # Default to newest
        if choice == "":
            return folders[0][1]

        # Check if it's a number
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(folders):
                return folders[idx][1]
            else:
                print(f"Invalid choice. Please enter 1-{len(folders)}.")
                continue

        # Check if it's a path
        if os.path.isdir(choice):
            return choice

        print(f"Invalid input. Please enter a number or valid path.")


def prompt_for_decisions(folder_path):
    """Prompt user to select an archivist decisions JSON file."""
    exports_folder = os.path.join(folder_path, "review", "exports")
    exports = list_available_exports(exports_folder)

    if not exports:
        print(f"\nNo JSON export files found in: {exports_folder}")
        print("Please export your review decisions from the HTML interface first.")
        print("\nYou can also enter a full path to a decisions JSON file.")

        while True:
            path = input("\nPath to decisions JSON (or 'q' to quit): ").strip()
            if path.lower() == 'q':
                return None
            if os.path.isfile(path) and path.endswith('.json'):
                return path
            print("Invalid path. Please enter a valid JSON file path.")

    print("\nAvailable archivist decisions exports:")
    print("-" * 60)
    for i, (name, path) in enumerate(exports, 1):
        mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
        marker = " (newest)" if i == 1 else ""
        print(f"  {i}. {name}{marker}")
        print(f"      Modified: {mtime}")

    print("-" * 60)
    print(f"  Enter 1-{len(exports)} to select an export")
    print(f"  Or press Enter to use the newest export (1)")
    print(f"  Or type a full path to a JSON file")

    while True:
        choice = input("\nSelect decisions export: ").strip()

        # Default to newest
        if choice == "":
            return exports[0][1]

        # Check if it's a number
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(exports):
                return exports[idx][1]
            else:
                print(f"Invalid choice. Please enter 1-{len(exports)}.")
                continue

        # Check if it's a path
        if os.path.isfile(choice) and choice.endswith('.json'):
            return choice

        print(f"Invalid input. Please enter a number or valid JSON path.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Integrate archivist edits into workflow outputs and generate final metadata.',
        epilog="""
Examples:
  python integrate-archivist-edits.py                           # Interactive prompts
  python integrate-archivist-edits.py --decisions path/to.json  # Use specific export
  python integrate-archivist-edits.py --folder /path/to/output  # Specify output folder
        """
    )
    parser.add_argument('--decisions', '-d',
                        help='Path to a specific archivist decisions JSON file')
    parser.add_argument('--folder', '-f',
                        help='Path to the output folder (defaults to interactive prompt)')
    parser.add_argument('--yes', '-y', action='store_true',
                        help='Skip confirmation prompt')

    args = parser.parse_args()

    print("Integrate Archivist Edits")
    print("=" * 60)

    base_output_dir = os.path.join(script_dir, "output_folders")

    # Get output folder - either from args or interactive prompt
    if args.folder:
        folder_path = args.folder
        if not os.path.exists(folder_path):
            print(f"Error: Specified folder not found: {folder_path}")
            return 1
        print(f"Using folder: {os.path.basename(folder_path)}")
    else:
        folder_path = prompt_for_folder(base_output_dir)
        if not folder_path:
            return 1
        print(f"\nSelected folder: {os.path.basename(folder_path)}")

    # Get decisions file - either from args or interactive prompt
    if args.decisions:
        decisions_path = args.decisions
        if not os.path.exists(decisions_path):
            print(f"Error: Specified decisions file not found: {decisions_path}")
            return 1
        print(f"Using decisions: {os.path.basename(decisions_path)}")
    else:
        decisions_path = prompt_for_decisions(folder_path)
        if not decisions_path:
            print("Operation cancelled.")
            return 0
        print(f"\nSelected decisions: {os.path.basename(decisions_path)}")

    # Confirm with user unless --yes flag
    if not args.yes:
        print("\n" + "-" * 60)
        print("Summary:")
        print(f"  Output folder: {os.path.basename(folder_path)}")
        print(f"  Decisions file: {os.path.basename(decisions_path)}")
        print("-" * 60)
        response = input("\nThis will modify deliverable files. Original files will be backed up. Continue? (yes/no): ").strip().lower()
        if response not in ['yes', 'y']:
            print("Operation cancelled.")
            return 0

    # Create integrator and run
    integrator = ArchivistEditsIntegrator(folder_path)
    success = integrator.run(decisions_path=decisions_path)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
