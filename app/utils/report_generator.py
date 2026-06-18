import os
import json
import csv
import io
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from app.utils.fix_suggestions import get_fix_suggestion

# Check for WeasyPrint availability
try:
    import weasyprint
    HAS_WEASYPRINT = True
except (OSError, ImportError):
    HAS_WEASYPRINT = False

import xhtml2pdf.pisa as pisa

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "reports")

def ensure_reports_dir():
    os.makedirs(REPORTS_DIR, exist_ok=True)

def generate_report_html(scan: dict, issues: list) -> str:
    """
    Renders the beautiful report template into a standalone HTML string.
    Injects inline CSS styles suitable for both web viewing and PDF conversion.
    """
    # Create rich issues containing fix suggestions for the report
    rich_issues = []
    for issue in issues:
        rule_id = issue.get("rule_id", "")
        message = issue.get("message", "")
        fix = get_fix_suggestion(rule_id, message)
        
        rich_issues.append({
            **issue,
            "fix_title": fix["title"],
            "fix_description": fix["description"],
            "fix_before": fix["before"],
            "fix_after": fix["after"],
            "doc_url": fix["doc_url"]
        })
        
    # Standard HTML template
    template_str = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>CodeVanguard Security Report</title>
        <style>
            @page {
                size: letter;
                margin: 0.8in;
            }
            body {
                font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
                color: #2D3748;
                line-height: 1.5;
                font-size: 10pt;
            }
            h1, h2, h3, h4 {
                font-family: Arial, sans-serif;
                color: #1A202C;
                margin-top: 0;
            }
            .header-table {
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 25px;
                border-bottom: 2px solid #E2E8F0;
                padding-bottom: 15px;
            }
            .header-title {
                font-size: 24pt;
                font-weight: bold;
                color: #4A5568;
            }
            .header-tagline {
                font-size: 10pt;
                color: #A0AEC0;
                font-style: italic;
            }
            .meta-table {
                width: 100%;
                margin-bottom: 30px;
                background-color: #F7FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 4px;
            }
            .meta-table td {
                padding: 10px 15px;
                border-bottom: 1px solid #E2E8F0;
                font-size: 9pt;
            }
            .meta-label {
                font-weight: bold;
                color: #4A5568;
                width: 30%;
            }
            .severity-badge {
                padding: 3px 8px;
                border-radius: 3px;
                font-size: 8pt;
                font-weight: bold;
                text-transform: uppercase;
                display: inline-block;
                color: #FFFFFF;
                text-align: center;
            }
            .badge-critical { background-color: #E53E3E; }
            .badge-high { background-color: #ED8936; }
            .badge-medium { background-color: #ECC94B; color: #2D3748; }
            .badge-low { background-color: #3182CE; }
            
            .summary-cards {
                width: 100%;
                margin-bottom: 30px;
            }
            .summary-card {
                padding: 15px;
                border-radius: 4px;
                text-align: center;
                border: 1px solid #E2E8F0;
            }
            .card-count {
                font-size: 20pt;
                font-weight: bold;
            }
            .issues-table {
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 40px;
            }
            .issues-table th {
                background-color: #EDF2F7;
                color: #4A5568;
                text-align: left;
                padding: 10px;
                font-size: 9pt;
                border-bottom: 2px solid #CBD5E0;
            }
            .issues-table td {
                padding: 10px;
                border-bottom: 1px solid #E2E8F0;
                font-size: 9pt;
            }
            .issue-detail {
                page-break-inside: avoid;
                margin-bottom: 35px;
                border: 1px solid #E2E8F0;
                border-radius: 4px;
                padding: 20px;
                background-color: #FFFFFF;
            }
            .issue-header {
                border-bottom: 1px solid #E2E8F0;
                padding-bottom: 10px;
                margin-bottom: 15px;
            }
            .code-block {
                background-color: #1A202C;
                color: #A3BDF2;
                font-family: 'Courier New', Courier, monospace;
                padding: 12px;
                border-radius: 4px;
                font-size: 8.5pt;
                margin-top: 5px;
                margin-bottom: 15px;
                white-space: pre-wrap;
                word-wrap: break-word;
            }
            .fix-grid {
                width: 100%;
                margin-top: 15px;
            }
            .fix-col {
                width: 50%;
                vertical-align: top;
                padding: 0 5px;
            }
            .fix-title-label {
                font-weight: bold;
                font-size: 9pt;
                margin-bottom: 4px;
            }
            .text-danger { color: #E53E3E; }
            .text-success { color: #38A169; }
            .doc-link {
                font-size: 8.5pt;
                color: #3182CE;
                text-decoration: none;
            }
        </style>
    </head>
    <body>
        <!-- Header -->
        <table class="header-table">
            <tr>
                <td>
                    <div class="header-title">CodeVanguard Report</div>
                    <div class="header-tagline">Scan. Detect. Secure. In Seconds.</div>
                </td>
                <td style="text-align: right; vertical-align: bottom; font-size: 9pt; color: #718096;">
                    Generated on: {{ scan.timestamp[:19].replace('T', ' ') }}
                </td>
            </tr>
        </table>

        <h2>Executive Summary</h2>
        <table class="meta-table">
            <tr>
                <td class="meta-label">Target File/Archive:</td>
                <td>{{ scan.filename }}</td>
                <td class="meta-label">Total Vulnerabilities:</td>
                <td><strong>{{ scan.total_issues }}</strong></td>
            </tr>
            <tr>
                <td class="meta-label">Scan ID:</td>
                <td><small>{{ scan.id }}</small></td>
                <td class="meta-label">File Size:</td>
                <td>{{ (scan.file_size / 1024) | round(1) }} KB</td>
            </tr>
        </table>

        <!-- Summary Cards Table -->
        <table class="summary-cards" style="width: 100%;">
            <tr>
                <td style="width: 25%; padding-right: 10px;">
                    <div class="summary-card" style="border-left: 5px solid #E53E3E;">
                        <div class="card-count text-danger">{{ scan.critical_count }}</div>
                        <div style="font-size: 8pt; color: #718096; text-transform: uppercase;">Critical</div>
                    </div>
                </td>
                <td style="width: 25%; padding-right: 10px; padding-left: 10px;">
                    <div class="summary-card" style="border-left: 5px solid #ED8936;">
                        <div class="card-count" style="color: #ED8936;">{{ scan.high_count }}</div>
                        <div style="font-size: 8pt; color: #718096; text-transform: uppercase;">High</div>
                    </div>
                </td>
                <td style="width: 25%; padding-right: 10px; padding-left: 10px;">
                    <div class="summary-card" style="border-left: 5px solid #D69E2E;">
                        <div class="card-count" style="color: #D69E2E;">{{ scan.medium_count }}</div>
                        <div style="font-size: 8pt; color: #718096; text-transform: uppercase;">Medium</div>
                    </div>
                </td>
                <td style="width: 25%; padding-left: 10px;">
                    <div class="summary-card" style="border-left: 5px solid #3182CE;">
                        <div class="card-count" style="color: #3182CE;">{{ scan.low_count }}</div>
                        <div style="font-size: 8pt; color: #718096; text-transform: uppercase;">Low</div>
                    </div>
                </td>
            </tr>
        </table>

        <h2>Vulnerability Index</h2>
        {% if not issues %}
            <p>No vulnerabilities identified. Good job!</p>
        {% else %}
            <table class="issues-table">
                <thead>
                    <tr>
                        <th style="width: 12%;">Severity</th>
                        <th style="width: 15%;">Scanner</th>
                        <th style="width: 20%;">Rule ID</th>
                        <th>Location & File</th>
                        <th>Vulnerability Message</th>
                    </tr>
                </thead>
                <tbody>
                    {% for issue in issues %}
                    <tr>
                        <td>
                            <span class="severity-badge badge-{{ issue.severity }}">
                                {{ issue.severity }}
                            </span>
                        </td>
                        <td>{{ issue.scanner | upper }}</td>
                        <td><code>{{ issue.rule_id }}</code></td>
                        <td>{{ issue.filepath }}:{{ issue.line_number }}</td>
                        <td>{{ issue.message | truncate(80) }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>

            <div style="page-break-before: always;"></div>

            <h2>Detailed Vulnerability Findings</h2>
            {% for issue in rich_issues %}
            <div class="issue-detail">
                <div class="issue-header">
                    <table style="width: 100%;">
                        <tr>
                            <td>
                                <span class="severity-badge badge-{{ issue.severity }}">
                                    {{ issue.severity }}
                                </span>
                                <strong style="font-size: 11pt; margin-left: 10px;">
                                    {{ issue.fix_title }}
                                </strong>
                            </td>
                            <td style="text-align: right; font-size: 8.5pt; color: #718096;">
                                {{ issue.scanner | upper }} | <code>{{ issue.rule_id }}</code>
                            </td>
                        </tr>
                    </table>
                </div>

                <div style="font-size: 9pt; margin-bottom: 10px;">
                    <strong>Location:</strong> <code>{{ issue.filepath }}</code>, line {{ issue.line_number }}
                </div>
                
                <div style="font-size: 9pt; margin-bottom: 12px; color: #4A5568;">
                    <strong>Details:</strong> {{ issue.message }}
                </div>

                <strong>Vulnerable Code Snippet:</strong>
                <pre class="code-block">{{ issue.code_snippet }}</pre>

                <strong>Actionable Fix Suggestion:</strong>
                <p style="font-size: 8.5pt; color: #718096; margin-top: 5px; margin-bottom: 10px;">
                    {{ issue.fix_description }}
                </p>

                <!-- Side-by-Side Code Comparison -->
                <table class="fix-grid">
                    <tr>
                        <td class="fix-col">
                            <div class="fix-title-label text-danger">Before (Vulnerable):</div>
                            <pre class="code-block" style="background-color: #2D1A1A; color: #F8B4B4;">{{ issue.fix_before }}</pre>
                        </td>
                        <td class="fix-col">
                            <div class="fix-title-label text-success">After (Secured):</div>
                            <pre class="code-block" style="background-color: #1A2D20; color: #B4F8C8;">{{ issue.fix_after }}</pre>
                        </td>
                    </tr>
                </table>
                
                {% if issue.doc_url %}
                    <div style="margin-top: 8px;">
                        <a href="{{ issue.doc_url }}" class="doc-link" target="_blank">
                            Read Official Security Advisory &rarr;
                        </a>
                    </div>
                {% endif %}
            </div>
            {% endfor %}
        {% endif %}
    </body>
    </html>
    """
    
    # We render this using simple string replacement or simple Jinja Environment
    # Since we are using Jinja templates for HTML anyway, let's load from memory template
    env = Environment()
    template = env.from_string(template_str)
    return template.render(scan=scan, issues=issues, rich_issues=rich_issues)

def export_html_report(scan: dict, issues: list) -> bytes:
    """Returns HTML report bytes."""
    html_content = generate_report_html(scan, issues)
    return html_content.encode("utf-8")

def export_json_report(scan: dict, issues: list) -> bytes:
    """Returns JSON report bytes."""
    report_data = {
        "scan": scan,
        "issues": issues
    }
    return json.dumps(report_data, indent=2).encode("utf-8")

def export_csv_report(scan: dict, issues: list) -> bytes:
    """Returns CSV report bytes."""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Headers
    writer.writerow(["Scan ID", "Filename", "Timestamp", "Scanner", "Rule ID", "Severity", "Filepath", "Line Number", "Message"])
    
    # Data Rows
    for issue in issues:
        writer.writerow([
            scan["id"],
            scan["filename"],
            scan["timestamp"],
            issue.get("scanner"),
            issue.get("rule_id"),
            issue.get("severity"),
            issue.get("filepath"),
            issue.get("line_number"),
            issue.get("message")
        ])
        
    return output.getvalue().encode("utf-8")

def export_pdf_report(scan: dict, issues: list) -> bytes:
    """
    Generates a PDF report bytes.
    Attempts to use WeasyPrint, and falls back to xhtml2pdf (pisa) if missing binary dependencies.
    """
    html_content = generate_report_html(scan, issues)
    
    # Try WeasyPrint first
    if HAS_WEASYPRINT:
        try:
            print("Generating PDF using WeasyPrint...")
            pdf_bytes = weasyprint.HTML(string=html_content).write_pdf()
            return pdf_bytes
        except Exception as e:
            print(f"WeasyPrint PDF generation failed: {e}. Falling back to xhtml2pdf.")
            
    # Fallback to xhtml2pdf (pisa)
    print("Generating PDF using xhtml2pdf...")
    pdf_buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(
        src=html_content,
        dest=pdf_buffer
    )
    
    if pisa_status.err:
        raise RuntimeError(f"xhtml2pdf compilation error: {pisa_status.err}")
        
    return pdf_buffer.getvalue()
