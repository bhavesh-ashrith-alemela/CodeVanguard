import asyncio
import traceback
import os
import sys
import time
import logging

from app.scanners.bandit_scanner import BanditScanner
from app.scanners.semgrep_scanner import SemgrepScanner
from app.scanners.secret_scanner import SecretScanner
from app.utils.git_history import secure_bare_clone
from app.utils.db import (
    get_scan, update_scan_status, update_scan_progress,
    update_scan_metrics, save_scan_results, get_repository, get_installation,
    upsert_baseline_findings, get_repository_baseline_findings,
    update_scan_pr_metrics, update_repo_last_scanned,
    save_pr_summary, get_latest_pr_summary
)
from app.utils.file_handler import get_scan_dir, delete_scan_dir, safe_extract_tar
from app.utils.file_filter import filter_repository_files
from app.utils.github import validate_github_url, download_github_tarball
from app.utils.github_app import get_installation_access_token
from app.utils.rate_limiter import release_active_scan
from app.utils.diff_scanner import (
    fetch_pr_changed_files, filter_pr_scan_targets,
    classify_pr_findings, determine_pr_verdict,
    fetch_pr_files_with_patches, fetch_pr_metadata
)
from app.utils.config_parser import parse_codevanguard_config
from app.utils.check_run import create_check_run, complete_check_run
from app.utils.pr_comment import post_or_update_pr_comment
from app.utils.sarif import generate_sarif_report, upload_sarif_to_github
from app.services.pr_summary.facts import build_pr_summary_facts
from app.services.pr_summary.renderers import to_markdown_comment, to_check_summary
from app.services.pr_summary.narrative import generate_pr_narrative

logger = logging.getLogger(__name__)

FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://code-vanguard.vercel.app")

def get_peak_memory_mb() -> float:
    """Calculates peak resident set size (RSS) memory in megabytes."""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)
    except Exception:
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if sys.platform == "darwin":
                return usage / (1024 * 1024)
            return usage / 1024
        except Exception:
            return 0.0

async def run_scan(scan_id: str, target_dir: str = "", client_ip: str = "127.0.0.1"):
    """
    Full-lifecycle SAST scan orchestrator:
    1. Downloads & extracts archives securely (GitHub App, Public URL, Zip, Paste).
    2. Identifies scan trigger: PR diff-aware scan vs. Full baseline scan.
    3. Respects repo settings and .codevanguard.yml configuration.
    4. Runs Bandit and Semgrep scanners concurrently with process isolation.
    5. Classifies PR findings against baseline, generates Check Run, sticky PR comment & SARIF.
    6. Measures duration and logs peak memory consumption.
    7. Ensures workspace deletion and abuse lock release in finally block.
    """
    start_time = time.time()
    scan_dir = get_scan_dir(scan_id)
    files_scanned = 0
    files_skipped = 0

    try:
        scan = get_scan(scan_id)
        if not scan:
            raise RuntimeError(f"Scan record {scan_id} not found in database.")

        # If scan was already marked failed / superseded by a newer push, abort early
        if scan.get("status") in ("failed", "superseded"):
            logger.info(f"Scan {scan_id} was already marked as {scan.get('status')}; aborting execution.")
            return

        source_type = scan.get("source_type", "paste")
        trigger = scan.get("trigger", "manual")
        pr_number = scan.get("pr_number")
        repo_id = scan.get("repo_id")
        commit_sha = scan.get("commit_sha", "")

        if scan.get("status") in ("failed", "cancelled"):
            logger.info(f"Scan {scan_id} was cancelled or superseded before execution. Aborting.")
            return

        running_ok = update_scan_status(scan_id, "running")
        if not running_ok:
            logger.info(f"Scan {scan_id} could not transition to running (superseded). Aborting.")
            return

        # Resolve GitHub App credentials & repository records
        auth_token = None
        repo_record = None
        owner = None
        repo_name = None

        if source_type == "github_app" and repo_id:
            repo_record = get_repository(repo_id)
            if repo_record:
                inst = get_installation(repo_record["installation_id"])
                if inst:
                    auth_token, _ = get_installation_access_token(inst["github_installation_id"])
                parts = repo_record["full_name"].split("/", 1)
                if len(parts) == 2:
                    owner, repo_name = parts[0], parts[1]

        # Handle on-demand full git history secret scan
        if trigger == "history":
            if not owner or not repo_name or not auth_token:
                err_msg = "Cannot run git history scan: missing repository coordinates or authorization token."
                logger.warning(err_msg)
                update_scan_status(scan_id, "failed", error_message=err_msg)
                update_scan_progress(scan_id, "failed")
                return

            update_scan_progress(scan_id, "cloning bare history")
            try:
                with secure_bare_clone(owner, repo_name, auth_token=auth_token) as bare_git_dir:
                    update_scan_progress(scan_id, "scanning secret history")
                    sec_scanner = SecretScanner(git_dir=bare_git_dir)
                    secret_issues = await sec_scanner.scan()
                    duration_ms = int((time.time() - start_time) * 1000)
                    save_scan_results(
                        scan_id,
                        secret_issues,
                        duration_ms=duration_ms,
                        files_scanned=len(secret_issues),
                        files_skipped=0
                    )
                    if repo_id:
                        upsert_baseline_findings(repo_id, scan_id, commit_sha or "HEAD", secret_issues)
                        update_repo_last_scanned(repo_id)
                    update_scan_progress(scan_id, "completed", status="completed")
                    return
            except Exception as e:
                logger.warning(f"Git history bare clone scan failed: {e}")
                update_scan_status(scan_id, "failed", error_message=str(e))
                update_scan_progress(scan_id, "failed")
                return

        # 1. Download & Extract Archive
        if source_type in ("github_public", "github_app"):
            update_scan_progress(scan_id, "downloading")
            source_url = scan.get("source_url", "")

            if not owner or not repo_name:
                owner, repo_name = validate_github_url(source_url)

            tarball_path = os.path.join(scan_dir, "repo.tar.gz")
            download_github_tarball(owner, repo_name, commit_sha, tarball_path, auth_token=auth_token)

            update_scan_progress(scan_id, "extracting")
            extract_dir = os.path.join(scan_dir, "extracted")
            safe_extract_tar(tarball_path, extract_dir, strip_top_level=True)

            try:
                os.remove(tarball_path)
            except OSError:
                pass

            target_dir = extract_dir
        elif not target_dir:
            target_dir = scan_dir

        # 2. Parse Repository Configuration (.codevanguard.yml)
        repo_settings = repo_record.get("settings") if repo_record else {}
        config = parse_codevanguard_config(target_dir, default_settings=repo_settings)

        if not config.enabled:
            save_scan_results(scan_id, [], duration_ms=int((time.time() - start_time) * 1000), files_scanned=0, files_skipped=0)
            update_scan_progress(scan_id, "completed", status="completed")
            return

        # 3. Handle Pull Request Diff-Aware Scan Flow
        if trigger == "pr" and pr_number and owner and repo_name and auth_token:
            pr_detail_url = f"{FRONTEND_URL}/repos/{repo_id}/pulls/{pr_number}"

            # Create 'in_progress' GitHub Check Run
            check_run_id = create_check_run(
                owner=owner,
                repo=repo_name,
                head_sha=commit_sha,
                auth_token=auth_token,
                details_url=pr_detail_url
            )

            # Fetch changed files
            changed_files = fetch_pr_changed_files(owner, repo_name, pr_number, auth_token=auth_token)
            target_files = filter_pr_scan_targets(target_dir, changed_files, ignore_patterns=config.ignore_globs)

            files_scanned = len(target_files)
            files_skipped = max(0, len(changed_files) - files_scanned)
            update_scan_metrics(scan_id, files_scanned=files_scanned, files_skipped=files_skipped)

            tasks = []
            scanner_names = []

            has_python_targets = any(f.endswith(".py") for f in target_files)
            if has_python_targets:
                update_scan_progress(scan_id, "scanning bandit")
                py_targets = [f for f in target_files if f.endswith(".py")]
                bandit = BanditScanner(target_dir, target_files=py_targets)
                tasks.append(bandit.scan())
                scanner_names.append("bandit")

            if target_files:
                update_scan_progress(scan_id, "scanning semgrep")
                semgrep = SemgrepScanner(target_dir, target_files=target_files)
                tasks.append(semgrep.scan())
                scanner_names.append("semgrep")

                update_scan_progress(scan_id, "scanning secrets")
                secrets_scanner = SecretScanner(target_dir=target_dir, target_files=target_files)
                tasks.append(secrets_scanner.scan())
                scanner_names.append("secret")

            all_issues = []
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for idx, res in enumerate(results):
                    if isinstance(res, Exception):
                        logger.warning(f"Scanner {scanner_names[idx]} error: {res}")
                    elif res:
                        all_issues.extend(res)

            # Baseline classification
            baseline_findings = get_repository_baseline_findings(repo_id)
            new_findings, existing_findings, fixed_findings = classify_pr_findings(
                all_issues, baseline_findings, changed_files
            )

            verdict = determine_pr_verdict(new_findings, fail_on=config.fail_on)

            # Save scan results with diff metrics
            duration_ms = int((time.time() - start_time) * 1000)
            save_scan_results(
                scan_id,
                all_issues,
                duration_ms=duration_ms,
                files_scanned=files_scanned,
                files_skipped=files_skipped
            )

            update_scan_pr_metrics(
                scan_id,
                verdict=verdict,
                new_count=len(new_findings),
                fixed_count=len(fixed_findings),
                existing_count=len(existing_findings),
                check_run_id=check_run_id
            )

            # Re-verify that scan was not superseded during scan execution
            current_scan = get_scan(scan_id)
            if current_scan and current_scan.get("status") in ("failed", "cancelled"):
                logger.info(f"Scan {scan_id} was superseded while running. Aborting without publishing results.")
                return

            # Build deterministic PR Summary Facts and Reviewer Needs (Fail-safe)
            custom_comment_body = None
            custom_check_summary = None
            try:
                pr_meta = fetch_pr_metadata(owner, repo_name, pr_number, auth_token=auth_token)
                if not pr_meta.get("head_sha"):
                    pr_meta["head_sha"] = commit_sha
                if not pr_meta.get("title") or pr_meta.get("title") == f"Pull Request #{pr_number}":
                    pr_meta["title"] = scan.get("filename") or f"Pull Request #{pr_number}"

                pr_diff_files = fetch_pr_files_with_patches(owner, repo_name, pr_number, auth_token=auth_token)
                prev_summary = get_latest_pr_summary(repo_id, pr_number)

                summary_facts = build_pr_summary_facts(
                    pr_dict=pr_meta,
                    changed_files=changed_files,
                    file_diffs=pr_diff_files,
                    raw_new_findings=new_findings,
                    raw_fixed_findings=fixed_findings,
                    raw_existing_findings=existing_findings,
                    total_baseline_count=len(baseline_findings),
                    fail_on=config.fail_on,
                    previous_summary=prev_summary
                )

                narrative_enabled = bool(repo_record.get("narrative_enabled", 0)) if repo_record else False
                narrative_res = generate_pr_narrative(summary_facts, narrative_enabled=narrative_enabled)
                narrative_text = narrative_res.get("text")

                # Store summary facts in database
                save_pr_summary(
                    repo_id=repo_id,
                    pr_number=pr_number,
                    scan_id=scan_id,
                    head_sha=commit_sha,
                    facts=summary_facts.model_dump() if hasattr(summary_facts, "model_dump") else summary_facts.dict(),
                    narrative=narrative_text,
                    narrative_source=narrative_res.get("source", "template"),
                    model=narrative_res.get("model")
                )

                custom_comment_body = to_markdown_comment(summary_facts, narrative=narrative_text, dashboard_url=pr_detail_url)
                custom_check_summary = to_check_summary(summary_facts, narrative=narrative_text, dashboard_url=pr_detail_url)
            except Exception as e:
                logger.warning(f"Failed to generate or save PR summary facts: {e}")

            # Complete Check Run with batched annotations
            if check_run_id:
                complete_check_run(
                    owner=owner,
                    repo=repo_name,
                    check_run_id=check_run_id,
                    verdict=verdict,
                    new_findings=new_findings,
                    fixed_count=len(fixed_findings),
                    existing_count=len(existing_findings),
                    auth_token=auth_token,
                    details_url=pr_detail_url,
                    summary=custom_check_summary
                )

            # Post or update sticky PR comment
            if config.pr_comment_enabled:
                post_or_update_pr_comment(
                    owner=owner,
                    repo=repo_name,
                    pull_number=pr_number,
                    verdict=verdict,
                    new_findings=new_findings,
                    fixed_count=len(fixed_findings),
                    existing_count=len(existing_findings),
                    auth_token=auth_token,
                    dashboard_url=pr_detail_url,
                    custom_body=custom_comment_body
                )

            # Upload SARIF if enabled
            if config.sarif_upload_enabled:
                sarif_doc = generate_sarif_report(scan, new_findings)
                upload_sarif_to_github(
                    owner=owner,
                    repo=repo_name,
                    commit_sha=commit_sha,
                    ref=f"refs/pull/{pr_number}/head",
                    sarif_data=sarif_doc,
                    auth_token=auth_token
                )

            update_repo_last_scanned(repo_id)
            print(f"[Scan {scan_id} PR #{pr_number}] Verdict: {verdict} | New: {len(new_findings)} | Fixed: {len(fixed_findings)} | Duration: {duration_ms}ms")
            return

        # 4. Handle Full / Baseline Repository Scan (Push to default branch or manual scan)
        update_scan_progress(scan_id, "filtering")
        filter_result = filter_repository_files(target_dir)
        files_scanned = filter_result.files_scanned
        files_skipped = filter_result.files_skipped

        update_scan_metrics(scan_id, files_scanned=files_scanned, files_skipped=files_skipped)

        if files_scanned == 0:
            save_scan_results(
                scan_id,
                [],
                duration_ms=int((time.time() - start_time) * 1000),
                files_scanned=0,
                files_skipped=files_skipped
            )
            update_scan_progress(scan_id, "completed", status="completed")
            return

        tasks = []
        scanner_names = []

        if filter_result.has_python:
            update_scan_progress(scan_id, "scanning bandit")
            bandit = BanditScanner(target_dir)
            tasks.append(bandit.scan())
            scanner_names.append("bandit")

        update_scan_progress(scan_id, "scanning semgrep")
        semgrep = SemgrepScanner(target_dir)
        tasks.append(semgrep.scan())
        scanner_names.append("semgrep")

        update_scan_progress(scan_id, "scanning secrets")
        secrets_scanner = SecretScanner(target_dir=target_dir)
        tasks.append(secrets_scanner.scan())
        scanner_names.append("secret")

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_issues = []
        for idx, res in enumerate(results):
            if isinstance(res, Exception):
                logger.warning(f"Scanner {scanner_names[idx]} error: {res}")
            elif res:
                all_issues.extend(res)

        # Inspect git history for deleted/past secrets if github credentials are present
        if source_type == "github_app" and owner and repo_name and auth_token:
            try:
                update_scan_progress(scan_id, "scanning git history secrets")
                with secure_bare_clone(owner, repo_name, auth_token=auth_token) as bare_git_dir:
                    history_scanner = SecretScanner(git_dir=bare_git_dir, target_dir=target_dir)
                    hist_issues = await history_scanner.scan()
                    existing_hashes = {iss.get("secret_hash") for iss in all_issues if iss.get("secret_hash")}
                    for h_iss in hist_issues:
                        if h_iss.get("secret_hash") not in existing_hashes:
                            existing_hashes.add(h_iss.get("secret_hash"))
                            all_issues.append(h_iss)
            except Exception as ex:
                logger.warning(f"Git history secret scan non-blocking warning: {ex}")

        update_scan_progress(scan_id, "saving")
        duration_ms = int((time.time() - start_time) * 1000)
        save_scan_results(
            scan_id,
            all_issues,
            duration_ms=duration_ms,
            files_scanned=files_scanned,
            files_skipped=files_skipped
        )

        # Baseline synchronization ONLY for default branch scans (push or default branch scan)
        is_default_branch = False
        default_branch = "main"
        if repo_record:
            default_branch = repo_record.get("default_branch", "main")
            scan_branch = scan.get("branch") or default_branch
            is_default_branch = (scan_branch == default_branch)

        if repo_id and commit_sha and is_default_branch:
            upsert_baseline_findings(repo_id, scan_id, commit_sha, all_issues)
            update_repo_last_scanned(repo_id)

            if config.sarif_upload_enabled and owner and repo_name and auth_token:
                sarif_doc = generate_sarif_report(scan, all_issues)
                upload_sarif_to_github(
                    owner=owner,
                    repo=repo_name,
                    commit_sha=commit_sha,
                    ref=f"refs/heads/{default_branch}",
                    sarif_data=sarif_doc,
                    auth_token=auth_token
                )

        peak_mb = get_peak_memory_mb()
        print(f"[Scan {scan_id}] Baseline Completed in {duration_ms}ms | Peak RSS: {peak_mb:.1f} MB | Scanned: {files_scanned} | Findings: {len(all_issues)}")

    except Exception as e:
        error_msg = f"Scan failed: {str(e)}"
        print(f"{error_msg}\n{traceback.format_exc()}")
        update_scan_status(scan_id, "failed", error_message=str(e))
        update_scan_progress(scan_id, "failed")
    finally:
        delete_scan_dir(scan_id)
        release_active_scan(client_ip, scan_id)
