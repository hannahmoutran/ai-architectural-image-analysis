#!/usr/bin/env python3
"""
Step 5: Create Interactive HTML Review Interface for Architectural Drawings
============================================================================

Generates a local HTML review interface allowing archivists to:
- View architectural drawing images alongside AI-generated metadata
- Edit all AI-generated fields (title, description, subjects, entities, etc.)
- Approve/reject/edit controlled vocabulary terms
- Add new terms manually
- Export decisions to JSON for integration back into the workflow

Usage:
    python step-5-html-review.py
    python run.py 5
"""

import os
import sys
import json
import math
import shutil
import re
from datetime import datetime

# Add CODE directory to path for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from shared_utilities import find_newest_folder
from config import MEDIUM_TERMS, SUPPORT_TERMS


class HTMLReviewBuilder:
    """Builds interactive HTML review pages for architectural drawing metadata."""

    def __init__(self, folder_path, records_per_page=10):
        self.folder_path = folder_path
        self.records_per_page = records_per_page
        self.json_data = None
        self.data_items = []
        self.workflow_timestamp = None
        self.review_folder = None
        self.images_folder = None
        self.folder_name = os.path.basename(folder_path)
        self.collection_name = ''
        self.model_used = ''

    def load_json_data(self):
        """Load workflow JSON data."""
        json_folder = os.path.join(self.folder_path, "metadata", "json")
        json_path = os.path.join(json_folder, "drawings_workflow.json")

        if not os.path.exists(json_path):
            print(f"Error: drawings_workflow.json not found at {json_path}")
            return False

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                self.json_data = json.load(f)

            # Extract data items (exclude api_stats entry)
            if self.json_data and isinstance(self.json_data[-1], dict) and 'api_stats' in self.json_data[-1]:
                self.data_items = self.json_data[:-1]
            else:
                self.data_items = self.json_data

            # Extract timestamp from folder name
            # Format: ArchImagesAI_[folder]_[model]_YYYY-MM-DD_Time_HH-MM-SS
            parts = self.folder_name.split('_')
            if len(parts) >= 4:
                date_idx = -3  # YYYY-MM-DD is 3rd from end
                time_idx = -1  # HH-MM-SS is last
                self.workflow_timestamp = f"{parts[date_idx]}_{parts[time_idx]}"
            else:
                self.workflow_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

            print(f"Loaded {len(self.data_items)} records from workflow JSON")

            # Extract collection name from first record's folder field
            if self.data_items and isinstance(self.data_items[0], dict):
                self.collection_name = self.data_items[0].get('folder', '')
            else:
                self.collection_name = ''

            # Extract model from logs
            self.model_used = self._extract_model_from_logs()

            return True

        except Exception as e:
            print(f"Error loading JSON: {e}")
            return False

    def _extract_model_from_logs(self):
        """Extract model used from token usage logs in the logs folder."""
        logs_folder = os.path.join(self.folder_path, "logs")

        if not os.path.exists(logs_folder):
            return 'unknown-model'

        for filename in os.listdir(logs_folder):
            # Only process token usage logs, skip step2 API logs (not LLM)
            if filename.endswith("_token_usage_log.txt") and "step2_vocab_api" not in filename:
                filepath = os.path.join(logs_folder, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    match = re.search(r'Model used:\s*(.+?)(?:\n|$)', content)
                    if match:
                        return match.group(1).strip()
                except Exception:
                    pass

        return 'unknown-model'

    def create_review_folder(self):
        """Create the review folder structure."""
        self.review_folder = os.path.join(self.folder_path, "review")
        self.images_folder = os.path.join(self.review_folder, "images")
        exports_folder = os.path.join(self.review_folder, "exports")

        os.makedirs(self.review_folder, exist_ok=True)
        os.makedirs(self.images_folder, exist_ok=True)
        os.makedirs(exports_folder, exist_ok=True)

        print(f"Created review folder structure at: {self.review_folder}")
        return True

    def copy_images(self):
        """Copy source images to review/images/ for portability."""
        copied_count = 0
        for item in self.data_items:
            if 'image_path' in item:
                src_path = item['image_path']
                if os.path.exists(src_path):
                    filename = os.path.basename(src_path)
                    dest_path = os.path.join(self.images_folder, filename)
                    try:
                        shutil.copy2(src_path, dest_path)
                        copied_count += 1
                    except Exception as e:
                        print(f"Warning: Could not copy {filename}: {e}")

        print(f"Copied {copied_count} images to review folder")
        return True

    def escape_html(self, text):
        """Escape HTML special characters."""
        if text is None:
            return ""
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")

    def escape_js_string(self, text):
        """Escape text for use in JavaScript strings."""
        if text is None:
            return ""
        return str(text).replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")

    def get_css_styles(self):
        """Return the CSS styles for the review interface."""
        return """
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            line-height: 1.5;
        }
        .header {
            background-color: #2c3e50;
            color: white;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .header h1 { margin: 0 0 10px 0; }
        .header p { margin: 5px 0; opacity: 0.9; }

        .navigation {
            background-color: white;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .nav-btn {
            background-color: #3498db;
            color: white;
            padding: 10px 20px;
            text-decoration: none;
            border-radius: 5px;
            margin: 0 10px;
            font-weight: bold;
            display: inline-block;
            border: none;
            cursor: pointer;
        }
        .nav-btn:hover { background-color: #2980b9; }
        .nav-btn.disabled { background-color: #95a5a6; pointer-events: none; }

        .record {
            background-color: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            margin-bottom: 30px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .record.reviewed { border-left: 5px solid #27ae60; }
        .record.has-edits { border-left: 5px solid #f39c12; }
        .record.error-record { border-left: 5px solid #e74c3c; }
        .error-notice {
            background: #fdecea;
            border: 1px solid #e74c3c;
            border-radius: 5px;
            padding: 10px 15px;
            margin-bottom: 15px;
            color: #c0392b;
            font-weight: bold;
        }

        .record-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #eee;
        }
        .record-title { font-size: 20px; font-weight: bold; color: #2c3e50; }
        .record-status { display: flex; gap: 10px; align-items: center; }

        .content-grid {
            display: grid;
            grid-template-columns: 400px 1fr;
            gap: 20px;
        }
        @media (max-width: 1000px) {
            .content-grid { grid-template-columns: 1fr; }
        }

        .image-container {
            text-align: center;
            background: #f8f9fa;
            padding: 10px;
            border-radius: 5px;
        }
        .image-container img {
            max-width: 100%;
            height: auto;
            max-height: 500px;
            border: 2px solid #ddd;
            border-radius: 5px;
            cursor: pointer;
            transition: transform 0.2s;
        }
        .image-container img:hover { transform: scale(1.02); }
        .image-filename {
            margin-top: 10px;
            font-size: 12px;
            color: #666;
            word-break: break-all;
        }

        .field-group {
            margin-bottom: 15px;
            padding: 12px;
            background: #f8f9fa;
            border-radius: 5px;
        }
        .field-group.edited { background: #fff3cd; }

        .field-label {
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 5px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .field-label .edit-indicator {
            font-size: 11px;
            color: #f39c12;
            font-weight: normal;
        }

        .field-input {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
            font-family: inherit;
        }
        .field-input:focus {
            border-color: #3498db;
            outline: none;
            box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2);
        }
        .field-input.edited { border-color: #f39c12; background: #fffbf0; }

        textarea.field-input {
            min-height: 80px;
            resize: vertical;
        }
        textarea.field-input.large { min-height: 150px; }

        .list-item {
            display: flex;
            gap: 10px;
            margin-bottom: 8px;
            align-items: center;
        }
        .list-item input { flex: 1; }
        .list-item .remove-btn {
            background: #e74c3c;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 5px 10px;
            cursor: pointer;
            font-size: 12px;
        }
        .list-item .remove-btn:hover { background: #c0392b; }
        .add-btn {
            background: #27ae60;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 8px 15px;
            cursor: pointer;
            font-size: 13px;
            margin-top: 5px;
        }
        .add-btn:hover { background: #229954; }

        .contributor-item {
            display: flex;
            gap: 10px;
            margin-bottom: 8px;
            align-items: center;
        }

        .section-header {
            font-size: 16px;
            font-weight: bold;
            color: #2c3e50;
            margin: 20px 0 10px 0;
            padding-bottom: 5px;
            border-bottom: 2px solid #3498db;
        }

        .vocab-section { margin-top: 20px; }
        .vocab-group {
            margin-bottom: 15px;
            padding: 12px;
            background: #f8f9fa;
            border-radius: 5px;
        }
        .vocab-group-title {
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 10px;
        }
        .vocab-term {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px;
            margin: 5px 0;
            background: white;
            border-radius: 4px;
            border: 1px solid #ddd;
        }
        .vocab-term.approved { background: #d4edda; border-color: #28a745; }
        .vocab-term.rejected { background: #f8d7da; border-color: #dc3545; text-decoration: line-through; opacity: 0.7; }
        .vocab-term.cascade-rejected { background: #ffe0e0; border-color: #ff9999; opacity: 0.6; }
        .vocab-term.cascade-rejected .vocab-term-label { text-decoration: line-through; }
        .vocab-term.pending { background: #fff3cd; border-color: #ffc107; }

        .vocab-term-label { flex: 1; }
        .derived-from-badge {
            font-size: 10px;
            padding: 2px 6px;
            background: #e9ecef;
            color: #6c757d;
            border-radius: 3px;
            white-space: nowrap;
            max-width: 150px;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .cascade-indicator {
            font-size: 11px;
            color: #dc3545;
            font-style: italic;
        }
        .vocab-term-source {
            font-size: 11px;
            padding: 2px 6px;
            background: #6c757d;
            color: white;
            border-radius: 3px;
        }
        .vocab-term-source.lcsh { background: #007bff; }
        .vocab-term-source.fast { background: #28a745; }
        .vocab-term-source.aat { background: #dc3545; }
        .vocab-term-source.tgn { background: #6f42c1; }

        .term-actions {
            display: flex;
            gap: 5px;
        }
        .term-btn {
            padding: 4px 10px;
            border: none;
            border-radius: 3px;
            cursor: pointer;
            font-size: 12px;
        }
        .term-btn.approve { background: #28a745; color: white; }
        .term-btn.reject { background: #dc3545; color: white; }
        .term-btn.approve:hover { background: #218838; }
        .term-btn.reject:hover { background: #c82333; }
        .term-btn.active { opacity: 0.6; }

        .term-uri {
            font-size: 11px;
            color: #3498db;
            text-decoration: none;
            padding: 2px 6px;
            background: #e8f4fc;
            border-radius: 3px;
            margin-left: 5px;
        }
        .term-uri:hover { background: #d0e8f7; text-decoration: underline; }

        .add-term-row {
            display: flex;
            gap: 10px;
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px dashed #ddd;
        }
        .add-term-row input { flex: 1; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
        .add-term-row select { padding: 8px; border: 1px solid #ddd; border-radius: 4px; }

        .actions-section {
            margin-top: 20px;
            padding: 15px;
            background: #e8f4f8;
            border-radius: 5px;
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            align-items: center;
        }
        .reviewed-checkbox {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .reviewed-checkbox input { width: 20px; height: 20px; }

        .notes-section {
            margin-top: 15px;
        }
        .notes-section textarea {
            width: 100%;
            min-height: 60px;
        }

        .save-btn {
            background: #27ae60;
            color: white;
            border: none;
            padding: 12px 25px;
            border-radius: 5px;
            cursor: pointer;
            font-weight: bold;
            font-size: 14px;
        }
        .save-btn:hover { background: #229954; }

        .export-section {
            background: white;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .export-btn {
            background: #e74c3c;
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 5px;
            cursor: pointer;
            font-weight: bold;
            font-size: 16px;
        }
        .export-btn:hover { background: #c0392b; }

        .progress-bar {
            width: 100%;
            height: 20px;
            background: #ddd;
            border-radius: 10px;
            overflow: hidden;
            margin: 10px 0;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #27ae60, #2ecc71);
            transition: width 0.3s;
        }

        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        .summary-card {
            background: white;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .summary-card .number {
            font-size: 32px;
            font-weight: bold;
            color: #2c3e50;
        }
        .summary-card .label {
            color: #666;
            font-size: 14px;
        }

        .page-links {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }
        .page-link {
            background-color: #3498db;
            color: white;
            padding: 15px;
            text-decoration: none;
            border-radius: 5px;
            text-align: center;
            font-weight: bold;
        }
        .page-link:hover { background-color: #2980b9; }

        /* Topic pills layout */
        .topics-pills {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            padding: 4px 0 10px 0;
        }
        .topics-pills .vocab-term {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 5px 12px 5px 14px;
            border-radius: 20px;
            font-size: 13px;
            width: auto;
        }
        .topics-pills .vocab-term.approved {
            background: #e8f5e9;
            border-color: #66bb6a;
        }
        .topics-pills .vocab-term.rejected {
            text-decoration: none;
            opacity: 0.85;
        }
        .topics-pills .vocab-term.rejected .vocab-term-label {
            text-decoration: line-through;
            color: #888;
        }
        .topics-pills .vocab-term.cascade-rejected {
            text-decoration: none;
        }
        .topics-pills .vocab-term.cascade-rejected .vocab-term-label {
            text-decoration: line-through;
            opacity: 0.6;
        }
        .topics-pills .vocab-term-source {
            font-size: 10px;
            padding: 1px 5px;
            opacity: 0.65;
        }
        .topics-pills .term-btn {
            padding: 2px 7px;
            font-size: 11px;
            border-radius: 10px;
        }

        /* Heading card improvements (selected subject headings) */
        .headings-list .vocab-term {
            border-left: 3px solid #ddd;
            transition: border-color 0.15s, background 0.15s;
        }
        .headings-list .vocab-term.approved {
            border-left-color: #28a745;
        }
        .headings-list .vocab-term.rejected {
            border-left-color: #dc3545;
        }
        .headings-list .vocab-term.cascade-rejected {
            border-left-color: #ff9999;
        }

        /* Collapsible section (Other Subject Headings / Other Format/Media) */
        .collapsible-toggle {
            display: flex;
            align-items: center;
            gap: 10px;
            cursor: pointer;
            padding: 10px 14px;
            background: #f5f7ff;
            border: 1px dashed #b0bdd6;
            border-radius: 6px;
            user-select: none;
            font-weight: 600;
            font-size: 13px;
            color: #3d5280;
            transition: background 0.15s;
            margin-top: 15px;
        }
        .collapsible-toggle:hover { background: #eaeefc; }
        .collapsible-toggle .toggle-label { flex: 1; }
        .term-count-badge {
            font-size: 11px;
            font-weight: normal;
            padding: 2px 9px;
            background: #dce3f5;
            border-radius: 10px;
            color: #3d5280;
            white-space: nowrap;
        }
        .chevron {
            font-size: 11px;
            transition: transform 0.2s;
            color: #6b85b5;
        }
        .chevron.open { transform: rotate(180deg); }
        .collapsible-content { padding-top: 4px; }
        .collapsible-content .vocab-group {
            margin-top: 0;
            border-top: none;
            border-radius: 0 0 5px 5px;
        }

        /* Alternative terms card grid */
        .other-terms-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
            grid-auto-rows: 1fr;
            gap: 10px;
            padding: 4px 0 8px 0;
        }
        .other-terms-grid .vocab-term {
            flex-direction: column;
            align-items: flex-start;
            gap: 0;
            padding: 12px;
            min-height: 90px;
            border-radius: 6px;
        }
        .other-terms-grid .vocab-term .card-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            width: 100%;
            gap: 8px;
            margin-bottom: 10px;
        }
        .other-terms-grid .vocab-term .vocab-term-label {
            font-weight: bold;
            font-size: 14px;
            line-height: 1.35;
            color: #2c3e50;
            flex: 1;
        }
        .other-terms-grid .vocab-term .card-badges {
            display: flex;
            flex-direction: column;
            gap: 3px;
            align-items: flex-end;
            flex-shrink: 0;
        }
        .other-terms-grid .vocab-term .term-actions { margin-top: auto; }
        .other-terms-grid .vocab-term.approved {
            background: #d4edda;
            border-color: #28a745;
        }
        .other-terms-grid .vocab-term.rejected {
            text-decoration: none;
            opacity: 0.85;
        }
        .other-terms-grid .vocab-term.rejected .vocab-term-label {
            text-decoration: line-through;
            color: #888;
        }
        .other-terms-grid .vocab-term .term-btn { text-decoration: none; }
        .name-modal-overlay {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.5);
            z-index: 9999;
            align-items: center;
            justify-content: center;
        }
        .name-modal-overlay.active { display: flex; }
        .name-modal {
            background: #fff;
            border-radius: 8px;
            padding: 30px 34px;
            max-width: 420px;
            width: 90%;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
        }
        .name-modal h2 { margin: 0 0 8px; font-size: 1.25rem; color: #2c3e50; }
        .name-modal p { margin: 0 0 18px; color: #555; }
        .name-modal input[type="text"] {
            width: 100%;
            padding: 9px 12px;
            border: 1px solid #ccc;
            border-radius: 5px;
            font-size: 1rem;
            margin-bottom: 16px;
        }
        .name-modal-actions { text-align: right; }
        .name-modal button {
            background: #2c3e50;
            color: #fff;
            border: none;
            border-radius: 5px;
            padding: 9px 22px;
            font-size: 1rem;
            cursor: pointer;
        }
        .name-modal button:hover { background: #1a252f; }
        """

    def get_javascript(self):
        """Return the JavaScript for the review interface."""
        return f"""
        const STORAGE_PREFIX = 'arch-review-{self.workflow_timestamp}-';
        const WORKFLOW_FOLDER = '{self.escape_js_string(self.folder_name)}';
        const COLLECTION_NAME = '{self.escape_js_string(self.collection_name)}';
        const MODEL_USED = '{self.escape_js_string(self.model_used)}';

        function setStorage(key, value) {{
            try {{
                localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(value));
            }} catch (e) {{
                console.error('Storage error:', e);
            }}
        }}

        function getStorage(key, defaultValue = null) {{
            try {{
                const val = localStorage.getItem(STORAGE_PREFIX + key);
                return val ? JSON.parse(val) : defaultValue;
            }} catch (e) {{
                console.error('Storage read error:', e);
                return defaultValue;
            }}
        }}

        function getAllWorkflowKeys() {{
            const keys = [];
            for (let i = 0; i < localStorage.length; i++) {{
                const key = localStorage.key(i);
                if (key && key.startsWith(STORAGE_PREFIX)) {{
                    keys.push(key.replace(STORAGE_PREFIX, ''));
                }}
            }}
            return keys;
        }}

        function showNameModal(callback) {{
            let overlay = document.getElementById('name-modal-overlay');
            if (!overlay) {{
                overlay = document.createElement('div');
                overlay.id = 'name-modal-overlay';
                overlay.className = 'name-modal-overlay';
                overlay.innerHTML =
                    '<div class="name-modal">' +
                    '<h2>Welcome!</h2>' +
                    '<p>Please enter your name &mdash; it will be saved for this review session.</p>' +
                    '<input type="text" id="name-modal-input" autocomplete="name">' +
                    '<div class="name-modal-actions"><button id="name-modal-submit">Continue</button></div>' +
                    '</div>';
                document.body.appendChild(overlay);
            }}
            const input = document.getElementById('name-modal-input');
            const submitBtn = document.getElementById('name-modal-submit');
            overlay.classList.add('active');
            input.focus();
            const submit = () => {{
                const name = input.value.trim();
                if (!name) {{ input.focus(); return; }}
                setStorage('reviewer-name', name);
                overlay.classList.remove('active');
                if (callback) callback(name);
            }};
            submitBtn.onclick = submit;
            input.onkeydown = (e) => {{ if (e.key === 'Enter') submit(); }};
        }}

        function promptForReviewerName() {{
            if (!getStorage('reviewer-name', null)) {{
                showNameModal(null);
            }}
        }}

        function autoMarkReviewed(recordId) {{
            // Automatically mark record as reviewed when any edit is made
            const reviewedCheckbox = document.getElementById('reviewed-' + recordId);
            if (reviewedCheckbox && !reviewedCheckbox.checked) {{
                reviewedCheckbox.checked = true;
                setStorage('reviewed-' + recordId, true);
                updateProgress();
            }}
        }}

        function saveFieldValue(recordId, fieldName, value) {{
            const edits = getStorage('edits-' + recordId, {{}});

            // Get the original value from localStorage (stored on page load)
            const originalValue = getStorage('original-field-' + fieldName + '-' + recordId, '');

            if (value !== originalValue) {{
                edits[fieldName] = {{ value: value, original: originalValue, edited: true }};
                autoMarkReviewed(recordId);
            }} else {{
                delete edits[fieldName];
            }}

            setStorage('edits-' + recordId, edits);
            updateFieldStyle(recordId, fieldName, value !== originalValue);
            updateRecordStatus(recordId);
        }}

        function updateFieldStyle(recordId, fieldName, isEdited) {{
            const input = document.getElementById('field-' + recordId + '-' + fieldName);
            const group = input ? input.closest('.field-group') : null;

            if (input) {{
                if (isEdited) {{
                    input.classList.add('edited');
                }} else {{
                    input.classList.remove('edited');
                }}
            }}
            if (group) {{
                if (isEdited) {{
                    group.classList.add('edited');
                }} else {{
                    group.classList.remove('edited');
                }}
            }}
        }}

        function updateRecordStatus(recordId) {{
            const record = document.getElementById('record-' + recordId);
            if (!record) return;

            const edits = getStorage('edits-' + recordId, {{}});
            const reviewed = getStorage('reviewed-' + recordId, false);

            record.classList.toggle('reviewed', reviewed);
            record.classList.toggle('has-edits', Object.keys(edits).length > 0);
        }}

        function setReviewed(recordId, checked) {{
            setStorage('reviewed-' + recordId, checked);
            updateRecordStatus(recordId);
            updateProgress();
        }}

        function saveNotes(recordId, notes) {{
            setStorage('notes-' + recordId, notes);
        }}

        function saveContributors(recordId) {{
            const container = document.getElementById('contributors-' + recordId);
            const items = container.querySelectorAll('.contributor-item');
            const contributors = [];

            items.forEach(item => {{
                const name = item.querySelector('.contrib-name').value.trim();
                const role = item.querySelector('.contrib-role').value.trim();
                if (name) {{
                    contributors.push({{ name, role }});
                }}
            }});

            const edits = getStorage('edits-' + recordId, {{}});
            const originalContribs = getStorage('original-contributors-' + recordId, null);
            const isEdited = JSON.stringify(contributors) !== JSON.stringify(originalContribs);

            if (isEdited) {{
                edits['contributors'] = {{ value: contributors, original: originalContribs, edited: true }};
            }} else {{
                delete edits['contributors'];
            }}
            setStorage('edits-' + recordId, edits);

            const group = container.closest('.field-group');
            if (group) group.classList.toggle('edited', isEdited);

            if (isEdited) autoMarkReviewed(recordId);
            updateRecordStatus(recordId);
        }}

        function addContributor(recordId) {{
            const container = document.getElementById('contributors-' + recordId);
            const div = document.createElement('div');
            div.className = 'contributor-item';
            div.innerHTML = `
                <input type="text" class="field-input contrib-name" placeholder="Name" style="flex:1;" oninput="saveContributors(${{recordId}})">
                <input type="text" class="field-input contrib-role" placeholder="Role" style="width:150px;flex-shrink:0;" oninput="saveContributors(${{recordId}})">
                <button class="remove-btn" onclick="this.parentElement.remove(); saveContributors(${{recordId}})">X</button>
            `;
            container.appendChild(div);
        }}

        function saveListField(recordId, fieldName) {{
            const container = document.getElementById(fieldName + '-' + recordId);
            const items = container.querySelectorAll('.list-item input');
            const values = [];

            items.forEach(input => {{
                const val = input.value.trim();
                if (val) values.push(val);
            }});

            const edits = getStorage('edits-' + recordId, {{}});
            const originalValues = getStorage('original-' + fieldName + '-' + recordId, null);
            const isEdited = JSON.stringify(values) !== JSON.stringify(originalValues);

            if (isEdited) {{
                edits[fieldName] = {{ value: values, original: originalValues, edited: true }};
            }} else {{
                delete edits[fieldName];
            }}
            setStorage('edits-' + recordId, edits);

            const group = container.closest('.field-group');
            if (group) group.classList.toggle('edited', isEdited);

            if (isEdited) autoMarkReviewed(recordId);
            updateRecordStatus(recordId);
        }}

        function addListItem(recordId, fieldName) {{
            const container = document.getElementById(fieldName + '-' + recordId);
            const div = document.createElement('div');
            div.className = 'list-item';
            div.innerHTML = `
                <input type="text" class="field-input" placeholder="Enter value..." oninput="saveListField(${{recordId}}, '${{fieldName}}')">
                <button class="remove-btn" onclick="this.parentElement.remove(); saveListField(${{recordId}}, '${{fieldName}}')">X</button>
            `;
            container.appendChild(div);
        }}

        function buildListItemRow(recordId, fieldName, value) {{
            const div = document.createElement('div');
            div.className = 'list-item';
            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'field-input';
            input.placeholder = 'Enter value...';
            input.value = value;
            input.addEventListener('input', () => saveListField(recordId, fieldName));
            const btn = document.createElement('button');
            btn.className = 'remove-btn';
            btn.textContent = 'X';
            btn.addEventListener('click', () => {{ div.remove(); saveListField(recordId, fieldName); }});
            div.appendChild(input);
            div.appendChild(btn);
            return div;
        }}

        function restoreListFieldValues(recordId, fieldName, values) {{
            // Rebuild a list field from saved edits so refreshing the page
            // shows the archivist's edited values, not the original AI values.
            const container = document.getElementById(fieldName + '-' + recordId);
            if (!container || !Array.isArray(values)) return;
            container.innerHTML = '';
            values.forEach(v => container.appendChild(buildListItemRow(recordId, fieldName, v)));
            const group = container.closest('.field-group');
            if (group) group.classList.add('edited');
        }}

        function buildContributorRow(recordId, name, role) {{
            const div = document.createElement('div');
            div.className = 'contributor-item';
            const nameInput = document.createElement('input');
            nameInput.type = 'text';
            nameInput.className = 'field-input contrib-name';
            nameInput.placeholder = 'Name';
            nameInput.style.flex = '1';
            nameInput.value = name;
            nameInput.addEventListener('input', () => saveContributors(recordId));
            const roleInput = document.createElement('input');
            roleInput.type = 'text';
            roleInput.className = 'field-input contrib-role';
            roleInput.placeholder = 'Role';
            roleInput.style.width = '150px';
            roleInput.style.flexShrink = '0';
            roleInput.value = role;
            roleInput.addEventListener('input', () => saveContributors(recordId));
            const btn = document.createElement('button');
            btn.className = 'remove-btn';
            btn.textContent = 'X';
            btn.addEventListener('click', () => {{ div.remove(); saveContributors(recordId); }});
            div.appendChild(nameInput);
            div.appendChild(roleInput);
            div.appendChild(btn);
            return div;
        }}

        function restoreContributorValues(recordId, contributors) {{
            const container = document.getElementById('contributors-' + recordId);
            if (!container || !Array.isArray(contributors)) return;
            container.innerHTML = '';
            contributors.forEach(c => container.appendChild(buildContributorRow(recordId, c.name || '', c.role || '')));
            const group = container.closest('.field-group');
            if (group) group.classList.add('edited');
        }}

        function setTermStatus(recordId, termId, status, isCascade = false) {{
            const termDecisions = getStorage('terms-' + recordId, {{}});

            // Store the status with cascade info if applicable
            if (isCascade) {{
                termDecisions[termId] = {{ status: 'cascade_rejected', cascadeFrom: status }};
            }} else {{
                termDecisions[termId] = status;
            }}
            setStorage('terms-' + recordId, termDecisions);

            const termEl = document.getElementById('term-' + recordId + '-' + termId);
            if (termEl) {{
                termEl.classList.remove('approved', 'rejected', 'pending', 'cascade-rejected');

                if (isCascade) {{
                    termEl.classList.add('cascade-rejected');
                    // Show cascade indicator
                    const cascadeIndicator = termEl.querySelector('.cascade-indicator');
                    if (cascadeIndicator) cascadeIndicator.style.display = 'inline';
                }} else {{
                    termEl.classList.add(status);
                    // Hide cascade indicator
                    const cascadeIndicator = termEl.querySelector('.cascade-indicator');
                    if (cascadeIndicator) cascadeIndicator.style.display = 'none';
                }}

                // Show/hide appropriate buttons based on status
                const rejectBtn = termEl.querySelector('.term-btn.reject');
                const approveBtn = termEl.querySelector('.term-btn.approve');

                if (status === 'rejected' || isCascade) {{
                    // Show Restore button, hide Reject button
                    if (rejectBtn) rejectBtn.style.display = 'none';
                    if (approveBtn) {{
                        approveBtn.style.display = 'inline-block';
                        approveBtn.textContent = 'Restore';
                    }}
                }} else if (status === 'approved') {{
                    // For default-approved items, show Reject, hide Restore
                    const defaultStatus = termEl.dataset.default;
                    if (defaultStatus === 'approved') {{
                        if (rejectBtn) rejectBtn.style.display = 'inline-block';
                        if (approveBtn) approveBtn.style.display = 'none';
                    }} else {{
                        // For opt-in items (other choices), show both
                        if (rejectBtn) {{
                            rejectBtn.style.display = 'inline-block';
                            rejectBtn.textContent = 'Remove';
                        }}
                        if (approveBtn) approveBtn.style.display = 'none';
                    }}
                }}
            }}
            autoMarkReviewed(recordId);
            updateRecordStatus(recordId);
        }}

        function rejectTopicWithCascade(recordId, topicTermId, topicText) {{
            // First, reject the topic itself
            setTermStatus(recordId, topicTermId, 'rejected');

            // Then, cascade-reject all subject headings derived from this topic
            const record = document.getElementById('record-' + recordId);
            if (!record) return;

            const derivedHeadings = record.querySelectorAll('.vocab-term[data-derived-from="' + CSS.escape(topicText) + '"]');
            derivedHeadings.forEach(headingEl => {{
                const headingTermId = headingEl.id.replace('term-' + recordId + '-', '');
                // Mark as cascade-rejected (not explicitly rejected)
                setTermStatus(recordId, headingTermId, topicText, true);
            }});

            // Store the cascade rejection mapping
            const cascadeMap = getStorage('cascade-rejections-' + recordId, {{}});
            cascadeMap[topicText] = derivedHeadings.length;
            setStorage('cascade-rejections-' + recordId, cascadeMap);
        }}

        function restoreTopicWithCascade(recordId, topicTermId, topicText) {{
            // First, restore the topic itself
            setTermStatus(recordId, topicTermId, 'approved');

            // Then, restore all subject headings that were cascade-rejected from this topic
            const record = document.getElementById('record-' + recordId);
            if (!record) return;

            const termDecisions = getStorage('terms-' + recordId, {{}});
            const derivedHeadings = record.querySelectorAll('.vocab-term[data-derived-from="' + CSS.escape(topicText) + '"]');

            derivedHeadings.forEach(headingEl => {{
                const headingTermId = headingEl.id.replace('term-' + recordId + '-', '');
                const decision = termDecisions[headingTermId];

                // Only restore if it was cascade-rejected from this specific topic
                // (not if the user explicitly rejected it)
                if (decision && typeof decision === 'object' && decision.status === 'cascade_rejected' && decision.cascadeFrom === topicText) {{
                    setTermStatus(recordId, headingTermId, 'approved');
                }}
            }});

            // Remove from cascade rejection mapping
            const cascadeMap = getStorage('cascade-rejections-' + recordId, {{}});
            delete cascadeMap[topicText];
            setStorage('cascade-rejections-' + recordId, cascadeMap);
        }}

        function acceptAllSelected(recordId) {{
            // Accept all selected vocabulary terms for this record
            const record = document.getElementById('record-' + recordId);
            if (!record) return;

            const selectedTerms = record.querySelectorAll('.vocab-term[data-group="selected"]');
            selectedTerms.forEach(termEl => {{
                const termId = termEl.id.replace('term-' + recordId + '-', '');
                setTermStatus(recordId, termId, 'approved');
            }});

            // Also accept all AI topics
            const subjectTerms = record.querySelectorAll('.vocab-term[data-default="approved"]:not([data-group])');
            subjectTerms.forEach(termEl => {{
                const termId = termEl.id.replace('term-' + recordId + '-', '');
                setTermStatus(recordId, termId, 'approved');
            }});
        }}

        function addNewTopic(recordId) {{
            const input = document.getElementById('new-topic-' + recordId);
            const subject = input.value.trim();

            if (!subject) {{
                alert('Please enter a topic');
                return;
            }}

            // Store in custom topics
            const customSubjects = getStorage('custom-topics-' + recordId, []);
            const subjectId = 'newtopic-' + Date.now();
            const topic = {{ id: subjectId, label: subject }};
            customSubjects.push(topic);
            setStorage('custom-topics-' + recordId, customSubjects);

            renderCustomTopic(recordId, topic);

            input.value = '';
            autoMarkReviewed(recordId);
            updateRecordStatus(recordId);
        }}

        function renderCustomTopic(recordId, topic) {{
            const input = document.getElementById('new-topic-' + recordId);
            if (!input) return;
            const addForm = input.closest('.add-topic-form');
            if (!addForm || document.getElementById('term-' + recordId + '-' + topic.id)) return;
            const div = document.createElement('div');
            div.className = 'vocab-term approved';
            div.id = 'term-' + recordId + '-' + topic.id;
            div.dataset.default = 'approved';
            div.dataset.category = 'topic';
            const label = document.createElement('span');
            label.className = 'vocab-term-label';
            label.textContent = topic.label;
            const source = document.createElement('span');
            source.className = 'vocab-term-source';
            source.textContent = 'Manual';
            const actions = document.createElement('div');
            actions.className = 'term-actions';
            const btn = document.createElement('button');
            btn.className = 'term-btn reject';
            btn.textContent = 'Remove';
            btn.addEventListener('click', () => removeCustomTopic(recordId, topic.id));
            actions.appendChild(btn);
            div.appendChild(label);
            div.appendChild(source);
            div.appendChild(actions);
            addForm.insertAdjacentElement('beforebegin', div);
        }}

        function removeCustomTopic(recordId, subjectId) {{
            let customSubjects = getStorage('custom-topics-' + recordId, []);
            customSubjects = customSubjects.filter(s => s.id !== subjectId);
            setStorage('custom-topics-' + recordId, customSubjects);

            const subjectEl = document.getElementById('term-' + recordId + '-' + subjectId);
            if (subjectEl) subjectEl.remove();
            updateRecordStatus(recordId);
        }}

        function addCustomTerm(recordId) {{
            const labelInput = document.getElementById('new-term-label-' + recordId);
            const uriInput = document.getElementById('new-term-uri-' + recordId);
            const sourceSelect = document.getElementById('new-term-source-' + recordId);

            const label = labelInput.value.trim();
            const uri = uriInput.value.trim();
            const source = sourceSelect.value;

            if (!label) {{
                alert('Please enter a term label');
                return;
            }}

            const customTerms = getStorage('custom-terms-' + recordId, []);
            const termId = 'custom-' + Date.now();
            const term = {{ id: termId, label, source, uri }};
            customTerms.push(term);
            setStorage('custom-terms-' + recordId, customTerms);

            renderCustomTerm(recordId, term);

            labelInput.value = '';
            uriInput.value = '';
            autoMarkReviewed(recordId);
            updateRecordStatus(recordId);
        }}

        function renderCustomTerm(recordId, term) {{
            const container = document.getElementById('custom-terms-container-' + recordId);
            if (!container) return;
            const uriDisplay = term.uri ? `<a href="${{term.uri}}" target="_blank" class="term-uri" title="${{term.uri}}">link</a>` : '';
            container.insertAdjacentHTML('beforeend', `
                <div class="vocab-term approved" id="term-${{recordId}}-${{term.id}}">
                    <span class="vocab-term-label">${{term.label}}</span>
                    ${{uriDisplay}}
                    <span class="vocab-term-source">${{term.source}}</span>
                    <div class="term-actions">
                        <button class="term-btn reject" onclick="removeCustomTerm(${{recordId}}, '${{term.id}}')">Remove</button>
                    </div>
                </div>
            `);
        }}

        function renderCustomMediumTerm(recordId, term) {{
            const container = document.getElementById('custom-medium-terms-container-' + recordId);
            if (!container) return;
            const uriDisplay = term.uri ? `<a href="${{term.uri}}" target="_blank" class="term-uri" title="${{term.uri}}">URI</a>` : '';
            container.insertAdjacentHTML('beforeend', `
                <div class="vocab-term approved" id="term-${{recordId}}-${{term.id}}">
                    <span class="vocab-term-label">${{term.label}}</span>
                    ${{uriDisplay}}
                    <span class="vocab-term-source aat">${{term.source}}</span>
                    <div class="term-actions">
                        <button class="term-btn reject" onclick="removeCustomMediumTerm(${{recordId}}, '${{term.id}}')">Remove</button>
                    </div>
                </div>
            `);
        }}

        function expandSection(contentId) {{
            const content = document.getElementById(contentId);
            if (!content) return;
            content.style.display = 'block';
            const toggle = content.previousElementSibling;
            const chevron = toggle ? toggle.querySelector('.chevron') : null;
            if (chevron) chevron.classList.add('open');
        }}

        function removeCustomTerm(recordId, termId) {{
            let customTerms = getStorage('custom-terms-' + recordId, []);
            customTerms = customTerms.filter(t => t.id !== termId);
            setStorage('custom-terms-' + recordId, customTerms);

            const termEl = document.getElementById('term-' + recordId + '-' + termId);
            if (termEl) termEl.remove();
            updateRecordStatus(recordId);
        }}

        function addCustomMediumTerm(recordId) {{
            const labelInput = document.getElementById('new-medium-label-' + recordId);
            const uriInput   = document.getElementById('new-medium-uri-' + recordId);
            const sourceSelect = document.getElementById('new-medium-source-' + recordId);

            const label  = labelInput.value.trim();
            const uri    = uriInput.value.trim();
            const source = sourceSelect.value;

            if (!label) {{
                alert('Please enter a term label');
                return;
            }}

            const customMediumTerms = getStorage('custom-medium-terms-' + recordId, []);
            const termId = 'medium-custom-' + Date.now();
            const term = {{ id: termId, label, source, uri }};
            customMediumTerms.push(term);
            setStorage('custom-medium-terms-' + recordId, customMediumTerms);

            renderCustomMediumTerm(recordId, term);

            labelInput.value = '';
            uriInput.value   = '';
            autoMarkReviewed(recordId);
            updateRecordStatus(recordId);
        }}

        function removeCustomMediumTerm(recordId, termId) {{
            let customMediumTerms = getStorage('custom-medium-terms-' + recordId, []);
            customMediumTerms = customMediumTerms.filter(t => t.id !== termId);
            setStorage('custom-medium-terms-' + recordId, customMediumTerms);

            const termEl = document.getElementById('term-' + recordId + '-' + termId);
            if (termEl) termEl.remove();
            updateRecordStatus(recordId);
        }}

        function updateProgress() {{
            const totalRecords = parseInt(document.body.dataset.totalRecords || '0');
            let reviewed = 0;

            for (let i = 1; i <= totalRecords; i++) {{
                if (getStorage('reviewed-' + i, false)) reviewed++;
            }}

            const progressFill = document.getElementById('progress-fill');
            const progressText = document.getElementById('progress-text');

            if (progressFill) {{
                const pct = totalRecords > 0 ? (reviewed / totalRecords * 100) : 0;
                progressFill.style.width = pct + '%';
            }}
            if (progressText) {{
                progressText.textContent = reviewed + ' / ' + totalRecords + ' reviewed';
            }}
        }}

        function storeOriginalListValues(recordId) {{
            // Store original values for list fields (for tracking deletions)
            const listFields = ['named_entities', 'geographic_entities'];
            listFields.forEach(fieldName => {{
                const storageKey = 'original-' + fieldName + '-' + recordId;
                if (getStorage(storageKey, null) === null) {{
                    const container = document.getElementById(fieldName + '-' + recordId);
                    if (container) {{
                        const items = container.querySelectorAll('.list-item input');
                        const values = [];
                        items.forEach(input => {{
                            const val = input.value.trim();
                            if (val) values.push(val);
                        }});
                        setStorage(storageKey, values);
                    }}
                }}
            }});

            // Store original contributors
            const contribKey = 'original-contributors-' + recordId;
            if (getStorage(contribKey, null) === null) {{
                const container = document.getElementById('contributors-' + recordId);
                if (container) {{
                    const items = container.querySelectorAll('.contributor-item');
                    const contributors = [];
                    items.forEach(item => {{
                        const name = item.querySelector('.contrib-name').value.trim();
                        const role = item.querySelector('.contrib-role').value.trim();
                        if (name) {{
                            contributors.push({{ name, role }});
                        }}
                    }});
                    setStorage(contribKey, contributors);
                }}
            }}

            // Store original values for text/textarea fields (for tracking edits including deletions)
            const textFields = ['title', 'genre', 'description', 'date_on_drawing', 'sheet_info', 'content_warning'];
            textFields.forEach(fieldName => {{
                const storageKey = 'original-field-' + fieldName + '-' + recordId;
                if (getStorage(storageKey, null) === null) {{
                    const input = document.getElementById('field-' + recordId + '-' + fieldName);
                    if (input) {{
                        // Store the actual value from the input/textarea element
                        setStorage(storageKey, input.value);
                    }}
                }}
            }});
        }}

        function restoreState() {{
            // Prompt for reviewer name on first load
            promptForReviewerName();

            // Restore edits, reviewed status, term decisions for all records on this page
            document.querySelectorAll('.record').forEach(record => {{
                const recordId = parseInt(record.id.replace('record-', ''));

                // Store record data (image path, page number) for the export
                setStorage('record-data-' + recordId, {{
                    image_path: record.dataset.imagePath || '',
                    page_number: parseInt(record.dataset.pageNumber || recordId, 10)
                }});

                // Store original values for list fields FIRST (before any edits are restored)
                storeOriginalListValues(recordId);

                // Restore field edits
                const edits = getStorage('edits-' + recordId, {{}});
                for (const [field, data] of Object.entries(edits)) {{
                    if (field === 'contributors') {{
                        restoreContributorValues(recordId, data.value);
                        continue;
                    }}
                    if (field === 'named_entities' || field === 'geographic_entities') {{
                        restoreListFieldValues(recordId, field, data.value);
                        continue;
                    }}
                    if (field === 'topics') {{
                        continue;
                    }}
                    const input = document.getElementById('field-' + recordId + '-' + field);
                    if (input && data.value !== undefined) {{
                        input.value = data.value;
                        updateFieldStyle(recordId, field, true);
                    }}
                }}

                // Restore reviewed checkbox
                const reviewedCheckbox = document.getElementById('reviewed-' + recordId);
                if (reviewedCheckbox) {{
                    reviewedCheckbox.checked = getStorage('reviewed-' + recordId, false);
                }}

                // Restore notes
                const notesField = document.getElementById('notes-' + recordId);
                const savedNotes = getStorage('notes-' + recordId, '');
                if (notesField && savedNotes) {{
                    notesField.value = savedNotes;
                }}

                // Restore term decisions and update button visibility
                const termDecisions = getStorage('terms-' + recordId, {{}});
                for (const [termId, decision] of Object.entries(termDecisions)) {{
                    const termEl = document.getElementById('term-' + recordId + '-' + termId);
                    if (termEl) {{
                        termEl.classList.remove('approved', 'rejected', 'pending', 'cascade-rejected');

                        // Handle both old format (string) and new format (object with cascade info)
                        let status;
                        let isCascade = false;
                        if (typeof decision === 'object' && decision.status === 'cascade_rejected') {{
                            status = 'cascade_rejected';
                            isCascade = true;
                            termEl.classList.add('cascade-rejected');
                            const cascadeIndicator = termEl.querySelector('.cascade-indicator');
                            if (cascadeIndicator) cascadeIndicator.style.display = 'inline';
                        }} else {{
                            status = decision;
                            termEl.classList.add(status);
                        }}

                        // Update button visibility
                        const rejectBtn = termEl.querySelector('.term-btn.reject');
                        const approveBtn = termEl.querySelector('.term-btn.approve');
                        const defaultStatus = termEl.dataset.default;

                        if (status === 'rejected' || isCascade) {{
                            if (rejectBtn) rejectBtn.style.display = 'none';
                            if (approveBtn) {{
                                approveBtn.style.display = 'inline-block';
                                approveBtn.textContent = 'Restore';
                            }}
                        }} else if (status === 'approved') {{
                            if (defaultStatus === 'approved') {{
                                if (rejectBtn) rejectBtn.style.display = 'inline-block';
                                if (approveBtn) approveBtn.style.display = 'none';
                            }} else {{
                                if (rejectBtn) {{
                                    rejectBtn.style.display = 'inline-block';
                                    rejectBtn.textContent = 'Remove';
                                }}
                                if (approveBtn) approveBtn.style.display = 'none';
                            }}
                        }}
                    }}
                }}

                // Re-render custom topics saved in previous sessions
                const savedCustomTopics = getStorage('custom-topics-' + recordId, []);
                savedCustomTopics.forEach(t => renderCustomTopic(recordId, t));

                // Re-render custom terms saved in previous sessions and
                // expand their collapsed form sections so they're visible
                const savedCustomTerms = getStorage('custom-terms-' + recordId, []);
                savedCustomTerms.forEach(t => renderCustomTerm(recordId, t));
                if (savedCustomTerms.length > 0) expandSection('custom-subject-form-content-' + recordId);

                const savedCustomMediumTerms = getStorage('custom-medium-terms-' + recordId, []);
                savedCustomMediumTerms.forEach(t => renderCustomMediumTerm(recordId, t));
                if (savedCustomMediumTerms.length > 0) expandSection('custom-medium-form-content-' + recordId);

                updateRecordStatus(recordId);
            }});

            updateProgress();
        }}

        function exportDecisions() {{
            const archivistName = getStorage('reviewer-name', null);
            if (!archivistName) {{
                showNameModal(() => exportDecisions());
                return;
            }}

            const totalRecords = parseInt(document.body.dataset.totalRecords || '0');
            const decisions = [];

            for (let i = 1; i <= totalRecords; i++) {{
                const edits = getStorage('edits-' + i, {{}});
                const reviewed = getStorage('reviewed-' + i, false);
                const notes = getStorage('notes-' + i, '');
                const termDecisions = getStorage('terms-' + i, {{}});
                const customTerms = getStorage('custom-terms-' + i, []);
                const customMediumTerms = getStorage('custom-medium-terms-' + i, []);
                const customTopics = getStorage('custom-topics-' + i, []);
                const recordData = getStorage('record-data-' + i, {{}});

                // Only include records that have been reviewed, edited, or annotated
                if (reviewed || Object.keys(edits).length > 0 || Object.keys(termDecisions).length > 0 || customTerms.length > 0 || customMediumTerms.length > 0 || customTopics.length > 0 || (notes && notes.trim())) {{
                    decisions.push({{
                        record_id: i,
                        image_path: recordData.image_path || '',
                        page_number: recordData.page_number || i,
                        reviewed: reviewed,
                        edits: edits,
                        term_decisions: termDecisions,
                        custom_terms: customTerms,
                        custom_medium_terms: customMediumTerms,
                        custom_topics: customTopics,
                        archivist_notes: notes
                    }});
                }}
            }}

            if (decisions.length === 0) {{
                alert('No records have been reviewed or edited yet.');
                return;
            }}

            const exportData = {{
                export_timestamp: new Date().toISOString(),
                workflow_folder: WORKFLOW_FOLDER,
                collection_name: COLLECTION_NAME,
                model_used: MODEL_USED,
                archivist_name: archivistName,
                total_records: totalRecords,
                reviewed_count: decisions.filter(d => d.reviewed).length,
                decisions: decisions
            }};

            // Build filename: collection_model_archivist_date.json
            const safeName = archivistName.replace(/[^\\w\\-]/g, '_');
            const safeCollection = COLLECTION_NAME.replace(/[^\\w\\-]/g, '_') || 'unknown';
            const safeModel = MODEL_USED.replace(/[^\\w\\-]/g, '_') || 'unknown';
            const dateStr = new Date().toISOString().split('T')[0];
            const filename = `${{safeCollection}}_${{safeModel}}_${{safeName}}_${{dateStr}}.json`;

            const blob = new Blob([JSON.stringify(exportData, null, 2)], {{ type: 'application/json' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            setTimeout(() => {{
                URL.revokeObjectURL(url);
                a.remove();
            }}, 100);

            alert('Exported ' + decisions.length + ' record decisions to:\\n' + filename);
        }}

        function toggleSection(contentId, toggleEl) {{
            const content = document.getElementById(contentId);
            if (!content) return;
            const chevron = toggleEl.querySelector('.chevron');
            const isHidden = content.style.display === 'none';
            content.style.display = isHidden ? 'block' : 'none';
            if (chevron) chevron.classList.toggle('open', isHidden);
        }}

        document.addEventListener('DOMContentLoaded', restoreState);
        """

    def generate_contributors_html(self, contributors, record_id, contributor_vocab_results=None):
        """Generate HTML for contributors list with optional FAST name authority URI links."""
        if contributor_vocab_results is None:
            contributor_vocab_results = {}

        html = f'<div id="contributors-{record_id}" class="list-field">'

        if contributors:
            for contrib in contributors:
                name_raw = contrib.get('name', '')
                role_raw = contrib.get('role', '')
                name = self.escape_html(name_raw)
                role = self.escape_html(role_raw)

                # Look up FAST name authority URI for this contributor
                vocab_terms = contributor_vocab_results.get(name_raw, [])
                uri_html = ''
                if vocab_terms:
                    term = vocab_terms[0]
                    uri = term.get('uri', '')
                    label = self.escape_html(term.get('label', ''))
                    if uri:
                        uri_html = f'<a href="{uri}" target="_blank" class="term-uri" title="{label} — {uri}">FAST</a>'

                html += f'''
                <div class="contributor-item">
                    <input type="text" class="field-input contrib-name" value="{name}" placeholder="Name" style="flex:1;" oninput="saveContributors({record_id})">
                    <input type="text" class="field-input contrib-role" value="{role}" placeholder="Role" style="width:150px;flex-shrink:0;" oninput="saveContributors({record_id})">
                    {uri_html}
                    <button class="remove-btn" onclick="this.parentElement.remove(); saveContributors({record_id})">X</button>
                </div>'''

        html += f'''
            </div>
            <button class="add-btn" onclick="addContributor({record_id})">+ Add Contributor</button>
        '''
        return html

    def generate_list_field_html(self, items, record_id, field_name, placeholder="Enter value..."):
        """Generate HTML for a list field (entities, subjects, etc.)."""
        html = f'<div id="{field_name}-{record_id}" class="list-field">'

        if items:
            for item in items:
                value = self.escape_html(item) if isinstance(item, str) else self.escape_html(str(item))
                html += f'''
                <div class="list-item">
                    <input type="text" class="field-input" value="{value}" placeholder="{placeholder}" oninput="saveListField({record_id}, '{field_name}')">
                    <button class="remove-btn" onclick="this.parentElement.remove(); saveListField({record_id}, '{field_name}')">X</button>
                </div>'''

        html += f'''
            </div>
            <button class="add-btn" onclick="addListItem({record_id}, '{field_name}')">+ Add Item</button>
        '''
        return html

    def generate_geographic_field_html(self, entities, record_id, geo_vocab_results=None):
        """Generate HTML for geographic entities list with FAST URI links when available."""
        if geo_vocab_results is None:
            geo_vocab_results = {}

        html = f'<div id="geographic_entities-{record_id}" class="list-field">'

        if entities:
            for entity in entities:
                entity_str = entity if isinstance(entity, str) else str(entity)
                value = self.escape_html(entity_str)

                vocab_terms = geo_vocab_results.get(entity_str, [])
                uri_html = ''
                if vocab_terms:
                    term = vocab_terms[0]
                    uri = term.get('uri', '')
                    label = self.escape_html(term.get('label', ''))
                    if uri:
                        uri_html = f'<a href="{uri}" target="_blank" class="term-uri" title="{label} — {uri}">FAST</a>'

                html += f'''
                <div class="list-item">
                    <input type="text" class="field-input" value="{value}" placeholder="Location..." oninput="saveListField({record_id}, \'geographic_entities\')">
                    {uri_html}
                    <button class="remove-btn" onclick="this.parentElement.remove(); saveListField({record_id}, \'geographic_entities\')">X</button>
                </div>'''

        html += f'''
            </div>
            <button class="add-btn" onclick="addListItem({record_id}, \'geographic_entities\')">+ Add Item</button>
        '''
        return html

    def generate_vocabulary_section(self, analysis, record_id):
        """Generate HTML for vocabulary term review section.

        Section order:
        1. TOPICS (AI-generated, no URIs) - auto-accepted, can reject or add new
        2. SUBJECT HEADINGS (controlled vocabulary with URIs):
           - Selected: auto-accepted, can reject
           - Other: opt-in only
        3. GENRE - editable genre field followed by its Getty AAT terms
        4. FORMAT/MEDIA (Getty AAT) - curated medium/support checklists

        Cascade rejection: When a topic is rejected, all subject headings derived
        from that topic are automatically cascade-rejected (shown visually).
        """
        html = '<div class="vocab-section">'

        # Build a mapping of topic text to index for cascade rejection tracking
        subjects = analysis.get('topics', [])
        subject_to_index = {subj: i for i, subj in enumerate(subjects)}

        # ==========================================
        # SECTION 1: TOPICS (AI-generated terms)
        # ==========================================
        html += '<div class="section-header">Topics</div>'
        html += '<p style="font-size: 12px; color: #666; margin: 5px 0 15px 0;">AI-generated topic terms. Rejecting a topic will also reject its derived subject headings below.</p>'

        html += '<div class="vocab-group headings-list">'
        html += f'''<div class="vocab-group-title" style="display: flex; justify-content: space-between; align-items: center;">
            <span>AI-Generated Topics <span style="font-weight: normal; font-size: 12px; color: #666;">(auto-accepted; reject if not applicable)</span></span>
        </div>'''
        if subjects:
            for i, subject in enumerate(subjects):
                term_id = f"topic-{i}"
                html += f'''
                <div class="vocab-term approved" id="term-{record_id}-{term_id}" data-default="approved" data-category="topic" data-topic-text="{self.escape_html(subject)}">
                    <span class="vocab-term-label">{self.escape_html(subject)}</span>
                    <span class="vocab-term-source">AI</span>
                    <div class="term-actions">
                        <button class="term-btn reject" onclick="rejectTopicWithCascade({record_id}, '{term_id}', '{self.escape_js_string(subject)}')">Reject</button>
                        <button class="term-btn approve" onclick="restoreTopicWithCascade({record_id}, '{term_id}', '{self.escape_js_string(subject)}')" style="display:none;">Restore</button>
                    </div>
                </div>'''
        else:
            html += '<p style="color: #999; font-style: italic;">No AI topics found</p>'

        # Add new topic form
        html += f'''
        <div class="add-topic-form" style="margin-top: 10px; padding-top: 10px; border-top: 1px dashed #ddd;">
            <div style="display: flex; gap: 10px; align-items: center;">
                <input type="text" id="new-topic-{record_id}" placeholder="Add new topic..." style="flex: 1; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                <button class="add-btn" onclick="addNewTopic({record_id})">+ Add Topic</button>
            </div>
        </div>
        '''
        html += '</div>'

        # ==========================================
        # SECTION 2: SUBJECT HEADINGS (controlled vocabulary)
        # ==========================================
        html += '<div class="section-header" style="margin-top: 25px;">Subject Headings</div>'
        html += '<p style="font-size: 12px; color: #666; margin: 5px 0 15px 0;">Controlled vocabulary terms (LCSH, FAST, Getty) with URIs/permalinks. Derived from topics above.</p>'

        # Selected Subject Headings - default to APPROVED (opt-out)
        final_terms = analysis.get('final_selected_terms', [])
        if final_terms:
            html += '<div class="vocab-group headings-list">'
            html += f'''<div class="vocab-group-title" style="display: flex; justify-content: space-between; align-items: center;">
                <span>Selected Subject Headings <span style="font-weight: normal; font-size: 12px; color: #666;">(auto-accepted; reject if not applicable)</span></span>
            </div>'''
            for i, term in enumerate(final_terms):
                term_id = f"selected-{i}"
                label = self.escape_html(term.get('label', ''))
                uri = term.get('uri', '')
                source = term.get('source', 'Unknown')
                source_class = source.lower().replace(' ', '').replace('getty', '')
                uri_html = f'<a href="{uri}" target="_blank" class="term-uri" title="{uri}">URI</a>' if uri else ''

                # Get the derived_from_topic for cascade rejection tracking
                derived_from = term.get('derived_from_topic', '')
                derived_from_escaped = self.escape_html(derived_from)
                derived_from_js = self.escape_js_string(derived_from)

                # Find the topic index for this heading
                subject_index = subject_to_index.get(derived_from, -1)
                derived_attr = f'data-derived-from="{derived_from_escaped}" data-derived-from-index="{subject_index}"' if derived_from else ''

                # Show which topic this heading was derived from
                derived_badge = f'<span class="derived-from-badge" title="Derived from topic: {derived_from_escaped}">from: {derived_from_escaped[:20]}{"..." if len(derived_from) > 20 else ""}</span>' if derived_from else ''

                html += f'''
                <div class="vocab-term approved" id="term-{record_id}-{term_id}" data-default="approved" data-group="selected" data-category="heading" {derived_attr}>
                    <span class="vocab-term-label">{label}</span>
                    {derived_badge}
                    {uri_html}
                    <span class="vocab-term-source {source_class}">{source}</span>
                    <div class="term-actions">
                        <button class="term-btn reject" onclick="setTermStatus({record_id}, '{term_id}', 'rejected')">Reject</button>
                        <button class="term-btn approve" onclick="setTermStatus({record_id}, '{term_id}', 'approved')" style="display:none;">Restore</button>
                    </div>
                    <span class="cascade-indicator" style="display:none; font-size: 11px; color: #dc3545; margin-left: 10px;">(auto-rejected: parent topic rejected)</span>
                </div>'''
            html += '</div>'
        else:
            html += '<div class="vocab-group"><p style="color: #999; font-style: italic;">No selected subject headings</p></div>'

        # Other Subject Headings - opt-IN (not selected by default)
        vocab_results = analysis.get('vocabulary_search_results', {})
        if vocab_results:
            # Get the labels of final selected terms to exclude them from "other choices"
            selected_labels = set()
            for term in final_terms:
                selected_labels.add(term.get('label', '').lower())

            # Group by source
            sources = {'LCSH': [], 'FAST': [], 'Getty AAT': [], 'Getty TGN': []}

            for orig_term, matches in vocab_results.items():
                for match in matches:
                    source = match.get('source', 'Unknown')
                    label = match.get('label', '')
                    # Skip if this term was already selected
                    if label.lower() in selected_labels:
                        continue
                    if source in sources:
                        sources[source].append({
                            'orig_term': orig_term,
                            'label': label,
                            'uri': match.get('uri', ''),
                            'source': source
                        })

            # Check if there are any "other choices" to show
            has_other_choices = any(len(terms) > 0 for terms in sources.values())

            if has_other_choices:
                total_other_count = sum(len(t) for t in sources.values())
                other_content_id = f"other-subjects-content-{record_id}"
                html += f'''<div class="collapsible-toggle" onclick="toggleSection('{other_content_id}', this)" role="button">
                    <span class="toggle-label">Alternative Subject Headings - click to expand</span>
                    <span class="term-count-badge">{total_other_count} available from vocabulary search</span>
                    <span class="chevron">&#9660;</span>
                </div>
                <div class="collapsible-content" id="{other_content_id}" style="display:none;">
                <div class="vocab-group" style="border: 1px dashed #ccc; border-top: none; border-radius: 0 0 5px 5px; margin-top: 0; padding-top: 8px;">
                <p style="font-size: 12px; color: #666; margin: 0 0 10px 0;">Not selected — click Add to include any of these terms.</p>
                <div class="other-terms-grid">'''

                for source_name, terms in sources.items():
                    if not terms:
                        continue

                    source_class = source_name.lower().replace(' ', '').replace('getty', '')

                    for i, term in enumerate(terms):
                        term_id = f"other-{source_class}-{i}"
                        label = self.escape_html(term['label'])
                        uri = term.get('uri', '')
                        uri_html = f'<a href="{uri}" target="_blank" class="term-uri" title="{uri}">URI</a>' if uri else ''
                        html += f'''
                        <div class="vocab-term" id="term-{record_id}-{term_id}" data-default="none" data-group="other" data-category="heading">
                            <div class="card-header">
                                <span class="vocab-term-label">{label}</span>
                                <div class="card-badges">
                                    {uri_html}
                                    <span class="vocab-term-source {source_class}">{source_name}</span>
                                </div>
                            </div>
                            <div class="term-actions">
                                <button class="term-btn approve" onclick="setTermStatus({record_id}, '{term_id}', 'approved')">Add</button>
                                <button class="term-btn reject" onclick="setTermStatus({record_id}, '{term_id}', 'rejected')" style="display:none;">Remove</button>
                            </div>
                        </div>'''

                html += '</div></div></div>'

        # ==========================================
        # SECTION 3: GENRE (editable field + Getty AAT vocabulary)
        # ==========================================
        html += '<div class="section-header" style="margin-top: 25px;">Genre</div>'
        genre_value = self.escape_html(analysis.get('genre', ''))
        html += f'''
        <div class="field-group" style="margin: 10px 0 15px 0;">
            <div class="field-label">Genre <span class="edit-indicator"></span></div>
            <input type="text" class="field-input"
                id="field-{record_id}-genre"
                value="{genre_value}"
                oninput="saveFieldValue({record_id}, 'genre', this.value)">
        </div>'''
        html += '<p style="font-size: 12px; color: #666; margin: 5px 0 15px 0;">Official Getty AAT terms for the drawing type/genre. Derived from the Genre field above.</p>'

        final_genre_terms = analysis.get('final_selected_genre_terms', [])
        if final_genre_terms:
            html += '<div class="vocab-group">'
            html += f'''<div class="vocab-group-title" style="display: flex; justify-content: space-between; align-items: center;">
                <span>Selected Genre Terms <span style="font-weight: normal; font-size: 12px; color: #666;">(auto-accepted; reject if not applicable)</span></span>
            </div>'''
            for i, term in enumerate(final_genre_terms):
                term_id = f"genre-selected-{i}"
                label = self.escape_html(term.get('label', ''))
                uri = term.get('uri', '')
                source = term.get('source', 'Unknown')
                source_class = source.lower().replace(' ', '').replace('getty', '')
                uri_html = f'<a href="{uri}" target="_blank" class="term-uri" title="{uri}">URI</a>' if uri else ''
                derived_from = term.get('derived_from_topic', '')
                derived_badge = f'<span class="derived-from-badge" title="Derived from: {self.escape_html(derived_from)}">{self.escape_html(derived_from[:25])}{"..." if len(derived_from) > 25 else ""}</span>' if derived_from else ''
                html += f'''
                <div class="vocab-term approved" id="term-{record_id}-{term_id}" data-default="approved" data-group="genre-selected" data-category="genre-term">
                    <span class="vocab-term-label">{label}</span>
                    {derived_badge}
                    {uri_html}
                    <span class="vocab-term-source {source_class}">{source}</span>
                    <div class="term-actions">
                        <button class="term-btn reject" onclick="setTermStatus({record_id}, '{term_id}', 'rejected')">Reject</button>
                        <button class="term-btn approve" onclick="setTermStatus({record_id}, '{term_id}', 'approved')" style="display:none;">Restore</button>
                    </div>
                </div>'''
            html += '</div>'
        else:
            html += '<div class="vocab-group"><p style="color: #999; font-style: italic;">No Genre vocabulary terms selected</p></div>'

        # Other Genre terms - opt-IN
        genre_vocab_results = analysis.get('genre_vocabulary_search_results', {})
        if genre_vocab_results:
            selected_genre_labels = set(t.get('label', '').lower() for t in final_genre_terms)
            other_genre_terms = []
            for topic, terms in genre_vocab_results.items():
                for term in terms:
                    label = term.get('label', '')
                    if label.lower() not in selected_genre_labels:
                        other_genre_terms.append({
                            'topic': topic,
                            'label': label,
                            'uri': term.get('uri', ''),
                            'source': term.get('source', 'Getty AAT')
                        })

            if other_genre_terms:
                other_genre_content_id = f"other-genre-content-{record_id}"
                html += f'''<div class="collapsible-toggle" onclick="toggleSection('{other_genre_content_id}', this)" role="button">
                    <span class="toggle-label">Alternative Genre Options - click to expand</span>
                    <span class="term-count-badge">{len(other_genre_terms)} available from vocabulary search</span>
                    <span class="chevron">&#9660;</span>
                </div>
                <div class="collapsible-content" id="{other_genre_content_id}" style="display:none;">
                <div class="vocab-group" style="border: 1px dashed #ccc; border-top: none; border-radius: 0 0 5px 5px; margin-top: 0; padding-top: 8px;">
                <p style="font-size: 12px; color: #666; margin: 0 0 10px 0;">Not selected — click Add to include any of these terms.</p>
                <div class="other-terms-grid">'''
                for i, term in enumerate(other_genre_terms):
                    term_id = f"genre-other-{i}"
                    label = self.escape_html(term['label'])
                    uri = term.get('uri', '')
                    source = term.get('source', 'Getty AAT')
                    source_class = source.lower().replace(' ', '').replace('getty', '')
                    uri_html = f'<a href="{uri}" target="_blank" class="term-uri" title="{uri}">URI</a>' if uri else ''
                    html += f'''
                    <div class="vocab-term" id="term-{record_id}-{term_id}" data-default="none" data-group="genre-other" data-category="genre-term">
                        <div class="card-header">
                            <span class="vocab-term-label">{label}</span>
                            <div class="card-badges">
                                {uri_html}
                                <span class="vocab-term-source {source_class}">{source}</span>
                            </div>
                        </div>
                        <div class="term-actions">
                            <button class="term-btn approve" onclick="setTermStatus({record_id}, '{term_id}', 'approved')">Add</button>
                            <button class="term-btn reject" onclick="setTermStatus({record_id}, '{term_id}', 'rejected')" style="display:none;">Remove</button>
                        </div>
                    </div>'''
                html += '</div></div></div>'

        # ==========================================
        # SECTION 4: CHRONOLOGICAL TERMS (FAST)
        # ==========================================
        html += '<div class="section-header" style="margin-top: 25px;">Chronological Terms</div>'
        html += '<p style="font-size: 12px; color: #666; margin: 5px 0 15px 0;">FAST chronological terms generated automatically from the Date on Drawing field.</p>'

        chrono_terms = analysis.get('chronological_vocabulary_terms', [])
        if chrono_terms:
            html += '<div class="vocab-group">'
            html += '''<div class="vocab-group-title">Selected Chronological Terms <span style="font-weight: normal; font-size: 12px; color: #666;">(auto-accepted; reject if not applicable)</span></div>'''
            for i, term in enumerate(chrono_terms):
                term_id = f"chrono-selected-{i}"
                label = self.escape_html(term.get('label', ''))
                uri = term.get('uri', '')
                source = term.get('source', 'FAST Chronological')
                uri_html = f'<a href="{uri}" target="_blank" class="term-uri" title="{uri}">URI</a>' if uri else ''
                html += f'''
                <div class="vocab-term approved" id="term-{record_id}-{term_id}" data-default="approved" data-group="chrono-selected" data-category="chrono-term">
                    <span class="vocab-term-label">{label}</span>
                    {uri_html}
                    <span class="vocab-term-source fast">{source}</span>
                    <div class="term-actions">
                        <button class="term-btn reject" onclick="setTermStatus({record_id}, '{term_id}', 'rejected')">Reject</button>
                        <button class="term-btn approve" onclick="setTermStatus({record_id}, '{term_id}', 'approved')" style="display:none;">Restore</button>
                    </div>
                </div>'''
            html += '</div>'
        else:
            html += '<div class="vocab-group"><p style="color: #999; font-style: italic;">No chronological terms (no date found on drawing)</p></div>'

        # ==========================================
        # SECTION 5: FORMAT/MEDIA VOCABULARY (Getty AAT)
        # ==========================================
        html += '<div class="section-header" style="margin-top: 25px;">Format/Media Vocabulary (Getty AAT)</div>'
        html += '<p style="font-size: 12px; color: #666; margin: 5px 0 15px 0;">Select all Getty AAT terms that apply to this drawing\'s medium and support. URIs link to the official Getty AAT record.</p>'

        # --- Medium (drawing materials) ---
        medium_content_id = f"medium-terms-content-{record_id}"
        html += f'''<div class="collapsible-toggle" onclick="toggleSection('{medium_content_id}', this)" role="button">
            <span class="toggle-label">Medium - click to expand</span>
            <span class="term-count-badge">{len(MEDIUM_TERMS)} drawing/inscribing/coloring materials</span>
            <span class="chevron">&#9660;</span>
        </div>
        <div class="collapsible-content" id="{medium_content_id}" style="display:none;">
        <div class="vocab-group" style="border: 1px dashed #ccc; border-top: none; border-radius: 0 0 5px 5px; margin-top: 0; padding-top: 8px;">
        <p style="font-size: 12px; color: #666; margin: 0 0 10px 0;">Click Add to select all medium terms that apply.</p>'''
        html += '<div class="other-terms-grid">'
        for i, term in enumerate(MEDIUM_TERMS):
            term_id = f"medium-curated-{i}"
            label = self.escape_html(term.get('label', ''))
            uri = term.get('uri', '')
            uri_html = f'<a href="{uri}" target="_blank" class="term-uri" title="{uri}">URI</a>' if uri else ''
            html += f'''
            <div class="vocab-term" id="term-{record_id}-{term_id}" data-default="none" data-group="medium-curated" data-category="medium-term">
                <div class="card-header">
                    <span class="vocab-term-label">{label}</span>
                    <div class="card-badges">
                        {uri_html}
                        <span class="vocab-term-source aat">Getty AAT</span>
                    </div>
                </div>
                <div class="term-actions">
                    <button class="term-btn approve" onclick="setTermStatus({record_id}, '{term_id}', 'approved')">Add</button>
                    <button class="term-btn reject" onclick="setTermStatus({record_id}, '{term_id}', 'rejected')" style="display:none;">Remove</button>
                </div>
            </div>'''
        html += '</div></div></div>'

        # --- Support (base/carrier material) ---
        support_content_id = f"support-terms-content-{record_id}"
        html += f'''<div class="collapsible-toggle" onclick="toggleSection('{support_content_id}', this)" role="button" style="margin-top: 12px;">
            <span class="toggle-label">Support - click to expand</span>
            <span class="term-count-badge">{len(SUPPORT_TERMS)} base/carrier materials</span>
            <span class="chevron">&#9660;</span>
        </div>
        <div class="collapsible-content" id="{support_content_id}" style="display:none;">
        <div class="vocab-group" style="border: 1px dashed #ccc; border-top: none; border-radius: 0 0 5px 5px; margin-top: 0; padding-top: 8px;">
        <p style="font-size: 12px; color: #666; margin: 0 0 10px 0;">Click Add to select all support terms that apply.</p>'''
        html += '<div class="other-terms-grid">'
        for i, term in enumerate(SUPPORT_TERMS):
            term_id = f"support-curated-{i}"
            label = self.escape_html(term.get('label', ''))
            uri = term.get('uri', '')
            uri_html = f'<a href="{uri}" target="_blank" class="term-uri" title="{uri}">URI</a>' if uri else ''
            html += f'''
            <div class="vocab-term" id="term-{record_id}-{term_id}" data-default="none" data-group="support-curated" data-category="medium-term">
                <div class="card-header">
                    <span class="vocab-term-label">{label}</span>
                    <div class="card-badges">
                        {uri_html}
                        <span class="vocab-term-source aat">Getty AAT</span>
                    </div>
                </div>
                <div class="term-actions">
                    <button class="term-btn approve" onclick="setTermStatus({record_id}, '{term_id}', 'approved')">Add</button>
                    <button class="term-btn reject" onclick="setTermStatus({record_id}, '{term_id}', 'rejected')" style="display:none;">Remove</button>
                </div>
            </div>'''
        html += '</div></div></div>'

        # ==========================================
        # SECTION 6: ADD CUSTOM TERMS (subject heading / format-media)
        # ==========================================
        html += '<div class="section-header" style="margin-top: 25px;">Add Custom Subject Heading or Format/Media Term</div>'

        # --- Custom subject heading form (collapsible) ---
        custom_subject_content_id = f"custom-subject-form-content-{record_id}"
        html += f'''<div class="collapsible-toggle" onclick="toggleSection('{custom_subject_content_id}', this)" role="button">
            <span class="toggle-label">Add Custom Subject Heading - click to expand</span>
            <span class="chevron">&#9660;</span>
        </div>
        <div class="collapsible-content" id="{custom_subject_content_id}" style="display:none;">
        <div class="vocab-group" style="border: 1px dashed #ccc; border-top: none; border-radius: 0 0 5px 5px; margin-top: 0; padding-top: 8px;">
            <div id="custom-terms-container-{record_id}"></div>
            <div class="add-term-form" style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px;">
                <div>
                    <label style="font-size: 12px; color: #666; display: block; margin-bottom: 3px;">Term Label *</label>
                    <input type="text" id="new-term-label-{record_id}" placeholder="e.g., Staircases" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                </div>
                <div>
                    <label style="font-size: 12px; color: #666; display: block; margin-bottom: 3px;">URI / Permalink (optional)</label>
                    <input type="text" id="new-term-uri-{record_id}" placeholder="e.g., http://id.loc.gov/authorities/subjects/sh85127265" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                </div>
                <div style="display: flex; gap: 10px; align-items: end;">
                    <div>
                        <label style="font-size: 12px; color: #666; display: block; margin-bottom: 3px;">Source</label>
                        <select id="new-term-source-{record_id}" style="padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                            <option value="LCSH">LCSH</option>
                            <option value="FAST">FAST</option>
                            <option value="Getty AAT">Getty AAT</option>
                            <option value="Manual">Manual/Other</option>
                        </select>
                    </div>
                    <button class="add-btn" onclick="addCustomTerm({record_id})" style="height: 38px;">Add Heading</button>
                </div>
            </div>
        </div>
        </div>'''

        # --- Custom Format/Media term form (collapsible) ---
        custom_medium_content_id = f"custom-medium-form-content-{record_id}"
        html += f'''<div class="collapsible-toggle" onclick="toggleSection('{custom_medium_content_id}', this)" role="button" style="margin-top: 12px;">
            <span class="toggle-label">Add Custom Format/Media Term - click to expand</span>
            <span class="chevron">&#9660;</span>
        </div>
        <div class="collapsible-content" id="{custom_medium_content_id}" style="display:none;">
        <div class="vocab-group" style="border: 1px dashed #ccc; border-top: none; border-radius: 0 0 5px 5px; margin-top: 0; padding-top: 8px;">
            <div id="custom-medium-terms-container-{record_id}"></div>
            <div class="add-term-form" style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px;">
                <div>
                    <label style="font-size: 12px; color: #666; display: block; margin-bottom: 3px;">Term Label *</label>
                    <input type="text" id="new-medium-label-{record_id}" placeholder="e.g., oil paint" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                </div>
                <div>
                    <label style="font-size: 12px; color: #666; display: block; margin-bottom: 3px;">Getty AAT URI (optional)</label>
                    <input type="text" id="new-medium-uri-{record_id}" placeholder="e.g., http://vocab.getty.edu/aat/300015050" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                </div>
                <div style="display: flex; gap: 10px; align-items: end;">
                    <div>
                        <label style="font-size: 12px; color: #666; display: block; margin-bottom: 3px;">Source</label>
                        <select id="new-medium-source-{record_id}" style="padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                            <option value="Getty AAT">Getty AAT</option>
                            <option value="Manual">Manual/Other</option>
                        </select>
                    </div>
                    <button class="add-btn" onclick="addCustomMediumTerm({record_id})" style="height: 38px;">Add Term</button>
                </div>
            </div>
        </div>
        </div>'''

        html += '</div>'
        return html

    def generate_record_html(self, record, global_id):
        """Generate HTML for a single record."""
        analysis = record.get('analysis', {})
        image_path = record.get('image_path', '')
        image_filename = os.path.basename(image_path)
        page_number = record.get('page_number', global_id)

        is_error_record = str(analysis.get('title', '')).startswith('Error:')

        error_class = ' error-record' if is_error_record else ''
        error_notice = f'<div class="error-notice">&#9888; This record failed during image analysis (API error). All fields are empty. Re-run Step 1.5 to reprocess this image: <code>{self.escape_html(image_filename)}</code></div>' if is_error_record else ''

        # Record data lives in data attributes; restoreState() copies it into
        # localStorage for the export (inline scripts here would run before the
        # main script block at the bottom of the page defines setStorage).
        html = f'''
        <div class="record{error_class}" id="record-{global_id}" data-image-path="{self.escape_html(image_path)}" data-page-number="{page_number}">
            {error_notice}
            <div class="record-header">
                <div class="record-title">Record {global_id}: {self.escape_html(analysis.get('title', 'Untitled'))}</div>
            </div>

            <div class="content-grid">
                <div class="image-section">
                    <div class="image-container">
                        <img src="images/{image_filename}"
                             alt="Drawing {global_id}"
                             onclick="window.open(this.src, '_blank')"
                             onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                        <div style="display: none; padding: 20px; color: #999;">Image not found</div>
                    </div>
                    <div class="image-filename">{image_filename}</div>
                </div>

                <div class="metadata-section">
                    <div class="section-header">Metadata Fields</div>
        '''

        # Text fields (genre is rendered in the vocabulary section, above its Getty AAT terms)
        fields = [
            ('title', 'Title', 'text'),
            ('description', 'Description', 'textarea-large'),
            ('date_on_drawing', 'Date on Drawing', 'text'),
            ('sheet_info', 'Sheet Info', 'textarea'),
            ('content_warning', 'Content Warning', 'text'),
        ]

        for field_name, label, field_type in fields:
            value = analysis.get(field_name, '')
            if field_name == 'content_warning' and (not value or str(value).strip().lower() in ('none', 'n/a')):
                continue
            escaped_value = self.escape_html(value)

            html += f'<div class="field-group">'
            html += f'<div class="field-label">{label} <span class="edit-indicator"></span></div>'

            if field_type == 'textarea' or field_type == 'textarea-large':
                large_class = ' large' if field_type == 'textarea-large' else ''
                html += f'''<textarea class="field-input{large_class}"
                    id="field-{global_id}-{field_name}"
                    oninput="saveFieldValue({global_id}, '{field_name}', this.value)">{escaped_value}</textarea>'''
            else:
                html += f'''<input type="text" class="field-input"
                    id="field-{global_id}-{field_name}"
                    value="{escaped_value}"
                    oninput="saveFieldValue({global_id}, '{field_name}', this.value)">'''

            html += '</div>'

        # Contributors
        html += '<div class="field-group">'
        html += '<div class="field-label">Contributors</div>'
        contributor_vocab_results = analysis.get('contributor_vocabulary_search_results', {})
        html += self.generate_contributors_html(analysis.get('contributors', []), global_id, contributor_vocab_results)
        html += '</div>'

        # Named Entities
        html += '<div class="field-group">'
        html += '<div class="field-label">Named Entities <span style="font-weight: normal; font-size: 12px; color: #666;">(buildings, clients, organizations, etc - not direct contributors)</span></div>'
        html += self.generate_list_field_html(analysis.get('named_entities', []), global_id, 'named_entities', 'Entity name...')
        html += '</div>'

        # Geographic Entities
        html += '<div class="field-group">'
        html += '<div class="field-label">Geographic Entities</div>'
        geo_vocab_results = analysis.get('geographic_vocabulary_search_results', {})
        html += self.generate_geographic_field_html(analysis.get('geographic_entities', []), global_id, geo_vocab_results)
        html += '</div>'

        # Close metadata section
        html += '</div></div>'

        # Vocabulary section (full width)
        html += self.generate_vocabulary_section(analysis, global_id)

        # Actions section
        html += f'''
            <div class="notes-section">
                <div class="field-label">Archivist Notes</div>
                <textarea class="field-input" id="notes-{global_id}"
                    placeholder="Add notes about this record..."
                    oninput="saveNotes({global_id}, this.value)"></textarea>
                <label class="reviewed-checkbox" style="margin-top: 10px;">
                    <input type="checkbox" id="reviewed-{global_id}" onchange="setReviewed({global_id}, this.checked)">
                    Reviewed
                </label>
            </div>
        </div>
        '''

        return html

    def create_index_page(self, total_pages):
        """Create the index page with navigation."""
        total_records = len(self.data_items)

        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Architectural Drawings Review - Index</title>
    <style>{self.get_css_styles()}</style>
</head>
<body data-total-records="{total_records}">
    <div class="header">
        <h1>Architectural Drawings Metadata Review</h1>
        <p>Workflow: {self.escape_html(self.folder_name)}</p>
        <p>Total Records: {total_records} | Pages: {total_pages}</p>
    </div>

    <div class="export-section">
        <h3>Progress</h3>
        <div class="progress-bar">
            <div class="progress-fill" id="progress-fill" style="width: 0%"></div>
        </div>
        <p id="progress-text">0 / {total_records} reviewed</p>

        <h3 style="margin-top: 20px;">Export Decisions</h3>
        <p>Export all reviewed records and edits to a JSON file for processing.</p>
        <button class="export-btn" onclick="exportDecisions()">Export All Decisions to JSON</button>
    </div>

    <div class="summary-grid">
        <div class="summary-card">
            <div class="number">{total_records}</div>
            <div class="label">Total Records</div>
        </div>
        <div class="summary-card">
            <div class="number">{total_pages}</div>
            <div class="label">Review Pages</div>
        </div>
        <div class="summary-card">
            <div class="number">{self.records_per_page}</div>
            <div class="label">Records per Page</div>
        </div>
    </div>

    <div class="export-section">
        <h3>Review Pages</h3>
        <p>Click a page to begin reviewing records.</p>
        <div class="page-links">'''

        for page_num in range(1, total_pages + 1):
            start_record = (page_num - 1) * self.records_per_page + 1
            end_record = min(page_num * self.records_per_page, total_records)
            html += f'''
            <a href="review-page-{page_num}.html" class="page-link">
                Page {page_num}<br>
                <small>Records {start_record}-{end_record}</small>
            </a>'''

        html += f'''
        </div>
    </div>

    <script>{self.get_javascript()}</script>
</body>
</html>'''

        index_path = os.path.join(self.review_folder, "review-index.html")
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"Created index page: review-index.html")
        return index_path

    def create_review_page(self, page_num, page_records, start_idx, total_pages):
        """Create a single review page."""
        total_records = len(self.data_items)

        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Review Page {page_num} - Architectural Drawings</title>
    <style>{self.get_css_styles()}</style>
</head>
<body data-total-records="{total_records}">
    <div class="header">
        <h1>Review Page {page_num} of {total_pages}</h1>
        <p>Records {start_idx + 1}-{start_idx + len(page_records)} of {total_records}</p>
    </div>

    <div class="navigation">
        <a href="review-index.html" class="nav-btn">Back to Index</a>'''

        if page_num > 1:
            html += f'<a href="review-page-{page_num - 1}.html" class="nav-btn">Previous</a>'
        else:
            html += '<span class="nav-btn disabled">Previous</span>'

        html += f'<span style="margin: 0 20px; font-weight: bold;">Page {page_num} of {total_pages}</span>'

        if page_num < total_pages:
            html += f'<a href="review-page-{page_num + 1}.html" class="nav-btn">Next</a>'
        else:
            html += '<span class="nav-btn disabled">Next</span>'

        html += '''
    </div>

    <div class="export-section" style="margin-bottom: 20px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <strong>Progress:</strong>
                <span id="progress-text">Loading...</span>
            </div>
            <button class="export-btn" onclick="exportDecisions()">Export All Decisions</button>
        </div>
        <div class="progress-bar" style="margin-top: 10px;">
            <div class="progress-fill" id="progress-fill" style="width: 0%"></div>
        </div>
    </div>
'''

        # Generate records
        for i, record in enumerate(page_records):
            global_id = start_idx + i + 1
            html += self.generate_record_html(record, global_id)

        # Navigation at bottom
        html += f'''
    <div class="navigation" style="margin-top: 20px;">
        <a href="review-index.html" class="nav-btn">Back to Index</a>'''

        if page_num > 1:
            html += f'<a href="review-page-{page_num - 1}.html" class="nav-btn">Previous</a>'
        else:
            html += '<span class="nav-btn disabled">Previous</span>'

        if page_num < total_pages:
            html += f'<a href="review-page-{page_num + 1}.html" class="nav-btn">Next</a>'
        else:
            html += '<span class="nav-btn disabled">Next</span>'

        html += f'''
    </div>

    <script>{self.get_javascript()}</script>
</body>
</html>'''

        page_path = os.path.join(self.review_folder, f"review-page-{page_num}.html")
        with open(page_path, 'w', encoding='utf-8') as f:
            f.write(html)

        return page_path

    def create_review_pages(self):
        """Create all paginated review pages."""
        total_records = len(self.data_items)
        total_pages = math.ceil(total_records / self.records_per_page)

        print(f"Creating {total_pages} review pages...")

        # Create index page
        self.create_index_page(total_pages)

        # Create individual pages
        for page_num in range(1, total_pages + 1):
            start_idx = (page_num - 1) * self.records_per_page
            end_idx = min(start_idx + self.records_per_page, total_records)
            page_records = self.data_items[start_idx:end_idx]

            self.create_review_page(page_num, page_records, start_idx, total_pages)
            print(f"  Created page {page_num}/{total_pages} with {len(page_records)} records")

        return total_pages

    def run(self):
        """Main execution method."""
        print("\n" + "=" * 60)
        print("Step 5: Creating HTML Review Interface")
        print("=" * 60)

        print(f"\nUsing folder: {self.folder_name}")

        # Load data
        if not self.load_json_data():
            return False

        if not self.data_items:
            print("No records found in workflow JSON")
            return False

        # Create folder structure
        if not self.create_review_folder():
            return False

        # Copy images
        self.copy_images()

        # Create HTML pages
        total_pages = self.create_review_pages()

        print("\n" + "=" * 60)
        print("HTML Review Interface Created Successfully!")
        print("=" * 60)
        print(f"\nOutput folder: {self.review_folder}")
        print(f"Total records: {len(self.data_items)}")
        print(f"Total pages: {total_pages}")
        print(f"\nTo begin review:")
        print(f"  1. Open: {os.path.join(self.review_folder, 'review-index.html')}")
        print(f"  2. Review and edit records")
        print(f"  3. Export decisions to JSON when complete")
        print("=" * 60)

        return True


def main():
    """Main entry point."""
    import argparse
    parser = argparse.ArgumentParser(description='Step 5: Create Interactive HTML Review Interface')
    parser.add_argument('--folder', '-f', default=None,
                        help='Output folder path (default: newest folder in output_folders)')
    args = parser.parse_args()

    print("Step 5: Create Interactive HTML Review Interface")
    print("=" * 60)

    if args.folder:
        folder_path = args.folder
        if not os.path.exists(folder_path):
            print(f"Error: Folder not found: {folder_path}")
            return 1
        print(f"Using folder: {os.path.basename(folder_path)}")
    else:
        # Find newest output folder
        base_output_dir = os.path.join(script_dir, "output_folders")
        folder_path = find_newest_folder(base_output_dir)

        if not folder_path:
            print(f"No output folders found in: {base_output_dir}")
            print("Please run Steps 1-4 first to generate workflow data.")
            return 1

        print(f"Auto-selected newest folder: {os.path.basename(folder_path)}")

    # Create builder and run
    builder = HTMLReviewBuilder(folder_path, records_per_page=10)
    success = builder.run()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
