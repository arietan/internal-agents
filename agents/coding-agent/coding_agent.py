"""
Internal Coding Agent

Analyzes a target repository, generates implementation changes guided by
project rules/skills/context, and raises a pull request.  Designed to run as
a Kubernetes Job or CronJob on a local cluster.

Trigger modes
─────────────
  schedule  – CronJob fires at a configured interval
  merge     – A webhook listener posts a Job when a PR merges

Environment variables (all configurable via K8s ConfigMap / Secret):
  GITHUB_TOKEN         – PAT with repo + pull-request write scope
  TARGET_REPO          – owner/repo to operate on
  TARGET_BRANCH        – base branch (default: main)
  CONTEXT_SOURCE       – "issues" | "roadmap_file" | "manual"
  CONTEXT_ISSUE_LABEL  – GitHub label to pick work items (default: ai-agent)
  ROADMAP_PATH         – path inside repo for roadmap/backlog file
  MANUAL_PROMPT        – free-form task description (CONTEXT_SOURCE=manual)
  AI_PROVIDER          – "anthropic" | "openai" | "ollama"
  AI_MODEL             – model identifier
  AI_BASE_URL          – base URL for self-hosted models (Ollama / vLLM)
  MAX_TOKENS           – response token budget (default: 8192)
  LANGFUSE_HOST        – Langfuse endpoint for tracing
  LANGFUSE_PUBLIC_KEY  – Langfuse public key
  LANGFUSE_SECRET_KEY  – Langfuse secret key
  SKILLS_PATH          – path to skills YAML inside the container
  RULES_PATH           – path to rules YAML inside the container
  DRY_RUN              – "true" to skip PR creation (default: false)
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import textwrap
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
log = logging.getLogger("coding-agent")

# ── Configuration ────────────────────────────────────────────────────────────


@dataclass
class Config:
    github_token: str = ""
    target_repo: str = ""
    target_branch: str = "main"
    context_source: str = "issues"
    context_issue_label: str = "ai-agent"
    roadmap_path: str = ""
    manual_prompt: str = ""
    ai_provider: str = "litellm"
    ai_model: str = "coding-model"
    ai_base_url: str = ""
    litellm_api_key: str = "sk-internal-agents-local"
    max_tokens: int = 8192
    langfuse_host: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    skills_path: str = "/etc/agent/skills.yaml"
    rules_path: str = "/etc/agent/rules.yaml"
    dry_run: bool = False
    work_dir: str = field(default_factory=lambda: tempfile.mkdtemp(prefix="coding-agent-"))

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            github_token=os.environ.get("GITHUB_TOKEN", ""),
            target_repo=os.environ.get("TARGET_REPO", ""),
            target_branch=os.environ.get("TARGET_BRANCH", "main"),
            context_source=os.environ.get("CONTEXT_SOURCE", "issues"),
            context_issue_label=os.environ.get("CONTEXT_ISSUE_LABEL", "ai-agent"),
            roadmap_path=os.environ.get("ROADMAP_PATH", ""),
            manual_prompt=os.environ.get("MANUAL_PROMPT", ""),
            ai_provider=os.environ.get("AI_PROVIDER", "litellm"),
            ai_model=os.environ.get("AI_MODEL", "coding-model"),
            ai_base_url=os.environ.get("AI_BASE_URL", ""),
            litellm_api_key=os.environ.get("LITELLM_API_KEY", "sk-internal-agents-local"),
            max_tokens=int(os.environ.get("MAX_TOKENS", "8192")),
            langfuse_host=os.environ.get("LANGFUSE_HOST", ""),
            langfuse_public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
            langfuse_secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
            skills_path=os.environ.get("SKILLS_PATH", "/etc/agent/skills.yaml"),
            rules_path=os.environ.get("RULES_PATH", "/etc/agent/rules.yaml"),
            dry_run=os.environ.get("DRY_RUN", "false").lower() == "true",
        )

    @property
    def is_local_model(self) -> bool:
        return self.ai_provider in ("ollama", "litellm", "vllm")

    def validate(self):
        if not self.github_token:
            raise ValueError("GITHUB_TOKEN is required")
        if not self.target_repo:
            raise ValueError("TARGET_REPO is required")


# ── Tracing (Langfuse) ──────────────────────────────────────────────────────


class Tracer:
    """Thin wrapper around Langfuse for optional observability."""

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
                name="coding-agent-run",
                metadata={"repo": cfg.target_repo, "provider": cfg.ai_provider},
            )
            log.info("Langfuse tracing enabled → %s", cfg.langfuse_host)

    def span(self, name: str, **kwargs):
        if self.trace:
            return self.trace.span(name=name, **kwargs)
        return _NoopSpan()

    def generation(self, name: str, **kwargs):
        if self.trace:
            return self.trace.generation(name=name, **kwargs)
        return _NoopSpan()

    def flush(self):
        if self.enabled:
            self.lf.flush()


class _NoopSpan:
    def end(self, **_):
        pass

    def update(self, **_):
        pass


# ── GitHub helpers ───────────────────────────────────────────────────────────


def gh(cfg: Config, *args: str, capture: bool = True) -> str:
    """Run a `gh` CLI command authenticated with the configured token."""
    env = {**os.environ, "GH_TOKEN": cfg.github_token}
    cmd = ["gh", *args]
    log.debug("gh %s", " ".join(args))
    result = subprocess.run(cmd, capture_output=capture, text=True, env=env, check=False)
    if result.returncode != 0:
        log.error("gh failed: %s", result.stderr.strip())
        raise RuntimeError(f"gh command failed: {' '.join(args)}")
    return result.stdout.strip() if capture else ""


def git(cwd: str, *args: str) -> str:
    cmd = ["git", "-C", cwd, *args]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        log.error("git failed: %s", result.stderr.strip())
        raise RuntimeError(f"git command failed: {' '.join(args)}")
    return result.stdout.strip()


# ── Context gathering ────────────────────────────────────────────────────────


def fetch_context_from_issues(cfg: Config) -> list[dict]:
    """Fetch open issues labelled for the agent."""
    raw = gh(
        cfg,
        "issue", "list",
        "--repo", cfg.target_repo,
        "--label", cfg.context_issue_label,
        "--state", "open",
        "--json", "number,title,body,labels",
        "--limit", "5",
    )
    issues = json.loads(raw) if raw else []
    log.info("Found %d issues labelled '%s'", len(issues), cfg.context_issue_label)
    return issues


def fetch_context_from_roadmap(cfg: Config, repo_dir: str) -> str:
    roadmap = Path(repo_dir) / cfg.roadmap_path
    if roadmap.exists():
        return roadmap.read_text()
    log.warning("Roadmap file not found: %s", cfg.roadmap_path)
    return ""


def gather_context(cfg: Config, repo_dir: str) -> str:
    if cfg.context_source == "manual":
        return cfg.manual_prompt

    if cfg.context_source == "roadmap_file":
        return fetch_context_from_roadmap(cfg, repo_dir)

    issues = fetch_context_from_issues(cfg)
    if not issues:
        log.info("No issues to work on. Exiting cleanly.")
        sys.exit(0)
    parts = []
    for iss in issues:
        parts.append(f"### Issue #{iss['number']}: {iss['title']}\n{iss.get('body', '')}")
    return "\n\n".join(parts)


# ── Codebase analysis ────────────────────────────────────────────────────────


def analyze_codebase(repo_dir: str) -> str:
    """Build a compact summary of the repo structure and key files."""
    tree_lines = []
    repo = Path(repo_dir)
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".tox"}

    for p in sorted(repo.rglob("*")):
        if any(part in skip for part in p.parts):
            continue
        rel = p.relative_to(repo)
        if p.is_file() and len(rel.parts) <= 4:
            tree_lines.append(str(rel))

    tree = "\n".join(tree_lines[:200])

    key_files = {}
    for name in ["README.md", "CONTRIBUTING.md", "CODEOWNERS", ".cursorrules", "pyproject.toml",
                  "package.json", "Makefile", "Dockerfile", "go.mod", "Cargo.toml"]:
        fp = repo / name
        if fp.exists():
            content = fp.read_text(errors="replace")[:2000]
            key_files[name] = content

    summary = f"## Repository structure\n```\n{tree}\n```\n\n"
    for fname, content in key_files.items():
        summary += f"## {fname}\n```\n{content}\n```\n\n"

    return summary


# ── LLM interaction ──────────────────────────────────────────────────────────


def load_yaml_config(path: str) -> str:
    p = Path(path)
    if p.exists():
        data = yaml.safe_load(p.read_text())
        return yaml.dump(data, default_flow_style=False)
    return ""


SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert software engineer acting as an internal coding agent.
    Your job is to implement changes in a codebase following project rules,
    conventions, and best practices.

    You will be given:
    1. A task description (from an issue, roadmap, or manual prompt)
    2. The repository structure and key files
    3. Project-specific rules and coding standards
    4. Available skills and patterns to follow

    Respond with a JSON object containing:
    {
      "branch_name": "short-kebab-case branch name",
      "commit_message": "conventional commit message",
      "pr_title": "concise PR title",
      "pr_body": "markdown PR description with ## Summary, ## Changes, ## Test plan",
      "files": [
        {
          "path": "relative/path/to/file",
          "action": "create|modify|delete",
          "content": "full file content (for create/modify)"
        }
      ],
      "reasoning": "brief explanation of approach taken"
    }

    Rules:
    - Follow existing project conventions exactly.
    - Write production-quality code with proper error handling.
    - Include tests when the project has a test suite.
    - Never introduce secrets or credentials in code.
    - Keep changes minimal and focused on the task.
    - Return ONLY valid JSON.""")


def build_prompt(task_context: str, codebase_summary: str, rules: str, skills: str) -> str:
    parts = [f"## Task\n{task_context}"]
    parts.append(codebase_summary)
    if rules:
        parts.append(f"## Project Rules\n```yaml\n{rules}\n```")
    if skills:
        parts.append(f"## Available Skills/Patterns\n```yaml\n{skills}\n```")
    return "\n\n".join(parts)


def call_llm(system: str, prompt: str, cfg: Config, tracer: Tracer) -> str:
    """Call the LLM via the configured backend (local/aws/azure/gcp)."""
    from agents.core.factory import get_llm

    gen = tracer.generation(
        name="coding-llm-call",
        model=cfg.ai_model,
        input={"system": system[:500], "user_prompt_len": len(prompt)},
    )
    log.info("Calling LLM (model=%s)", cfg.ai_model)
    resp = get_llm().call(system, prompt, cfg.ai_model, cfg.max_tokens)
    gen.end(output=resp.text[:1000])
    return resp.text


# ── Change application ───────────────────────────────────────────────────────


def parse_plan(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines[1:] if l.strip() != "```"]
        text = "\n".join(lines)
    return json.loads(text)


def apply_changes(repo_dir: str, plan: dict):
    """Write files to the repo working tree."""
    for f in plan.get("files", []):
        target = Path(repo_dir) / f["path"]
        action = f.get("action", "create")

        if action == "delete":
            if target.exists():
                target.unlink()
                log.info("Deleted %s", f["path"])
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f["content"])
        log.info("%s %s", "Created" if action == "create" else "Modified", f["path"])


# ── PR creation ──────────────────────────────────────────────────────────────


def create_pr(cfg: Config, repo_dir: str, plan: dict, issue_ref: Optional[str] = None) -> str:
    branch = plan["branch_name"]
    git(repo_dir, "checkout", "-b", branch)
    git(repo_dir, "add", "-A")
    git(repo_dir, "commit", "-m", plan["commit_message"])
    git(repo_dir, "push", "origin", branch)

    body = plan["pr_body"]
    if issue_ref:
        body += f"\n\nCloses {issue_ref}"
    body += "\n\n---\n*Raised by internal coding agent. Human review required before merge.*"

    pr_url = gh(
        cfg,
        "pr", "create",
        "--repo", cfg.target_repo,
        "--base", cfg.target_branch,
        "--head", branch,
        "--title", plan["pr_title"],
        "--body", body,
        "--label", "ai-generated",
    )
    return pr_url


# ── Audit log ────────────────────────────────────────────────────────────────


def write_audit_log(cfg: Config, plan: dict, pr_url: str):
    audit = {
        "run_id": str(uuid.uuid4()),
        "repo": cfg.target_repo,
        "provider": cfg.ai_provider,
        "model": cfg.ai_model,
        "branch": plan.get("branch_name", ""),
        "pr_url": pr_url,
        "files_changed": [f["path"] for f in plan.get("files", [])],
        "reasoning": plan.get("reasoning", ""),
    }
    log.info("Audit: %s", json.dumps(audit, indent=2))
    audit_dir = Path("/var/log/agent-audit")
    if audit_dir.exists():
        (audit_dir / f"{audit['run_id']}.json").write_text(json.dumps(audit, indent=2))


# ── Main orchestrator ────────────────────────────────────────────────────────


def run():
    from agents.telemetry import init_telemetry, record_run, record_pr_created, record_llm_call, trace_span
    from agents.compliance import (
        AuditRecord, write_audit_record, hash_content,
        check_kill_switch, AgentHaltedError,
        check_approved_provider, scan_for_sensitive_data,
        redact_sensitive_data, classify_data,
        build_coding_dvw,
    )

    cfg = Config.from_env()
    cfg.validate()

    init_telemetry("coding-agent")
    tracer = Tracer(cfg)

    run_id = str(uuid.uuid4())
    record_run("coding-agent")

    check_kill_switch()
    check_approved_provider(cfg.ai_provider)

    write_audit_record(AuditRecord(
        run_id=run_id, agent_name="coding-agent", event_type="run_start",
        model_provider=cfg.ai_provider, model_name=cfg.ai_model,
        target_repo=cfg.target_repo, trigger_event=os.environ.get("TRIGGER_EVENT", ""),
    ))

    with trace_span("coding-agent-full-run", {"repo": cfg.target_repo, "provider": cfg.ai_provider}) as root_span:
        log.info("Coding agent starting — repo=%s provider=%s run_id=%s", cfg.target_repo, cfg.ai_provider, run_id)

        # 1. Clone the target repo
        with trace_span("clone-repo"):
            repo_dir = os.path.join(cfg.work_dir, "repo")
            log.info("Cloning %s → %s", cfg.target_repo, repo_dir)
            subprocess.run(
                ["git", "clone", "--depth", "50",
                 f"https://x-access-token:{cfg.github_token}@github.com/{cfg.target_repo}.git",
                 repo_dir],
                check=True, capture_output=True, text=True,
            )

        # 2. Gather task context
        with trace_span("gather-context"):
            task_context = gather_context(cfg, repo_dir)
            log.info("Task context gathered (%d chars)", len(task_context))

        # 3. Analyze codebase
        with trace_span("analyze-codebase"):
            codebase_summary = analyze_codebase(repo_dir)
            log.info("Codebase analysis complete (%d chars)", len(codebase_summary))

        # 4. Load rules & skills
        rules = load_yaml_config(cfg.rules_path)
        skills = load_yaml_config(cfg.skills_path)

        # 5. Build prompt and run DLP scan
        prompt = build_prompt(task_context, codebase_summary, rules, skills)

        max_prompt_chars = 200_000
        if len(prompt) > max_prompt_chars:
            log.warning("Prompt too large (%d chars), truncating to %d", len(prompt), max_prompt_chars)
            prompt = prompt[:max_prompt_chars] + "\n\n[... truncated ...]"

        dlp_findings = scan_for_sensitive_data(prompt, source="llm_prompt")
        data_class = classify_data(prompt)
        if dlp_findings:
            log.warning("DLP: %d sensitive patterns found in prompt — redacting", len(dlp_findings))
            prompt = redact_sensitive_data(prompt)
            write_audit_record(AuditRecord(
                run_id=run_id, agent_name="coding-agent", event_type="dlp_finding",
                target_repo=cfg.target_repo, data_classification=data_class,
                compliance_flags=[f.pattern_type for f in dlp_findings],
            ))

        check_kill_switch()

        # 6. Call LLM
        import time as _time
        llm_start = _time.monotonic()
        llm_error = False
        with trace_span("llm-generate", {"provider": cfg.ai_provider, "model": cfg.ai_model}):
            log.info("Sending %d chars to %s/%s", len(prompt), cfg.ai_provider, cfg.ai_model)
            try:
                raw_response = call_llm(SYSTEM_PROMPT, prompt, cfg, tracer)
            except Exception:
                llm_error = True
                raise
            finally:
                duration = _time.monotonic() - llm_start
                record_llm_call("coding-agent", cfg.ai_provider, cfg.ai_model, duration, error=llm_error)

        write_audit_record(AuditRecord(
            run_id=run_id, agent_name="coding-agent", event_type="llm_call",
            model_provider=cfg.ai_provider, model_name=cfg.ai_model,
            target_repo=cfg.target_repo,
            input_hash=hash_content(SYSTEM_PROMPT + prompt),
            output_hash=hash_content(raw_response),
            input_size_bytes=len((SYSTEM_PROMPT + prompt).encode()),
            output_size_bytes=len(raw_response.encode()),
            input_content=SYSTEM_PROMPT + "\n---\n" + prompt,
            output_content=raw_response,
            data_classification=data_class,
        ))

        # 7. Parse the plan
        plan = parse_plan(raw_response)
        file_count = len(plan.get("files", []))
        log.info("Plan: branch=%s, files=%d", plan.get("branch_name"), file_count)

        if file_count == 0:
            log.info("No files to change. Agent run complete (no-op).")
            root_span.set_attribute("outcome", "noop")
            tracer.flush()
            return

        # 8. Build Decision Validity Warrant
        dvw = build_coding_dvw(
            task_context=task_context,
            codebase_summary_len=len(codebase_summary),
            model=cfg.ai_model,
            plan=plan,
            repo=cfg.target_repo,
        )

        # 9. Apply changes
        with trace_span("apply-changes", {"file_count": file_count}):
            apply_changes(repo_dir, plan)

        # 10. Create PR (or dry-run)
        if cfg.dry_run:
            log.info("[DRY RUN] Would create PR: %s", plan["pr_title"])
            pr_url = "dry-run://no-pr-created"
        else:
            with trace_span("create-pr"):
                issue_ref = None
                if cfg.context_source == "issues":
                    issues = fetch_context_from_issues(cfg)
                    if issues:
                        issue_ref = f"#{issues[0]['number']}"
                pr_url = create_pr(cfg, repo_dir, plan, issue_ref)
                log.info("PR created: %s", pr_url)
            record_pr_created("coding-agent", cfg.target_repo)

        # 11. Full compliance audit record
        write_audit_record(AuditRecord(
            run_id=run_id, agent_name="coding-agent", event_type="pr_created",
            model_provider=cfg.ai_provider, model_name=cfg.ai_model,
            target_repo=cfg.target_repo, pr_url=pr_url,
            files_changed=[f["path"] for f in plan.get("files", [])],
            risk_level="medium",
            human_action="pending",
            dvw_facts=dvw.facts,
            dvw_assumptions=dvw.assumptions,
            dvw_reasoning=dvw.reasoning_chain,
            data_classification=data_class,
        ))

        write_audit_log(cfg, plan, pr_url)
        root_span.set_attribute("outcome", "pr_created")
        root_span.set_attribute("pr_url", pr_url)
        root_span.set_attribute("run_id", run_id)
        tracer.flush()


if __name__ == "__main__":
    try:
        run()
    except Exception:
        log.exception("Coding agent failed")
        sys.exit(1)
