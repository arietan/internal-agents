"""
MAS AIRG Compliance Module — shared across all agents.

Provides:
  - Immutable hash-chained audit trail (delegates to core.AuditStore backend)
  - Kill switch / circuit breaker checks
  - Data classification & DLP pre-screening (delegates to core.ContentFilter)
  - Decision Validity Warrant (DVW) builder
  - AI system registry helpers

Backend selection is automatic via CLOUD_PROVIDER env var:
  local (default) — filesystem audit + regex DLP
  aws             — DynamoDB audit + Bedrock Guardrails
  azure           — Cosmos DB audit + AI Content Safety
  gcp             — Firestore audit + Cloud DLP API
"""

import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agents.core.audit import AuditRecord, compute_hash
from agents.core.factory import get_audit, get_config, get_content_filter

log = logging.getLogger("compliance")

AuditRecord = AuditRecord  # re-export for backward compatibility


def write_audit_record(record: AuditRecord) -> str:
    """Write a hash-chained audit record via the configured backend."""
    return get_audit().write_record(record)


def hash_content(content: str) -> str:
    return compute_hash(content)


def verify_chain_integrity() -> dict:
    """Verify the full audit chain via the configured backend."""
    return get_audit().verify_chain()


# ── Kill Switch / Circuit Breaker ────────────────────────────────────────────


class AgentHaltedError(Exception):
    """Raised when the kill switch is active."""
    pass


def check_kill_switch():
    """Check if the agent should halt. Call at the start of every run
    and before every LLM call.
    Raises AgentHaltedError if the kill switch is active.
    """
    env_val = os.environ.get("COMPLIANCE_KILL_SWITCH", "")
    if not env_val:
        env_val = get_config().get_parameter("COMPLIANCE_KILL_SWITCH")
    if env_val.lower() == "true":
        raise AgentHaltedError(
            "Agent operations halted by kill switch (COMPLIANCE_KILL_SWITCH=true). "
            "Contact the AI Oversight Committee to re-enable."
        )

    kill_file = Path("/etc/agent/kill-switch")
    if kill_file.exists():
        reason = kill_file.read_text().strip() or "No reason provided"
        raise AgentHaltedError(f"Agent halted via kill-switch file: {reason}")


# ── Data Classification & DLP ────────────────────────────────────────────────


@dataclass
class DLPFinding:
    pattern_type: str
    location: str
    snippet: str
    severity: str


def scan_for_sensitive_data(content: str, source: str = "prompt") -> list[DLPFinding]:
    """Scan text for sensitive data via the configured ContentFilter backend."""
    findings = get_content_filter().scan(content, source)
    return [
        DLPFinding(
            pattern_type=f.pattern_type,
            location=f.location,
            snippet=f.snippet,
            severity=f.severity,
        )
        for f in findings
    ]


def redact_sensitive_data(content: str) -> str:
    """Redact detected sensitive patterns via the configured ContentFilter backend."""
    return get_content_filter().redact(content)


def classify_data(content: str, file_paths: list[str] = None) -> str:
    """Classify data sensitivity level.
    Returns: public, internal, confidential, restricted
    """
    findings = scan_for_sensitive_data(content)
    if any(f.severity == "critical" for f in findings):
        return "restricted"
    if findings:
        return "confidential"

    restricted_paths = os.environ.get("DLP_DENY_PATTERNS", ".env,credentials,secrets,private").split(",")
    if file_paths:
        for fp in file_paths:
            for deny in restricted_paths:
                if deny.strip() in fp.lower():
                    return "confidential"

    return "internal"


# ── Provider Allowlist ───────────────────────────────────────────────────────


def check_approved_provider(provider: str):
    """Verify that the AI provider is on the approved list."""
    approved_str = os.environ.get("APPROVED_PROVIDERS", "")
    if not approved_str:
        approved_str = get_config().get_parameter("APPROVED_PROVIDERS")
    if not approved_str:
        approved_str = "litellm,ollama,vllm"
    approved = [p.strip().lower() for p in approved_str.split(",")]

    if provider.lower() not in approved:
        raise ValueError(
            f"AI provider '{provider}' is not approved. "
            f"Approved providers: {', '.join(approved)}. "
            "Contact the AI Oversight Committee to request provider approval."
        )


# ── Decision Validity Warrant ────────────────────────────────────────────────


@dataclass
class DecisionValidityWarrant:
    """
    Structured record per MAS AIRG for explaining AI-assisted decisions.
    Documents facts, assumptions, data sources, and logical chain.
    """
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent_name: str = ""
    decision_type: str = ""  # code_generation, code_review, reviewer_assignment

    facts: list = field(default_factory=list)
    assumptions: list = field(default_factory=list)
    data_sources: list = field(default_factory=list)
    temporal_validity: str = ""  # e.g., "valid at time of repository state at commit abc123"
    source_reliability: str = ""
    reasoning_chain: str = ""
    conclusion: str = ""
    confidence_level: str = ""  # high, medium, low
    limitations: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def build_coding_dvw(
    task_context: str,
    codebase_summary_len: int,
    model: str,
    plan: dict,
    repo: str,
    commit: str = "",
) -> DecisionValidityWarrant:
    files = plan.get("files", [])
    return DecisionValidityWarrant(
        agent_name="coding-agent",
        decision_type="code_generation",
        facts=[
            f"Target repository: {repo}",
            f"Task context length: {len(task_context)} chars",
            f"Codebase analysed: {codebase_summary_len} chars of structure/key files",
            f"Files to modify: {len(files)}",
            f"File paths: {[f.get('path', '') for f in files]}",
        ],
        assumptions=[
            "Repository state at clone time is the authoritative source",
            "Project rules and skills configs are current and approved",
            "LLM output follows the structured JSON schema as instructed",
        ],
        data_sources=[
            f"GitHub repository: {repo}",
            "Agent rules config: /etc/agent/rules.yaml",
            "Agent skills config: /etc/agent/skills.yaml",
        ],
        temporal_validity=f"Valid at repository state commit {commit}" if commit else "Valid at clone time",
        source_reliability="Repository is authoritative; LLM output requires human validation",
        reasoning_chain=plan.get("reasoning", ""),
        conclusion=f"Proposed {len(files)} file changes via PR",
        confidence_level="medium",
        limitations=[
            "LLM may hallucinate API calls or dependencies",
            "Generated code not yet validated by test suite",
            "Requires human review before merge",
        ],
    )


def build_review_dvw(
    pr_number: int,
    diff_len: int,
    review: dict,
    model: str,
    repo: str,
    approver_rec: dict,
) -> DecisionValidityWarrant:
    return DecisionValidityWarrant(
        agent_name="pr-review-agent",
        decision_type="code_review",
        facts=[
            f"PR #{pr_number} on {repo}",
            f"Diff size: {diff_len} chars",
            f"Issues found: {len(review.get('issues', []))}",
            f"Risk level assessed: {review.get('risk_level', 'unknown')}",
            f"Recommended approver: {approver_rec.get('recommended', 'none')}",
        ],
        assumptions=[
            "Diff represents the complete set of changes",
            "Review standards in rules.yaml are current",
            "Reviewer scoring is based on current team configuration",
        ],
        data_sources=[
            f"GitHub PR #{pr_number} metadata and diff",
            "Review standards: /etc/agent/rules.yaml",
            "Team config: /etc/agent/reviewers.yaml",
        ],
        temporal_validity=f"Valid at PR state when reviewed",
        source_reliability="PR diff is authoritative; LLM review requires human validation",
        reasoning_chain=review.get("summary", ""),
        conclusion=f"Recommendation: {review.get('recommendation', 'comment')}",
        confidence_level="medium",
        limitations=[
            "LLM may miss subtle bugs that require domain expertise",
            "Review does not replace security audit for critical systems",
            "Reviewer recommendation based on configured rules, not real-time availability",
        ],
    )
