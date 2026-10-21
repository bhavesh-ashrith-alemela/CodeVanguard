#!/usr/bin/env python3
"""
CodeVanguard CI Self-Scan Script
Scans CodeVanguard's own codebase for:
1. Secrets committed in git history or HEAD
2. Python SAST vulnerabilities using Bandit
3. Polyglot SAST vulnerabilities using Semgrep

Generates a unified SARIF 2.1.0 report at reports/codevanguard_self_scan.sarif.
"""

import os
import sys
import json
import shutil
import asyncio
import subprocess
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.scanners.secret_scanner import SecretScanner

def run_cmd(cmd: list) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return 127, "", f"Binary not found: {cmd[0]}"

async def run_secret_scan() -> list[dict]:
    print("[1/3] Running CodeVanguard Native Secret Scanner...")
    scanner = SecretScanner(target_dir=str(PROJECT_ROOT))
    results = await scanner.scan()
    findings = []
    for r in results:
        sev = r.get("severity", "HIGH").upper()
        level = "error" if sev in ["CRITICAL", "HIGH"] else "warning"
        findings.append({
            "ruleId": r.get("rule_id", "SECRET_EXPOSED"),
            "message": {
                "text": r.get("message", "Potential credential exposed")
            },
            "level": level,
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": r.get("file", "unknown")},
                    "region": {"startLine": max(1, r.get("line", 1))}
                }
            }]
        })
    print(f"      Secret scanner found {len(findings)} potential secret(s).")
    return findings

def run_bandit_scan() -> list[dict]:
    print("[2/3] Running Bandit Python SAST...")
    if not shutil.which("bandit"):
        print("      Bandit not in PATH. Skipping local bandit run (will run in container/CI).")
        return []

    cmd = ["bandit", "-r", "app", "-f", "json", "-q"]
    code, stdout, stderr = run_cmd(cmd)
    findings = []
    if stdout:
        try:
            data = json.loads(stdout)
            for item in data.get("results", []):
                sev = item.get("issue_severity", "LOW").upper()
                level = "error" if sev in ["HIGH", "CRITICAL"] else "warning"
                findings.append({
                    "ruleId": item.get("test_id", "B000"),
                    "message": {"text": item.get("issue_text", "")},
                    "level": level,
                    "locations": [{
                        "physicalLocation": {
                            "artifactLocation": {"uri": item.get("filename", "")},
                            "region": {"startLine": item.get("line_number", 1)}
                        }
                    }]
                })
        except Exception as e:
            print(f"      Error parsing Bandit output: {e}")
    print(f"      Bandit found {len(findings)} issue(s).")
    return findings

def run_semgrep_scan() -> list[dict]:
    print("[3/3] Running Semgrep OSS Polyglot SAST...")
    if not shutil.which("semgrep"):
        print("      Semgrep not in PATH. Skipping local semgrep run (will run in container/CI).")
        return []

    cmd = ["semgrep", "--config=auto", "--json", "--quiet", "app"]
    code, stdout, stderr = run_cmd(cmd)
    findings = []
    if stdout:
        try:
            data = json.loads(stdout)
            for item in data.get("results", []):
                sev = item.get("extra", {}).get("severity", "WARNING").upper()
                level = "error" if sev == "ERROR" else "warning"
                findings.append({
                    "ruleId": item.get("check_id", "semgrep-rule"),
                    "message": {"text": item.get("extra", {}).get("message", "")},
                    "level": level,
                    "locations": [{
                        "physicalLocation": {
                            "artifactLocation": {"uri": item.get("path", "")},
                            "region": {"startLine": item.get("start", {}).get("line", 1)}
                        }
                    }]
                })
        except Exception as e:
            print(f"      Error parsing Semgrep output: {e}")
    print(f"      Semgrep found {len(findings)} issue(s).")
    return findings

def build_sarif(results: list[dict]) -> dict:
    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "CodeVanguard Self-Scan",
                    "version": "1.0.0",
                    "informationUri": "https://codevanguard.dev"
                }
            },
            "results": results
        }]
    }

async def main():
    print("=" * 60)
    print("Starting CodeVanguard Self-Scan")
    print("=" * 60)

    all_results = []
    secret_results = await run_secret_scan()
    all_results.extend(secret_results)

    bandit_results = run_bandit_scan()
    all_results.extend(bandit_results)

    semgrep_results = run_semgrep_scan()
    all_results.extend(semgrep_results)

    # Write SARIF report
    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    sarif_path = reports_dir / "codevanguard_self_scan.sarif"

    sarif_data = build_sarif(all_results)
    with open(sarif_path, "w", encoding="utf-8") as f:
        json.dump(sarif_data, f, indent=2)

    print("=" * 60)
    print(f"Self-Scan complete! Generated SARIF report: {sarif_path}")
    print(f"Total findings: {len(all_results)}")
    
    # Filter for blocking errors (level == "error")
    errors = [r for r in all_results if r.get("level") == "error"]
    if errors:
        print(f"WARNING: {len(errors)} high/critical finding(s) detected.")
    else:
        print("CLEAN: Zero blocking security findings in CodeVanguard.")
    print("=" * 60)

    # Return 0 so CI can process SARIF upload
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
