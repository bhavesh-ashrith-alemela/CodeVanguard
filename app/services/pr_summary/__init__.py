"""
Pull Request Summary Service: Deterministic Facts, Pure Renderers, and Hallucination-Defended Narrative.
"""
from app.services.pr_summary.models import (
    PRSummaryFacts, PRDetails, FindingSummaryItem, FindingsGroup,
    DependencyChange, PushDelta, ActionItem
)
from app.services.pr_summary.facts import build_pr_summary_facts
from app.services.pr_summary.renderers import to_markdown_comment, to_check_summary, to_json
from app.services.pr_summary.narrative import generate_pr_narrative, validate_narrative

__all__ = [
    "PRSummaryFacts",
    "PRDetails",
    "FindingSummaryItem",
    "FindingsGroup",
    "DependencyChange",
    "PushDelta",
    "ActionItem",
    "build_pr_summary_facts",
    "to_markdown_comment",
    "to_check_summary",
    "to_json",
    "generate_pr_narrative",
    "validate_narrative",
]
