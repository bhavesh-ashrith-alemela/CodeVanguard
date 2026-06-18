import asyncio
import traceback
from app.scanners.bandit_scanner import BanditScanner
from app.scanners.semgrep_scanner import SemgrepScanner
from app.utils.db import update_scan_status, save_scan_results

async def run_scan(scan_id: str, target_dir: str):
    """
    Orchestrates the parallel execution of Bandit and Semgrep scanners.
    Updates the SQLite DB status dynamically.
    """
    try:
        # 1. Update status to 'running'
        update_scan_status(scan_id, "running")
        
        # 2. Initialize scanners
        bandit = BanditScanner(target_dir)
        semgrep = SemgrepScanner(target_dir)
        
        # 3. Execute concurrently
        bandit_task = bandit.scan()
        semgrep_task = semgrep.scan()
        
        # Gather results
        bandit_results, semgrep_results = await asyncio.gather(bandit_task, semgrep_task)
        
        # 4. Aggregate findings
        all_issues = []
        if bandit_results:
            all_issues.extend(bandit_results)
        if semgrep_results:
            all_issues.extend(semgrep_results)
            
        # 5. Save results to Database
        save_scan_results(scan_id, all_issues)
        
    except Exception as e:
        error_msg = f"Scan failed: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        update_scan_status(scan_id, "failed", error_message=str(e))
