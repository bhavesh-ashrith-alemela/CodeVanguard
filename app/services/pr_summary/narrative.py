"""
Optional LLM Reviewer Narrative with Strict Anti-Hallucination Validation.
Only operates on deterministic facts JSON. Never consumes or persists source code.
"""
import os
import re
import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, List, Set, Optional, Tuple

from app.services.pr_summary.models import PRSummaryFacts

logger = logging.getLogger(__name__)

def extract_valid_integers_from_facts(facts: PRSummaryFacts) -> Set[int]:
    """
    Extracts the exhaustive whitelist of valid integers from PRSummaryFacts.
    Any integer in the LLM narrative outside this set is considered a hallucination.
    """
    valid_ints: Set[int] = {0, 1} # 0 and 1 are basic linguistic constants (singular/plural)

    # PR details
    valid_ints.add(facts.pr.number)
    valid_ints.add(facts.pr.files_changed)
    valid_ints.add(facts.pr.additions)
    valid_ints.add(facts.pr.deletions)

    # Findings counts
    new_findings = facts.findings.new
    fixed_findings = facts.findings.fixed
    existing_touched = facts.findings.existing_touched

    valid_ints.add(len(new_findings))
    valid_ints.add(len(fixed_findings))
    valid_ints.add(len(existing_touched))
    valid_ints.add(facts.findings.hidden_existing_count)
    valid_ints.add(facts.findings.hidden_existing_count + len(existing_touched))

    # Severity counts
    crit = sum(1 for f in new_findings if f.severity.lower() == "critical")
    high = sum(1 for f in new_findings if f.severity.lower() == "high")
    med = sum(1 for f in new_findings if f.severity.lower() == "medium")
    low = sum(1 for f in new_findings if f.severity.lower() == "low")
    valid_ints.update({crit, high, med, low})

    # Line numbers
    for f in new_findings + fixed_findings + existing_touched:
        if f.line > 0:
            valid_ints.add(f.line)

    # Dependency changes
    valid_ints.add(len(facts.dependency_changes))

    # Delta counts
    valid_ints.add(facts.delta_since_previous_push.new_count)
    valid_ints.add(facts.delta_since_previous_push.fixed_count)
    valid_ints.add(abs(facts.delta_since_previous_push.delta_new))
    valid_ints.add(abs(facts.delta_since_previous_push.delta_fixed))

    # Actions counts
    valid_ints.add(len(facts.actions))
    valid_ints.add(facts.omitted_actions_count)

    return valid_ints

def validate_narrative(
    facts: PRSummaryFacts,
    narrative_text: str,
    referenced_finding_ids: List[str]
) -> Tuple[bool, Optional[str]]:
    """
    Validates LLM-generated narrative against facts:
    1. Integer Whitelist: Every integer in text MUST exist in facts.
    2. Finding ID Whitelist: Every referenced finding ID MUST exist in facts.
    3. Verdict Consistency: Narrative sentiment must not contradict the deterministic verdict.
    """
    if not narrative_text or not isinstance(narrative_text, str):
        return False, "Narrative text is empty or invalid."

    # 1. Hallucinated Integer Defense
    valid_integers = extract_valid_integers_from_facts(facts)
    found_integers = re.findall(r'\b\d+\b', narrative_text)
    for raw_int in found_integers:
        val = int(raw_int)
        if val not in valid_integers:
            return False, f"Hallucinated integer detected: '{val}' does not exist in deterministic facts."

    # 2. Finding ID Whitelist Defense
    known_finding_ids: Set[str] = set()
    for f in facts.findings.new + facts.findings.fixed + facts.findings.existing_touched:
        if f.finding_id:
            known_finding_ids.add(str(f.finding_id))

    for fid in referenced_finding_ids:
        if str(fid) not in known_finding_ids:
            return False, f"Hallucinated finding ID detected: '{fid}' does not exist in findings."

    # 3. Verdict Consistency Defense
    lower_text = narrative_text.lower()
    if facts.verdict == "block":
        contradictory_phrases = ["all checks passed", "ready to merge", "zero vulnerabilities", "is safe to merge"]
        for phrase in contradictory_phrases:
            if phrase in lower_text:
                return False, f"Verdict contradiction: Blocked PR described as '{phrase}'."
    elif facts.verdict == "safe":
        contradictory_phrases = ["blocked", "action required before merge", "critical vulnerability detected", "failed security gate"]
        for phrase in contradictory_phrases:
            if phrase in lower_text:
                return False, f"Verdict contradiction: Safe PR described as '{phrase}'."

    return True, None

def build_template_narrative(facts: PRSummaryFacts) -> str:
    """
    Produces a crisp, 2-3 sentence deterministic narrative directly from facts.
    Guaranteed zero hallucination.
    """
    pr_num = facts.pr.number
    files_changed = facts.pr.files_changed
    new_findings = facts.findings.new
    crit_count = sum(1 for f in new_findings if f.severity.lower() == "critical")
    high_count = sum(1 for f in new_findings if f.severity.lower() == "high")
    med_count = sum(1 for f in new_findings if f.severity.lower() == "medium")
    low_count = sum(1 for f in new_findings if f.severity.lower() == "low")
    fixed_count = len(facts.findings.fixed)

    if facts.verdict == "safe":
        if fixed_count > 0:
            return (
                f"Pull request #{pr_num} resolves {fixed_count} baseline finding(s) with zero new security vulnerabilities "
                f"introduced across {files_changed} modified file(s). All static analysis security checks passed."
            )
        return (
            f"Pull request #{pr_num} introduces zero new security findings across {files_changed} modified file(s). "
            f"All static analysis checks passed without blocking issues."
        )
    elif facts.verdict == "block":
        return (
            f"Pull request #{pr_num} introduces {len(new_findings)} new finding(s) including {crit_count} Critical "
            f"and {high_count} High severity issue(s) that exceed repository security gates. "
            f"Remediation is required prior to merge."
        )
    else: # attention
        return (
            f"Pull request #{pr_num} introduces {len(new_findings)} new finding(s) ({med_count} Medium, {low_count} Low) "
            f"across {files_changed} modified file(s). Review of highlighted findings is recommended before merging."
        )

def generate_pr_narrative(
    facts: PRSummaryFacts,
    narrative_enabled: bool = False
) -> Dict[str, Any]:
    """
    Generates a 2-3 sentence summary.
    If narrative_enabled is True and an LLM API key is present:
    queries the LLM with facts JSON only, validates the response with strict anti-hallucination checks,
    and returns LLM narrative or falls back safely to the deterministic template.
    """
    if not narrative_enabled:
        return {
            "text": build_template_narrative(facts),
            "referenced_finding_ids": [],
            "source": "template",
            "model": None
        }

    gemini_key = os.environ.get("GEMINI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    if not gemini_key and not openai_key:
        return {
            "text": build_template_narrative(facts),
            "referenced_finding_ids": [],
            "source": "template",
            "model": None
        }

    facts_dict = facts.model_dump() if hasattr(facts, "model_dump") else facts.dict()

    prompt = (
        "You are an expert security reviewer. You are given a JSON object of deterministic SAST facts "
        "about a pull request. Write a concise 2 to 3 sentence executive summary for the pull request reviewer.\n"
        "STRICT REQUIREMENTS:\n"
        "1. Mention ONLY facts and numbers present in the JSON input. Do NOT invent or estimate any counts or line numbers.\n"
        "2. Return ONLY a valid JSON object matching this schema: "
        '{"text": "2-3 sentence summary", "referenced_finding_ids": ["optional_id_1"]}\n'
        "3. Do not include markdown code block backticks around the JSON.\n\n"
        f"FACTS:\n{json.dumps(facts_dict)}"
    )

    try:
        if gemini_key:
            model_name = "gemini-1.5-flash"
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}
            }
            req = urllib.request.Request(
                api_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                candidate = resp_data["candidates"][0]["content"]["parts"][0]["text"]
        elif openai_key:
            model_name = "gpt-4o-mini"
            api_url = "https://api.openai.com/v1/chat/completions"
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "response_format": {"type": "json_object"}
            }
            req = urllib.request.Request(
                api_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {openai_key}"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                candidate = resp_data["choices"][0]["message"]["content"]

        # Parse LLM JSON
        parsed = json.loads(candidate.strip())
        narrative_text = parsed.get("text", "")
        ref_ids = parsed.get("referenced_finding_ids", [])

        # Validate strictly
        is_valid, error = validate_narrative(facts, narrative_text, ref_ids)
        if is_valid:
            return {
                "text": narrative_text,
                "referenced_finding_ids": ref_ids,
                "source": "llm",
                "model": model_name
            }
        else:
            logger.warning(f"LLM narrative rejected by anti-hallucination validator: {error}. Falling back to template.")
    except Exception as e:
        logger.warning(f"Failed to generate LLM narrative: {e}. Falling back to template.")

    return {
        "text": build_template_narrative(facts),
        "referenced_finding_ids": [],
        "source": "template",
        "model": None
    }
