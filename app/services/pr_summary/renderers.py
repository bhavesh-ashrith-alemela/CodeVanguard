"""
Pure Renderers for Pull Request Security Summaries.
Enforces character caps (60k for PR sticky comment, 65k for Check Run summary),
details collapse tags, and zero duplicate comments.
"""
import json
from typing import Optional

from app.services.pr_summary.models import PRSummaryFacts

STICKY_COMMENT_MARKER = "<!-- codevanguard-sticky-pr-comment -->"
MAX_PR_COMMENT_LENGTH = 60000
MAX_CHECK_SUMMARY_LENGTH = 65000

def to_markdown_comment(
    facts: PRSummaryFacts,
    narrative: Optional[str] = None,
    dashboard_url: str = ""
) -> str:
    """
    Renders the deterministic sticky PR comment in Markdown.
    Includes the hidden update marker, verdict, checklist, delta strip,
    categories touched, and collapsible details for long lists.
    Guaranteed strictly <= 60,000 characters.
    """
    lines = [
        STICKY_COMMENT_MARKER,
        "## 🛡️ CodeVanguard Security Review",
        ""
    ]

    # 1. Verdict Banner
    verdict_badges = {
        "block": "⛔ **BLOCK** — Action required before merge",
        "attention": "⚠️ **ATTENTION** — Review recommended",
        "safe": "✅ **SAFE** — All static security checks passed"
    }
    verdict_title = verdict_badges.get(facts.verdict, facts.verdict.upper())
    lines.append(f"### Verdict: {verdict_title}\n")

    if facts.reasons:
        for r in facts.reasons:
            lines.append(f"- {r}")
        lines.append("")

    # 2. Verified Narrative (if present)
    if narrative:
        clean_narrative = narrative.strip()
        lines.append(f"> 💬 **Reviewer Summary**:\n> {clean_narrative}\n")

    # 3. Needs Before Merge (Checklist)
    if facts.actions:
        lines.append("### 📋 Needs Before Merge")
        lines.append("Complete the following checklist prior to merging this pull request:\n")
        for act in facts.actions:
            location = f" (`{act.file}:{act.line}`)" if act.file and act.line else ""
            lines.append(f"- [ ] **{act.title}**{location}: {act.description}")
        if facts.omitted_actions_count > 0:
            lines.append(f"\n*... and {facts.omitted_actions_count} additional action item(s) (view all in dashboard).*")
        lines.append("")
    elif facts.verdict == "safe":
        lines.append("### 📋 Needs Before Merge\n- [x] All security checks clear — ready for code review.\n")

    # 4. Findings Delta & Metrics
    new_findings = facts.findings.new
    crit = sum(1 for f in new_findings if f.severity.lower() == "critical")
    high = sum(1 for f in new_findings if f.severity.lower() == "high")
    med = sum(1 for f in new_findings if f.severity.lower() == "medium")
    low = sum(1 for f in new_findings if f.severity.lower() == "low")

    lines.append("### 📊 Findings Delta")
    lines.append(f"- **New Findings:** +{len(new_findings)} ({crit} Critical, {high} High, {med} Medium, {low} Low)")
    lines.append(f"- **Fixed Baseline Findings:** -{len(facts.findings.fixed)}")
    lines.append(f"- **Existing Baseline Findings:** {facts.findings.hidden_existing_count + len(facts.findings.existing_touched)} ({len(facts.findings.existing_touched)} in touched files)")

    if facts.delta_since_previous_push.previous_head_sha:
        prev_sha = facts.delta_since_previous_push.previous_head_sha[:7]
        d_new = facts.delta_since_previous_push.delta_new
        d_fixed = facts.delta_since_previous_push.delta_fixed
        lines.append(f"- **Push Delta (vs {prev_sha}):** {d_new:+d} new, {d_fixed:+d} fixed")
    lines.append("")

    # 5. Categories Touched Chips
    if facts.categories_touched:
        chips = " ".join([f"`{cat}`" for cat in facts.categories_touched])
        lines.append(f"**Categories Touched:** {chips}\n")

    # 6. Collapsible Details: New Findings
    if new_findings:
        lines.append(f"<details><summary><b>🔍 View All New Findings ({len(new_findings)})</b></summary>\n")
        lines.append("| Severity | Rule | Location | Description |")
        lines.append("| :--- | :--- | :--- | :--- |")
        for f in new_findings:
            loc = f"`{f.file}:{f.line}`"
            clean_msg = f.message.replace("|", "\\|").replace("\n", " ").strip()
            lines.append(f"| **{f.severity.upper()}** | `{f.rule_id}` | {loc} | {clean_msg} |")
        lines.append("\n</details>\n")

    # 7. Collapsible Details: Dependency Changes
    if facts.dependency_changes:
        lines.append(f"<details><summary><b>📦 Dependency Changes ({len(facts.dependency_changes)})</b></summary>\n")
        lines.append("| Ecosystem | Package | Change | Version | Previous Version | Manifest |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for dep in facts.dependency_changes:
            prev = dep.previous_version or "—"
            ver = dep.version or "—"
            lines.append(f"| {dep.ecosystem} | `{dep.name}` | {dep.change_type} | `{ver}` | `{prev}` | `{dep.manifest_file}` |")
        lines.append("\n</details>\n")

    # 8. Collapsible Details: Fixed Baseline Findings
    if facts.findings.fixed:
        lines.append(f"<details><summary><b>✅ Resolved Baseline Findings ({len(facts.findings.fixed)})</b></summary>\n")
        for fix in facts.findings.fixed:
            lines.append(f"- **[{fix.severity.upper()}]** `{fix.rule_id}` in `{fix.file}:{fix.line}`")
        lines.append("\n</details>\n")

    # 9. Dashboard Link & Ephemeral Sandbox Footer
    if dashboard_url:
        lines.append(f"[👉 Open Full Interactive Report & Blueprints in CodeVanguard]({dashboard_url})\n")
    lines.append("*Scanned with Bandit & Semgrep in an ephemeral isolated sandbox. Source code is never stored.*")

    content = "\n".join(lines)

    # Enforce strict 60,000 characters limit
    if len(content) > MAX_PR_COMMENT_LENGTH:
        truncation_notice = "\n\n*(Truncated: full findings list exceeds GitHub comment limit. View complete report in dashboard.)*"
        cutoff = MAX_PR_COMMENT_LENGTH - len(truncation_notice)
        content = content[:cutoff] + truncation_notice

    return content

def to_check_summary(
    facts: PRSummaryFacts,
    narrative: Optional[str] = None,
    dashboard_url: str = ""
) -> str:
    """
    Renders the GitHub Check Run markdown summary.
    Guaranteed strictly <= 65,000 characters.
    """
    lines = [
        "## 🛡️ CodeVanguard SAST Check Run Summary",
        ""
    ]

    verdict_badges = {
        "block": "⛔ **BLOCK** — Action required before merge",
        "attention": "⚠️ **ATTENTION** — Review recommended",
        "safe": "✅ **SAFE** — All static security checks passed"
    }
    lines.append(f"### Verdict: {verdict_badges.get(facts.verdict, facts.verdict.upper())}\n")

    if facts.reasons:
        for r in facts.reasons:
            lines.append(f"- {r}")
        lines.append("")

    if narrative:
        lines.append(f"> 💬 **Reviewer Summary**:\n> {narrative.strip()}\n")

    if facts.actions:
        lines.append("### 📋 Needs Before Merge")
        for act in facts.actions:
            location = f" (`{act.file}:{act.line}`)" if act.file and act.line else ""
            lines.append(f"- [ ] **{act.title}**{location}: {act.description}")
        if facts.omitted_actions_count > 0:
            lines.append(f"\n*... and {facts.omitted_actions_count} additional action item(s).*")
        lines.append("")

    new_findings = facts.findings.new
    crit = sum(1 for f in new_findings if f.severity.lower() == "critical")
    high = sum(1 for f in new_findings if f.severity.lower() == "high")
    med = sum(1 for f in new_findings if f.severity.lower() == "medium")
    low = sum(1 for f in new_findings if f.severity.lower() == "low")

    lines.append("### 📊 Findings Delta")
    lines.append(f"- **New Findings:** +{len(new_findings)} ({crit} Critical, {high} High, {med} Medium, {low} Low)")
    lines.append(f"- **Fixed Baseline Findings:** -{len(facts.findings.fixed)}")
    lines.append(f"- **Existing Baseline Findings:** {facts.findings.hidden_existing_count + len(facts.findings.existing_touched)}")

    if facts.delta_since_previous_push.previous_head_sha:
        prev_sha = facts.delta_since_previous_push.previous_head_sha[:7]
        lines.append(f"- **Push Delta (vs {prev_sha}):** {facts.delta_since_previous_push.delta_new:+d} new, {facts.delta_since_previous_push.delta_fixed:+d} fixed")
    lines.append("")

    if facts.categories_touched:
        chips = " ".join([f"`{cat}`" for cat in facts.categories_touched])
        lines.append(f"**Categories Touched:** {chips}\n")

    if new_findings:
        lines.append(f"<details><summary><b>🔍 View All New Findings ({len(new_findings)})</b></summary>\n")
        lines.append("| Severity | Rule | Location | Description |")
        lines.append("| :--- | :--- | :--- | :--- |")
        for f in new_findings:
            clean_msg = f.message.replace("|", "\\|").replace("\n", " ").strip()
            lines.append(f"| **{f.severity.upper()}** | `{f.rule_id}` | `{f.file}:{f.line}` | {clean_msg} |")
        lines.append("\n</details>\n")

    if facts.dependency_changes:
        lines.append(f"<details><summary><b>📦 Dependency Changes ({len(facts.dependency_changes)})</b></summary>\n")
        for dep in facts.dependency_changes:
            lines.append(f"- `{dep.name}` ({dep.ecosystem}): {dep.change_type} {dep.version or ''}")
        lines.append("\n</details>\n")

    if dashboard_url:
        lines.append(f"\n[👉 Open Full Interactive Report in CodeVanguard]({dashboard_url})\n")

    content = "\n".join(lines)

    if len(content) > MAX_CHECK_SUMMARY_LENGTH:
        truncation_notice = "\n\n*(Truncated: summary exceeds GitHub Check Run output limit. View full report in dashboard.)*"
        cutoff = MAX_CHECK_SUMMARY_LENGTH - len(truncation_notice)
        content = content[:cutoff] + truncation_notice

    return content

def to_json(facts: PRSummaryFacts) -> str:
    """Serializes PRSummaryFacts to JSON string."""
    try:
        return facts.model_dump_json(indent=2)
    except AttributeError:
        return json.dumps(facts.dict(), indent=2)
