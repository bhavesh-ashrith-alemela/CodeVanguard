"""
End-to-End Auto-Fix Pipeline Orchestrator.
Coordinates context extraction, LLM patch generation, verification, and retry loop.
"""
import uuid
import logging
from typing import Dict, Any, Optional, Set

from app.services.autofix.context import extract_minimal_context
from app.services.autofix.prompts import build_autofix_prompt, AUTOFIX_SYSTEM_PROMPT
from app.services.autofix.verifier import verify_patch, VerificationResult
from app.services.autofix.llm.client import get_llm_client, LLMResponse
from app.utils.db import (
    save_fix_attempt, get_repo_daily_fix_count, update_fix_attempt_status
)

logger = logging.getLogger(__name__)

async def run_autofix_pipeline(
    repo: Dict[str, Any],
    finding: Dict[str, Any],
    file_content: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    existing_file_fingerprints: Optional[Set[str]] = None
) -> Dict[str, Any]:
    """
    Executes the verified auto-fix generation workflow:
    1. Quota & Opt-in validation
    2. Minimal AST context extraction & secret redaction
    3. LLM generation with untrusted code delimiters
    4. Verification pipeline (syntax check + Bandit/Semgrep re-scan)
    5. Retry 1x with feedback if verification fails
    6. Persists result in fix_attempts table
    """
    repo_id = repo["id"]
    finding_id = str(finding.get("id") or finding.get("finding_id", ""))
    fingerprint = str(finding.get("fingerprint", ""))
    rule_id = str(finding.get("rule_id", "security_issue"))
    severity = str(finding.get("severity", "high"))
    filepath = str(finding.get("filepath", "code.py"))
    line_number = int(finding.get("line_number") or 1)
    message = str(finding.get("message") or finding.get("fix_description") or "Security vulnerability detected.")

    # 1. Opt-In & Quota Validation
    if not repo.get("autofix_enabled"):
        raise ValueError(
            "Auto-fix is disabled for this repository. Enable it in Repository Settings with the disclosure."
        )

    daily_quota = int(repo.get("autofix_daily_quota") or 20)
    current_count = get_repo_daily_fix_count(repo_id)
    if current_count >= daily_quota:
        raise ValueError(
            f"Daily auto-fix quota exceeded for this repository ({current_count}/{daily_quota}). Quota resets at midnight UTC."
        )

    # 2. Extract Minimal Context
    context = extract_minimal_context(file_content, filepath, line_number)

    # 3. Initialize LLM Client
    client = get_llm_client(provider=provider, model=model)
    attempt_id = uuid.uuid4().hex

    # Record initial queued attempt
    save_fix_attempt(
        attempt_id=attempt_id,
        finding_id=finding_id,
        repo_id=repo_id,
        status="generated",
        provider=client.__class__.__name__.replace("Client", "").lower(),
        model=client.model or "default",
        target_file=filepath,
        target_function=context.function_name,
        start_line=context.start_line,
        end_line=context.end_line
    )

    # 4. Generate Initial Patch
    prompt = build_autofix_prompt(context, rule_id, severity, message)
    total_tokens_in = 0
    total_tokens_out = 0
    total_cost = 0.0

    llm_resp: LLMResponse = client.generate_patch(prompt, AUTOFIX_SYSTEM_PROMPT)
    total_tokens_in += llm_resp.tokens_in
    total_tokens_out += llm_resp.tokens_out
    total_cost += llm_resp.cost_usd

    parsed_json = llm_resp.parsed_json or {}
    patched_function = parsed_json.get("patched_function") or ""
    explanation = parsed_json.get("explanation") or "Security vulnerability resolved via minimal patch."

    # 5. Verification Attempt 1
    v_res: VerificationResult = await verify_patch(
        original_content=file_content,
        patched_function=patched_function,
        filepath=filepath,
        start_line=context.start_line,
        end_line=context.end_line,
        original_fingerprint=fingerprint,
        existing_file_fingerprints=existing_file_fingerprints
    )

    # 6. Retry 1x with verification error if initial verification failed
    if not v_res.is_verified and v_res.rejection_reason:
        logger.info(f"Auto-fix attempt 1 failed verification: {v_res.rejection_reason}. Retrying 1x with feedback...")
        retry_prompt = build_autofix_prompt(
            context, rule_id, severity, message, verification_feedback=v_res.rejection_reason
        )
        try:
            retry_resp = client.generate_patch(retry_prompt, AUTOFIX_SYSTEM_PROMPT)
            total_tokens_in += retry_resp.tokens_in
            total_tokens_out += retry_resp.tokens_out
            total_cost += retry_resp.cost_usd

            retry_json = retry_resp.parsed_json or {}
            if retry_json.get("patched_function"):
                patched_function = retry_json.get("patched_function")
                explanation = retry_json.get("explanation") or explanation

                v_res = await verify_patch(
                    original_content=file_content,
                    patched_function=patched_function,
                    filepath=filepath,
                    start_line=context.start_line,
                    end_line=context.end_line,
                    original_fingerprint=fingerprint,
                    existing_file_fingerprints=existing_file_fingerprints
                )
        except Exception as re_err:
            logger.warning(f"Auto-fix retry call error: {re_err}")

    # 7. Final Status & Persistence
    final_status = "verified" if v_res.is_verified else "rejected"
    verification_payload = {
        "is_verified": v_res.is_verified,
        "scanners_run": v_res.scanners_run,
        "syntax_valid": v_res.syntax_valid,
        "original_fingerprint_resolved": v_res.original_fingerprint_resolved,
        "new_findings_count": v_res.new_findings_count
    }

    result = save_fix_attempt(
        attempt_id=attempt_id,
        finding_id=finding_id,
        repo_id=repo_id,
        status=final_status,
        provider=client.__class__.__name__.replace("Client", "").lower(),
        model=client.model or "default",
        target_file=filepath,
        target_function=context.function_name,
        start_line=context.start_line,
        end_line=context.end_line,
        diff=v_res.diff,
        patch_code=v_res.patched_file_content if v_res.is_verified else None,
        explanation=explanation,
        verification_json=verification_payload,
        rejection_reason=v_res.rejection_reason,
        tokens_in=total_tokens_in,
        tokens_out=total_tokens_out,
        cost_usd=total_cost
    )

    return result
