import os
import json
import csv
import io
from datetime import datetime
try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError:
    Environment = None
    FileSystemLoader = None
    select_autoescape = None

from app.utils.fix_suggestions import get_fix_suggestion

# Check for WeasyPrint availability
try:
    import weasyprint
    HAS_WEASYPRINT = True
except (OSError, ImportError):
    HAS_WEASYPRINT = False

try:
    import xhtml2pdf.pisa as pisa
    HAS_XHTML2PDF = True
except ImportError:
    pisa = None
    HAS_XHTML2PDF = False

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
        
    # Load HTML template from separate templates folder
    templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(['html', 'xml'])
    )
    template = env.get_template("report_template.html")
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
