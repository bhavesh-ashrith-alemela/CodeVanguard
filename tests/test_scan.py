import os
import sys
import asyncio
import shutil

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.utils.db import init_db, create_scan, get_scan, get_scan_issues, get_scan_history
from app.scanners.scanner import run_scan
from app.utils.report_generator import export_html_report, export_json_report, export_csv_report, export_pdf_report
from app.utils.file_handler import delete_scan_dir

async def test_integration():
    print("=== STARTING CODEVANGUARD INTEGRATION TEST ===")
    
    # 1. Start clean: Delete existing test db if any
    db_path = "codevanguard.db"
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print("Removed old codevanguard.db")
        except OSError as e:
            print(f"Could not remove database: {e}")

    # 2. Init DB
    init_db()
    print("Database initialized successfully.")

    import uuid
    scan_id = f"test_integration_{uuid.uuid4().hex}"
    target_file = os.path.abspath("examples/vulnerable.py")
    
    if not os.path.exists(target_file):
        print(f"ERROR: Example file {target_file} not found!")
        sys.exit(1)
        
    print(f"Triggering parallel scan on: {target_file}")
    
    # Create scan entry in SQLite (pending status)
    create_scan(scan_id, "vulnerable.py", os.path.getsize(target_file))
    
    # Run orchestrator
    await run_scan(scan_id, target_file)
    
    # 4. Assert Scan Status in DB
    scan = get_scan(scan_id)
    if not scan:
        print("ERROR: Scan record not created in SQLite!")
        sys.exit(1)
        
    print("\n--- Scan Summary ---")
    print(f"ID: {scan['id']}")
    print(f"File: {scan['filename']}")
    print(f"Status: {scan['status']}")
    print(f"Total Issues: {scan['total_issues']}")
    print(f"Critical: {scan['critical_count']}")
    print(f"High: {scan['high_count']}")
    print(f"Medium: {scan['medium_count']}")
    print(f"Low: {scan['low_count']}")
    
    if scan["status"] != "completed":
        print(f"ERROR: Scan status is {scan['status']}. Error message: {scan.get('error_message')}")
        sys.exit(1)
        
    issues = get_scan_issues(scan_id)
    print(f"\nRetrieved {len(issues)} issues from SQLite database.")
    
    # Inspect a few issues
    print("\nSample Findings:")
    for idx, issue in enumerate(issues[:3]):
        print(f"[{idx+1}] Scanner: {issue['scanner'].upper()} | Rule: {issue['rule_id']} | Severity: {issue['severity'].upper()}")
        print(f"    File: {issue['filepath']}:{issue['line_number']}")
        print(f"    Message: {issue['message']}")
        print(f"    Snippet:\n{issue['code_snippet']}\n")

    # 5. Verify Report Exporters
    print("\n--- Verifying Exporters ---")
    
    # Export HTML
    html_bytes = export_html_report(scan, issues)
    print(f"HTML Exporter: OK ({len(html_bytes)} bytes)")
    
    # Export JSON
    json_bytes = export_json_report(scan, issues)
    print(f"JSON Exporter: OK ({len(json_bytes)} bytes)")
    
    # Export CSV
    csv_bytes = export_csv_report(scan, issues)
    print(f"CSV Exporter: OK ({len(csv_bytes)} bytes)")
    
    # Export PDF
    try:
        pdf_bytes = export_pdf_report(scan, issues)
        print(f"PDF Exporter: OK ({len(pdf_bytes)} bytes)")
        
        # Save pdf report to reports/ for verification
        os.makedirs("reports", exist_ok=True)
        pdf_path = os.path.join("reports", "test_report.pdf")
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        print(f"PDF saved to: {pdf_path}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"PDF Exporter FAILED: {e}")
        sys.exit(1)
        
    # Clean up files created during scan orchestration
    delete_scan_dir(scan_id)
    print("Cleaned up temporary folders.")

    print("\n=== INTEGRATION TEST PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    asyncio.run(test_integration())
