"""
Self-Healing Telemetry Watcher

Proactively queries the observability stack (Prometheus, Loki, Tempo) for
anomalies and errors, uses an LLM to diagnose root causes, and creates
GitHub issues labelled ``ai-agent`` so the Coding Agent can generate fix PRs.

Designed to run as a Kubernetes CronJob (every 15 min) or one-shot locally.

Environment variables (all configurable via K8s ConfigMap / Secret):
  GITHUB_TOKEN                – PAT with repo + issues write scope
  TARGET_REPO                 – owner/repo to create issues against
  PROMETHEUS_URL              – Prometheus query endpoint
  LOKI_URL                    – Loki query endpoint
  TEMPO_URL                   – Tempo query endpoint
  AI_PROVIDER                 – LLM provider (litellm | ollama | …)
  AI_MODEL                    – model identifier
  AI_BASE_URL                 – base URL for self-hosted models
  LITELLM_API_KEY             – key for LiteLLM gateway
  MAX_TOKENS                  – response token budget (default: 4096)
  HEALING_CONFIDENCE_THRESHOLD – min LLM confidence to file an issue (default: 0.7)
  HEALING_COOLDOWN_MINUTES    – per-alert dedup window (default: 30)
  HEALING_ENABLED             – "true" to enable (default: true)
"""

import json
import logging
import os
import subprocess
import sys
import textwrap
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin

import requests
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
log = logging.getLogger("telemetry-watcher")


# ── Configuration ────────────────────────────────────────────────────────────


@dataclass
class Config:
    github_token: str = ""
    target_repo: str = ""
    prometheus_url: str = "http://prometheus.ai-observability.svc.cluster.local:9090"
    loki_url: str = "http://loki.ai-observability.svc.cluster.local:3100"
    tempo_url: str = "http://grafana-tempo.ai-observability.svc.cluster.local:3200"
    ai_provider: str = "litellm"
    ai_model: str = "coding-model"
    ai_base_url: str = ""
    litellm_api_key: str = "sk-internal-agents-local"
    max_tokens: int = 4096
    confidence_threshold: float = 0.7
    cooldown_minutes: int = 30
    healing_enabled: bool = True

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            github_token=os.environ.get("GITHUB_TOKEN", ""),
            target_repo=os.environ.get("TARGET_REPO", ""),
            prometheus_url=os.environ.get(
                "PROMETHEUS_URL",
                "http://prometheus.ai-observability.svc.cluster.local:9090",
            ),
            loki_url=os.environ.get(
                "LOKI_URL",
                "http://loki.ai-observability.svc.cluster.local:3100",
            ),
            tempo_url=os.environ.get(
                "TEMPO_URL",
                "http://grafana-tempo.ai-observability.svc.cluster.local:3200",
            ),
            ai_provider=os.environ.get("AI_PROVIDER", "litellm"),
            ai_model=os.environ.get("AI_MODEL", "coding-model"),
            ai_base_url=os.environ.get("AI_BASE_URL", ""),
            litellm_api_key=os.environ.get("LITELLM_API_KEY", "sk-internal-agents-local"),
            max_tokens=int(os.environ.get("MAX_TOKENS", "4096")),
            confidence_threshold=float(os.environ.get("HEALING_CONFIDENCE_THRESHOLD", "0.7")),
            cooldown_minutes=int(os.environ.get("HEALING_COOLDOWN_MINUTES", "30")),
            healing_enabled=os.environ.get("HEALING_ENABLED", "true").lower() == "true",
        )

    @property
    def is_local_model(self) -> bool:
        return self.ai_provider in ("ollama", "litellm", "vllm")

    def validate(self):
        if not self.github_token:
            raise ValueError("GITHUB_TOKEN is required")
        if not self.target_repo:
            raise ValueError("TARGET_REPO is required")


# ── Telemetry data collection ────────────────────────────────────────────────


@dataclass
class Alert:
    name: str
    severity: str
    state: str
    summary: str
    description: str
    expression: str
    labels: dict = field(default_factory=dict)
    fingerprint: str = ""


@dataclass
class LogEntry:
    timestamp: str
    message: str
    labels: dict = field(default_factory=dict)


@dataclass
class TelemetrySnapshot:
    alerts: list[Alert] = field(default_factory=list)
    error_logs: list[LogEntry] = field(default_factory=list)
    error_traces: list[dict] = field(default_factory=list)
    metrics_summary: dict = field(default_factory=dict)


def fetch_prometheus_alerts(cfg: Config) -> list[Alert]:
    """Query Prometheus /api/v1/alerts for currently firing alerts."""
    try:
        resp = requests.get(
            urljoin(cfg.prometheus_url, "/api/v1/alerts"),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("Failed to query Prometheus alerts: %s", exc)
        return []

    alerts = []
    for group in data.get("data", {}).get("alerts", []):
        if group.get("state") != "firing":
            continue
        annotations = group.get("annotations", {})
        labels = group.get("labels", {})
        alerts.append(Alert(
            name=labels.get("alertname", "unknown"),
            severity=labels.get("severity", "warning"),
            state="firing",
            summary=annotations.get("summary", ""),
            description=annotations.get("description", ""),
            expression=group.get("activeAt", ""),
            labels=labels,
            fingerprint=_alert_fingerprint(labels),
        ))
    log.info("Prometheus: %d firing alerts", len(alerts))
    return alerts


def fetch_prometheus_metrics(cfg: Config) -> dict:
    """Query a few key health metrics from Prometheus."""
    queries = {
        "llm_error_rate": 'rate(agent_llm_call_errors_total[15m]) / (rate(agent_llm_call_total[15m]) + 0.001)',
        "agent_job_failures": 'sum(kube_job_status_failed{namespace="ai-agents"}) or vector(0)',
        "pod_restarts": 'sum(increase(kube_pod_container_status_restarts_total{namespace=~"ai-agents|ai-models"}[1h])) or vector(0)',
    }
    results = {}
    for name, expr in queries.items():
        try:
            resp = requests.get(
                urljoin(cfg.prometheus_url, "/api/v1/query"),
                params={"query": expr},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            result_list = data.get("data", {}).get("result", [])
            if result_list:
                results[name] = float(result_list[0].get("value", [0, 0])[1])
            else:
                results[name] = 0.0
        except Exception as exc:
            log.warning("Prometheus metric query '%s' failed: %s", name, exc)
            results[name] = None
    log.info("Prometheus metrics: %s", results)
    return results


def fetch_loki_error_logs(cfg: Config, lookback_minutes: int = 30) -> list[LogEntry]:
    """Query Loki for recent error-level logs."""
    end_ns = int(time.time() * 1e9)
    start_ns = end_ns - (lookback_minutes * 60 * int(1e9))
    query = '{namespace=~"ai-agents|ai-models"} |~ "(?i)(error|exception|fatal|panic|traceback)"'

    try:
        resp = requests.get(
            urljoin(cfg.loki_url, "/loki/api/v1/query_range"),
            params={
                "query": query,
                "start": str(start_ns),
                "end": str(end_ns),
                "limit": 100,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("Failed to query Loki: %s", exc)
        return []

    entries = []
    for stream in data.get("data", {}).get("result", []):
        labels = stream.get("stream", {})
        for ts, line in stream.get("values", []):
            entries.append(LogEntry(
                timestamp=ts,
                message=line[:500],
                labels=labels,
            ))

    entries.sort(key=lambda e: e.timestamp, reverse=True)
    log.info("Loki: %d error log entries (last %d min)", len(entries), lookback_minutes)
    return entries[:50]


def fetch_tempo_error_traces(cfg: Config, lookback_minutes: int = 30) -> list[dict]:
    """Query Tempo for recent traces with error status."""
    end_s = int(time.time())
    start_s = end_s - (lookback_minutes * 60)

    try:
        resp = requests.get(
            urljoin(cfg.tempo_url, "/api/search"),
            params={
                "tags": "status.code=error",
                "start": str(start_s),
                "end": str(end_s),
                "limit": 20,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("Failed to query Tempo: %s", exc)
        return []

    traces = data.get("traces", [])
    log.info("Tempo: %d error traces (last %d min)", len(traces), lookback_minutes)
    return traces[:20]


def collect_telemetry(cfg: Config) -> TelemetrySnapshot:
    """Aggregate signals from all observability backends."""
    return TelemetrySnapshot(
        alerts=fetch_prometheus_alerts(cfg),
        error_logs=fetch_loki_error_logs(cfg),
        error_traces=fetch_tempo_error_traces(cfg),
        metrics_summary=fetch_prometheus_metrics(cfg),
    )


# ── LLM diagnosis ───────────────────────────────────────────────────────────


DIAGNOSIS_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a senior SRE / platform engineer performing root-cause analysis.
    You are given telemetry data from a Kubernetes-hosted AI agent platform:
    firing alerts, recent error logs, error traces, and key metrics.

    Your job is to:
    1. Correlate the signals and identify the root cause.
    2. Determine if this is a code-level issue that can be fixed via a PR
       (as opposed to infrastructure / config / transient issues).
    3. If actionable, provide a structured diagnosis.

    Return ONLY a JSON object:
    {
      "actionable": true|false,
      "title": "concise issue title for a GitHub issue",
      "diagnosis": "2-4 sentence root cause explanation",
      "affected_files": ["likely file paths to investigate"],
      "proposed_fix": "concrete description of what code change would fix this",
      "severity": "critical|high|medium|low",
      "confidence": 0.0-1.0,
      "alert_names": ["list of correlated alert names"],
      "skip_reason": "if not actionable, explain why"
    }

    Rules:
    - Only mark actionable if you are confident a code change will help.
    - Infrastructure issues (node down, disk full) are NOT actionable.
    - Transient network blips with auto-recovery are NOT actionable.
    - Return ONLY valid JSON.""")


def build_diagnosis_prompt(snapshot: TelemetrySnapshot) -> str:
    parts = []

    if snapshot.alerts:
        parts.append("## Firing Alerts")
        for a in snapshot.alerts:
            parts.append(f"- **{a.name}** [{a.severity}]: {a.summary}")
            if a.description:
                parts.append(f"  Detail: {a.description}")

    if snapshot.metrics_summary:
        parts.append("\n## Key Metrics")
        for k, v in snapshot.metrics_summary.items():
            parts.append(f"- {k}: {v}")

    if snapshot.error_logs:
        parts.append(f"\n## Recent Error Logs ({len(snapshot.error_logs)} entries)")
        for entry in snapshot.error_logs[:20]:
            pod = entry.labels.get("pod", entry.labels.get("container", "unknown"))
            parts.append(f"- [{pod}] {entry.message[:200]}")

    if snapshot.error_traces:
        parts.append(f"\n## Error Traces ({len(snapshot.error_traces)} traces)")
        for t in snapshot.error_traces[:10]:
            root = t.get("rootServiceName", "unknown")
            duration = t.get("durationMs", 0)
            spans = t.get("spanCount", 0) if isinstance(t.get("spanCount"), int) else 0
            parts.append(f"- service={root} duration={duration}ms spans={spans}")

    if not parts:
        return "No telemetry signals detected. All systems appear healthy."

    return "\n".join(parts)


def call_llm(system: str, prompt: str, cfg: Config) -> str:
    """Call the LLM via the configured backend (local/aws/azure/gcp)."""
    from agents.core.factory import get_llm
    resp = get_llm().call(system, prompt, cfg.ai_model, cfg.max_tokens)
    return resp.text


def diagnose(snapshot: TelemetrySnapshot, cfg: Config) -> Optional[dict]:
    """Send telemetry snapshot to LLM and parse structured diagnosis."""
    prompt = build_diagnosis_prompt(snapshot)
    if "No telemetry signals" in prompt:
        log.info("No signals to diagnose — all clear.")
        return None

    log.info("Sending %d chars to %s for diagnosis", len(prompt), cfg.ai_provider)
    raw = call_llm(DIAGNOSIS_SYSTEM_PROMPT, prompt, cfg)

    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines[1:] if l.strip() != "```"]
        text = "\n".join(lines)

    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        log.error("Failed to parse LLM diagnosis JSON: %s\nRaw: %s", exc, raw[:500])
        return None

    if not result.get("actionable"):
        log.info("Diagnosis not actionable: %s", result.get("skip_reason", "no reason"))
        return None

    confidence = float(result.get("confidence", 0))
    if confidence < cfg.confidence_threshold:
        log.info("Diagnosis confidence %.2f below threshold %.2f — skipping",
                 confidence, cfg.confidence_threshold)
        return None

    return result


# ── GitHub issue management ──────────────────────────────────────────────────


def _gh(cfg: Config, *args: str) -> str:
    env = {**os.environ, "GH_TOKEN": cfg.github_token}
    result = subprocess.run(["gh", *args], capture_output=True, text=True, env=env, check=False)
    if result.returncode != 0:
        log.error("gh failed: %s", result.stderr.strip())
        raise RuntimeError(f"gh command failed: {' '.join(args)}")
    return result.stdout.strip()


def _alert_fingerprint(labels: dict) -> str:
    """Stable fingerprint from alert labels for deduplication."""
    key = json.dumps(
        {k: v for k, v in sorted(labels.items()) if k != "instance"},
        sort_keys=True,
    )
    import hashlib
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def find_existing_issues(cfg: Config) -> list[dict]:
    """Return open issues with the ai-agent label."""
    raw = _gh(
        cfg,
        "issue", "list",
        "--repo", cfg.target_repo,
        "--label", "ai-agent",
        "--state", "open",
        "--json", "number,title,body",
        "--limit", "50",
    )
    return json.loads(raw) if raw else []


def issue_already_exists(existing: list[dict], fingerprint: str, title: str) -> bool:
    """Check dedup: matching fingerprint in body or very similar title."""
    for iss in existing:
        body = iss.get("body", "")
        if fingerprint and f"fingerprint:{fingerprint}" in body:
            return True
        if iss.get("title", "").lower().strip() == title.lower().strip():
            return True
    return False


def create_healing_issue(cfg: Config, diagnosis: dict, snapshot: TelemetrySnapshot) -> str:
    """Create a GitHub issue for the coding agent to pick up."""
    fingerprint = ""
    if diagnosis.get("alert_names"):
        fp_labels = {"alertname": diagnosis["alert_names"][0]}
        fingerprint = _alert_fingerprint(fp_labels)

    severity = diagnosis.get("severity", "medium")
    title = f"[self-healing] {diagnosis['title']}"

    evidence_lines = []
    for a in snapshot.alerts:
        if a.name in (diagnosis.get("alert_names") or []):
            evidence_lines.append(f"- Alert **{a.name}** [{a.severity}]: {a.summary}")
    for entry in snapshot.error_logs[:5]:
        evidence_lines.append(f"- Log: `{entry.message[:120]}`")
    evidence = "\n".join(evidence_lines) if evidence_lines else "_no raw evidence captured_"

    body = textwrap.dedent(f"""\
        ## Self-Healing Diagnosis

        **Severity:** {severity}
        **Confidence:** {diagnosis.get('confidence', 'N/A')}
        **Correlated alerts:** {', '.join(diagnosis.get('alert_names', []) or ['none'])}

        ### Root Cause
        {diagnosis.get('diagnosis', 'No diagnosis available.')}

        ### Proposed Fix
        {diagnosis.get('proposed_fix', 'No fix proposed.')}

        ### Affected Files
        {chr(10).join('- `' + f + '`' for f in (diagnosis.get('affected_files') or ['unknown']))}

        ### Telemetry Evidence
        {evidence}

        ---
        _Created by the self-healing telemetry watcher. fingerprint:{fingerprint}_
    """)

    issue_url = _gh(
        cfg,
        "issue", "create",
        "--repo", cfg.target_repo,
        "--title", title,
        "--body", body,
        "--label", "ai-agent",
    )
    log.info("Created issue: %s", issue_url)
    return issue_url


# ── Main orchestrator ────────────────────────────────────────────────────────


def run():
    from agents.telemetry import init_telemetry, record_run, trace_span
    from agents.compliance import (
        AuditRecord, write_audit_record, hash_content,
        check_kill_switch, AgentHaltedError,
        check_approved_provider,
    )

    cfg = Config.from_env()
    cfg.validate()

    if not cfg.healing_enabled:
        log.info("Self-healing disabled (HEALING_ENABLED != true). Exiting.")
        return

    init_telemetry("telemetry-watcher")
    run_id = str(uuid.uuid4())
    record_run("telemetry-watcher")

    check_kill_switch()
    check_approved_provider(cfg.ai_provider)

    write_audit_record(AuditRecord(
        run_id=run_id, agent_name="telemetry-watcher", event_type="run_start",
        model_provider=cfg.ai_provider, model_name=cfg.ai_model,
        target_repo=cfg.target_repo,
    ))

    with trace_span("telemetry-watcher-run", {"repo": cfg.target_repo}) as root_span:
        log.info("Telemetry watcher starting — repo=%s run_id=%s", cfg.target_repo, run_id)

        # 1. Collect telemetry from all backends
        with trace_span("collect-telemetry"):
            snapshot = collect_telemetry(cfg)

        total_signals = len(snapshot.alerts) + len(snapshot.error_logs) + len(snapshot.error_traces)
        log.info("Collected %d total signals (%d alerts, %d logs, %d traces)",
                 total_signals, len(snapshot.alerts), len(snapshot.error_logs),
                 len(snapshot.error_traces))

        if total_signals == 0:
            log.info("No telemetry signals — system healthy. Exiting.")
            root_span.set_attribute("outcome", "healthy")
            return

        check_kill_switch()

        # 2. Send to LLM for diagnosis
        llm_start = time.monotonic()
        with trace_span("llm-diagnose", {"provider": cfg.ai_provider, "model": cfg.ai_model}):
            diagnosis = diagnose(snapshot, cfg)
        llm_duration = time.monotonic() - llm_start

        from agents.telemetry import record_llm_call
        record_llm_call("telemetry-watcher", cfg.ai_provider, cfg.ai_model,
                        llm_duration, error=(diagnosis is None and total_signals > 0))

        if diagnosis is None:
            log.info("No actionable diagnosis. Exiting.")
            root_span.set_attribute("outcome", "not_actionable")
            return

        log.info("Diagnosis: %s (confidence=%.2f, severity=%s)",
                 diagnosis.get("title"), diagnosis.get("confidence", 0),
                 diagnosis.get("severity"))

        # 3. Deduplication check
        with trace_span("dedup-check"):
            existing = find_existing_issues(cfg)
            fingerprint = ""
            if diagnosis.get("alert_names"):
                fingerprint = _alert_fingerprint({"alertname": diagnosis["alert_names"][0]})

            if issue_already_exists(existing, fingerprint, f"[self-healing] {diagnosis['title']}"):
                log.info("Issue already exists for this diagnosis — skipping.")
                root_span.set_attribute("outcome", "deduplicated")
                return

        check_kill_switch()

        # 4. Create GitHub issue
        with trace_span("create-issue"):
            issue_url = create_healing_issue(cfg, diagnosis, snapshot)

        write_audit_record(AuditRecord(
            run_id=run_id, agent_name="telemetry-watcher", event_type="issue_created",
            model_provider=cfg.ai_provider, model_name=cfg.ai_model,
            target_repo=cfg.target_repo, pr_url=issue_url,
            risk_level=diagnosis.get("severity", "medium"),
            dvw_facts=[
                f"Alerts: {len(snapshot.alerts)}",
                f"Error logs: {len(snapshot.error_logs)}",
                f"Error traces: {len(snapshot.error_traces)}",
                f"Diagnosis confidence: {diagnosis.get('confidence')}",
            ],
            dvw_reasoning=diagnosis.get("diagnosis", ""),
        ))

        root_span.set_attribute("outcome", "issue_created")
        root_span.set_attribute("issue_url", issue_url)
        root_span.set_attribute("diagnosis_confidence", diagnosis.get("confidence", 0))
        log.info("Self-healing issue created: %s", issue_url)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        log.exception("Telemetry watcher failed")
        sys.exit(1)
