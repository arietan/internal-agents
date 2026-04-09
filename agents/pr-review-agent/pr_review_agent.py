"""
PR Review Agent

Triggered when the coding agent (or any contributor) raises a PR.
Reviews the diff using an LLM, recommends the best human approver
based on CODEOWNERS / git blame / team config, and posts structured
review comments on the PR.

Runs as a K8s Deployment listening for GitHub webhooks, or can be
invoked directly as a one-shot Job.

Environment variables:
  GITHUB_TOKEN           – PAT with repo + pull-request write scope
  TARGET_REPO            – owner/repo (can also come from webhook payload)
  PR_NUMBER              – PR to review (one-shot mode)
  AI_PROVIDER            – "anthropic" | "openai" | "ollama"
  AI_MODEL               – model identifier
  AI_BASE_URL            – for self-hosted models
  MAX_TOKENS             – response budget (default: 8192)
  REVIEWERS_PATH         – path to reviewers YAML (/etc/agent/reviewers.yaml)
  RULES_PATH             – path to review standards (/etc/agent/rules.yaml)
  LANGFUSE_HOST          – Langfuse tracing endpoint
  LANGFUSE_PUBLIC_KEY    – Langfuse public key
  LANGFUSE_SECRET_KEY    – Langfuse secret key
  AUTO_ASSIGN_REVIEWER   – "true" to auto-request review from recommended approver
"""

import json
import logging
import os
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
log = logging.getLogger("pr-review-agent")


@dataclass
class Config:
    github_token: str = ""
    target_repo: str = ""
    pr_number: int = 0
    ai_provider: str = "litellm"
    ai_model: str = "review-model"
    ai_base_url: str = ""
    litellm_api_key: str = "sk-internal-agents-local"
    max_tokens: int = 8192
    reviewers_path: str = "/etc/agent/reviewers.yaml"
    rules_path: str = "/etc/agent/rules.yaml"
    langfuse_host: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    auto_assign_reviewer: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            github_token=os.environ.get("GITHUB_TOKEN", ""),
            target_repo=os.environ.get("TARGET_REPO", ""),
            pr_number=int(os.environ.get("PR_NUMBER", "0")),
            ai_provider=os.environ.get("AI_PROVIDER", "litellm"),
            ai_model=os.environ.get("AI_REVIEW_MODEL", os.environ.get("AI_MODEL", "review-model")),
            ai_base_url=os.environ.get("AI_BASE_URL", ""),
            litellm_api_key=os.environ.get("LITELLM_API_KEY", "sk-internal-agents-local"),
            max_tokens=int(os.environ.get("MAX_TOKENS", "8192")),
            reviewers_path=os.environ.get("REVIEWERS_PATH", "/etc/agent/reviewers.yaml"),
            rules_path=os.environ.get("RULES_PATH", "/etc/agent/rules.yaml"),
            langfuse_host=os.environ.get("LANGFUSE_HOST", ""),
            langfuse_public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
            langfuse_secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
            auto_assign_reviewer=os.environ.get("AUTO_ASSIGN_REVIEWER", "false").lower() == "true",
        )

    @property
    def is_local_model(self) -> bool:
        return self.ai_provider in ("ollama", "litellm", "vllm")


# ── Tracing ──────────────────────────────────────────────────────────────────


class Tracer:
    def __init__(self, cfg: Config):
        self.enabled = bool(cfg.langfuse_host and cfg.langfuse_public_key)
        self.trace = None
        if self.enabled:
            from langfuse import Langfuse
            self.lf = Langfuse(
                host=cfg.langfuse_host,
                public_key=cfg.langfuse_public_key,
                secret_key=cfg.langfuse_secret_key,
            )
            self.trace = self.lf.trace(
                name="pr-review-agent-run",
                metadata={"repo": cfg.target_repo, "pr": cfg.pr_number},
            )

    def generation(self, name: str, **kwargs):
        if self.trace:
            return self.trace.generation(name=name, **kwargs)
        return _Noop()

    def span(self, name: str, **kwargs):
        if self.trace:
            return self.trace.span(name=name, **kwargs)
        return _Noop()

    def flush(self):
        if self.enabled:
            self.lf.flush()


class _Noop:
    def end(self, **_): pass
    def update(self, **_): pass


# ── GitHub helpers ───────────────────────────────────────────────────────────


def gh(cfg: Config, *args: str) -> str:
    env = {**os.environ, "GH_TOKEN": cfg.github_token}
    result = subprocess.run(["gh", *args], capture_output=True, text=True, env=env, check=False)
    if result.returncode != 0:
        log.error("gh failed: %s", result.stderr.strip())
        raise RuntimeError(f"gh failed: {' '.join(args)}")
    return result.stdout.strip()


# ── Diff & PR metadata ──────────────────────────────────────────────────────


def fetch_pr_metadata(cfg: Config) -> dict:
    raw = gh(
        cfg,
        "pr", "view", str(cfg.pr_number),
        "--repo", cfg.target_repo,
        "--json", "title,body,author,labels,files,additions,deletions,baseRefName,headRefName",
    )
    return json.loads(raw)


def fetch_pr_diff(cfg: Config) -> str:
    return gh(
        cfg,
        "pr", "diff", str(cfg.pr_number),
        "--repo", cfg.target_repo,
    )


def fetch_changed_files(cfg: Config) -> list[str]:
    raw = gh(
        cfg,
        "pr", "view", str(cfg.pr_number),
        "--repo", cfg.target_repo,
        "--json", "files",
    )
    data = json.loads(raw)
    return [f["path"] for f in data.get("files", [])]


# ── Reviewer recommendation ─────────────────────────────────────────────────


def load_team_config(path: str) -> dict:
    p = Path(path)
    if p.exists():
        return yaml.safe_load(p.read_text()) or {}
    return {}


def recommend_approver(
    changed_files: list[str],
    team_config: dict,
    pr_author: str,
) -> dict:
    """
    Score each reviewer based on:
      - File path ownership rules (from reviewers.yaml)
      - Expertise tags matching file extensions
      - Availability / workload hints
    Exclude the PR author from recommendations.
    """
    reviewers = team_config.get("reviewers", [])
    if not reviewers:
        return {"recommended": None, "reason": "No reviewers configured"}

    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}

    for reviewer in reviewers:
        name = reviewer["github"]
        if name == pr_author:
            continue

        scores[name] = 0
        reasons[name] = []

        ownership_patterns = reviewer.get("owns", [])
        for pattern in ownership_patterns:
            matching = [f for f in changed_files if _matches_pattern(f, pattern)]
            if matching:
                scores[name] += len(matching) * 10
                reasons[name].append(f"owns {pattern} ({len(matching)} files)")

        expertise = reviewer.get("expertise", [])
        for ext in _extract_extensions(changed_files):
            if ext in expertise:
                scores[name] += 5
                reasons[name].append(f"expertise in {ext}")

        if reviewer.get("lead"):
            scores[name] += 2
            reasons[name].append("team lead")

        workload = reviewer.get("current_prs", 0)
        if workload > 3:
            scores[name] -= 3
            reasons[name].append(f"heavy load ({workload} open PRs)")

    if not scores:
        return {"recommended": None, "reason": "No eligible reviewers (author excluded)"}

    best = max(scores, key=scores.get)
    return {
        "recommended": best,
        "score": scores[best],
        "reason": "; ".join(reasons[best]),
        "all_scores": {k: {"score": v, "reasons": reasons[k]} for k, v in sorted(scores.items(), key=lambda x: -x[1])},
    }


def _matches_pattern(filepath: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return filepath.startswith(prefix)
    if pattern.startswith("*."):
        ext = pattern[1:]
        return filepath.endswith(ext)
    return filepath == pattern


def _extract_extensions(files: list[str]) -> set[str]:
    exts = set()
    for f in files:
        if "." in f:
            exts.add("." + f.rsplit(".", 1)[-1])
    return exts


# ── LLM review ──────────────────────────────────────────────────────────────


REVIEW_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a senior software engineer performing a thorough code review.
    You are constructive, precise, and focus on what matters: bugs, security,
    performance, maintainability, and test coverage. You do not nitpick style
    issues that linters handle.

    You will receive the PR metadata, the diff, and the team's review standards.

    Return a JSON object:
    {
      "summary": "2-3 sentence assessment",
      "risk_level": "low|medium|high|critical",
      "issues": [
        {
          "file": "path/to/file",
          "line": 42,
          "severity": "critical|high|medium|low",
          "category": "bug|security|performance|maintainability|testing",
          "description": "what's wrong",
          "suggestion": "how to fix it"
        }
      ],
      "strengths": ["things done well"],
      "recommendation": "approve|request_changes|comment",
      "reviewer_notes": "any context the human reviewer should know"
    }

    Rules:
    - Only report confident findings. No speculation.
    - Every issue must have a concrete suggestion.
    - Use exact file paths and line numbers from the diff.
    - Return ONLY valid JSON.""")


def build_review_prompt(pr_meta: dict, diff: str, rules: str) -> str:
    parts = []
    parts.append(f"## PR #{pr_meta.get('number', '?')}: {pr_meta.get('title', '')}")
    parts.append(f"**Author:** {pr_meta.get('author', {}).get('login', 'unknown')}")
    parts.append(f"**Base:** {pr_meta.get('baseRefName', '')} ← {pr_meta.get('headRefName', '')}")
    parts.append(f"**Stats:** +{pr_meta.get('additions', 0)} / -{pr_meta.get('deletions', 0)}")

    body = pr_meta.get("body", "")
    if body:
        parts.append(f"\n### PR Description\n{body}")

    if rules:
        parts.append(f"\n### Review Standards\n```yaml\n{rules}\n```")

    parts.append(f"\n### Diff\n```diff\n{diff}\n```")
    return "\n\n".join(parts)


def call_llm(system: str, prompt: str, cfg: Config, tracer: Tracer) -> str:
    """Call the LLM via the configured backend (local/aws/azure/gcp)."""
    from agents.core.factory import get_llm

    gen = tracer.generation(name="review-llm-call", model=cfg.ai_model)
    log.info("Calling LLM (model=%s)", cfg.ai_model)
    resp = get_llm().call(system, prompt, cfg.ai_model, cfg.max_tokens)
    gen.end(output=resp.text[:1000])
    return resp.text


def parse_review(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines[1:] if l.strip() != "```"]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        log.error("Failed to parse review JSON: %s", e)
        return {
            "summary": "Review agent could not produce structured output.",
            "risk_level": "medium",
            "issues": [],
            "strengths": [],
            "recommendation": "comment",
        }


# ── Comment formatting ───────────────────────────────────────────────────────


RISK_EMOJI = {"low": "\U0001f7e2", "medium": "\U0001f7e1", "high": "\U0001f7e0", "critical": "\U0001f534"}
REC_LABEL = {
    "approve": "\u2705 Approve",
    "request_changes": "\u26a0\ufe0f Changes Requested",
    "comment": "\U0001f4ac Comments",
}


def format_review_comment(review: dict, approver_rec: dict) -> str:
    risk = review.get("risk_level", "low")
    rec = review.get("recommendation", "comment")
    issues = review.get("issues", [])

    lines = [
        "## AI Code Review",
        "",
        f"**Risk Level:** {RISK_EMOJI.get(risk, '')} {risk.capitalize()}",
        f"**Recommendation:** {REC_LABEL.get(rec, rec)}",
        "",
        "### Summary",
        review.get("summary", "No summary."),
        "",
    ]

    if issues:
        lines.append(f"### Issues ({len(issues)})")
        lines.append("")
        for i, iss in enumerate(issues, 1):
            sev = iss.get("severity", "low").upper()
            cat = iss.get("category", "general")
            loc = ""
            if iss.get("file"):
                loc = f" `{iss['file']}:{iss.get('line', '')}`"
            lines.append(f"**{i}. [{sev}] [{cat}]**{loc}")
            lines.append(f"  {iss.get('description', '')}")
            if iss.get("suggestion"):
                lines.append(f"  > **Suggestion:** {iss['suggestion']}")
            lines.append("")

    strengths = review.get("strengths", [])
    if strengths:
        lines.append("### Strengths")
        for s in strengths:
            lines.append(f"- {s}")
        lines.append("")

    lines.append("### Recommended Approver")
    if approver_rec.get("recommended"):
        lines.append(f"**@{approver_rec['recommended']}** — {approver_rec.get('reason', '')}")
        all_scores = approver_rec.get("all_scores", {})
        if len(all_scores) > 1:
            lines.append("")
            lines.append("<details><summary>All candidate scores</summary>")
            lines.append("")
            lines.append("| Reviewer | Score | Reasons |")
            lines.append("|----------|-------|---------|")
            for name, info in all_scores.items():
                reasons = "; ".join(info.get("reasons", []))
                lines.append(f"| @{name} | {info.get('score', 0)} | {reasons} |")
            lines.append("")
            lines.append("</details>")
    else:
        lines.append(f"*{approver_rec.get('reason', 'Could not determine approver')}*")

    lines.append("")
    lines.append("---")
    lines.append("*Automated review by PR Review Agent. Human approval is still required.*")

    return "\n".join(lines)


# ── Actions ──────────────────────────────────────────────────────────────────


def post_review_comment(cfg: Config, comment: str):
    gh(
        cfg,
        "pr", "comment", str(cfg.pr_number),
        "--repo", cfg.target_repo,
        "--body", comment,
    )
    log.info("Posted review comment on PR #%d", cfg.pr_number)


def assign_reviewer(cfg: Config, reviewer: str):
    gh(
        cfg,
        "pr", "edit", str(cfg.pr_number),
        "--repo", cfg.target_repo,
        "--add-reviewer", reviewer,
    )
    log.info("Assigned @%s as reviewer on PR #%d", reviewer, cfg.pr_number)


# ── Main ─────────────────────────────────────────────────────────────────────


def review_pr(cfg: Config):
    from agents.telemetry import init_telemetry, record_run, record_review_posted, record_llm_call, trace_span
    from agents.compliance import (
        AuditRecord, write_audit_record, hash_content,
        check_kill_switch, check_approved_provider,
        scan_for_sensitive_data, redact_sensitive_data, classify_data,
        build_review_dvw,
    )
    import time as _time
    import uuid as _uuid

    cfg.github_token = cfg.github_token or os.environ.get("GITHUB_TOKEN", "")
    if not cfg.github_token or not cfg.target_repo or not cfg.pr_number:
        log.error("GITHUB_TOKEN, TARGET_REPO, and PR_NUMBER are required")
        sys.exit(1)

    init_telemetry("pr-review-agent")
    tracer = Tracer(cfg)

    run_id = str(_uuid.uuid4())
    record_run("pr-review-agent")

    check_kill_switch()
    check_approved_provider(cfg.ai_provider)

    write_audit_record(AuditRecord(
        run_id=run_id, agent_name="pr-review-agent", event_type="run_start",
        model_provider=cfg.ai_provider, model_name=cfg.ai_model,
        target_repo=cfg.target_repo, pr_number=cfg.pr_number,
    ))

    with trace_span("pr-review-full-run", {"repo": cfg.target_repo, "pr": cfg.pr_number}) as root_span:
        log.info("Reviewing PR #%d on %s (run_id=%s)", cfg.pr_number, cfg.target_repo, run_id)

        # 1. Fetch PR info and diff
        with trace_span("fetch-pr-data"):
            pr_meta = fetch_pr_metadata(cfg)
            pr_meta["number"] = cfg.pr_number
            diff = fetch_pr_diff(cfg)
            changed_files = fetch_changed_files(cfg)

        if not diff.strip():
            log.info("Empty diff — nothing to review.")
            return

        max_diff = 150_000
        if len(diff) > max_diff:
            log.warning("Diff too large (%d chars), truncating", len(diff))
            diff = diff[:max_diff] + "\n\n[... diff truncated ...]"

        # 2. DLP scan on diff content
        dlp_findings = scan_for_sensitive_data(diff, source="pr_diff")
        data_class = classify_data(diff, changed_files)
        if dlp_findings:
            log.warning("DLP: %d sensitive patterns in PR diff — redacting before LLM", len(dlp_findings))
            diff = redact_sensitive_data(diff)
            write_audit_record(AuditRecord(
                run_id=run_id, agent_name="pr-review-agent", event_type="dlp_finding",
                target_repo=cfg.target_repo, pr_number=cfg.pr_number,
                data_classification=data_class,
                compliance_flags=[f.pattern_type for f in dlp_findings],
            ))

        # 3. Load review rules and team config
        rules = ""
        rules_path = Path(cfg.rules_path)
        if rules_path.exists():
            rules = rules_path.read_text()

        team_config = load_team_config(cfg.reviewers_path)
        pr_author = pr_meta.get("author", {}).get("login", "")

        # 4. Recommend approver
        with trace_span("recommend-approver"):
            approver_rec = recommend_approver(changed_files, team_config, pr_author)
            log.info("Recommended approver: %s (score=%s)", approver_rec.get("recommended"), approver_rec.get("score"))

        check_kill_switch()

        # 5. LLM review
        llm_start = _time.monotonic()
        llm_error = False
        with trace_span("llm-review", {"provider": cfg.ai_provider, "model": cfg.ai_model}):
            prompt = build_review_prompt(pr_meta, diff, rules)
            log.info("Sending %d chars to %s for review", len(prompt), cfg.ai_provider)
            try:
                raw = call_llm(REVIEW_SYSTEM_PROMPT, prompt, cfg, tracer)
            except Exception:
                llm_error = True
                raise
            finally:
                duration = _time.monotonic() - llm_start
                record_llm_call("pr-review-agent", cfg.ai_provider, cfg.ai_model, duration, error=llm_error)

        write_audit_record(AuditRecord(
            run_id=run_id, agent_name="pr-review-agent", event_type="llm_call",
            model_provider=cfg.ai_provider, model_name=cfg.ai_model,
            target_repo=cfg.target_repo, pr_number=cfg.pr_number,
            input_hash=hash_content(REVIEW_SYSTEM_PROMPT + prompt),
            output_hash=hash_content(raw),
            input_size_bytes=len((REVIEW_SYSTEM_PROMPT + prompt).encode()),
            output_size_bytes=len(raw.encode()),
            input_content=REVIEW_SYSTEM_PROMPT + "\n---\n" + prompt,
            output_content=raw,
            data_classification=data_class,
        ))

        review = parse_review(raw)
        issue_count = len(review.get("issues", []))
        recommendation = review.get("recommendation", "comment")
        log.info("Review: %d issues, recommendation=%s", issue_count, recommendation)

        # 6. Build Decision Validity Warrant
        dvw = build_review_dvw(
            pr_number=cfg.pr_number, diff_len=len(diff),
            review=review, model=cfg.ai_model,
            repo=cfg.target_repo, approver_rec=approver_rec,
        )

        # 7. Post comment
        with trace_span("post-review"):
            comment = format_review_comment(review, approver_rec)
            post_review_comment(cfg, comment)
        record_review_posted("pr-review-agent", recommendation)

        # 8. Auto-assign reviewer if configured
        if cfg.auto_assign_reviewer and approver_rec.get("recommended"):
            with trace_span("assign-reviewer"):
                assign_reviewer(cfg, approver_rec["recommended"])

        # 9. Full compliance audit record
        write_audit_record(AuditRecord(
            run_id=run_id, agent_name="pr-review-agent", event_type="review_posted",
            model_provider=cfg.ai_provider, model_name=cfg.ai_model,
            target_repo=cfg.target_repo, pr_number=cfg.pr_number,
            risk_level=review.get("risk_level", "unknown"),
            recommendation=recommendation,
            human_approver=approver_rec.get("recommended", ""),
            human_action="pending",
            dvw_facts=dvw.facts,
            dvw_assumptions=dvw.assumptions,
            dvw_reasoning=dvw.reasoning_chain,
            data_classification=data_class,
        ))

        root_span.set_attribute("issues_found", issue_count)
        root_span.set_attribute("recommendation", recommendation)
        root_span.set_attribute("approver", approver_rec.get("recommended", ""))
        root_span.set_attribute("run_id", run_id)
        tracer.flush()


if __name__ == "__main__":
    try:
        config = Config.from_env()
        review_pr(config)
    except Exception:
        log.exception("PR review agent failed")
        sys.exit(1)
