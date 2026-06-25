import asyncio
import traceback
import os
from app.scanners.bandit_scanner import BanditScanner
from app.scanners.semgrep_scanner import SemgrepScanner
from app.utils.db import update_scan_status, save_scan_results

def has_python_files(target_path: str) -> bool:
    """Helper to detect if a path contains any Python (.py) files."""
    if os.path.isfile(target_path):
        return target_path.endswith(".py")
    elif os.path.isdir(target_path):
        for root, _, files in os.walk(target_path):
            for file in files:
                if file.endswith(".py"):
                    return True
    return False

async def run_scan(scan_id: str, target_dir: str):
    """
    Orchestrates the execution of Semgrep and Bandit scanners.
    Updates the database status dynamically.
    """
    try:
        # 1. Update status to 'running'
        update_scan_status(scan_id, "running")
        
        tasks = []
        scanner_names = []
        
        # 2. Conditionally initialize Bandit (Python only)
        if has_python_files(target_dir):
            bandit = BanditScanner(target_dir)
            tasks.append(bandit.scan())
            scanner_names.append("bandit")
            
        # 3. Always run Semgrep
        semgrep = SemgrepScanner(target_dir)
        tasks.append(semgrep.scan())
        scanner_names.append("semgrep")
        
        # Execute concurrently
        results = await asyncio.gather(*tasks)
        
        # 4. Aggregate findings
        all_issues = []
        for res in results:
            if res:
                all_issues.extend(res)
                
        # 5. Save results to Database
        save_scan_results(scan_id, all_issues)
        
    except Exception as e:
        error_msg = f"Scan failed: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        update_scan_status(scan_id, "failed", error_message=str(e))

