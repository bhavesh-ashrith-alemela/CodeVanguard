"""
Deterministic Facts Builder for Pull Request Security Summaries.
Computes versioned PRSummaryFacts with zero source code persistence.
"""
import os
import re
import fnmatch
from typing import List, Dict, Any, Optional, Tuple

from app.services.pr_summary.models import (
    PRSummaryFacts, PRDetails, FindingSummaryItem, FindingsGroup,
    DependencyChange, PushDelta, ActionItem
)

# Load categories from categories.yaml
CATEGORIES_FILE = os.path.join(os.path.dirname(__file__), "categories.yaml")

DEFAULT_CATEGORIES = {
    "auth": ["*auth*", "*login*", "*session*", "*jwt*", "*token*", "*permission*", "*role*", "*oauth*", "*credential*"],
    "db": ["*migration*", "*migrations/*", "*model*", "*models/*", "*schema*", "*sql*", "*db*", "*query*", "*entity*"],
    "subprocess/exec": ["*subprocess*", "*exec*", "*command*", "*runner*", "*shell*", "*spawn*", "*process*"],
    "dependency manifests": ["requirements*.txt", "package*.json", "go.mod", "go.sum", "Cargo.toml", "Gemfile*", "pom.xml", "build.gradle*", "Pipfile*", "pyproject.toml"],
    "ci_workflows": [".github/workflows/*", ".gitlab-ci.yml", "Jenkinsfile*", ".circleci/*", ".travis.yml"],
    "config/secrets": [".env*", "*config*", "*.conf", "*.yaml", "*.yml", "*.toml", "*.ini"],
    "infra": ["Dockerfile*", "docker-compose*", "k8s/*", "helm/*", "terraform/*", "*.tf", "render.yaml", "vercel.json", "cloudbuild.yaml"]
}

def load_categories_config() -> Dict[str, List[str]]:
    """Loads path patterns from categories.yaml with resilient fallback."""
    if not os.path.exists(CATEGORIES_FILE):
        return DEFAULT_CATEGORIES

    try:
        try:
            import yaml
            with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    return data
        except ImportError:
            pass

        # Simple line-based fallback parser
        categories: Dict[str, List[str]] = {}
        current_cat = None
        with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
            for line in f:
                sline = line.strip()
                if not sline or sline.startswith("#"):
                    continue
                if not line.startswith(" ") and ":" in sline:
                    current_cat = sline.split(":", 1)[0].strip()
                    categories[current_cat] = []
                elif current_cat and sline.startswith("- "):
                    pattern = sline[2:].strip().strip('"').strip("'")
                    categories[current_cat].append(pattern)
        return categories if categories else DEFAULT_CATEGORIES
    except Exception:
        return DEFAULT_CATEGORIES

CATEGORIES_MAP = load_categories_config()

def detect_categories_touched(changed_files: List[str]) -> List[str]:
    """Identifies which architectural categories were touched by the PR."""
    touched = set()
    for file_path in changed_files:
        norm_path = file_path.replace("\\", "/").strip().lstrip("/")
        base_name = os.path.basename(norm_path)
        for category, patterns in CATEGORIES_MAP.items():
            for pat in patterns:
                pat_clean = pat.replace("\\", "/").strip().lstrip("/")
                if fnmatch.fnmatch(norm_path.lower(), pat_clean.lower()) or \
                   fnmatch.fnmatch(base_name.lower(), pat_clean.lower()):
                    touched.add(category)
                    break
    # Stable ordering for determinism
    preferred_order = [
        "auth", "db", "subprocess/exec", "dependency manifests",
        "ci_workflows", "config/secrets", "infra"
    ]
    result = [cat for cat in preferred_order if cat in touched]
    for cat in sorted(touched):
        if cat not in result:
            result.append(cat)
    return result

def parse_dependency_diffs(file_diffs: List[Dict[str, Any]]) -> List[DependencyChange]:
    """
    Parses manifest diffs (requirements.txt, package.json, go.mod)
    to extract added, removed, or updated dependencies.
    """
    changes: List[DependencyChange] = []
    
    for item in file_diffs:
        filename = item.get("filename", "")
        norm_name = filename.replace("\\", "/").strip().lstrip("/")
        base_name = os.path.basename(norm_name).lower()
        patch = item.get("patch") or ""
        if not patch:
            continue

        if base_name.startswith("requirements") and base_name.endswith(".txt"):
            changes.extend(_parse_requirements_diff(norm_name, patch))
        elif base_name in ("package.json", "package-lock.json"):
            changes.extend(_parse_package_json_diff(norm_name, patch))
        elif base_name == "go.mod":
            changes.extend(_parse_go_mod_diff(norm_name, patch))

    return changes

def _parse_requirements_diff(filename: str, patch: str) -> List[DependencyChange]:
    added: Dict[str, str] = {}
    removed: Dict[str, str] = {}

    req_pattern = re.compile(r'^([a-zA-Z0-9_\-\.]+)(?:([=<>!~@]+)(.+))?$')

    for line in patch.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            content = line[1:].strip().split("#")[0].strip()
            if not content:
                continue
            m = req_pattern.match(content)
            if m:
                pkg = m.group(1).lower()
                ver = (m.group(2) or "") + (m.group(3) or "")
                added[pkg] = ver or "latest"
        elif line.startswith("-"):
            content = line[1:].strip().split("#")[0].strip()
            if not content:
                continue
            m = req_pattern.match(content)
            if m:
                pkg = m.group(1).lower()
                ver = (m.group(2) or "") + (m.group(3) or "")
                removed[pkg] = ver or "latest"

    changes = []
    # Updated: both added and removed
    for pkg in list(added.keys()):
        if pkg in removed:
            changes.append(DependencyChange(
                ecosystem="pip",
                name=pkg,
                change_type="updated",
                version=added[pkg],
                previous_version=removed[pkg],
                manifest_file=filename
            ))
            del added[pkg]
            del removed[pkg]

    # Added only
    for pkg, ver in added.items():
        changes.append(DependencyChange(
            ecosystem="pip",
            name=pkg,
            change_type="added",
            version=ver,
            manifest_file=filename
        ))

    # Removed only
    for pkg, ver in removed.items():
        changes.append(DependencyChange(
            ecosystem="pip",
            name=pkg,
            change_type="removed",
            previous_version=ver,
            manifest_file=filename
        ))

    return changes

def _parse_package_json_diff(filename: str, patch: str) -> List[DependencyChange]:
    pkg_pattern = re.compile(r'^\s*["\']([^"\']+)["\']\s*:\s*["\']([^"\']+)["\']')
    added: Dict[str, str] = {}
    removed: Dict[str, str] = {}

    for line in patch.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            content = line[1:].strip().rstrip(",")
            m = pkg_pattern.match(content)
            if m and not m.group(1).startswith("$") and m.group(1) not in ("name", "version", "description", "main", "scripts"):
                added[m.group(1)] = m.group(2)
        elif line.startswith("-"):
            content = line[1:].strip().rstrip(",")
            m = pkg_pattern.match(content)
            if m and not m.group(1).startswith("$") and m.group(1) not in ("name", "version", "description", "main", "scripts"):
                removed[m.group(1)] = m.group(2)

    changes = []
    for pkg in list(added.keys()):
        if pkg in removed:
            changes.append(DependencyChange(
                ecosystem="npm",
                name=pkg,
                change_type="updated",
                version=added[pkg],
                previous_version=removed[pkg],
                manifest_file=filename
            ))
            del added[pkg]
            del removed[pkg]

    for pkg, ver in added.items():
        changes.append(DependencyChange(
            ecosystem="npm",
            name=pkg,
            change_type="added",
            version=ver,
            manifest_file=filename
        ))

    for pkg, ver in removed.items():
        changes.append(DependencyChange(
            ecosystem="npm",
            name=pkg,
            change_type="removed",
            previous_version=ver,
            manifest_file=filename
        ))

    return changes

def _parse_go_mod_diff(filename: str, patch: str) -> List[DependencyChange]:
    go_pattern = re.compile(r'^\s*([a-zA-Z0-9_\-\./]+)\s+(v[0-9a-zA-Z\.\-]+)')
    added: Dict[str, str] = {}
    removed: Dict[str, str] = {}

    for line in patch.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            content = line[1:].strip()
            m = go_pattern.match(content)
            if m and m.group(1) != "module" and m.group(1) != "go":
                added[m.group(1)] = m.group(2)
        elif line.startswith("-"):
            content = line[1:].strip()
            m = go_pattern.match(content)
            if m and m.group(1) != "module" and m.group(1) != "go":
                removed[m.group(1)] = m.group(2)

    changes = []
    for mod in list(added.keys()):
        if mod in removed:
            changes.append(DependencyChange(
                ecosystem="go",
                name=mod,
                change_type="updated",
                version=added[mod],
                previous_version=removed[mod],
                manifest_file=filename
            ))
            del added[mod]
            del removed[mod]

    for mod, ver in added.items():
        changes.append(DependencyChange(
            ecosystem="go",
            name=mod,
            change_type="added",
            version=ver,
            manifest_file=filename
        ))

    for mod, ver in removed.items():
        changes.append(DependencyChange(
            ecosystem="go",
            name=mod,
            change_type="removed",
            previous_version=ver,
            manifest_file=filename
        ))

    return changes

def _is_secret_finding(rule_id: str, message: str, file_path: str) -> bool:
    """Detects whether a finding represents leaked credentials, tokens, or secret keys."""
    text = f"{rule_id} {message} {file_path}".lower()
    secret_terms = ["secret", "private_key", "token", "password", "credential", "api_key", "bearer", "jwt_secret"]
    return any(term in text for term in secret_terms)

def build_actions_checklist(
    new_findings: List[FindingSummaryItem],
    categories_touched: List[str],
    dependency_changes: List[DependencyChange],
    max_items: int = 10
) -> Tuple[List[ActionItem], int]:
    """
    Orders checklist by strict priority:
    1. Critical findings
    2. Secrets / Credential rotation
    3. High findings
    4. Workflow or Dependency issues
    5. Medium findings
    Capped at max_items (10) with count of omitted items.
    """
    all_actions: List[ActionItem] = []

    # Priority 1: Secrets / Credential leaks (Rotate this credential first!)
    for f in new_findings:
        if _is_secret_finding(f.rule_id, f.message, f.file):
            all_actions.append(ActionItem(
                priority=1,
                category="secrets_rotation",
                title=f"Rotate this credential: Rotate leaked secret in {f.file}:{f.line}",
                description="Rotate this credential immediately; removing it from code or history is secondary. Revoke in provider console and update secrets manager.",
                finding_id=f.finding_id,
                fingerprint=f.fingerprint,
                file=f.file,
                line=f.line
            ))

    # Priority 2: Other Critical findings
    for f in new_findings:
        if f.severity.lower() == "critical" and not _is_secret_finding(f.rule_id, f.message, f.file):
            all_actions.append(ActionItem(
                priority=2,
                category="critical_finding",
                title=f"[CRITICAL] Remediate {f.rule_id} in {f.file}:{f.line}",
                description=f.message,
                finding_id=f.finding_id,
                fingerprint=f.fingerprint,
                file=f.file,
                line=f.line
            ))

    # Priority 3: Other High findings
    for f in new_findings:
        if f.severity.lower() == "high" and not _is_secret_finding(f.rule_id, f.message, f.file):
            all_actions.append(ActionItem(
                priority=3,
                category="high_finding",
                title=f"[HIGH] Remediate {f.rule_id} in {f.file}:{f.line}",
                description=f.message,
                finding_id=f.finding_id,
                fingerprint=f.fingerprint,
                file=f.file,
                line=f.line
            ))

    # Priority 4: CI Workflow & Dependency Changes
    if "ci_workflows" in categories_touched:
        all_actions.append(ActionItem(
            priority=4,
            category="workflow_audit",
            title="Review modified CI/CD workflows",
            description="Audit GitHub Actions workflow modifications for script injections, unpinned third-party actions, or excessive GITHUB_TOKEN permissions."
        ))

    if dependency_changes:
        all_actions.append(ActionItem(
            priority=4,
            category="dependency_audit",
            title=f"Audit {len(dependency_changes)} dependency change(s)",
            description=f"Inspect newly introduced packages ({', '.join(d.name for d in dependency_changes[:3])}{'...' if len(dependency_changes) > 3 else ''}) for supply-chain risks and exact version pinning."
        ))

    # Priority 5: Medium findings
    for f in new_findings:
        if f.severity.lower() == "medium" and not _is_secret_finding(f.rule_id, f.message, f.file):
            all_actions.append(ActionItem(
                priority=5,
                category="medium_finding",
                title=f"[MEDIUM] Review {f.rule_id} in {f.file}:{f.line}",
                description=f.message,
                finding_id=f.finding_id,
                fingerprint=f.fingerprint,
                file=f.file,
                line=f.line
            ))

    total = len(all_actions)
    omitted = max(0, total - max_items)
    return all_actions[:max_items], omitted

def compute_pr_verdict(
    new_findings: List[FindingSummaryItem],
    fail_on: str = "high"
) -> Tuple[str, List[str]]:
    """
    Computes verdict ('block', 'attention', 'safe') and explanatory reasons list.
    """
    severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    threshold = severity_order.get(fail_on.lower(), 3)
    if fail_on.lower() == "none":
        threshold = 999

    reasons: List[str] = []
    blocking_count = 0

    crit_count = sum(1 for f in new_findings if f.severity.lower() == "critical")
    high_count = sum(1 for f in new_findings if f.severity.lower() == "high")
    med_count = sum(1 for f in new_findings if f.severity.lower() == "medium")
    low_count = sum(1 for f in new_findings if f.severity.lower() == "low")

    for f in new_findings:
        sev_weight = severity_order.get(f.severity.lower(), 1)
        if sev_weight >= threshold:
            blocking_count += 1

    if blocking_count > 0:
        verdict = "block"
        reasons.append(f"{blocking_count} new finding(s) meet or exceed the repository block threshold ('{fail_on}').")
        if crit_count:
            reasons.append(f"{crit_count} Critical severity vulnerability must be fixed before merge.")
        if high_count:
            reasons.append(f"{high_count} High severity vulnerability requires remediation.")
    elif len(new_findings) > 0:
        verdict = "attention"
        reasons.append(f"{len(new_findings)} new finding(s) detected below the '{fail_on}' block threshold; attention recommended.")
        if med_count:
            reasons.append(f"{med_count} Medium severity finding(s) present.")
        if low_count:
            reasons.append(f"{low_count} Low severity finding(s) present.")
    else:
        verdict = "safe"
        reasons.append("Zero new security findings introduced in this pull request.")

    return verdict, reasons

def build_pr_summary_facts(
    pr_dict: Dict[str, Any],
    changed_files: List[str],
    file_diffs: List[Dict[str, Any]],
    raw_new_findings: List[Dict[str, Any]],
    raw_fixed_findings: List[Dict[str, Any]],
    raw_existing_findings: List[Dict[str, Any]],
    total_baseline_count: int,
    fail_on: str = "high",
    previous_summary: Optional[Dict[str, Any]] = None
) -> PRSummaryFacts:
    """
    Assembles a completely deterministic, typed PRSummaryFacts object.
    Never persists source code or raw snippets.
    """
    pr_details = PRDetails(
        number=int(pr_dict.get("number", 0)),
        head_sha=str(pr_dict.get("head_sha", "")),
        base_sha=str(pr_dict.get("base_sha", "")),
        title=str(pr_dict.get("title", f"Pull Request #{pr_dict.get('number', '')}")),
        author=str(pr_dict.get("author", "unknown")),
        files_changed=int(pr_dict.get("files_changed", len(changed_files))),
        additions=int(pr_dict.get("additions", 0)),
        deletions=int(pr_dict.get("deletions", 0))
    )

    categories_touched = detect_categories_touched(changed_files)
    dependency_changes = parse_dependency_diffs(file_diffs)

    def to_item(f: Dict[str, Any]) -> FindingSummaryItem:
        finding_id_val = f.get("finding_id") or f.get("id")
        has_v_fix = f.get("has_verified_fix")
        fix_att_id = f.get("fix_attempt_id")
        if (has_v_fix is None or fix_att_id is None) and finding_id_val:
            try:
                from app.utils.db import get_latest_fix_attempt_for_finding
                latest_fix = get_latest_fix_attempt_for_finding(str(finding_id_val))
                if latest_fix:
                    has_v_fix = (latest_fix.get("status") in ("verified", "pr_opened", "merged"))
                    fix_att_id = latest_fix.get("id")
            except Exception:
                pass

        return FindingSummaryItem(
            finding_id=finding_id_val,
            fingerprint=f.get("fingerprint", ""),
            severity=f.get("severity", "medium").lower(),
            rule_id=f.get("rule_id", "security-issue"),
            message=f.get("message") or f.get("fix_description", "Security vulnerability"),
            file=f.get("filepath") or f.get("file", "unknown"),
            line=int(f.get("line_number") or f.get("line", 1)),
            has_verified_fix=has_v_fix,
            fix_attempt_id=fix_att_id
        )

    new_items = [to_item(f) for f in raw_new_findings]
    fixed_items = [to_item(f) for f in raw_fixed_findings]
    existing_touched = [to_item(f) for f in raw_existing_findings]

    hidden_existing_count = max(0, total_baseline_count - len(existing_touched))

    findings_group = FindingsGroup(
        new=new_items,
        fixed=fixed_items,
        existing_touched=existing_touched,
        hidden_existing_count=hidden_existing_count
    )

    # Compute delta versus previous scan of the same PR
    current_new_count = len(new_items)
    current_fixed_count = len(fixed_items)
    delta_new = 0
    delta_fixed = 0
    prev_head_sha = None

    if previous_summary and "facts" in previous_summary:
        prev_facts = previous_summary["facts"]
        if isinstance(prev_facts, dict) and "findings" in prev_facts:
            prev_new = len(prev_facts["findings"].get("new", []))
            prev_fixed = len(prev_facts["findings"].get("fixed", []))
            delta_new = current_new_count - prev_new
            delta_fixed = current_fixed_count - prev_fixed
            prev_head_sha = previous_summary.get("head_sha")

    delta_since_previous = PushDelta(
        new_count=current_new_count,
        fixed_count=current_fixed_count,
        delta_new=delta_new,
        delta_fixed=delta_fixed,
        previous_head_sha=prev_head_sha
    )

    verdict, reasons = compute_pr_verdict(new_items, fail_on=fail_on)
    actions, omitted_count = build_actions_checklist(
        new_items, categories_touched, dependency_changes, max_items=10
    )

    return PRSummaryFacts(
        version=1,
        pr=pr_details,
        categories_touched=categories_touched,
        findings=findings_group,
        dependency_changes=dependency_changes,
        delta_since_previous_push=delta_since_previous,
        verdict=verdict,
        reasons=reasons,
        actions=actions,
        omitted_actions_count=omitted_count
    )
